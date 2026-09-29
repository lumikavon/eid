"""Current-grant pending-fact reads and explicit human confirmation."""
from hashlib import sha256
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..documents.domain import content_hash
from ..documents.editor_repository import editable_document
from ..errors import ApiError
from .copilot import resolve, interpret
from .copilot_routes import _validated_view, fenced_run, pack_job
from .patch_routes import selected
from .sections import evidence
from ..knowledge.evidence import pinned as evidence_pinned
from ..knowledge.governance import local_source


class Confirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_version_id: UUID
    revision: int = Field(ge=1, le=9007199254740990)
    value: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1000)


class Capture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: UUID
    base_version_id: UUID
    revision: int = Field(ge=1, le=9007199254740990)


def captured(conn, subject, workspace_id, document_id, row, outline, view, head):
    _, target, digest = resolve(head, row['section_id'], row['block_id'], row['target_hash'], 'create_pending')
    try:
        output = json.loads(row['output']['proposal'])
    except (TypeError, KeyError, ValueError) as exc:
        raise ApiError(422, 'PENDING_PROPOSAL_INVALID', '待确认提案格式无效') from exc
    ref = output.get('source_ref') if isinstance(output, dict) else None
    source = next((dict(item, source_ref=ref) for item in view['items']
        if type(ref) is int and item['ordinal'] == ref and ref <= 12), None)
    if source and source['chain'] == 'attachment':
        pack = conn.execute('''SELECT content,content_hash FROM section_evidence_pack WHERE id=%s
            AND workspace_id=%s AND job_id=%s AND document_id=%s AND section_id=%s
            AND outline_version_id=%s AND context_version_id=%s AND document_version_id=%s''',
            (row['pack_id'], workspace_id, row['pack_job_id'], document_id, row['section_id'],
             outline['version_id'], outline['context_version_id'], row['document_version_id'])).fetchone()
        from ..task_contract import canonical
        if not pack or pack['content_hash'] != row['pack_hash'] or sha256(canonical(pack['content'])).hexdigest() != row['pack_hash']:
            raise ApiError(409, 'PENDING_SOURCE_CHANGED', '证据包已变化')
        if ref > len(pack['content']['items']):
            raise ApiError(409, 'PENDING_SOURCE_CHANGED', '引用已变化')
        original = pack['content']['items'][ref-1]
        if any(original[key] != source[key] for key in ('source_id','chunk_hash','locator')):
            raise ApiError(409, 'PENDING_SOURCE_CHANGED', '来源定位已变化')
        if any(original.get(key) != source.get(key) for key in ('version','classification','excerpt')):
            raise ApiError(409, 'PENDING_SOURCE_CHANGED', '来源版本或摘要已变化')
        _, _, anchor, _, _ = evidence_pinned(conn, subject, workspace_id, document_id,
            row['section_id'],outline['version_id'],outline['context_version_id'],row['document_version_id'])
        if local_source(conn,workspace_id,anchor,source['source_id'],source['version'],source['chunk_hash'],
                source['locator'],source['classification'],original['page'],original['ordinal'],subject) != source['excerpt']:
            raise ApiError(409, 'PENDING_SOURCE_CHANGED', '当前来源已变化')
    if source and source['chain'] == 'enterprise':
        raise ApiError(409, 'PENDING_SOURCE_UNVERIFIED', '企业来源需要重新核验')
    proposal = interpret('create_pending', target, digest, output, source)
    item = proposal['items'][0]
    return item, digest


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}/pending-facts')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @router.post('')
    def capture(workspace_id: UUID, document_id: UUID, command: Capture,
                response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            with connection(settings) as first:
                editable_document(first, current.subject, workspace_id, document_id)
                runs = selected(first, current.subject, workspace_id, document_id,
                    [command.run_id], command.base_version_id, command.revision)
                row, policy, outline = runs[0]
                if row['operation'] != 'create_pending':
                    raise ApiError(422, 'PENDING_PROPOSAL_INVALID', '操作不是待确认项')
            view = evidence(settings, pack_job(row, outline))
            with connection(settings) as conn:
                facts, _ = editable_document(conn, current.subject, workspace_id, document_id, exclusive=True)
                if str(facts['actor_id']) != str(row['actor_id']):
                    raise ApiError(404, 'PENDING_PROPOSAL_NOT_FOUND', '提案不属于当前作者')
                conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                    (document_id, workspace_id)).fetchone()
                previous = conn.execute('''SELECT id,status,document_version_id FROM ai_pending_fact WHERE workspace_id=%s
                    AND copilot_run_id=%s AND document_id=%s''',
                    (workspace_id, command.run_id, document_id)).fetchone()
                row, policy, outline = selected(conn, current.subject, workspace_id, document_id,
                    [command.run_id], command.base_version_id, command.revision)[0]
                if row['operation'] != 'create_pending':
                    raise ApiError(422, 'PENDING_PROPOSAL_INVALID', '操作不是待确认项')
                _validated_view(view, row, policy)
                fenced_run(conn, workspace_id, document_id, row['model_run_id'], row['output'], view)
                head = conn.execute('''SELECT v.ast,v.content_hash FROM document d JOIN document_version v
                    ON v.id=d.head_version_id AND v.document_id=d.id WHERE d.id=%s AND d.workspace_id=%s
                    AND d.head_version_id=%s AND d.revision=%s''',
                    (document_id, workspace_id, command.base_version_id, command.revision)).fetchone()
                if not head or content_hash(head['ast']) != head['content_hash']:
                    raise ApiError(409, 'PENDING_VERSION_CHANGED', '当前文档已变化')
                if runs[0][0]['id'] != row['id'] or runs[0][0]['view_hash'] != row['view_hash']:
                    raise ApiError(409, 'PENDING_STALE', '当前提案证据已变化')
                item, digest = captured(conn, current.subject, workspace_id, document_id,
                    row, outline, view, head['ast'])
                if previous:
                    if previous['document_version_id'] != command.base_version_id:
                        raise ApiError(409, 'PENDING_VERSION_CHANGED', '旧提案不可用')
                    return {'data': {'id': previous['id'], 'status': previous['status']}}
                identifier = uuid4()
                conn.execute('''INSERT INTO ai_pending_fact(id,workspace_id,document_id,document_version_id,
                    section_id,block_id,actor_id,subject,copilot_run_id,reason,proposed_value,evidence,target_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (identifier, workspace_id, document_id, command.base_version_id,row['section_id'],
                     row['block_id'],facts['actor_id'],current.subject,command.run_id,
                     '模型建议核对该位置事实，未提供独立验证',item['proposed_value'],Jsonb(item['evidence']),digest))
                return {'data': {'id': identifier, 'status': 'pending'}}
        except AccessDenied as exc:
            raise ApiError(404, 'DOCUMENT_NOT_FOUND', '文档不可访问') from exc

    @router.get('')
    def listing(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with connection(settings) as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
            head = conn.execute('SELECT head_version_id,revision FROM document WHERE id=%s AND workspace_id=%s',
                (document_id, workspace_id)).fetchone()
            if not head:
                raise ApiError(404, 'DOCUMENT_NOT_FOUND', '文档不可访问')
            rows = conn.execute('''SELECT p.id,p.section_id,p.block_id,p.reason,p.proposed_value,p.evidence,
                p.status,p.confirmed_value,p.confirmed_by,p.confirmed_at,p.created_at,p.document_version_id,
                p.target_hash FROM ai_pending_fact p WHERE p.workspace_id=%s AND p.document_id=%s
                AND p.document_version_id=%s ORDER BY p.created_at,p.id LIMIT 200''',
                (workspace_id, document_id, head['head_version_id'])).fetchall()
            count = conn.execute('''SELECT count(*) AS n FROM ai_pending_fact WHERE workspace_id=%s
                AND document_id=%s AND document_version_id=%s AND status='pending' ''',
                (workspace_id, document_id, head['head_version_id'])).fetchone()['n']
            return {'data': {'items': rows, 'pending_count': count,
                'version_id': head['head_version_id'], 'revision': head['revision']}}

    @router.get('/history')
    def history(workspace_id: UUID, document_id: UUID, response: Response,
                current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with connection(settings) as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
            rows = conn.execute('''SELECT p.id,p.document_version_id,p.section_id,p.block_id,p.reason,
                p.proposed_value,p.evidence,p.status,p.confirmed_value,p.confirmed_by,p.confirmed_at,
                e.reason AS resolution_reason,e.value_hash,e.created_at AS resolved_at
                FROM ai_pending_fact p LEFT JOIN ai_pending_event e ON e.workspace_id=p.workspace_id
                AND e.fact_id=p.id WHERE p.workspace_id=%s AND p.document_id=%s
                ORDER BY p.created_at DESC,p.id DESC LIMIT 200''',
                (workspace_id, document_id)).fetchall()
            return {'data': {'items': rows}}

    @router.post('/{fact_id}/confirm')
    def confirm(workspace_id: UUID, document_id: UUID, fact_id: UUID, command: Confirm,
                request: Request, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        if not command.value.strip() or not command.reason.strip():
            raise ApiError(422, 'PENDING_VALUE_INVALID', '确认值与原因不能为空')
        try:
            with connection(settings) as preliminary:
                editable_document(preliminary, current.subject, workspace_id, document_id)
                proposed = preliminary.execute('''SELECT copilot_run_id FROM ai_pending_fact
                    WHERE id=%s AND workspace_id=%s AND document_id=%s AND document_version_id=%s''',
                    (fact_id, workspace_id, document_id, command.base_version_id)).fetchone()
                if not proposed:
                    raise ApiError(404, 'PENDING_NOT_FOUND', '待确认项不存在')
                initial = selected(preliminary, current.subject, workspace_id, document_id,
                    [proposed['copilot_run_id']], command.base_version_id, command.revision)[0]
            view = evidence(settings, pack_job(initial[0], initial[2]))
            with connection(settings) as conn:
                facts, _ = editable_document(conn, current.subject, workspace_id, document_id, exclusive=True)
                conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                    (document_id, workspace_id)).fetchone()
                head = conn.execute('''SELECT v.ast,v.content_hash,d.revision FROM document d JOIN document_version v
                    ON v.id=d.head_version_id AND v.document_id=d.id WHERE d.id=%s AND d.workspace_id=%s
                    AND d.head_version_id=%s AND d.revision=%s''',
                    (document_id, workspace_id, command.base_version_id, command.revision)).fetchone()
                if not head or content_hash(head['ast']) != head['content_hash']:
                    raise ApiError(409, 'PENDING_VERSION_CHANGED', '文档已变化，请重新查看待确认项')
                item = conn.execute('''SELECT * FROM ai_pending_fact WHERE id=%s AND workspace_id=%s
                    AND document_id=%s AND document_version_id=%s FOR UPDATE''',
                    (fact_id, workspace_id, document_id, command.base_version_id)).fetchone()
                if not item or item['status'] != 'pending':
                    raise ApiError(409, 'PENDING_STALE', '待确认项已变化')
                row, policy, outline = selected(conn, current.subject, workspace_id, document_id,
                    [item['copilot_run_id']], command.base_version_id, command.revision)[0]
                _validated_view(view, row, policy)
                fenced_run(conn, workspace_id, document_id, row['model_run_id'], row['output'], view)
                proposal, _ = captured(conn, current.subject, workspace_id, document_id,
                    row, outline, view, head['ast'])
                if initial[0]['id'] != row['id'] or initial[0]['view_hash'] != row['view_hash']:
                    raise ApiError(409, 'PENDING_STALE', '当前提案证据已变化')
                if (item['target_hash'] != row['target_hash'] or item['proposed_value'] != proposal['proposed_value']
                        or item['evidence'] != proposal['evidence']
                        or item['section_id'] != row['section_id'] or item['block_id'] != row['block_id']):
                    raise ApiError(409, 'PENDING_STALE', '待确认依据已变化')
                _, block, digest = resolve(head['ast'], item['section_id'], item['block_id'],
                    item['target_hash'], 'create_pending')
                if not block or digest != item['target_hash']:
                    raise ApiError(409, 'PENDING_STALE', '定位文本已变化')
                # This is a disposition, never a claim that the proposed model value was verified.
                conn.execute('''UPDATE ai_pending_fact SET status='confirmed',confirmed_value=%s,
                    confirmed_by=%s,confirmed_at=clock_timestamp() WHERE id=%s AND status='pending' ''',
                    (command.value, facts['actor_id'], fact_id))
                conn.execute('''INSERT INTO ai_pending_event(id,workspace_id,fact_id,actor_id,action,
                    base_version_id,reason,value_hash) VALUES (%s,%s,%s,%s,'confirm',%s,%s,%s)''',
                    (uuid4(), workspace_id, fact_id, facts['actor_id'], command.base_version_id,
                     command.reason, sha256(command.value.encode()).hexdigest()))
                conn.execute('''INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,
                    before_policy,after_policy,request_id,trace_id,occurred_at) VALUES
                    (%s,%s,%s,%s,'pending:confirm',%s,%s,%s,%s,clock_timestamp())''',
                    (uuid4(), workspace_id, facts['actor_id'], document_id,
                     Jsonb({'fact_id': str(fact_id), 'status': 'pending'}),
                     Jsonb({'fact_id': str(fact_id), 'status': 'confirmed'}),
                     request.state.request_id, request.state.trace_id))
                count = conn.execute('''SELECT count(*) AS n FROM ai_pending_fact WHERE workspace_id=%s
                    AND document_id=%s AND document_version_id=%s AND status='pending' ''',
                    (workspace_id, document_id, command.base_version_id)).fetchone()['n']
                return {'data': {'id': fact_id, 'status': 'confirmed', 'pending_count': count}}
        except AccessDenied as exc:
            raise ApiError(404, 'DOCUMENT_NOT_FOUND', '文档不可访问') from exc

    return router
