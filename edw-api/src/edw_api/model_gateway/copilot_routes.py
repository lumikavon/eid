"""Copilot target inspection with current document authorization."""
from hashlib import sha256
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..auth import bearer_token
from ..db import connection
from ..documents.editor_repository import editable_document
from ..documents.domain import content_hash
from ..documents.outline_repository import read_outline
from ..errors import ApiError
from ..knowledge.evidence import pinned as evidence_pinned
from ..knowledge.governance import local_source
from ..task_contract import canonical
from .copilot import CATALOG, interpret, resolve, result, structured
from .policy import GenerateInput
from .repository import reserve
from .repository import active, current_document
from .routes import _schedule
from .sections import evidence


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: str = Field(max_length=64)
    document_version_id: UUID
    document_revision: int = Field(ge=1)
    section_id: UUID
    block_id: UUID | None = None
    target_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    prompt: str = Field(default='', max_length=4000)
    request_key: UUID
    pack_job_id: UUID
    pack_id: UUID


def pack_job(row, outline):
    return {'subject': row['subject'], 'workspace_id': row['workspace_id'], 'document_id': row['document_id'],
        'section_id': row['section_id'], 'outline_version_id': outline['version_id'],
        'context_version_id': outline['context_version_id'], 'document_version_id': row['document_version_id'],
        'document_revision': row['document_revision'], 'pack_id': row['pack_id'],
        'pack_job_id': row['pack_job_id'], 'pack_hash': row['pack_hash'],
        'actor_id': row['actor_id'], 'policy_epoch': row['policy_epoch'],
        'policy_version_id': row['policy_version_id'], 'policy_revision': row['policy_revision']}


def _copilot_run(conn, workspace_id, document_id, model_run_id):
    return conn.execute('''SELECT c.*,m.policy_epoch,m.policy_version_id,m.policy_revision
            FROM copilot_run c JOIN model_generation_run m ON m.workspace_id=c.workspace_id
            AND m.id=c.model_run_id AND m.document_id=c.document_id
            AND m.actor_id=c.actor_id AND m.subject=c.subject
            WHERE c.workspace_id=%s AND c.document_id=%s AND c.model_run_id=%s''',
            (workspace_id, document_id, model_run_id)).fetchone()


NON_BLOCKING_GAPS = frozenset({'SOURCE_SCAN_LIMIT', 'ENTERPRISE_UNAVAILABLE',
                               'SEMANTIC_UNAVAILABLE', 'RERANK_UNAVAILABLE',
                               'KEY_FACT_SUPPORT_NOT_VERIFIED', 'ITEM_BUDGET_EXHAUSTED'})


def usable_view(view):
    return (bool(view['items']) and not view['conflict_ids'] and not view['version_conflicts']
            and not any(gap not in NON_BLOCKING_GAPS for gap in view['gaps']))


def _validated_view(view, row, policy):
    if (view['view_hash'] != row['view_hash'] or not usable_view(view)
            or any(item['classification'] > policy['max_classification'] for item in view['items'])):
        raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '当前证据已变化')


def attest_run(settings, workspace_id, document_id, model_run_id):
    with connection(settings) as conn:
        row = _copilot_run(conn, workspace_id, document_id, model_run_id)
        if not row:
            return
        auth = current_document(conn, row['subject'], workspace_id, document_id,
                                row['document_version_id'], row['document_revision'])
        editable_document(conn, row['subject'], workspace_id, document_id)
        pointer, policy = active(conn, workspace_id)
        if (not policy or policy['provider'] != 'internal' or policy['id'] != row['policy_version_id']
                or pointer['revision'] != row['policy_revision']
                or tuple(row['policy_epoch']) != auth.policy_epoch or str(row['actor_id']) != auth.actor_id):
            raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '模型策略或授权已变化')
        outline = read_outline(conn, row['subject'], workspace_id, document_id)
        if outline['state'] != 'OUTLINE_READY' or str(row['section_id']) not in {s['id'] for s in outline['snapshot']['sections']}:
            raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '大纲或章节已变化')
    view = evidence(settings, pack_job(row, outline))
    _validated_view(view, row, policy)
    return row, view


