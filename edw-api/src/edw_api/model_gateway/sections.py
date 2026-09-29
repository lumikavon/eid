"""Fenced section proposals grounded in currently visible evidence."""
from hashlib import sha256
import json
from threading import Event, Thread
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..access.policy import AccessDenied
from ..db import connection
from ..documents.outline_repository import read_outline
from ..errors import ApiError
from ..knowledge.evidence import visible
from ..knowledge.evidence import pinned as evidence_pinned
from ..task_contract import canonical
from .policy import GenerateInput, PolicyDraft, decide, input_token_ceiling
from .repository import active, current_document
from .transport import generate


class SectionClaim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=1500)
    source_ref: int = Field(ge=1, le=12)


class SectionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    blocks: list[SectionClaim] = Field(min_length=1, max_length=12)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    missing: list[str] = Field(default_factory=list, max_length=12)


def decode_section(response):
    try:
        return SectionResponse.model_validate(json.loads(response)).model_dump()
    except (ValueError, ValidationError) as exc:
        raise ApiError(422, 'MODEL_OUTPUT_INVALID', '章节结构化响应无效') from exc


def _safe_notes(output):
    notes = output['assumptions'] + output['missing']
    if any(not item.strip() or len(item) > 256 for item in notes):
        raise ApiError(422, 'MODEL_OUTPUT_INVALID', '模型待确认信息无效')
    return output['assumptions'], output['missing']


def status(job):
    return {key: job[key] for key in ('id', 'section_id', 'state', 'stage', 'attempt', 'error_code',
                                       'missing', 'proposal_hash', 'updated_at')}


def pinned(conn, job):
    auth = current_document(conn, job['subject'], job['workspace_id'], job['document_id'],
                            job['document_version_id'], job['document_revision'])
    outline = read_outline(conn, job['subject'], job['workspace_id'], job['document_id'])
    if (outline['version_id'] != job['outline_version_id'] or outline['context_version_id'] != job['context_version_id']
            or tuple(job['policy_epoch']) != auth.policy_epoch or str(job['actor_id']) != auth.actor_id):
        raise ApiError(409, 'SECTION_SCOPE_CHANGED', '大纲或授权已变化')
    section = next((item for item in outline['snapshot']['sections'] if item['id'] == str(job['section_id'])), None)
    if section is None:
        raise ApiError(409, 'SECTION_SCOPE_CHANGED', '章节已变化')
    pointer, row = active(conn, job['workspace_id'])
    if (not row or row['id'] != job['policy_version_id'] or pointer['revision'] != job['policy_revision']):
        raise ApiError(409, 'SECTION_POLICY_CHANGED', '模型策略已变化')
    return section, auth, PolicyDraft.model_validate({field: row[field] for field in PolicyDraft.model_fields})


def live_scope(conn, job):
    section, auth, policy = pinned(conn, job)
    evidence_pinned(conn, job['subject'], job['workspace_id'], job['document_id'], job['section_id'],
                    job['outline_version_id'], job['context_version_id'], job['document_version_id'])
    return section, auth, policy


def evidence(settings, job):
    with connection(settings) as conn:
        pack = conn.execute('''SELECT id,content_hash FROM section_evidence_pack
            WHERE id=%s AND job_id=%s AND workspace_id=%s AND document_id=%s AND section_id=%s
            AND outline_version_id=%s AND context_version_id=%s AND document_version_id=%s''',
            (job['pack_id'], job['pack_job_id'], job['workspace_id'], job['document_id'], job['section_id'],
             job['outline_version_id'], job['context_version_id'], job['document_version_id'])).fetchone()
        live_scope(conn, job)
        if not pack or pack['content_hash'] != job['pack_hash']:
            raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '章节证据已变化')
        source_job = conn.execute('SELECT * FROM section_evidence_job WHERE id=%s AND state=\'SUCCEEDED\'',
                                  (job['pack_job_id'],)).fetchone()
        if not source_job or source_job['document_revision'] != job['document_revision']:
            raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '章节证据已变化')
    view = visible(settings, source_job)
    if not view or str(job['pack_id']) != view['id'] or view['snapshot_hash'] != job['pack_hash']:
        raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '章节证据已变化')
    return view


