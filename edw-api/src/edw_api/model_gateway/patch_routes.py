"""Human-selected AI decisions; only the API may advance the document head."""
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
from ..documents.schemas import DomainAst
from ..documents.editor_repository import editable_document, save_document
from ..documents.editor_routes import SaveDocument
from ..documents.outline_repository import read_outline
from ..errors import ApiError
from ..knowledge.evidence import pinned as evidence_pinned
from ..knowledge.governance import local_source
from ..task_contract import canonical
from .copilot import interpret, resolve, structured
from .copilot_routes import _validated_view, fenced_run, pack_job
from .patches import apply_selected
from .repository import active, current_document
from .sections import evidence


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: UUID
    base_version_id: UUID
    base_revision: int = Field(ge=1, le=9007199254740990)
    action: str = Field(pattern='^(accept|reject)$')
    run_ids: list[UUID] = Field(min_length=1, max_length=12)


def request_hash(command):
    intent = command.model_dump(mode='json', exclude={'request_key'})
    return sha256(canonical(intent)).hexdigest()


def selected(conn, subject, workspace_id, document_id, run_ids, base_version, revision):
    entries = []
    for run_id in run_ids:
        row = conn.execute('''SELECT c.*,m.state,m.output,m.output_sha256,m.policy_epoch,
            m.policy_version_id,m.policy_revision,m.usage,p.model_id,p.prompt_ref,p.prompt_sha256
            FROM copilot_run c JOIN model_generation_run m ON m.id=c.model_run_id
            AND m.workspace_id=c.workspace_id AND m.document_id=c.document_id AND m.actor_id=c.actor_id
            AND m.subject=c.subject
            JOIN model_policy_version p ON p.id=m.policy_version_id AND p.workspace_id=m.workspace_id
            WHERE c.id=%s AND c.workspace_id=%s AND c.document_id=%s AND c.subject=%s''',
            (run_id, workspace_id, document_id, subject)).fetchone()
        if (not row or row['document_version_id'] != base_version or row['document_revision'] != revision
                or row['state'] != 'SUCCEEDED' or not row['output']
                or sha256(canonical(row['output'])).hexdigest() != row['output_sha256']):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '候审提案或基础版本已变化')
        if row['section_id'] is None:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '候审提案缺少目标')
        auth = current_document(conn, subject, workspace_id, document_id, base_version, revision)
        pointer, policy = active(conn, workspace_id)
        if (not policy or policy['provider'] != 'internal' or policy['id'] != row['policy_version_id']
                or pointer['revision'] != row['policy_revision']
                or tuple(row['policy_epoch']) != auth.policy_epoch or str(row['actor_id']) != auth.actor_id):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '提案策略或权限已变化')
        outline = read_outline(conn, subject, workspace_id, document_id)
        if outline['state'] != 'OUTLINE_READY':
            raise ApiError(409, 'AI_PATCH_CONFLICT', '确认大纲已变化')
        if str(row['section_id']) not in {item['id'] for item in outline['snapshot']['sections']}:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '章节已从大纲移除')
        entries.append((row, policy, outline))
    return entries