def fenced_run(conn, workspace_id, document_id, model_run_id, output, view):
    row = _copilot_run(conn, workspace_id, document_id, model_run_id)
    if not row:
        return
    editable_document(conn, row['subject'], workspace_id, document_id)
    auth = current_document(conn, row['subject'], workspace_id, document_id,
                            row['document_version_id'], row['document_revision'])
    pointer, policy = active(conn, workspace_id)
    if (not policy or policy['provider'] != 'internal' or policy['id'] != row['policy_version_id']
            or pointer['revision'] != row['policy_revision']
            or tuple(row['policy_epoch']) != auth.policy_epoch or str(row['actor_id']) != auth.actor_id):
        raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '模型策略或授权已变化')
    outline = read_outline(conn, row['subject'], workspace_id, document_id)
    if outline['state'] != 'OUTLINE_READY' or str(row['section_id']) not in {s['id'] for s in outline['snapshot']['sections']}:
        raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '大纲或章节已变化')
    pack = conn.execute('''SELECT p.content_hash,p.content,j.state,j.document_revision FROM section_evidence_pack p
        JOIN section_evidence_job j ON j.id=p.job_id AND j.workspace_id=p.workspace_id
        WHERE p.id=%s AND p.workspace_id=%s AND p.job_id=%s AND p.document_id=%s
        AND p.section_id=%s AND p.outline_version_id=%s AND p.context_version_id=%s
        AND p.document_version_id=%s AND j.actor_id=%s AND j.subject=%s''',
        (row['pack_id'], workspace_id, row['pack_job_id'], document_id, row['section_id'],
         outline['version_id'], outline['context_version_id'], row['document_version_id'],
         row['actor_id'], row['subject'])).fetchone()
    if (not pack or pack['state'] != 'SUCCEEDED' or pack['content_hash'] != row['pack_hash']
            or sha256(canonical(pack['content'])).hexdigest() != row['pack_hash']
            or pack['document_revision'] != row['document_revision'] or view['view_hash'] != row['view_hash']):
        raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '当前证据已变化')
    _validated_view(view, row, policy)
    head = conn.execute('''SELECT v.ast,v.content_hash FROM document d JOIN document_version v
        ON v.id=d.head_version_id AND v.document_id=d.id WHERE d.id=%s AND d.workspace_id=%s
        AND d.head_version_id=%s AND d.revision=%s''',
        (document_id, workspace_id, row['document_version_id'], row['document_revision'])).fetchone()
    if not head or content_hash(head['ast']) != head['content_hash']:
        raise ApiError(409, 'COPILOT_DOCUMENT_CHANGED', '目标文档已变化')
    _, target, digest = resolve(head['ast'], row['section_id'], row['block_id'],
                                row['target_hash'], row['operation'])
    try:
        payload = json.loads(output['proposal'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '模型输出结构无效') from exc
    source_ref = payload.get('source_ref') if isinstance(payload, dict) else None
    source = next((dict(item, source_ref=source_ref) for item in view['items']
        if type(source_ref) is int and item['ordinal'] == source_ref and source_ref <= 12), None)
    if source and source['chain'] == 'attachment':
        if source_ref > len(pack['content']['items']):
            raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '来源定位已变化')
        original = pack['content']['items'][source_ref - 1]
        if (original['source_id'] != source['source_id'] or original['chunk_hash'] != source['chunk_hash']
                or original['locator'] != source['locator']
                or any(original.get(key) != source.get(key)
                       for key in ('version', 'classification', 'excerpt'))):
            raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '来源定位已变化')
        _, _, anchor, _, _ = evidence_pinned(
            conn, row['subject'], workspace_id, document_id, row['section_id'],
            outline['version_id'], outline['context_version_id'], row['document_version_id'])
        if local_source(conn, workspace_id, anchor, source['source_id'], source['version'],
                source['chunk_hash'], source['locator'], source['classification'],
                original['page'], original['ordinal'], row['subject']) != source['excerpt']:
            raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '当前来源已变化')
    proposal = (structured(row['operation'], target, digest, payload, source)
                if row['operation'] in ('table','mermaid') else interpret(row['operation'], target, digest, payload, source))
    if proposal.get('state') == 'BLOCKED_BY_MISSING_INFO':
        raise ApiError(422, 'COPILOT_OUTPUT_UNSUPPORTED', '当前操作缺少可用提案结构')


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}/copilot')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @router.get('/catalog')
    def catalog(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with connection(settings) as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
        return {'data': {'items': [{'id': key, **value.__dict__} for key, value in CATALOG.items()]}}

    @router.get('/targets')
    def targets(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with connection(settings) as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
            row = conn.execute('''SELECT d.head_version_id,d.revision,v.ast,v.content_hash FROM document d
                JOIN document_version v ON v.id=d.head_version_id AND v.document_id=d.id
                WHERE d.id=%s AND d.workspace_id=%s''', (document_id, workspace_id)).fetchone()
            if not row or content_hash(row['ast']) != row['content_hash']:
                raise ApiError(503, 'COPILOT_INTEGRITY', '正文校验失败')
            sections = [{'id': section['id'], 'title': section['title'],
                         'hash': sha256(canonical(section)).hexdigest(),
                         'blocks': [{'id': block['id'], 'type': block['type'],
                                     'hash': sha256(canonical(block)).hexdigest()}
                                    for block in section['blocks']]}
                        for section in row['ast']['document']['sections']]
            return {'data': {'document_version_id': row['head_version_id'],
                             'document_revision': row['revision'], 'sections': sections}}

    @router.post('/execute')
    def execute(workspace_id: UUID, document_id: UUID, command: Command, response: Response,
                background: BackgroundTasks, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with connection(settings) as conn:
            facts, _ = editable_document(conn, current.subject, workspace_id, document_id)
            row = conn.execute('''SELECT v.ast,v.content_hash FROM document d JOIN document_version v
                ON v.id=d.head_version_id AND v.document_id=d.id
                WHERE d.id=%s AND d.workspace_id=%s AND d.head_version_id=%s AND d.revision=%s''',
                (document_id, workspace_id, command.document_version_id, command.document_revision)).fetchone()
            if not row:
                raise ApiError(409, 'COPILOT_DOCUMENT_CHANGED', '文档版本已变化')
            if content_hash(row['ast']) != row['content_hash']:
                raise ApiError(503, 'COPILOT_INTEGRITY', '正文校验失败')
            config, target, digest = resolve(row['ast'], command.section_id, command.block_id,
                                             command.target_hash, command.operation)
            result(command.operation, target, digest, prompt=command.prompt)
            if command.operation == 'plantuml':
                raise ApiError(422, 'GRAPH_UNSUPPORTED', 'PlantUML 未配置受支持的安全转换')
            outline = read_outline(conn, current.subject, workspace_id, document_id)
            if outline['state'] != 'OUTLINE_READY' or str(command.section_id) not in {s['id'] for s in outline['snapshot']['sections']}:
                raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '大纲或章节已变化')
            source = conn.execute('''SELECT p.content_hash,j.document_revision,j.state FROM section_evidence_pack p
                JOIN section_evidence_job j ON j.id=p.job_id AND j.workspace_id=p.workspace_id
                WHERE p.id=%s AND p.job_id=%s AND p.workspace_id=%s AND p.document_id=%s
                AND p.section_id=%s AND p.document_version_id=%s AND p.outline_version_id=%s
                AND p.context_version_id=%s AND j.subject=%s AND j.actor_id=%s''',
                (command.pack_id, command.pack_job_id, workspace_id, document_id, command.section_id,
                 command.document_version_id, outline['version_id'], outline['context_version_id'], current.subject,
                  UUID(str(facts['actor_id'])))).fetchone()
            if not source or source['document_revision'] != command.document_revision or source['state'] != 'SUCCEEDED':
                raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '需要当前章节证据')
            auth = current_document(conn, current.subject, workspace_id, document_id,
                                    command.document_version_id, command.document_revision)
            pointer, policy = active(conn, workspace_id)
            if not policy or policy['provider'] != 'internal':
                raise ApiError(403, 'COPILOT_MODEL_UNAVAILABLE', '当前模型策略不允许')
            view = evidence(settings, pack_job({**source, 'subject': current.subject,
                'workspace_id': workspace_id, 'document_id': document_id, 'section_id': command.section_id,
                'document_version_id': command.document_version_id, 'document_revision': command.document_revision,
                'pack_id': command.pack_id, 'pack_job_id': command.pack_job_id,
                'pack_hash': source['content_hash'], 'actor_id': facts['actor_id'],
                'policy_epoch': list(auth.policy_epoch), 'policy_version_id': policy['id'],
                'policy_revision': pointer['revision']}, outline))
            if not usable_view(view):
                raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '当前证据不足或存在冲突')
            if any(item['classification'] > policy['max_classification'] for item in view['items']):
                raise ApiError(403, 'COPILOT_MODEL_UNAVAILABLE', '证据密级超出模型策略')
            if not any(item['ordinal'] <= 12 for item in view['items']):
                raise ApiError(409, 'COPILOT_EVIDENCE_CHANGED', '当前证据超出可引用范围')
            # Only current verified excerpts, not caller-asserted citations, enter the model input.
            text = canonical({'operation': command.operation, 'target': target, 'input': command.prompt,
                              'pack_id': str(command.pack_id), 'view_hash': view['view_hash'],
                              'target_hash': digest,
                               'output_contract': ({'operation': command.operation, 'target_hash': digest,
                                   'rows': 'bounded array of rows and text cells' if command.operation=='table' else None,
                                   'diagram': 'flowchart TD with plain nodes and arrows only' if command.operation=='mermaid' else None,
                                   'source_ref': 'number from sources', 'quote': 'exact source text'}
                                   if config.family=='structured' else {'operation': command.operation,
                                   'target_hash': digest, 'text': 'unverified proposal; human review required',
                                   'source_ref': 'number from sources', 'quote': 'exact source text'}),
                              'sources': [{'ref': item['ordinal'], 'text': item['excerpt'][:1500]}
                                          for item in view['items'] if item['ordinal'] <= 12]}).decode('utf-8')
            if len(text) > 32000:
                raise ApiError(422, 'COPILOT_INPUT_INVALID', '目标超过模型上下文上限')
            model = reserve(conn, current.subject, workspace_id, document_id,
                GenerateInput(request_key=str(command.request_key), document_version_id=str(command.document_version_id),
                    document_revision=command.document_revision, capability='structured_proposal', text=text),
                str(command.request_key), str(command.request_key).replace('-', ''))
            if model['policy_version_id'] != policy['id'] or model['policy_revision'] != pointer['revision']:
                raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '模型策略已变化')
            if tuple(model['policy_epoch']) != auth.policy_epoch or model['actor_id'] != UUID(auth.actor_id):
                raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '当前授权已变化')
            row = conn.execute('''INSERT INTO copilot_run(id,workspace_id,document_id,actor_id,subject,request_key,
                model_run_id,document_version_id,document_revision,section_id,block_id,operation,
                pack_job_id,pack_id,pack_hash,view_hash,target_hash,prompt_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (workspace_id,actor_id,request_key) DO NOTHING RETURNING *''',
                (uuid4(), workspace_id, document_id, model['actor_id'], current.subject, command.request_key,
                 model['id'], command.document_version_id, command.document_revision, command.section_id,
                 command.block_id, command.operation, command.pack_job_id, command.pack_id,
                  source['content_hash'], view['view_hash'], digest, sha256(command.prompt.encode()).hexdigest())).fetchone()
            if not row:
                row = conn.execute('''SELECT * FROM copilot_run WHERE workspace_id=%s AND actor_id=%s AND request_key=%s''',
                                   (workspace_id, model['actor_id'], command.request_key)).fetchone()
            if (not row or row['model_run_id'] != model['id'] or row['document_id'] != document_id
                    or row['subject'] != current.subject or row['actor_id'] != model['actor_id']
                    or row['operation'] != command.operation or row['section_id'] != command.section_id
                    or row['document_version_id'] != command.document_version_id
                    or row['document_revision'] != command.document_revision
                    or row['block_id'] != command.block_id or row['pack_id'] != command.pack_id
                    or row['pack_job_id'] != command.pack_job_id or row['pack_hash'] != source['content_hash']
                    or row['view_hash'] != view['view_hash']
                    or row['target_hash'] != digest
                    or row['prompt_hash'] != sha256(command.prompt.encode()).hexdigest()):
                raise ApiError(409, 'COPILOT_REQUEST_CONFLICT', '操作标识已用于其他内容')
        attest_run(settings, workspace_id, document_id, model['id'])
        if model['state'] == 'QUEUED':
            _schedule(settings, background, workspace_id, document_id, model['id'])
        return {'data': {'id': row['id'], 'model_run_id': model['id'], 'state': model['state'],
                'operation': command.operation, 'label': config.label, 'family': config.family,
                'document_version_id': command.document_version_id, 'document_revision': command.document_revision,
                'section_id': command.section_id, 'block_id': command.block_id, 'target_hash': digest}}

    @router.get('/runs/{run_id}')
    def observe(workspace_id: UUID, document_id: UUID, run_id: UUID, response: Response,
                current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with connection(settings) as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
            row = conn.execute('''SELECT c.*,m.state,m.stage,m.output,m.output_sha256,m.policy_version_id,
                m.policy_revision,m.policy_epoch,m.usage FROM copilot_run c JOIN model_generation_run m
                ON m.id=c.model_run_id AND m.workspace_id=c.workspace_id AND m.document_id=c.document_id
                AND m.actor_id=c.actor_id AND m.subject=c.subject
                WHERE c.id=%s AND c.workspace_id=%s AND c.document_id=%s AND c.subject=%s''',
                (run_id, workspace_id, document_id, current.subject)).fetchone()
            if not row:
                raise ApiError(404, 'COPILOT_RUN_NOT_FOUND', '操作不存在或不可访问')
            head = conn.execute('''SELECT v.ast,v.content_hash FROM document d JOIN document_version v
                ON v.id=d.head_version_id AND v.document_id=d.id WHERE d.id=%s AND d.workspace_id=%s
                AND d.head_version_id=%s AND d.revision=%s''',
                (document_id, workspace_id, row['document_version_id'], row['document_revision'])).fetchone()
            if not head or content_hash(head['ast']) != head['content_hash']:
                raise ApiError(409, 'COPILOT_DOCUMENT_CHANGED', '目标文档已变化')
            config, target, digest = resolve(head['ast'], row['section_id'], row['block_id'],
                                             row['target_hash'], row['operation'])
            payload = {'id': row['id'], 'model_run_id': row['model_run_id'], 'state': row['state'],
                       'stage': row['stage'], 'operation': row['operation'], 'family': config.family,
                       'target_hash': digest}
            if row['state'] == 'SUCCEEDED':
                auth = current_document(conn, current.subject, workspace_id, document_id,
                    row['document_version_id'], row['document_revision'])
                pointer, policy = active(conn, workspace_id)
                if (not policy or policy['provider'] != 'internal' or policy['id'] != row['policy_version_id']
                        or pointer['revision'] != row['policy_revision']
                        or tuple(row['policy_epoch']) != auth.policy_epoch or str(row['actor_id']) != auth.actor_id):
                    raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '模型策略或权限已变化')
                if not row['output'] or sha256(canonical(row['output'])).hexdigest() != row['output_sha256']:
                    raise ApiError(503, 'COPILOT_OUTPUT_INVALID', '模型输出校验失败')
                outline = read_outline(conn, current.subject, workspace_id, document_id)
                if outline['state'] != 'OUTLINE_READY' or str(row['section_id']) not in {s['id'] for s in outline['snapshot']['sections']}:
                    raise ApiError(409, 'COPILOT_SCOPE_CHANGED', '大纲已变化')
            else:
                outline = None
        if row['state'] == 'SUCCEEDED':
            view = evidence(settings, pack_job(row, outline))
            _validated_view(view, row, policy)
            try:
                output = json.loads(row['output']['proposal'])
                source_ref = output.get('source_ref') if isinstance(output, dict) else None
                source = next((dict(item, source_ref=source_ref) for item in view['items']
                    if type(source_ref) is int and item['ordinal'] == source_ref and source_ref <= 12), None)
                payload['response'] = (structured(row['operation'], target, digest, output, source)
                    if row['operation'] in ('table','mermaid') else interpret(row['operation'], target, digest, output, source))
            except (ValueError, TypeError, KeyError, ValidationError) as exc:
                raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '模型结果未通过结构校验') from exc
            payload['provenance'] = {'run_id': row['model_run_id'], 'pack_id': row['pack_id'],
                'pack_hash': row['pack_hash'], 'view_hash': row['view_hash'],
                'policy_version_id': row['policy_version_id'], 'usage': row['usage'],
                'output_sha256': row['output_sha256']}
        return {'data': payload}

    return router