def _input(section, view):
    items = view['items'][:12]
    gaps = sorted(set(view['gaps']))
    if not items or view['conflict_ids'] or view['version_conflicts']:
        return None, sorted(set(gaps + (['NO_CURRENT_SUPPORT'] if not items else ['SOURCE_CONFLICT_REQUIRES_REVIEW'])))
    # Only verified excerpts are supplied. Model text cannot grant access or select a source.
    data = {'section': section['title'], 'sources': [
        {'ref': index, 'text': item['excerpt'][:1500]} for index, item in enumerate(items, 1)]}
    text = canonical(data).decode('utf-8')
    return (text if len(text) <= 32000 else None), (gaps if len(text) <= 32000 else ['CONTEXT_LIMIT'])


def supported_claims(blocks, items):
    claims = []
    for block in blocks:
        index = block['source_ref']
        if index > min(len(items), 12):
            return []
        item = items[index - 1]
        if block['text'].strip() != item['excerpt'][:1500].strip():
            return []
        claims.append({'text': block['text'], 'source_ref': index, 'source_id': item['source_id'],
                       'locator': item['locator'], 'version': item['version']})
    return claims


def cross_section_checks(proposals):
    conflicts = set()
    versions = {}
    facts = {}
    for proposal in proposals:
        for claim in proposal['claims']:
            source = claim['source_id']
            prior_version = versions.setdefault(source, claim['version'])
            if prior_version != claim['version']:
                conflicts.add(source)
            key = source, claim['locator']
            prior_text = facts.setdefault(key, claim['text'])
            if prior_text != claim['text']:
                conflicts.add(source)
    return sorted(conflicts)


