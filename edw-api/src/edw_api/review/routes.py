"""Current-access review submission and fenced, API-owned execution."""
from contextlib import contextmanager
from uuid import UUID, uuid4
import hashlib
import hmac
import json
import time

import psycopg
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..documents.domain import content_hash
from ..documents.editor_repository import read_version
from ..documents.context_repository import _head as context_head
from ..documents.outline_repository import _template_sections
from ..errors import ApiError
from ..model_gateway.repository import audit
from ..model_gateway.patch_routes import Decision as PatchDecision, selected as selected_patches
from ..model_gateway.patch_routes import persist_decision
from ..model_gateway.copilot_routes import pack_job
from ..model_gateway.sections import evidence
from ..task_contract import canonical
from .rules import CATEGORIES, RULE_VERSION, inspect


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: UUID
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)


class DispositionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: UUID
    base_version_id: UUID
    base_revision: int = Field(ge=1, le=9007199254740991)
    action: str = Field(pattern='^(accept|reject|modify|handled)$')
    reason: str | None = Field(default=None, max_length=4000)
    patch_run_id: UUID | None = None
    recheck_run_id: UUID | None = None


def current(conn, subject, workspace_id, document_id, *, review=False):
    facts, resource, auth = checked(conn, subject, workspace_id,
                                    'document:review' if review else 'resource:read', document_id)
    if resource['kind'] != 'document':
        raise AccessDenied()
    head = conn.execute('''SELECT d.head_version_id,d.revision,d.template_version_id,v.ast,v.content_hash
        FROM document d JOIN document_version v ON v.id=d.head_version_id AND v.document_id=d.id
        WHERE d.id=%s AND d.workspace_id=%s FOR SHARE OF d''', (document_id, workspace_id)).fetchone()
    if not head or resource['head_ref'] != head['head_version_id'] or content_hash(head['ast']) != head['content_hash']:
        raise ApiError(503, 'REVIEW_DOCUMENT_INTEGRITY', '当前文档不可审校')
    return facts, auth, head


