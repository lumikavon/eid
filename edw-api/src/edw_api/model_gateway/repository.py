"""Current-policy management and fenced generation persistence."""
from hashlib import sha256
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..documents.outline_repository import read_outline
from ..errors import ApiError
from .policy import GenerateInput, PolicyDraft, PROMPT_HASH, decide, input_token_ceiling


def admin(conn, subject, workspace_id, *, exclusive=False):
    facts, _, auth = checked(conn, subject, workspace_id, 'membership:manage', exclusive=exclusive)
    if 'system_admin' not in facts['roles']:
        raise AccessDenied()
    return facts, auth


def audit(conn, actor, workspace_id, target, action, before, after, request_id, trace_id):
    # No secret, prompt, input or output is ever sent to the ordinary access audit.
    conn.execute('''INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,
        after_policy,request_id,trace_id,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())''',
        (uuid4(), workspace_id, actor, target, action, Jsonb(before), Jsonb(after), request_id, trace_id))


def public(row):
    if row is None:
        return None
    return {key: row[key] for key in ('id', 'workspace_id', 'version', 'provider', 'model_id',
        'prompt_ref', 'prompt_sha256', 'capabilities', 'max_classification', 'max_context_chars',
        'max_output_tokens', 'daily_token_budget', 'max_cost_micros', 'timeout_seconds',
        'redact_rules', 'external_l2_exception', 'created_at')}


def active(conn, workspace_id):
    pointer = conn.execute('SELECT * FROM model_policy_active WHERE workspace_id=%s', (workspace_id,)).fetchone()
    row = None
    if pointer and pointer['version_id']:
        row = conn.execute('SELECT * FROM model_policy_version WHERE workspace_id=%s AND id=%s',
                           (workspace_id, pointer['version_id'])).fetchone()
    return pointer, row