def run(settings, workspace_id, document_id, job_id):
    fence = uuid4()
    stop = Event()
    heartbeat = None
    with connection(settings) as conn:
        job = conn.execute('''UPDATE section_generation_job SET state='RUNNING',stage='retrieving',
            attempt=attempt+1,fence=%s,lease_until=clock_timestamp()+interval '90 seconds',
            next_retry_at=NULL,next_wake_at=clock_timestamp()+interval '90 seconds',updated_at=clock_timestamp()
            WHERE id=%s AND workspace_id=%s AND document_id=%s AND attempt<3 AND
            (state='QUEUED' OR (state='RETRY_WAIT' AND next_retry_at<=clock_timestamp()) OR
            (state='RUNNING' AND lease_until<clock_timestamp())) RETURNING *''',
            (fence, job_id, workspace_id, document_id)).fetchone()
    if not job:
        return
    def renew():
        while not stop.wait(15):
            try:
                with connection(settings) as conn:
                    updated = conn.execute('''UPDATE section_generation_job SET lease_until=clock_timestamp()+interval '90 seconds'
                        WHERE id=%s AND fence=%s AND state='RUNNING' AND lease_until>clock_timestamp() RETURNING id''',
                        (job_id, fence)).fetchone()
                    if not updated:
                        return
            except Exception:
                return
    heartbeat = Thread(target=renew, daemon=True)
    heartbeat.start()
    try:
        with connection(settings) as conn:
            section, auth, policy = live_scope(conn, job)
            context = conn.execute('SELECT snapshot FROM project_context_version WHERE id=%s AND document_id=%s',
                                   (job['context_version_id'], document_id)).fetchone()
            if not context:
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '项目上下文已变化')
        view = evidence(settings, job)
        text, gaps = _input(section, view)
        if text:
            context_text = canonical({'intent': context['snapshot'].get('intent')})
            text += '\n' + context_text.decode('utf-8')
            if len(text) > 32000:
                text, gaps = None, ['CONTEXT_LIMIT']
        with connection(settings) as conn:
            claimed = conn.execute("UPDATE section_generation_job SET stage='evidence',updated_at=clock_timestamp() WHERE id=%s AND fence=%s AND lease_until>clock_timestamp() RETURNING id", (job_id, fence)).fetchone()
            if not claimed:
                return
        if text is None:
            state, error, proposal = 'BLOCKED_BY_MISSING_INFO', 'SECTION_MISSING_SUPPORT', None
        else:
            command = GenerateInput(request_key=str(job['request_key']), document_version_id=str(job['document_version_id']),
                document_revision=job['document_revision'], capability='structured_proposal', text=text)
            if policy.provider != 'internal':
                raise ApiError(403, 'MODEL_SOURCE_UNVERIFIED', '证据外发尚未获准')
            decision = decide(policy, command, max(auth.classification,
                *(item['classification'] for item in view['items'])))
            estimate = (input_token_ceiling(decision.safe_input) + policy.max_output_tokens) * 2 * 3
            with connection(settings) as conn:
                conn.execute('SELECT workspace_id FROM model_policy_active WHERE workspace_id=%s FOR UPDATE',
                             (workspace_id,)).fetchone()
                prior = conn.execute('SELECT reserved_tokens FROM section_generation_job WHERE id=%s AND fence=%s',
                                     (job_id, fence)).fetchone()
                if not prior:
                    return
                if prior['reserved_tokens'] == 0:
                    already = conn.execute('''SELECT coalesce(sum(reserved_tokens),0) AS total FROM model_generation_run
                        WHERE workspace_id=%s AND created_at>=date_trunc('day',clock_timestamp())''',
                        (workspace_id,)).fetchone()['total']
                    sections = conn.execute('''SELECT coalesce(sum(reserved_tokens),0) AS total FROM section_generation_job
                        WHERE workspace_id=%s AND created_at>=date_trunc('day',clock_timestamp())''',
                        (workspace_id,)).fetchone()['total']
                    if sections + already + estimate > policy.daily_token_budget:
                        raise ApiError(429, 'MODEL_QUOTA_EXCEEDED', '模型额度不足')
                    conn.execute('''UPDATE section_generation_job SET reserved_tokens=%s
                        WHERE id=%s AND fence=%s AND reserved_tokens=0''', (estimate, job_id, fence))
                elif prior['reserved_tokens'] < estimate:
                    raise ApiError(409, 'SECTION_SCOPE_CHANGED', '任务额度已变化')
            with connection(settings) as conn:
                claimed = conn.execute("UPDATE section_generation_job SET stage='generating',updated_at=clock_timestamp() WHERE id=%s AND fence=%s AND lease_until>clock_timestamp() RETURNING id", (job_id, fence)).fetchone()
                if not claimed:
                    return
            output, usage, repairs = generate(settings, policy, decision)
            # A string response is never interpreted as claims or citations. A claim is
            # only emitted when it exactly matches a current excerpt, by indexed source.
            with connection(settings) as conn:
                claimed = conn.execute("UPDATE section_generation_job SET stage='validating',updated_at=clock_timestamp() WHERE id=%s AND fence=%s AND lease_until>clock_timestamp() RETURNING id", (job_id, fence)).fetchone()
                if not claimed:
                    return
            section_output = decode_section(output['proposal'])
            assumptions, missing = _safe_notes(section_output)
            claims = supported_claims(section_output['blocks'], view['items'])
            if not claims or assumptions or missing:
                state, error, proposal = 'BLOCKED_BY_MISSING_INFO', 'SECTION_UNSUPPORTED_OUTPUT', None
                gaps = sorted(set(gaps + missing + assumptions + (['UNVERIFIED_GENERATED_CLAIM'] if not claims else [])))
            else:
                proposal = {'schema_version': 1, 'section_id': str(job['section_id']),
                    'ast': [{'id': str(uuid4()), 'type': 'paragraph', 'content': {'text': block['text']}}
                            for block in section_output['blocks']],
                    'claims': claims, 'citations': claims,
                    'assumptions': assumptions, 'missing': sorted(set(gaps + missing)),
                    'provenance': {'pack_id': str(job['pack_id']), 'pack_hash': job['pack_hash'],
                        'policy_version_id': str(job['policy_version_id']), 'model_id': policy.model_id,
                        'prompt_ref': policy.prompt_ref, 'prompt_sha256': policy.prompt_sha256,
                        'usage': usage, 'repair_count': repairs}}
                state, error = 'SUCCEEDED', None
        # Reattest external sources outside the committing transaction.
        if evidence(settings, job)['view_hash'] != view['view_hash']:
            raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '证据权限已变化')
        with connection(settings) as conn:
            conn.execute('SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR SHARE', (workspace_id,)).fetchone()
            conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE', (document_id, workspace_id)).fetchone()
            current = conn.execute('SELECT * FROM section_generation_job WHERE id=%s FOR UPDATE', (job_id,)).fetchone()
            if not current or current['fence'] != fence or current['state'] != 'RUNNING' or not current['lease_until'] or current['lease_until'] <= conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']:
                return
            live_scope(conn, current)
            context_now = conn.execute('SELECT snapshot FROM project_context_version WHERE id=%s AND document_id=%s',
                (job['context_version_id'], document_id)).fetchone()
            if not context_now or context_now['snapshot'] != context['snapshot']:
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '项目上下文已变化')
            source = conn.execute('SELECT state,document_revision FROM section_evidence_job WHERE id=%s AND workspace_id=%s',
                                  (job['pack_job_id'], workspace_id)).fetchone()
            if not source or source['state'] != 'SUCCEEDED' or source['document_revision'] != job['document_revision']:
                raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '章节证据已变化')
            pack = conn.execute('SELECT content_hash FROM section_evidence_pack WHERE id=%s AND workspace_id=%s',
                                (job['pack_id'], workspace_id)).fetchone()
            if not pack or pack['content_hash'] != job['pack_hash']:
                raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '章节证据已变化')
            digest = sha256(canonical(proposal)).hexdigest() if proposal else None
            conn.execute('''UPDATE section_generation_job SET state=%s,stage=%s,error_code=%s,missing=%s,
                proposal=%s,proposal_hash=%s,fence=NULL,lease_until=NULL,updated_at=clock_timestamp()
                WHERE id=%s AND fence=%s''', (state, 'done' if proposal else 'blocked', error,
                Jsonb(gaps), Jsonb(proposal) if proposal else None, digest, job_id, fence))
    except Exception as exc:
        conflict = isinstance(exc, ApiError) and exc.status_code == 409
        blocked = isinstance(exc, AccessDenied) or isinstance(exc, ApiError) and exc.status_code in (403, 404, 422, 429)
        code = exc.code if isinstance(exc, ApiError) else 'SECTION_DEPENDENCY_UNAVAILABLE'
        try:
            with connection(settings) as conn:
                conn.execute('''UPDATE section_generation_job SET state=CASE WHEN %s THEN 'CONFLICT'
                WHEN %s THEN 'BLOCKED' WHEN attempt>=3 OR %s THEN 'FAILED' ELSE 'RETRY_WAIT' END,
                stage='failed',error_code=%s,
                next_retry_at=CASE WHEN NOT %s AND NOT %s AND attempt<3 AND NOT %s
                    THEN clock_timestamp()+interval '10 seconds' ELSE NULL END,
                next_wake_at=clock_timestamp()+interval '10 seconds',fence=NULL,lease_until=NULL,
                updated_at=clock_timestamp() WHERE id=%s AND fence=%s AND state='RUNNING' ''',
                    (conflict, blocked, isinstance(exc, ApiError) and not exc.retryable, code,
                     conflict, blocked, isinstance(exc, ApiError) and not exc.retryable, job_id, fence))
        except Exception:
            # The lease remains reclaimable when a terminal-state write fails.
            pass
    finally:
        stop.set()
        if heartbeat:
            heartbeat.join(timeout=2)


def assemble(outline, jobs):
    ordered = []
    for section in outline['snapshot']['sections']:
        job = next((row for row in jobs if str(row['section_id']) == section['id']), None)
        if (not job or job['state'] != 'SUCCEEDED' or not job['proposal']
                or job['proposal'].get('section_id') != section['id']
                or sha256(canonical(job['proposal'])).hexdigest() != job['proposal_hash']):
            raise ApiError(409, 'SECTION_ASSEMBLY_INCOMPLETE', '章节提案不完整')
        ordered.append(job['proposal'])
    if len(jobs) != len(ordered):
        raise ApiError(409, 'SECTION_ASSEMBLY_INCOMPLETE', '章节提案范围不匹配')
    return {'sections': ordered, 'conflicts': cross_section_checks(ordered), 'review_required': True}
