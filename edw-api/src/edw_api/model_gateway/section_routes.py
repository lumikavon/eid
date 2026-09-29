"""Authorized submission and observation of section-scoped proposals."""
from contextlib import contextmanager
from hashlib import sha256
import hmac
import time
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..documents.outline_repository import read_outline
from ..errors import ApiError
from ..knowledge.evidence import visible
from ..task_contract import canonical
from .repository import active, current_document
from .sections import assemble, evidence, live_scope, run, status


class SectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: UUID
    section_id: UUID
    document_version_id: UUID
    document_revision: int = Field(ge=1, le=9007199254740991)
    pack_job_id: UUID
    pack_id: UUID


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}/generation')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(404, 'SECTION_NOT_FOUND', '章节任务不存在或不可访问') from exc
        except psycopg.Error as exc:
            raise ApiError(503, 'SECTION_STORAGE_UNAVAILABLE', '章节任务存储不可用', retryable=True) from exc

    def load(conn, workspace_id, document_id, job_id, subject):
        row = conn.execute('SELECT * FROM section_generation_job WHERE id=%s AND workspace_id=%s AND document_id=%s',
                           (job_id, workspace_id, document_id)).fetchone()
        if not row or row['subject'] != subject:
            raise AccessDenied()
        live_scope(conn, row)
        return row

    def schedule(background, workspace_id, document_id, job_id):
        if len(settings.model_wake_key) >= 32:
            from celery import Celery
            try:
                Celery(broker=settings.rabbitmq_url).send_task('eid.section.wake.v1',
                    args=[str(workspace_id), str(document_id), str(job_id)],
                    queue='generation', expires=120, retry=False, ignore_result=True)
                return
            except Exception:
                pass
        background.add_task(run, settings, workspace_id, document_id, job_id)

    @router.get('/scope')
    def scope(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            outline = read_outline(conn, current.subject, workspace_id, document_id)
            if outline['state'] != 'OUTLINE_READY':
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '大纲尚未确认')
            current_document(conn, current.subject, workspace_id, document_id,
                             outline['document_version_id'], outline['document_revision'])
            return {'data': {'sections': outline['snapshot']['sections'],
                'document_version_id': outline['document_version_id'],
                'document_revision': outline['document_revision']}}

    @router.post('/sections', status_code=202)
    def submit(workspace_id: UUID, document_id: UUID, command: SectionRequest, background: BackgroundTasks,
               response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            auth = current_document(conn, current.subject, workspace_id, document_id,
                                    command.document_version_id, command.document_revision)
            outline = read_outline(conn, current.subject, workspace_id, document_id)
            if outline['state'] != 'OUTLINE_READY' or command.section_id not in [UUID(s['id']) for s in outline['snapshot']['sections']]:
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '章节不属于当前确认大纲')
            pointer, policy = active(conn, workspace_id)
            if not policy or policy['provider'] != 'internal':
                raise ApiError(403, 'SECTION_MODEL_UNAVAILABLE', '当前章节模型未配置或不允许')
            pack = conn.execute('''SELECT p.content_hash,j.state,j.document_revision FROM section_evidence_pack p
                JOIN section_evidence_job j ON j.id=p.job_id AND j.workspace_id=p.workspace_id
                WHERE p.id=%s AND p.job_id=%s AND p.workspace_id=%s AND p.document_id=%s AND p.section_id=%s
                AND p.outline_version_id=%s AND p.context_version_id=%s AND p.document_version_id=%s
                AND j.actor_id=%s AND j.subject=%s''',
                (command.pack_id, command.pack_job_id, workspace_id, document_id, command.section_id,
                 outline['version_id'], outline['context_version_id'], command.document_version_id,
                 UUID(auth.actor_id), current.subject)).fetchone()
            if not pack or pack['state'] != 'SUCCEEDED' or pack['document_revision'] != command.document_revision:
                raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '请先取得当前章节证据')
            row = conn.execute('''INSERT INTO section_generation_job(id,workspace_id,document_id,actor_id,subject,
                request_key,section_id,outline_version_id,context_version_id,document_version_id,document_revision,
                pack_job_id,pack_id,pack_hash,policy_version_id,policy_revision,policy_epoch)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (workspace_id,actor_id,request_key) DO NOTHING RETURNING *''',
                (uuid4(), workspace_id, document_id, UUID(auth.actor_id), current.subject, command.request_key,
                 command.section_id, outline['version_id'], outline['context_version_id'],
                 command.document_version_id, command.document_revision, command.pack_job_id, command.pack_id,
                 pack['content_hash'], policy['id'], pointer['revision'], Jsonb(list(auth.policy_epoch)))).fetchone()
            if not row:
                row = conn.execute('''SELECT * FROM section_generation_job WHERE workspace_id=%s AND actor_id=%s
                    AND request_key=%s''', (workspace_id, UUID(auth.actor_id), command.request_key)).fetchone()
            if (not row or row['subject'] != current.subject or row['document_id'] != document_id
                    or row['section_id'] != command.section_id or row['document_version_id'] != command.document_version_id
                    or row['document_revision'] != command.document_revision or row['pack_id'] != command.pack_id
                    or row['pack_job_id'] != command.pack_job_id or row['pack_hash'] != pack['content_hash']
                    or row['outline_version_id'] != outline['version_id']
                    or row['context_version_id'] != outline['context_version_id']
                    or row['policy_version_id'] != policy['id']
                    or row['policy_revision'] != pointer['revision'] or tuple(row['policy_epoch']) != auth.policy_epoch):
                raise ApiError(409, 'SECTION_REQUEST_CONFLICT', '请求标识已用于其他输入')
            payload = status(row)
        # Verify current source visibility before returning a runnable task. A denied source
        # cannot be transformed into model context by simply knowing a Pack identifier.
        evidence(settings, row)
        if row['state'] == 'QUEUED':
            schedule(background, workspace_id, document_id, row['id'])
        return {'data': payload}

    @router.get('/sections/{section_id}/inputs')
    def inputs(workspace_id: UUID, document_id: UUID, section_id: UUID, response: Response,
               current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            outline = read_outline(conn, current.subject, workspace_id, document_id)
            if outline['state'] != 'OUTLINE_READY' or str(section_id) not in {s['id'] for s in outline['snapshot']['sections']}:
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '章节尚未确认')
            auth = current_document(conn, current.subject, workspace_id, document_id,
                                    outline['document_version_id'], outline['document_revision'])
            pack = conn.execute('''SELECT p.id,p.job_id FROM section_evidence_pack p JOIN section_evidence_job j
                ON j.id=p.job_id AND j.workspace_id=p.workspace_id WHERE p.workspace_id=%s AND p.document_id=%s
                AND p.section_id=%s AND p.outline_version_id=%s AND p.context_version_id=%s
                AND p.document_version_id=%s AND j.document_revision=%s AND j.subject=%s
                AND j.actor_id=%s AND j.state='SUCCEEDED'
                ORDER BY j.updated_at DESC LIMIT 1''', (workspace_id, document_id, section_id,
                outline['version_id'], outline['context_version_id'], outline['document_version_id'],
                outline['document_revision'], current.subject, UUID(auth.actor_id))).fetchone()
            payload = {'section_id': section_id, 'document_version_id': outline['document_version_id'],
                'document_revision': outline['document_revision'], 'pack_id': pack['id'] if pack else None,
                'pack_job_id': pack['job_id'] if pack else None}
        if pack:
            with database() as conn:
                source = conn.execute('SELECT * FROM section_evidence_job WHERE id=%s AND workspace_id=%s',
                                      (pack['job_id'], workspace_id)).fetchone()
            view = visible(settings, source)
            payload['gaps'] = view['gaps'] if view else ['NO_CURRENT_SUPPORT']
            if view and not view['items']:
                payload['gaps'] = sorted(set(payload['gaps'] + ['NO_CURRENT_SUPPORT']))
        else:
            payload['gaps'] = ['EVIDENCE_PACK_REQUIRED']
        return {'data': payload}

    @router.get('/sections/{job_id}')
    def observe(workspace_id: UUID, document_id: UUID, job_id: UUID, background: BackgroundTasks,
                response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            row = load(conn, workspace_id, document_id, job_id, current.subject)
            now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            restart = (row['state'] == 'RETRY_WAIT' and row['next_retry_at'] and row['next_retry_at'] <= now
                       or row['state'] == 'RUNNING' and row['lease_until'] and row['lease_until'] < now)
            payload = status(row)
        if row['state'] == 'SUCCEEDED':
            view = evidence(settings, row)
            if not row['proposal'] or row['proposal'].get('section_id') != str(row['section_id']) or sha256(canonical(row['proposal'])).hexdigest() != row['proposal_hash']:
                raise ApiError(503, 'SECTION_PROPOSAL_INTEGRITY', '提案完整性校验失败')
            if view['id'] != str(row['pack_id']):
                raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '证据已变化')
            for claim in row['proposal']['claims']:
                if not any(item['source_id'] == claim['source_id'] and item['version'] == claim['version']
                           and item['locator'] == claim['locator'] and item['excerpt'][:1500].strip() == claim['text'].strip()
                           for item in view['items']):
                    raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '引用证据已变化')
            payload['proposal'] = row['proposal']
            with database() as conn:
                load(conn, workspace_id, document_id, job_id, current.subject)
        if restart:
            schedule(background, workspace_id, document_id, job_id)
        return {'data': payload}

    @router.get('/jobs')
    def jobs(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            outline = read_outline(conn, current.subject, workspace_id, document_id)
            if outline['state'] != 'OUTLINE_READY':
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '大纲尚未确认')
            auth = current_document(conn, current.subject, workspace_id, document_id,
                                    outline['document_version_id'], outline['document_revision'])
            rows = conn.execute('''SELECT * FROM section_generation_job WHERE workspace_id=%s AND document_id=%s
                AND actor_id=%s AND subject=%s AND outline_version_id=%s AND document_version_id=%s
                AND document_revision=%s ORDER BY updated_at DESC LIMIT 30''',
                (workspace_id, document_id, UUID(auth.actor_id), current.subject, outline['version_id'],
                 outline['document_version_id'], outline['document_revision'])).fetchall()
            return {'data': {'items': [status(row) for row in rows]}}

    @router.post('/sections/{job_id}/cancel')
    def cancel(workspace_id: UUID, document_id: UUID, job_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            load(conn, workspace_id, document_id, job_id, current.subject)
            row = conn.execute('''UPDATE section_generation_job SET state='CANCELLED',stage='cancelled',
                fence=NULL,lease_until=NULL,next_retry_at=NULL,proposal=NULL,proposal_hash=NULL,
                updated_at=clock_timestamp() WHERE id=%s AND state IN ('QUEUED','RUNNING','RETRY_WAIT') RETURNING *''',
                (job_id,)).fetchone()
            if not row:
                row = load(conn, workspace_id, document_id, job_id, current.subject)
            return {'data': status(row)}

    @router.get('/assembly')
    def assembly(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            outline = read_outline(conn, current.subject, workspace_id, document_id)
            if outline['state'] != 'OUTLINE_READY':
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '大纲尚未确认')
            rows = conn.execute('''SELECT * FROM section_generation_job WHERE workspace_id=%s AND document_id=%s
                AND subject=%s AND outline_version_id=%s AND document_version_id=%s AND document_revision=%s
                AND state='SUCCEEDED' ORDER BY updated_at DESC LIMIT 64''', (workspace_id, document_id,
                current.subject, outline['version_id'], outline['document_version_id'], outline['document_revision'])).fetchall()
            selected = []
            for section in outline['snapshot']['sections']:
                row = next((item for item in rows if str(item['section_id']) == section['id']), None)
                if not row:
                    raise ApiError(409, 'SECTION_ASSEMBLY_INCOMPLETE', '章节提案不完整')
                live_scope(conn, row)
                selected.append(row)
        for row in selected:
            view = evidence(settings, row)
            for claim in row['proposal']['claims']:
                if not any(item['source_id'] == claim['source_id'] and item['version'] == claim['version']
                           and item['locator'] == claim['locator'] and item['excerpt'][:1500].strip() == claim['text'].strip()
                           for item in view['items']):
                    raise ApiError(409, 'SECTION_EVIDENCE_CHANGED', '引用证据已变化')
        with database() as conn:
            latest = read_outline(conn, current.subject, workspace_id, document_id)
            if latest['state'] != 'OUTLINE_READY' or latest['version_id'] != outline['version_id']:
                raise ApiError(409, 'SECTION_SCOPE_CHANGED', '大纲已变化')
            for row in selected:
                live_scope(conn, row)
        return {'data': assemble(outline, selected)}

    @router.post('/sections/{job_id}/wake', include_in_schema=False)
    def wake(workspace_id: UUID, document_id: UUID, job_id: UUID, background: BackgroundTasks,
             x_model_time: str = Header(default=''), x_model_mac: str = Header(default='')):
        try:
            timestamp = int(x_model_time)
        except ValueError:
            timestamp = 0
        message = f'{workspace_id}:{document_id}:{job_id}:{timestamp}'.encode('ascii')
        expected = hmac.new(settings.model_wake_key.encode(), message, sha256).hexdigest()
        if len(settings.model_wake_key) < 32 or abs(time.time() - timestamp) > 30 or not hmac.compare_digest(expected, x_model_mac):
            raise ApiError(404, 'SECTION_NOT_FOUND', '章节任务不存在或不可访问')
        with database() as conn:
            if not conn.execute('SELECT id FROM section_generation_job WHERE id=%s AND workspace_id=%s AND document_id=%s',
                                (job_id, workspace_id, document_id)).fetchone():
                raise AccessDenied()
        background.add_task(run, settings, workspace_id, document_id, job_id)
        return {'data': {'accepted': True}}

    return router