def create_version(conn, subject, workspace_id, draft: PolicyDraft, request_id, trace_id):
    facts, _ = admin(conn, subject, workspace_id, exclusive=True)
    if draft.prompt_sha256 != PROMPT_HASH:
        raise ApiError(422, 'MODEL_PROMPT_UNAPPROVED', 'Prompt 版本未获批准')
    conn.execute('INSERT INTO model_policy_active(workspace_id) VALUES (%s) ON CONFLICT DO NOTHING', (workspace_id,))
    conn.execute('SELECT * FROM model_policy_active WHERE workspace_id=%s FOR UPDATE', (workspace_id,)).fetchone()
    version = conn.execute('SELECT coalesce(max(version),0)+1 AS next FROM model_policy_version WHERE workspace_id=%s',
                           (workspace_id,)).fetchone()['next']
    row = conn.execute('''INSERT INTO model_policy_version(id,workspace_id,version,created_by,provider,model_id,
        prompt_ref,prompt_sha256,capabilities,max_classification,max_context_chars,max_output_tokens,
        daily_token_budget,max_cost_micros,timeout_seconds,redact_rules,external_l2_exception)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (uuid4(), workspace_id, version, facts['actor_id'], draft.provider, draft.model_id,
         draft.prompt_ref, draft.prompt_sha256, Jsonb(draft.capabilities), draft.max_classification,
         draft.max_context_chars, draft.max_output_tokens, draft.daily_token_budget,
         draft.max_cost_micros, draft.timeout_seconds, Jsonb(draft.redact_rules),
         draft.external_l2_exception)).fetchone()
    audit(conn, facts['actor_id'], workspace_id, row['id'], 'model:version:create', {},
          {'version': version}, request_id, trace_id)
    return public(row)


def activate(conn, subject, workspace_id, version_id, expected_revision, request_id, trace_id):
    facts, _ = admin(conn, subject, workspace_id, exclusive=True)
    conn.execute('INSERT INTO model_policy_active(workspace_id) VALUES (%s) ON CONFLICT DO NOTHING', (workspace_id,))
    pointer = conn.execute('SELECT * FROM model_policy_active WHERE workspace_id=%s FOR UPDATE',
                           (workspace_id,)).fetchone()
    if pointer['revision'] != expected_revision:
        raise ApiError(409, 'MODEL_POLICY_CHANGED', '模型策略版本已变化')
    row = conn.execute('SELECT * FROM model_policy_version WHERE workspace_id=%s AND id=%s',
                       (workspace_id, version_id)).fetchone() if version_id else None
    if row:
        PolicyDraft.model_validate({field: row[field] for field in PolicyDraft.model_fields})
        if row['prompt_sha256'] != PROMPT_HASH:
            raise ApiError(422, 'MODEL_PROMPT_UNAPPROVED', 'Prompt 版本未获批准')
    if version_id and not row:
        raise ApiError(404, 'MODEL_POLICY_NOT_FOUND', '模型策略版本不存在')
    conn.execute('UPDATE model_policy_active SET version_id=%s,revision=revision+1 WHERE workspace_id=%s',
                 (version_id, workspace_id))
    audit(conn, facts['actor_id'], workspace_id, version_id or workspace_id, 'model:policy:activate',
          {'version_id': str(pointer['version_id']) if pointer['version_id'] else None},
          {'version_id': str(version_id) if version_id else None}, request_id, trace_id)
    return {'revision': expected_revision + 1, 'active': public(row)}


def current_document(conn, subject, workspace_id, document_id, version, revision):
    _, resource, auth = checked(conn, subject, workspace_id, 'document:edit', document_id)
    if resource['kind'] != 'document':
        raise AccessDenied()
    doc = conn.execute('SELECT head_version_id,revision FROM document WHERE id=%s AND workspace_id=%s FOR SHARE',
                       (document_id, workspace_id)).fetchone()
    if not doc or doc['head_version_id'] != version or doc['revision'] != revision:
        raise ApiError(409, 'MODEL_DOCUMENT_CHANGED', '文档版本已变化')
    outline = read_outline(conn, subject, workspace_id, document_id)
    if (outline['state'] != 'OUTLINE_READY' or outline['document_version_id'] != version
            or outline['document_revision'] != revision):
        raise ApiError(409, 'MODEL_SCOPE_UNCONFIRMED', '缺少已确认的当前文档范围')
    return auth


def reserve(conn, subject, workspace_id, document_id, command: GenerateInput, request_id, trace_id):
    auth = current_document(conn, subject, workspace_id, document_id,
                            UUID(command.document_version_id), command.document_revision)
    # Source-backed text must be assembled from current authorized sources by Story 4.2.
    # This entrypoint requires the ready, confirmed current outline but does not
    # attest arbitrary text to that outline; only the internal route is enabled.
    conn.execute('INSERT INTO model_policy_active(workspace_id) VALUES (%s) ON CONFLICT DO NOTHING', (workspace_id,))
    pointer = conn.execute('SELECT * FROM model_policy_active WHERE workspace_id=%s FOR UPDATE',
                           (workspace_id,)).fetchone()
    _, policy_row = active(conn, workspace_id)
    if not policy_row:
        raise ApiError(503, 'MODEL_DISABLED', '模型未启用')
    policy = PolicyDraft.model_validate({field: policy_row[field] for field in PolicyDraft.model_fields})
    # Story 4.1 accepts only direct document-scoped text. Evidence/source binding belongs to 4.2;
    # never trust classifications asserted by a caller as current source attestations.
    if command.source_classifications:
        raise ApiError(422, 'MODEL_SOURCE_UNVERIFIED', '来源尚未通过当前授权核验')
    if policy.provider == 'external':
        # Arbitrary caller text cannot be classified reliably by its document label.
        # Until a trusted source-attestation flow exists, no external egress is permitted.
        raise ApiError(403, 'MODEL_SOURCE_UNVERIFIED', '外发来源密级无法核验')
    decision = decide(policy, command, auth.classification)
    old = conn.execute('''SELECT * FROM model_generation_run WHERE workspace_id=%s AND actor_id=%s AND request_key=%s''',
                       (workspace_id, UUID(auth.actor_id), UUID(command.request_key))).fetchone()
    if old:
        if (old['document_id'] != document_id or old['document_version_id'] != UUID(command.document_version_id)
                or old['document_revision'] != command.document_revision or old['input_sha256'] != decision.input_sha256
                or old['policy_version_id'] != policy_row['id'] or old['policy_revision'] != pointer['revision']
                or old['capability'] != command.capability):
            raise ApiError(409, 'MODEL_REQUEST_CONFLICT', '请求标识已用于其他内容')
        if (old['safe_input_sha256'] != sha256(decision.safe_input.encode()).hexdigest()
                or old['input_char_count'] != len(decision.safe_input)):
            raise ApiError(409, 'MODEL_REQUEST_CONFLICT', '请求标识已用于其他内容')
        if old['subject'] != subject:
            raise AccessDenied()
        return old
    # Reserve each attempt's byte-based input ceiling and output cap, including
    # one repair per try; a failed run still consumes its conservative reservation.
    estimate = (input_token_ceiling(decision.safe_input) + policy.max_output_tokens) * 2 * 3
    budget = conn.execute('''SELECT coalesce(sum(reserved_tokens),0) AS reserved
        FROM model_generation_run WHERE workspace_id=%s
        AND created_at>=date_trunc('day',clock_timestamp())''', (workspace_id,)).fetchone()['reserved']
    if estimate + budget > policy.daily_token_budget:
        raise ApiError(429, 'MODEL_QUOTA_EXCEEDED', '模型额度不足')
    row = conn.execute('''INSERT INTO model_generation_run(id,workspace_id,document_id,actor_id,subject,
        request_key,policy_version_id,document_version_id,document_revision,policy_epoch,policy_revision,capability,
        input_sha256,safe_input_sha256,input_char_count,reserved_tokens,safe_input,route) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (uuid4(), workspace_id, document_id, UUID(auth.actor_id), subject, UUID(command.request_key),
         policy_row['id'], UUID(command.document_version_id), command.document_revision,
         Jsonb(list(auth.policy_epoch)), pointer['revision'], command.capability, decision.input_sha256,
         sha256(decision.safe_input.encode()).hexdigest(), len(decision.safe_input),
         estimate, decision.safe_input, decision.route)).fetchone()
    audit(conn, auth.actor_id, workspace_id, row['id'], 'model:run:reserved', {},
          {'route': decision.route, 'policy_version_id': str(policy_row['id']),
           'input_sha256': decision.input_sha256}, request_id, trace_id)
    return row


def status(row):
    return {key: row[key] for key in ('id','state','stage','attempt','repair_count','error_code','route',
                                      'policy_version_id','input_sha256','output_sha256','usage','updated_at')}