def derive(conn, subject, workspace_id, document_id, row, outline, view, head):
    _, target, digest = resolve(head, row['section_id'], row['block_id'],
                                row['target_hash'], row['operation'])
    try:
        output = json.loads(row['output']['proposal'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiError(422, 'AI_PATCH_INVALID', '提案响应不可解析') from exc
    ref = output.get('source_ref') if isinstance(output, dict) else None
    source = next((dict(item, source_ref=ref) for item in view['items']
        if type(ref) is int and item['ordinal'] == ref and ref <= 12), None)
    if source and source['chain'] == 'attachment':
        pack = conn.execute('''SELECT content,content_hash FROM section_evidence_pack WHERE
            id=%s AND workspace_id=%s AND job_id=%s AND document_id=%s AND section_id=%s
            AND outline_version_id=%s AND context_version_id=%s AND document_version_id=%s''',
            (row['pack_id'], workspace_id, row['pack_job_id'], document_id, row['section_id'],
             outline['version_id'], outline['context_version_id'], row['document_version_id'])).fetchone()
        if not pack or pack['content_hash'] != row['pack_hash'] or sha256(canonical(pack['content'])).hexdigest() != row['pack_hash']:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '持久证据包已变化')
        if ref > len(pack['content']['items']):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '来源序号已变化')
        original = pack['content']['items'][ref - 1]
        if any(original[key] != source[key] for key in ('source_id', 'chunk_hash', 'locator')):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '来源定位已变化')
        if any(original.get(key) != source.get(key) for key in ('version','classification','excerpt')):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '来源版本或摘要已变化')
        _, _, anchor, _, _ = evidence_pinned(conn, subject, workspace_id, document_id,
            row['section_id'], outline['version_id'], outline['context_version_id'], row['document_version_id'])
        if local_source(conn, workspace_id, anchor, source['source_id'], source['version'],
                source['chunk_hash'], source['locator'], source['classification'], original['page'],
                original['ordinal'], subject) != source['excerpt']:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '当前附件来源已变化')
    if source and source['chain'] == 'enterprise':
        raise ApiError(409, 'AI_PATCH_SOURCE_UNVERIFIED', '企业来源需重新核验后方可接受')
    proposal = (structured(row['operation'], target, digest, output, source)
                if row['operation'] in ('table','mermaid') else interpret(row['operation'], target, digest, output, source))
    if proposal['family'] != 'patch' or not proposal.get('patch'):
        raise ApiError(422, 'AI_PATCH_INVALID', '此操作没有可接受的 Patch')
    return {'section_id': str(row['section_id']), 'patch': proposal['patch'],
            'provenance': {'run_id': str(row['model_run_id']), 'copilot_id': str(row['id']),
                'pack_id': str(row['pack_id']), 'pack_hash': row['pack_hash'],
                'view_hash': row['view_hash'], 'policy_version_id': str(row['policy_version_id']),
                'model_id': row['model_id'], 'prompt_ref': row['prompt_ref'],
                'prompt_sha256': row['prompt_sha256'], 'output_sha256': row['output_sha256'],
                'target_hash': digest, 'patch_hash': sha256(canonical(proposal['patch'])).hexdigest(),
                'usage': row['usage']}}