def source_safe(conn, workspace_id, anchor, subject, citations):
    from ..knowledge.governance import local_source, decorate
    for citation in citations:
        if citation['needs_review'] or citation['chain'] != 'attachment':
            raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验')
        try:
            from ..task_contract import canonical
            if hashlib.sha256(canonical(citation['content'])).hexdigest() != citation['pack_hash']:
                raise ValueError('Pack integrity')
            hit = citation['content']['items'][citation['item_ordinal'] - 1]
            if (citation['item_ordinal'] < 1 or hit['source_id'] != citation['source_id']
                    or hit['chain'] != citation['chain']
                    or hit['version'] != citation['source_version']
                    or hit['chunk_hash'] != citation['chunk_hash'] or hit['locator'] != citation['locator']
                    or hit['excerpt'] != citation['excerpt']):
                raise ValueError('Pinned source mismatch')
        except (IndexError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验') from exc
        try:
            text = local_source(conn, workspace_id, anchor, citation['source_id'],
                                citation['source_version'], citation['chunk_hash'], citation['locator'],
                                hit['classification'], hit['page'], hit['ordinal'], subject)
        except (AccessDenied, KeyError, TypeError) as exc:
            raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验') from exc
        if text != citation['excerpt'] or citation['quoted_text'] not in text:
            raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验')
        governed = decorate(conn, anchor, [dict(hit)], workspace_id)
        if not governed or any(g.get('conflict_id') for g in governed[0].get('governance', [])):
            raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验')


def citation_rows(conn, workspace_id, document_id, version_id):
    return conn.execute('''SELECT c.id,c.section_id,c.block_id,c.selected_text,c.needs_review,
        l.source_id,l.source_version,l.chain,l.chunk_hash,l.locator,l.quoted_text,l.item_ordinal,
        i.excerpt,p.content,p.content_hash AS pack_hash FROM document_citation c JOIN claim_evidence_link l
        ON l.id=c.link_id AND l.workspace_id=c.workspace_id
        JOIN section_evidence_item i ON i.pack_id=l.pack_id AND i.ordinal=l.item_ordinal
        JOIN section_evidence_pack p ON p.id=i.pack_id AND p.workspace_id=c.workspace_id
        WHERE c.workspace_id=%s AND c.document_id=%s AND c.document_version_id=%s ORDER BY c.id''',
        (workspace_id, document_id, version_id)).fetchall()


def snapshot(conn, subject, workspace_id, document_id, version_id, ast):
    template = conn.execute('SELECT structure FROM template_version WHERE id=%s',
                            (ast['document']['metadata']['template_version_id'],)).fetchone()
    if not template:
        raise ApiError(409, 'REVIEW_TEMPLATE_CHANGED', '模板不可用')
    claims = conn.execute('''SELECT id,section_id,block_id,statement,critical,status,needs_review
        FROM document_claim WHERE workspace_id=%s AND document_id=%s AND document_version_id=%s ORDER BY id''',
        (workspace_id, document_id, version_id)).fetchall()
    citations = citation_rows(conn, workspace_id, document_id, version_id)
    policy = _template_sections(conn, ast['document']['metadata']['template_version_id'])
    structure = {**template['structure'], 'policy_sections': policy}
    context = context_head(conn, document_id)
    facts = []
    context_confirmed = False
    if context and context['document_version_id'] == version_id:
        from ..documents.context_repository import _snapshot, _sources
        context_value = _snapshot(context)
        _sources(conn, subject, workspace_id, context_value)
        facts = context_value.model_dump(mode='json')['facts']
        context_confirmed = context['confirmed_at'] is not None and context['ready_at_confirmation'] is True
    structure['context_confirmed'] = context_confirmed
    return structure, claims, facts, citations


def source_snapshot(citations):
    return [{key: row[key] for key in ('id', 'section_id', 'block_id', 'selected_text', 'needs_review',
            'source_id', 'source_version', 'chain', 'chunk_hash', 'locator', 'quoted_text',
            'item_ordinal', 'excerpt')} for row in citations]


def input_hash(claims, facts, citations):
    body = {'claims': [dict(row) for row in claims], 'facts': facts, 'citations': source_snapshot(citations)}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def view(row, head):
    return {'id': row['id'], 'document_version_id': row['document_version_id'],
            'document_revision': row['document_revision'], 'template_version_id': row['template_version_id'],
            'rule_version': row['rule_version'], 'model_version': row['model_version'],
            'state': 'STALE' if row['document_version_id'] != head['head_version_id'] or
            row['document_revision'] != head['revision'] or row['content_hash'] != head['content_hash'] else row['state'],
            'current_eligible': False,
            'created_at': row['created_at'], 'error_code': row['error_code']}


def eligible(row, head, auth, results):
    return (row['state'] == 'COMPLETED' and row['document_version_id'] == head['head_version_id']
            and row['document_revision'] == head['revision'] and row['content_hash'] == head['content_hash']
            and tuple(row['policy_epoch']) == auth.policy_epoch
            and row['rule_version'] == RULE_VERSION
            and len(results) == len(CATEGORIES)
            and {item['category'] for item in results} == set(CATEGORIES)
            and all(item['state'] == 'COMPLETED' and item['rule_version'] == row['rule_version']
                    and item['model_version'] == row['model_version'] for item in results))


def accessible_result(conn, row, head, auth, subject, workspace_id, document_id, results):
    if not eligible(row, head, auth, results):
        return False
    try:
        structure, claims, facts, citations = snapshot(conn, subject, workspace_id, document_id,
                                                       row['document_version_id'], head['ast'])
        if content_hash(structure) != row['template_hash'] or input_hash(claims, facts, citations) != row['input_hash']:
            return False
        anchor = conn.execute('SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s',
                              (document_id, workspace_id)).fetchone()
        source_safe(conn, workspace_id, anchor, subject, citations)
        return True
    except (ApiError, AccessDenied, ValueError, KeyError, TypeError):
        return False


def current_results(conn, row):
    results = conn.execute('SELECT * FROM review_result WHERE run_id=%s ORDER BY category', (row['id'],)).fetchall()
    complete = (len(results) == len(CATEGORIES) and {item['category'] for item in results} == set(CATEGORIES)
                and all(item['state'] == 'COMPLETED' and item['rule_version'] == row['rule_version']
                        and item['model_version'] == row['model_version'] for item in results))
    return results, complete


def issue_filters(severity, section_id, status, keyword):
    if severity and severity not in ('critical', 'high', 'medium', 'low'):
        raise ApiError(422, 'REVIEW_FILTER_INVALID', '无效严重级别')
    if status and status not in ('OPEN', 'REJECTED', 'MODIFY', 'PENDING_RECHECK', 'HANDLED'):
        raise ApiError(422, 'REVIEW_FILTER_INVALID', '无效处置状态')
    return severity, section_id, status, keyword.strip() or None if keyword else None


def filtered_issues(conn, run_id, filters, *, sources_current, citations=(), current_version_id=None, offset=0, limit=100):
    severity, section_id, status, keyword = filters
    # The keyword predicate must use exactly the same safe fields as issue_view.
    # Source-linked quotes are excluded here; their authorization is checked per issue later.
    condition = '''i.run_id=%s AND (%s::text IS NULL OR i.severity=%s)
        AND (%s::uuid IS NULL OR i.section_id=%s::uuid)
        AND (%s::text IS NULL OR COALESCE(CASE WHEN d.action='handled'
             AND rr.document_version_id<>%s::uuid THEN 'PENDING_RECHECK'
             WHEN d.action='handled' THEN 'HANDLED' WHEN d.action='reject' THEN 'REJECTED'
             WHEN d.action='modify' THEN 'MODIFY' WHEN d.action='accept' THEN 'PENDING_RECHECK'
             END,'OPEN')=%s)
        AND (%s::text IS NULL OR ((%s::boolean AND (i.source_id IS NULL OR EXISTS
              (SELECT 1 FROM jsonb_to_recordset(%s::jsonb) AS c(source_id text,section_id uuid,block_id uuid)
               WHERE c.source_id=i.source_id AND c.section_id=i.section_id AND c.block_id=i.block_id))
              AND i.quote ILIKE '%%' || %s || '%%')
             OR i.impact ILIKE '%%' || %s || '%%' OR i.suggestion ILIKE '%%' || %s || '%%'
             OR i.rule_id ILIKE '%%' || %s || '%%'))'''
    params = (run_id, severity, severity, section_id, section_id, status, current_version_id, status,
               keyword, sources_current, Jsonb([{'source_id': str(c['source_id']),
                   'section_id': str(c['section_id']), 'block_id': str(c['block_id'])} for c in citations]),
               keyword, keyword, keyword, keyword)
    tables = ''' FROM review_issue i LEFT JOIN LATERAL
        (SELECT * FROM review_disposition WHERE issue_id=i.id ORDER BY (action='handled') DESC,created_at DESC,id DESC LIMIT 1)
        d ON true LEFT JOIN review_run rr ON rr.id=d.recheck_run_id '''
    count = conn.execute('SELECT count(*) AS count' + tables + ' WHERE ' + condition, params).fetchone()['count']
    rows = conn.execute('SELECT i.*,d.id AS disposition_id,d.action AS disposition_action,d.reason AS disposition_reason,'
                        'd.result_version_id,d.recheck_run_id,rr.document_version_id AS recheck_version_id' +
                         tables + ' WHERE ' + condition +
                        ' ORDER BY i.created_at,i.id LIMIT %s OFFSET %s', (*params, limit, offset)).fetchall()
    return rows, count


def issue_view(issue, ast, *, sources_current, citations=(), current_version_id=None):
    sections = ast['document']['sections']
    section = next((item for item in sections if item['id'] == str(issue['section_id'])), None)
    block = next((item for item in section['blocks'] if item['id'] == str(issue['block_id'])), None) if section else None
    authorized_source = sources_current and (not issue['source_id'] or any(
        str(citation['source_id']) == str(issue['source_id']) and citation['section_id'] == issue['section_id']
        and citation['block_id'] == issue['block_id'] for citation in citations))
    result = {key: issue[key] for key in ('id', 'category', 'rule_id', 'severity', 'section_id',
              'block_id', 'claim_id', 'impact', 'suggestion')}
    action = issue.get('disposition_action')
    closed = action == 'handled' and issue.get('recheck_version_id') is not None and (
        current_version_id is None or issue['recheck_version_id'] == current_version_id)
    result.update(status='PENDING_RECHECK' if action == 'handled' and not closed else
                  {'accept':'PENDING_RECHECK','reject':'REJECTED','modify':'MODIFY',
                   'handled':'HANDLED'}.get(action, 'OPEN'),
                   disposition_id=issue.get('disposition_id'),
                   reason=issue.get('disposition_reason'),
                   result_version_id=issue.get('result_version_id'),
                   recheck_run_id=issue.get('recheck_run_id'),
                   blocking=not closed, section_title=section['title'] if section else None,
                  block_type=block['type'] if block else None,
                  quote=issue['quote'] if authorized_source else '[来源需复核]',
                  source_id=issue['source_id'] if authorized_source else None,
                  source_state='current' if authorized_source else 'denied',
                  details=issue['details'] if authorized_source else {})
    result['trace'] = [{'source_id': citation['source_id'], 'version': citation['source_version'],
                        'locator': citation['locator'], 'quoted_text': citation['quoted_text']}
                       for citation in citations if authorized_source and issue['source_id']
                       and str(citation['source_id']) == str(issue['source_id'])
                       and citation['section_id'] == issue['section_id']
                       and citation['block_id'] == issue['block_id']]
    return result


def inspection(conn, row, head, subject, workspace_id, document_id):
    version = read_version(conn, subject, workspace_id, document_id, row['document_version_id'])
    if version['content_hash'] != row['content_hash'] or version['revision'] != row['document_revision']:
        raise ApiError(409, 'REVIEW_VERSION_CHANGED', '审校版本已失效')
    citations = citation_rows(conn, workspace_id, document_id, row['document_version_id'])
    anchor = conn.execute('SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s',
                          (document_id, workspace_id)).fetchone()
    try:
        source_safe(conn, workspace_id, anchor, subject, citations)
        sources_current = True
    except ApiError as exc:
        if exc.code != 'REVIEW_SOURCE_CHANGED':
            raise
        sources_current = False
    # A stale run cannot rely on historical authorization, even when its citation bytes still match.
    if row['document_version_id'] != head['head_version_id']:
        sources_current = False
    elif sources_current:
        # Old citations on a new head are marked needs_review by the editor; never treat that
        # historical snapshot as current evidence.
        sources_current = all(not citation['needs_review'] for citation in citations)
    return version['ast'], sources_current, citations


def version_comparison(pinned, current_ast):
    def blocks(ast):
        return {block['id']: (section['id'], block) for section in ast['document']['sections']
                for block in section['blocks']}
    before, after = blocks(pinned), blocks(current_ast)
    return {'added_blocks': len(after.keys() - before.keys()),
             'removed_blocks': len(before.keys() - after.keys()),
             'changed_blocks': sum(before[key] != after[key] for key in before.keys() & after.keys())}


def same_defect(issue, other):
    return (issue['category'] == other['category'] and issue['rule_id'] == other['rule_id']
            and issue['section_id'] == other['section_id'] and issue['block_id'] == other['block_id']
            and ((issue.get('details') or {}).get('field') == (other.get('details') or {}).get('field')))


def disposition_digest(command):
    return hashlib.sha256(canonical(command.model_dump(mode='json', exclude={'request_key'}))).hexdigest()


def disposition(conn, subject, workspace_id, document_id, run_id, issue_id, command, request,
                initial=(), views=()):
    # Lock the workspace before the head; permission changes take an exclusive workspace lock.
    checked(conn, subject, workspace_id, 'document:review', document_id, exclusive=True)
    conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                 (document_id, workspace_id))
    facts, auth, head = current(conn, subject, workspace_id, document_id, review=True)
    digest = disposition_digest(command)
    prior = conn.execute('''SELECT * FROM review_disposition WHERE workspace_id=%s AND actor_id=%s
        AND request_key=%s''', (workspace_id, facts['actor_id'], command.request_key)).fetchone()
    if prior:
        if (prior['document_id'] != document_id or prior['run_id'] != run_id or prior['issue_id'] != issue_id
                or prior['subject'] != subject or prior['request_hash'] != digest):
            raise ApiError(409, 'REVIEW_REQUEST_CONFLICT', '请求标识已用于其他处置')
        if ((prior['action'] == 'accept' and (head['head_version_id'] != prior['result_version_id']
                or head['revision'] != prior['result_revision'])) or
                (prior['action'] != 'accept' and (head['head_version_id'] != prior['base_version_id']
                or head['revision'] != prior['base_revision']))):
            raise ApiError(409, 'REVIEW_VERSION_CHANGED', '处置版本已不是当前版本')
        return {'data': disposition_view(prior, replayed=True)}
    row = conn.execute('''SELECT * FROM review_run WHERE id=%s AND workspace_id=%s AND document_id=%s''',
                       (run_id, workspace_id, document_id)).fetchone()
    issue = conn.execute('SELECT * FROM review_issue WHERE run_id=%s AND id=%s', (run_id, issue_id)).fetchone()
    if not row or not issue:
        raise ApiError(404, 'REVIEW_ISSUE_NOT_FOUND', '问题不存在或无权处置')
    if head['head_version_id'] != command.base_version_id or head['revision'] != command.base_revision:
        raise ApiError(409, 'REVIEW_VERSION_CHANGED', '文档已产生新版本')
    results, _ = current_results(conn, row)
    if row['state'] != 'COMPLETED':
        raise ApiError(409, 'REVIEW_RUN_STALE', '审校运行或权限已变化')
    if command.action != 'handled':
        if not accessible_result(conn, row, head, auth, subject, workspace_id, document_id, results):
            raise ApiError(409, 'REVIEW_RUN_STALE', '须对当前版本和来源重新审校')
    elif row['document_version_id'] == head['head_version_id']:
        raise ApiError(409, 'REVIEW_RECHECK_REQUIRED', '须在正文更新后独立重审')
    # Historical findings may be closed only by a fresh current run; the old
    # runner's policy epoch is not an authorization for today's operator.
    earlier = conn.execute('''SELECT * FROM review_disposition WHERE issue_id=%s
        ORDER BY created_at DESC,id DESC''', (issue_id,)).fetchall()
    if any(item['action'] == 'handled' for item in earlier) or (earlier and command.action != 'handled'):
        raise ApiError(409, 'REVIEW_ALREADY_DISPOSED', '问题已有不可变处置')
    reason = command.reason.strip() if command.reason else None
    if command.action == 'reject' and not reason:
        raise ApiError(422, 'REVIEW_REASON_REQUIRED', '拒绝必须说明理由')
    if ((command.action != 'accept' and command.patch_run_id)
            or (command.action != 'handled' and command.recheck_run_id)):
        raise ApiError(422, 'REVIEW_DISPOSITION_INVALID', '处置证据与操作不匹配')
    patch_id = result_id = result_revision = recheck_id = None
    if command.action == 'modify':
        sections = head['ast']['document']['sections']
        section = next((s for s in sections if s['id'] == str(issue['section_id'])), None)
        if not section or not any(b['id'] == str(issue['block_id']) for b in section['blocks']):
            raise ApiError(409, 'REVIEW_LOCATOR_CHANGED', '问题未定位到当前真实块')
        from ..documents.editor_repository import editable_document
        editable_document(conn, subject, workspace_id, document_id)
    if command.action == 'accept':
        if not command.patch_run_id or len(initial) != 1 or len(views) != 1:
            raise ApiError(422, 'REVIEW_PATCH_REQUIRED', '必须选择经过校验的 Patch')
        proposal = initial[0][0]
        if (proposal['id'] != command.patch_run_id or proposal['section_id'] != issue['section_id']
                or proposal['block_id'] != issue['block_id']):
            raise ApiError(409, 'REVIEW_PATCH_MISMATCH', 'Patch 与问题定位不一致')
        patch_command = PatchDecision(request_key=command.request_key, base_version_id=command.base_version_id,
            base_revision=command.base_revision, action='accept', run_ids=[command.patch_run_id])
        patch = persist_decision(conn, subject, workspace_id, document_id, patch_command, request,
                                 initial, views, None)
        patch_id, result_id, result_revision = patch['data']['id'], patch['data']['version_id'], patch['data']['revision']
    if command.action == 'handled':
        if earlier and earlier[0]['action'] not in ('accept', 'modify'):
            raise ApiError(409, 'REVIEW_ALREADY_DISPOSED', '既有决议保持未解决；须对新审校问题作出处置')
        if earlier and earlier[0]['action'] == 'accept' and (
                row['document_version_id'] == head['head_version_id'] or
                earlier[0]['result_version_id'] != head['head_version_id']):
            raise ApiError(409, 'REVIEW_VERSION_CHANGED', 'Patch 结果不是当前版本')
        if not command.recheck_run_id or command.recheck_run_id == run_id:
            raise ApiError(409, 'REVIEW_RECHECK_REQUIRED', '必须选择后续独立重审')
        recheck = conn.execute('''SELECT * FROM review_run WHERE id=%s AND workspace_id=%s AND document_id=%s''',
                               (command.recheck_run_id, workspace_id, document_id)).fetchone()
        if (not recheck or recheck['created_at'] <= row['created_at']
                or recheck['document_revision'] <= row['document_revision']):
            raise ApiError(409, 'REVIEW_RECHECK_REQUIRED', '重审必须晚于原审校')
        recheck_results, _ = current_results(conn, recheck)
        if not accessible_result(conn, recheck, head, auth, subject, workspace_id, document_id, recheck_results):
            raise ApiError(409, 'REVIEW_RECHECK_REQUIRED', '重审不满足当前版本、来源与权限')
        peers = conn.execute('SELECT * FROM review_issue WHERE run_id=%s', (recheck['id'],)).fetchall()
        if any(same_defect(issue, peer) for peer in peers):
            raise ApiError(409, 'REVIEW_DEFECT_PERSISTS', '重审仍发现同一缺陷')
        recheck_id = recheck['id']
    identifier = uuid4()
    conn.execute('''INSERT INTO review_disposition(id,workspace_id,document_id,run_id,issue_id,actor_id,
        subject,request_key,request_hash,action,base_version_id,base_revision,reason,patch_decision_id,
        result_version_id,result_revision,recheck_run_id,section_id,block_id,policy_epoch)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (identifier, workspace_id, document_id, run_id, issue_id, facts['actor_id'], subject,
         command.request_key, digest, command.action, command.base_version_id, command.base_revision,
         reason, patch_id, result_id, result_revision, recheck_id, issue['section_id'], issue['block_id'],
         Jsonb(list(auth.policy_epoch))))
    audit(conn, facts['actor_id'], workspace_id, issue_id, 'review:disposition:' + command.action,
          {'run_id': str(run_id), 'version_id': str(row['document_version_id'])},
          {'disposition_id': str(identifier), 'patch_decision_id': str(patch_id) if patch_id else None,
           'result_version_id': str(result_id) if result_id else None,
           'recheck_run_id': str(recheck_id) if recheck_id else None}, request.state.request_id, request.state.trace_id)
    return {'data': {'id': identifier, 'action': command.action, 'version_id': result_id,
                     'revision': result_revision, 'section_id': issue['section_id'],
                     'block_id': issue['block_id'], 'replayed': False}}


def disposition_view(row, *, replayed):
    return {'id': row['id'], 'action': row['action'], 'version_id': row['result_version_id'],
            'revision': row['result_revision'], 'section_id': row['section_id'],
            'block_id': row['block_id'], 'replayed': replayed}


def execute(settings, workspace_id, document_id, run_id):
    fence = uuid4()
    def fail(code, state='FAILED'):
        try:
            with connection(settings) as conn:
                conn.execute('''UPDATE review_run SET state=%s,error_code=%s,fence=NULL,
                    lease_until=NULL,updated_at=clock_timestamp() WHERE id=%s AND fence=%s
                    AND state='RUNNING' AND lease_until>clock_timestamp()''',
                    (state, code, run_id, fence))
        except psycopg.Error:
            pass
    try:
        with connection(settings) as conn:
            conn.execute('SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR SHARE', (workspace_id,))
            row = conn.execute('''UPDATE review_run SET state='RUNNING',attempt=attempt+1,fence=%s,
                lease_until=clock_timestamp()+interval '90 seconds',
                next_wake_at=clock_timestamp()+interval '90 seconds',updated_at=clock_timestamp()
                WHERE id=%s AND workspace_id=%s AND document_id=%s AND attempt<3 AND
                 (state='QUEUED' OR (state='RUNNING' AND lease_until<clock_timestamp())) RETURNING *''',
                (fence, run_id, workspace_id, document_id)).fetchone()
            if not row:
                conn.execute('''UPDATE review_run SET state='FAILED',error_code='REVIEW_RETRY_EXHAUSTED',
                    fence=NULL,lease_until=NULL,updated_at=clock_timestamp()
                    WHERE id=%s AND workspace_id=%s AND document_id=%s AND attempt>=3
                     AND (state='QUEUED' OR (state='RUNNING' AND lease_until<clock_timestamp()))''',
                    (run_id, workspace_id, document_id))
                return
        with connection(settings) as conn:
            _, auth, head = current(conn, row['subject'], workspace_id, document_id, review=True)
            if (head['head_version_id'] != row['document_version_id'] or head['revision'] != row['document_revision']
                    or head['content_hash'] != row['content_hash'] or head['template_version_id'] != row['template_version_id']
                    or tuple(row['policy_epoch']) != auth.policy_epoch or str(row['actor_id']) != auth.actor_id):
                raise AccessDenied()
            structure, claims, facts, citations = snapshot(conn, row['subject'], workspace_id, document_id,
                                                            row['document_version_id'], head['ast'])
            if (content_hash(structure) != row['template_hash'] or
                    input_hash(claims, facts, citations) != row['input_hash']):
                raise ApiError(409, 'REVIEW_TEMPLATE_CHANGED', '模板已变化')
            if row['rule_version'] != RULE_VERSION:
                raise ApiError(409, 'REVIEW_RULE_CHANGED', '审校规则版本已变化')
        with connection(settings) as conn:
            conn.execute('SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR SHARE', (workspace_id,))
            locked = conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                                  (document_id, workspace_id)).fetchone()
            job = conn.execute('SELECT * FROM review_run WHERE id=%s FOR UPDATE', (run_id,)).fetchone()
            if not locked or not job or job['fence'] != fence or job['state'] != 'RUNNING' or not job['lease_until'] or job['lease_until'] <= conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']:
                return
            _, auth, head = current(conn, job['subject'], workspace_id, document_id, review=True)
            if (head['head_version_id'] != job['document_version_id'] or head['revision'] != job['document_revision']
                    or head['content_hash'] != job['content_hash'] or head['template_version_id'] != job['template_version_id']
                    or tuple(job['policy_epoch']) != auth.policy_epoch or str(job['actor_id']) != auth.actor_id):
                raise AccessDenied()
            fresh_structure, fresh_claims, fresh_facts, fresh_citations = snapshot(
                conn, job['subject'], workspace_id, document_id, job['document_version_id'], head['ast'])
            if (content_hash(fresh_structure) != job['template_hash'] or
                    input_hash(fresh_claims, fresh_facts, fresh_citations) != job['input_hash']):
                raise ApiError(409, 'REVIEW_TEMPLATE_CHANGED', '模板已变化')
            anchor = conn.execute('SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s',
                                  (document_id, workspace_id)).fetchone()
            try:
                source_safe(conn, workspace_id, anchor, job['subject'], fresh_citations)
                sources_current = True
                outcomes, issues = inspect(head['ast'], fresh_structure, fresh_claims,
                    project_facts=fresh_facts, citations=fresh_citations)
                if head['ast']['document']['metadata']['document_type'] == 'test_plan':
                    from ..documents.traceability import coverage
                    trace = coverage(conn, job['subject'], workspace_id, head['ast'], document_id, head['head_version_id'])
                    defects = [*trace['unlinked'],
                               *(link for link in trace['links'] if link['state'] != 'current'),
                               *(entry for entry in trace['requirements'] if entry['state'] != 'covered')]
                    for defect in defects:
                        # Baseline locators belong to a different document. Keep them
                        # in details; never present them as blocks of this test plan.
                        external = 'document_id' in defect
                        issues.append({'id': str(uuid4()), 'category': 'requirement',
                            'rule_id': 'test_coverage_' + defect.get('state', 'unlinked'), 'severity': 'high',
                            'section_id': None if external else defect['section_id'],
                            'block_id': None if external else defect['block_id'],
                            'claim_id': None, 'source_id': None, 'quote': '测试追踪待核验',
                            'impact': '需求覆盖缺失、冗余或版本/阈值不一致',
                            'suggestion': '核对当前基线与测试链，不替换批准阈值', 'details': defect})
            except ApiError as exc:
                if exc.code != 'REVIEW_SOURCE_CHANGED':
                    raise
                sources_current = False
                outcomes, issues = inspect(head['ast'], fresh_structure, fresh_claims,
                    project_facts=fresh_facts, citations=(), stale_sources=fresh_citations)
                for outcome in outcomes:
                    if outcome['category'] == 'fact':
                        outcome['state'] = 'UNEVALUATED'
                        outcome['error_code'] = 'REVIEW_SOURCE_CHANGED'
                for issue in issues:
                    if issue['rule_id'] == 'obsolete_citation':
                        issue['quote'] = '[来源需复核]'
                        issue['source_id'] = None
            if job['rule_version'] != RULE_VERSION:
                raise ApiError(409, 'REVIEW_RULE_CHANGED', '审校规则版本已变化')
            for outcome in outcomes:
                conn.execute('''INSERT INTO review_result(run_id,category,state,rule_version,model_version,execution_kind,error_code)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)''', (run_id, outcome['category'], outcome['state'],
                    outcome['rule_version'], outcome['model_version'], outcome['execution_kind'], outcome['error_code']))
            for issue in issues:
                conn.execute('''INSERT INTO review_issue(id,run_id,category,rule_id,severity,section_id,block_id,
                    claim_id,source_id,quote,impact,suggestion,details) VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (issue['id'], run_id, issue['category'], issue['rule_id'], issue['severity'],
                     issue['section_id'], issue['block_id'], issue['claim_id'], issue['source_id'],
                     issue['quote'], issue['impact'], issue['suggestion'], Jsonb(issue['details'])))
            complete = sources_current and len(outcomes) == len(CATEGORIES) and all(item['state'] == 'COMPLETED'
                and item['rule_version'] == job['rule_version'] and item['model_version'] == job['model_version']
                for item in outcomes)
            conn.execute('''UPDATE review_run SET state=%s,error_code=%s,fence=NULL,lease_until=NULL,
                updated_at=clock_timestamp() WHERE id=%s AND fence=%s''',
                ('COMPLETED' if complete else 'FAILED', None if complete else
                 'REVIEW_SOURCE_CHANGED' if not sources_current else 'REQUIRED_REVIEWER_INCOMPLETE', run_id, fence))
            audit(conn, job['actor_id'], workspace_id, run_id, 'review:completed', {},
                  {'complete': complete, 'result_count': len(outcomes), 'issue_count': len(issues)}, str(run_id), str(fence))
    except Exception as exc:
        state = ('DENIED' if isinstance(exc, AccessDenied) else 'STALE' if isinstance(exc, ApiError)
                 and exc.code in ('REVIEW_RULE_CHANGED', 'REVIEW_TEMPLATE_CHANGED') else 'FAILED')
        fail('REVIEW_ACCESS_OR_INPUT_CHANGED' if isinstance(exc, AccessDenied) else
             exc.code if isinstance(exc, ApiError) else 'REVIEW_EXECUTION_FAILED', state)


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}/reviews')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(404, 'REVIEW_NOT_FOUND', '审校不存在或无权查看') from exc
        except psycopg.Error as exc:
            raise ApiError(503, 'REVIEW_STORAGE_UNAVAILABLE', '审校存储不可用', retryable=True) from exc

    @router.post('', status_code=202)
    def submit(workspace_id: UUID, document_id: UUID, body: ReviewRequest,
               request: Request, response: Response, current_actor=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            facts, auth, head = current(conn, current_actor.subject, workspace_id, document_id, review=True)
            if head['head_version_id'] != body.document_version_id or head['revision'] != body.document_revision:
                raise ApiError(409, 'REVIEW_VERSION_CHANGED', '文档已产生新版本')
            structure, claims, project_facts, citations = snapshot(conn, current_actor.subject, workspace_id,
                                                                    document_id, body.document_version_id, head['ast'])
            row = conn.execute('''INSERT INTO review_run(id,workspace_id,document_id,actor_id,subject,request_key,
                 document_version_id,document_revision,content_hash,template_version_id,template_hash,input_hash,
                 rule_version,model_version,policy_epoch)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'none',%s)
                ON CONFLICT (workspace_id,actor_id,request_key) DO NOTHING RETURNING *''',
                (uuid4(), workspace_id, document_id, facts['actor_id'], current_actor.subject, body.request_key,
                 body.document_version_id, body.document_revision, head['content_hash'], head['template_version_id'],
                  content_hash(structure), input_hash(claims, project_facts, citations), RULE_VERSION,
                  Jsonb(list(auth.policy_epoch)))).fetchone()
            created = row is not None
            if not row:
                row = conn.execute('SELECT * FROM review_run WHERE workspace_id=%s AND actor_id=%s AND request_key=%s',
                                   (workspace_id, facts['actor_id'], body.request_key)).fetchone()
            if (not row or row['subject'] != current_actor.subject or row['document_id'] != document_id
                    or row['document_version_id'] != body.document_version_id or row['document_revision'] != body.document_revision
                    or row['content_hash'] != head['content_hash'] or row['template_version_id'] != head['template_version_id']
                     or row['template_hash'] != content_hash(structure)
                     or row['input_hash'] != input_hash(claims, project_facts, citations)
                    or row['rule_version'] != RULE_VERSION or tuple(row['policy_epoch']) != auth.policy_epoch):
                raise ApiError(409, 'REVIEW_REQUEST_CONFLICT', '请求标识已用于其他审校输入')
            if created:
                audit(conn, facts['actor_id'], workspace_id, row['id'], 'review:requested', {},
                      {'document_version_id': str(body.document_version_id)}, request.state.request_id, request.state.trace_id)
            payload = view(row, head)
        return {'data': payload}

    @router.get('')
    def history(workspace_id: UUID, document_id: UUID, response: Response, current_actor=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            _, auth, head = current(conn, current_actor.subject, workspace_id, document_id)
            rows = conn.execute('''SELECT * FROM review_run WHERE workspace_id=%s AND document_id=%s
                ORDER BY created_at DESC,id DESC LIMIT 50''', (workspace_id, document_id)).fetchall()
            items = []
            for row in rows:
                payload = view(row, head)
                results, _ = current_results(conn, row)
                payload['current_eligible'] = accessible_result(conn, row, head, auth,
                    current_actor.subject, workspace_id, document_id, results)
                payload['results'] = [dict(item) for item in results]
                items.append(payload)
            return {'data': {'items': items}}

    @router.get('/{run_id}')
    def detail(workspace_id: UUID, document_id: UUID, run_id: UUID, response: Response,
               severity: str | None = Query(default=None, max_length=16),
               section_id: UUID | None = None, status: str | None = Query(default=None, max_length=16),
               keyword: str | None = Query(default=None, max_length=128),
               offset: int = Query(default=0, ge=0, le=100000),
               current_actor=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        filters = issue_filters(severity, section_id, status, keyword)
        with database() as conn:
            _, auth, head = current(conn, current_actor.subject, workspace_id, document_id)
            row = conn.execute('SELECT * FROM review_run WHERE workspace_id=%s AND document_id=%s AND id=%s',
                               (workspace_id, document_id, run_id)).fetchone()
            if not row:
                raise ApiError(404, 'REVIEW_NOT_FOUND', '审校不存在或无权查看')
            results, _ = current_results(conn, row)
            payload = view(row, head)
            payload['current_eligible'] = accessible_result(conn, row, head, auth,
                current_actor.subject, workspace_id, document_id, results)
            ast, sources_current, citations = inspection(conn, row, head, current_actor.subject, workspace_id, document_id)
            issues, total = filtered_issues(conn, run_id, filters, sources_current=sources_current,
                                             citations=citations,
                                            current_version_id=head['head_version_id'], offset=offset)
            visible = [issue_view(item, ast, sources_current=sources_current, citations=citations,
                                    current_version_id=head['head_version_id']) for item in issues]
            coverage_metric = {'numerator': None, 'denominator': None, 'state': 'unevaluated'}
            if payload['current_eligible'] and ast['document']['metadata']['document_type'] == 'test_plan':
                from ..documents.traceability import coverage
                coverage_metric = coverage(conn, current_actor.subject, workspace_id, ast, document_id, row['document_version_id'])
            # A ratio is defined only for this concrete, bounded result set's count, not a quality score.
            return {'data': {**payload, 'results': [dict(item) for item in results],
                             'issues': visible, 'issue_count': total, 'returned_count': len(visible),
                             'offset': offset, 'page_size': 100,
                             'source_state': 'current' if sources_current else 'denied',
                             'sections': [{'id': section['id'], 'title': section['title']}
                                          for section in ast['document']['sections']],
                             'metrics': {'issue_count': {'numerator': total, 'denominator': None,
                                                         'state': 'count'},
                                         'score': {'numerator': None, 'denominator': None,
                                                   'state': 'unevaluated'},
                                          'coverage': coverage_metric},
                             'version': {'id': row['document_version_id'], 'revision': row['document_revision'],
                                         'current_id': head['head_version_id'], 'current_revision': head['revision'],
                                         'comparison': version_comparison(ast, head['ast'])}}}

    @router.get('/{run_id}/issues/{issue_id}')
    def issue_detail(workspace_id: UUID, document_id: UUID, run_id: UUID, issue_id: UUID,
                     response: Response, current_actor=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            _, _, head = current(conn, current_actor.subject, workspace_id, document_id)
            row = conn.execute('SELECT * FROM review_run WHERE workspace_id=%s AND document_id=%s AND id=%s',
                               (workspace_id, document_id, run_id)).fetchone()
            if not row:
                raise ApiError(404, 'REVIEW_NOT_FOUND', '审校不存在或无权查看')
            ast, sources_current, citations = inspection(conn, row, head, current_actor.subject, workspace_id, document_id)
            issue = conn.execute('''SELECT i.*,d.id AS disposition_id,d.action AS disposition_action,
                d.reason AS disposition_reason,d.result_version_id,d.recheck_run_id,
                rr.document_version_id AS recheck_version_id
                FROM review_issue i LEFT JOIN LATERAL (SELECT * FROM review_disposition
                WHERE issue_id=i.id ORDER BY (action='handled') DESC,created_at DESC,id DESC LIMIT 1) d ON true
                LEFT JOIN review_run rr ON rr.id=d.recheck_run_id
                WHERE i.run_id=%s AND i.id=%s''',
                                  (run_id, issue_id)).fetchone()
            if not issue:
                raise ApiError(404, 'REVIEW_ISSUE_NOT_FOUND', '问题不存在或无权查看')
            return {'data': issue_view(issue, ast, sources_current=sources_current, citations=citations,
                                       current_version_id=head['head_version_id'])}

    @router.post('/{run_id}/issues/{issue_id}/dispositions')
    def decide_issue(workspace_id: UUID, document_id: UUID, run_id: UUID, issue_id: UUID,
                     command: DispositionRequest, request: Request, response: Response,
                     current_actor=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        initial, views = (), ()
        if command.action == 'accept' and command.patch_run_id:
            # Evidence retrieval happens outside the commit transaction; persist_decision
            # rechecks every selected run and evidence under the final lock.
            with database() as preliminary:
                facts, _, head = current(preliminary, current_actor.subject, workspace_id, document_id, review=True)
                prior = preliminary.execute('''SELECT id FROM review_disposition WHERE workspace_id=%s
                    AND actor_id=%s AND request_key=%s''',
                    (workspace_id, facts['actor_id'], command.request_key)).fetchone()
                if not prior and head['head_version_id'] == command.base_version_id and head['revision'] == command.base_revision:
                    owned = preliminary.execute('''SELECT 1 FROM review_issue i JOIN review_run r ON r.id=i.run_id
                        WHERE i.id=%s AND r.id=%s AND r.workspace_id=%s AND r.document_id=%s''',
                        (issue_id, run_id, workspace_id, document_id)).fetchone()
                    if not owned:
                        raise ApiError(404, 'REVIEW_ISSUE_NOT_FOUND', '问题不存在或无权处置')
                    initial = selected_patches(preliminary, current_actor.subject, workspace_id, document_id,
                                               [command.patch_run_id], command.base_version_id, command.base_revision)
            views = [evidence(settings, pack_job(row, outline)) for row, _, outline in initial]
        with database() as conn:
            return disposition(conn, current_actor.subject, workspace_id, document_id,
                               run_id, issue_id, command, request, initial, views)

    @router.post('/{run_id}/wake')
    def wake(workspace_id: UUID, document_id: UUID, run_id: UUID,
             x_review_time: str = Header(default=''), x_review_mac: str = Header(default='')):
        key = settings.model_wake_key
        try:
            timestamp = int(x_review_time)
        except ValueError:
            timestamp = 0
        expected = hmac.new(key.encode(), f'{workspace_id}:{document_id}:{run_id}:{timestamp}'.encode('ascii'),
                            hashlib.sha256).hexdigest()
        if len(key) < 32 or abs(time.time() - timestamp) > 30 or not hmac.compare_digest(x_review_mac, expected):
            raise ApiError(403, 'REVIEW_WAKE_DENIED', '任务通知无效')
        execute(settings, workspace_id, document_id, run_id)
        return {'data': {'accepted': True}}

    return router
