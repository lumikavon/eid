"""Current-access review submission and fenced, API-owned execution."""
from contextlib import contextmanager
from uuid import UUID, uuid4
import hashlib
import hmac
import json
import time

import psycopg
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..documents.domain import content_hash
from ..documents.context_repository import _head as context_head
from ..errors import ApiError
from ..model_gateway.repository import audit
from .rules import CATEGORIES, RULE_VERSION, inspect


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: UUID
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)


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
    from ..knowledge.governance import local_source
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


def citation_rows(conn, workspace_id, document_id, version_id):
    return conn.execute('''SELECT c.section_id,c.block_id,c.selected_text,c.needs_review,
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
    context = context_head(conn, document_id)
    facts = []
    if context and context['document_version_id'] == version_id:
        from ..documents.context_repository import _snapshot, _sources
        context_value = _snapshot(context)
        _sources(conn, subject, workspace_id, context_value)
        facts = context_value.model_dump(mode='json')['facts']
    return template['structure'], claims, facts, citations


def source_snapshot(citations):
    return [{key: row[key] for key in ('section_id', 'block_id', 'selected_text', 'needs_review',
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
            outcomes, issues = inspect(head['ast'], structure, claims, project_facts=facts,
                                       stale_sources=[c for c in citations if c['needs_review']])
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
            except ApiError as exc:
                if exc.code != 'REVIEW_SOURCE_CHANGED':
                    raise
                sources_current = False
                outcomes, issues = inspect(head['ast'], fresh_structure, fresh_claims,
                    project_facts=fresh_facts, stale_sources=fresh_citations)
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
    def detail(workspace_id: UUID, document_id: UUID, run_id: UUID, response: Response, current_actor=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
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
            try:
                citations = citation_rows(conn, workspace_id, document_id, row['document_version_id'])
                anchor = conn.execute('SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s',
                                      (document_id, workspace_id)).fetchone()
                source_safe(conn, workspace_id, anchor, current_actor.subject, citations)
                issues = conn.execute('SELECT * FROM review_issue WHERE run_id=%s ORDER BY created_at,id LIMIT 500',
                                      (run_id,)).fetchall()
            except ApiError:
                issues = [{**dict(item), 'quote': '[来源需复核]', 'source_id': None, 'details': {}}
                          for item in conn.execute('''SELECT * FROM review_issue WHERE run_id=%s
                              AND rule_id='obsolete_citation' ORDER BY created_at,id LIMIT 500''',
                              (run_id,)).fetchall()]
            return {'data': {**payload, 'results': [dict(item) for item in results],
                             'issues': [dict(item) for item in issues]}}

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