def recheck(conn, workspace_id, document_id, runs, views):
    prepared = []
    for (row, policy, outline), view in zip(runs, views):
        _validated_view(view, row, policy)
        fenced_run(conn, workspace_id, document_id, row['model_run_id'], row['output'], view)
        prepared.append(row)
    return prepared


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}/ai-patches')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @router.post('/decisions')
    def decide(workspace_id: UUID, document_id: UUID, command: Decision, request: Request,
               response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        if len(set(command.run_ids)) != len(command.run_ids):
            raise ApiError(422, 'AI_PATCH_INVALID', '重复选择提案')
        try:
            with connection(settings) as preliminary:
                preliminary_facts, _ = editable_document(preliminary, current.subject, workspace_id, document_id)
                existing = preliminary.execute('''SELECT id FROM ai_patch_decision WHERE workspace_id=%s
                    AND actor_id=%s AND request_key=%s''',
                    (workspace_id, preliminary_facts['actor_id'], command.request_key)).fetchone()
                initial = selected(preliminary, current.subject, workspace_id, document_id,
                                   command.run_ids, command.base_version_id, command.base_revision) if not existing else []
            views = [evidence(settings, pack_job(row, outline)) for row, _, outline in initial]
            with connection(settings) as conn:
                return persist_decision(conn, current.subject, workspace_id, document_id,
                                        command, request, initial, views, existing)
        except AccessDenied as exc:
            raise ApiError(404, 'DOCUMENT_NOT_FOUND', '文档或证据不可访问') from exc

    return router


def persist_decision(conn, subject, workspace_id, document_id, command, request, initial, views, existing):
    """Commit one author's decision under current workspace/document locks."""
    facts, _ = editable_document(conn, subject, workspace_id, document_id, exclusive=True)
    if not conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                        (document_id, workspace_id)).fetchone():
        raise ApiError(404, 'DOCUMENT_NOT_FOUND', '文档不可访问')
    digest = request_hash(command)
    prior = conn.execute('''SELECT * FROM ai_patch_decision WHERE workspace_id=%s AND actor_id=%s
        AND request_key=%s''', (workspace_id, UUID(str(facts['actor_id'])), command.request_key)).fetchone()
    if prior:
        if (prior['document_id'] != document_id or prior['subject'] != subject
                or prior['provenance']['request_hash'] != digest):
            raise ApiError(409, 'AI_PATCH_REQUEST_CONFLICT', '请求标识已用于其他选择')
        if not existing or prior['id'] != existing['id']:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '请求状态已变化，请重新确认')
        current_head = conn.execute('''SELECT d.head_version_id,d.revision,v.ast,v.content_hash
            FROM document d JOIN document_version v ON v.id=d.head_version_id
            AND v.document_id=d.id WHERE d.id=%s AND d.workspace_id=%s''',
            (document_id, workspace_id)).fetchone()
        if not current_head or content_hash(current_head['ast']) != current_head['content_hash']:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '当前文档不可核对')
        if (prior['action'] == 'accept' and
                (current_head['head_version_id'] != prior['result_version_id']
                 or current_head['revision'] != prior['result_revision'])):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '接受结果不再是当前版本，请比较历史')
        return {'data': {'id': prior['id'], 'action': prior['action'],
            'version_id': prior['result_version_id'], 'revision': prior['result_revision'], 'replayed': True}}
    if existing:
        raise ApiError(409, 'AI_PATCH_CONFLICT', '请求状态已变化，请重新确认')
    prior = conn.execute('''SELECT * FROM ai_patch_decision WHERE workspace_id=%s AND actor_id=%s
        AND request_key=%s''', (workspace_id, UUID(str(facts['actor_id'])), command.request_key)).fetchone()
    if prior:
        if (prior['document_id'] != document_id or prior['subject'] != subject
                or prior['provenance']['request_hash'] != digest):
            raise ApiError(409, 'AI_PATCH_REQUEST_CONFLICT', '请求标识已用于其他选择')
        raise ApiError(409, 'AI_PATCH_CONFLICT', '并发请求已提交，请重新读取决议')
    if command.action == 'accept':
        used = conn.execute('''SELECT 1 FROM ai_patch_decision WHERE workspace_id=%s
            AND document_id=%s AND action='accept' AND run_ids && %s::uuid[] LIMIT 1''',
            (workspace_id, document_id, command.run_ids)).fetchone()
        if used:
            raise ApiError(409, 'AI_PATCH_ALREADY_APPLIED', '提案已接受，请比较最新版本')
    runs = selected(conn, subject, workspace_id, document_id,
                    command.run_ids, command.base_version_id, command.base_revision)
    if len(runs) != len(initial) or any(row['id'] != before[0]['id'] or row['pack_hash'] != before[0]['pack_hash']
           or row['view_hash'] != before[0]['view_hash']
           for (row, _, _), before in zip(runs, initial)):
        raise ApiError(409, 'AI_PATCH_CONFLICT', '候审证据已变化')
    head = conn.execute('''SELECT v.ast,v.content_hash FROM document d JOIN document_version v
        ON v.id=d.head_version_id AND v.document_id=d.id WHERE d.id=%s AND d.workspace_id=%s
        AND d.head_version_id=%s AND d.revision=%s''',
        (document_id, workspace_id, command.base_version_id, command.base_revision)).fetchone()
    if not head or content_hash(head['ast']) != head['content_hash']:
        raise ApiError(409, 'AI_PATCH_CONFLICT', '基础版本已变化，请比较最新版本')
    recheck(conn, workspace_id, document_id, runs, views)
    prepared = []
    for (row, _, outline), view in zip(runs, views):
        prepared.append(derive(conn, subject, workspace_id, document_id,
                               row, outline, view, head['ast']))
    if command.action == 'accept':
        ast = apply_selected(head['ast'], prepared)
        saved = save_document(conn, subject, workspace_id, document_id,
            SaveDocument(base_version_id=command.base_version_id, revision=command.base_revision,
                         ast=DomainAst.model_validate(ast)), request.state.request_id, request.state.trace_id)
        version_id, revision = saved['version_id'], saved['revision']
    else:
        version_id, revision = None, None
    identifier = uuid4()
    provenance = {'request_hash': digest, 'selected': [entry['provenance'] for entry in prepared]}
    conn.execute('''INSERT INTO ai_patch_decision(id,workspace_id,document_id,actor_id,subject,
        request_key,action,base_version_id,base_revision,run_ids,provenance,result_version_id,result_revision)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (identifier, workspace_id, document_id, UUID(str(facts['actor_id'])), subject,
         command.request_key, command.action, command.base_version_id, command.base_revision,
         command.run_ids, Jsonb(provenance), version_id, revision))
    conn.execute('''INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,
        before_policy,after_policy,request_id,trace_id,occurred_at) VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())''',
        (uuid4(), workspace_id, facts['actor_id'], document_id, f'ai_patch:{command.action}',
         Jsonb({'base_version_id': str(command.base_version_id), 'revision': command.base_revision}),
         Jsonb({'decision_id': str(identifier), 'result_version_id': str(version_id) if version_id else None}),
         request.state.request_id, request.state.trace_id))
    return {'data': {'id': identifier, 'action': command.action,
        'version_id': version_id, 'revision': revision, 'replayed': False}}
