"""Durable section Pack jobs. The API owns authorization and final commits."""
from contextlib import contextmanager
import hashlib
import hmac
import time
from threading import Event, Thread
from uuid import UUID, uuid4
import logging

import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, BackgroundTasks, Depends, Response, Header

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from ..task_contract import SectionEvidenceInput
from .evidence import commit, pinned, prepare, visible

log = logging.getLogger(__name__)


def _status(job):
    return {'id': job['id'], 'state': job['state'], 'stage': job['stage'],
            'attempt': job['attempt'], 'error_code': job['error_code'],
            'updated_at': job['updated_at']}


def _run(settings, job_id, workspace_id):
    """Fenced attempt; no sensitive parameters in a broker message or a log."""
    fence = uuid4()
    stop = Event()
    heartbeat = None
    try:
        with connection(settings) as conn:
            job = conn.execute('''UPDATE section_evidence_job SET state='RUNNING',stage='planning',
                attempt=attempt+1,fence=%s,lease_until=clock_timestamp()+interval '120 seconds',
                next_retry_at=NULL,updated_at=clock_timestamp()
                WHERE id=%s AND workspace_id=%s AND attempt<3 AND
                (state='QUEUED' OR (state='RETRY_WAIT' AND next_retry_at<=clock_timestamp())
                OR (state='RUNNING' AND lease_until<clock_timestamp())) RETURNING *''',
                (fence, job_id, workspace_id)).fetchone()
            if not job:
                return
        def renew():
            while not stop.wait(25):
                try:
                    with connection(settings) as conn:
                        updated = conn.execute('''UPDATE section_evidence_job SET
                            lease_until=clock_timestamp()+interval '120 seconds'
                            WHERE id=%s AND workspace_id=%s AND fence=%s AND state='RUNNING'
                            AND lease_until>clock_timestamp() RETURNING id''',
                            (job_id, workspace_id, fence)).fetchone()
                        if not updated:
                            return
                except psycopg.Error:
                    # Never replace a stale fence; commit still checks the DB lease.
                    return
        heartbeat = Thread(target=renew, daemon=True)
        heartbeat.start()
        with connection(settings) as conn:
            conn.execute("UPDATE section_evidence_job SET stage='retrieving',updated_at=clock_timestamp() WHERE id=%s AND fence=%s", (job_id, fence))
        result = prepare(settings, job)
        with connection(settings) as conn:
            conn.execute("UPDATE section_evidence_job SET stage='verifying',updated_at=clock_timestamp() WHERE id=%s AND fence=%s", (job_id, fence))
        commit(settings, job, fence, result)
    except Exception as exc:
        # Never save a passage if any pinned prerequisite or authorization changed.
        blocked = isinstance(exc, AccessDenied) or isinstance(exc, ApiError) and not exc.retryable
        if blocked:
            try:
                with connection(settings) as conn:
                    conn.execute("UPDATE section_evidence_job SET state='BLOCKED',stage='blocked',error_code='PREREQUISITE_OR_ACCESS_CHANGED',fence=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE id=%s AND fence=%s", (job_id, fence))
            except psycopg.Error:
                pass
            log.warning('evidence_build_blocked error_type=%s', type(exc).__name__)
            return
        try:
            with connection(settings) as conn:
                conn.execute('''UPDATE section_evidence_job SET
                    state=CASE WHEN attempt>=3 THEN 'FAILED' ELSE 'RETRY_WAIT' END,
                    stage=CASE WHEN attempt>=3 THEN 'failed' ELSE 'retry_wait' END,
                    error_code=CASE WHEN attempt>=3 THEN 'ATTEMPTS_EXHAUSTED' ELSE 'DEPENDENCY_UNAVAILABLE' END,
                    next_retry_at=CASE WHEN attempt>=3 THEN NULL ELSE clock_timestamp()+interval '10 seconds' END,
                    fence=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE id=%s AND fence=%s''', (job_id, fence))
        except psycopg.Error:
            pass
        log.warning('evidence_build_retry error_type=%s', type(exc).__name__)
    finally:
        stop.set()
        if heartbeat is not None:
            heartbeat.join(timeout=2)


def _schedule(settings, background, job_id, workspace_id, document_id):
    if len(settings.evidence_wake_key) >= 32:
        from celery import Celery
        try:
            broker = Celery(broker=settings.rabbitmq_url)
            broker.send_task('eid.evidence.wake.v1', args=[str(workspace_id), str(document_id), str(job_id)],
                             queue='retrieval', expires=120, retry=False)
            return
        except Exception:
            # The persisted job can be retried from observation; never lose the identifier.
            pass
    background.add_task(_run, settings, job_id, workspace_id)


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}/evidence')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(404, 'EVIDENCE_NOT_FOUND', '章节证据不存在或不可访问') from exc
        except psycopg.Error as exc:
            raise ApiError(503, 'EVIDENCE_UNAVAILABLE', '章节证据暂不可用', retryable=True) from exc

    def load(conn, workspace_id, document_id, job_id, current):
        row = conn.execute('SELECT * FROM section_evidence_job WHERE workspace_id=%s AND document_id=%s AND id=%s',
                           (workspace_id, document_id, job_id)).fetchone()
        if not row:
            raise AccessDenied()
        section, outline, anchor, auth, metadata = pinned(conn, current.subject, workspace_id, document_id,
            row['section_id'], row['outline_version_id'], row['context_version_id'], row['document_version_id'])
        if str(row['actor_id']) != auth.actor_id or row['subject'] != current.subject or metadata['revision'] != row['document_revision']:
            raise AccessDenied()
        return row

    @router.post('/jobs')
    def request_pack(workspace_id: UUID, document_id: UUID, command: SectionEvidenceInput,
                     background: BackgroundTasks, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            _, outline, _, auth, metadata = pinned(conn, current.subject, workspace_id, document_id,
                command.section_id, command.outline_version_id, command.context_version_id, command.document_version_id)
            if metadata['revision'] != command.document_revision:
                raise ApiError(409, 'EVIDENCE_DOCUMENT_CHANGED', '正文已变化')
            row = conn.execute('''SELECT * FROM section_evidence_job WHERE workspace_id=%s AND actor_id=%s AND request_key=%s''',
                               (workspace_id, UUID(auth.actor_id), command.request_key)).fetchone()
            if not row:
                row = conn.execute('''INSERT INTO section_evidence_job(id,workspace_id,document_id,actor_id,subject,section_id,
                    outline_version_id,context_version_id,document_version_id,document_revision,policy_epoch,request_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (workspace_id,actor_id,request_key) DO NOTHING RETURNING *''',
                    (uuid4(), workspace_id, document_id, UUID(auth.actor_id), current.subject, command.section_id,
                     command.outline_version_id, command.context_version_id, command.document_version_id,
                     command.document_revision, Jsonb(list(auth.policy_epoch)), command.request_key)).fetchone()
                if not row:
                    row = conn.execute('''SELECT * FROM section_evidence_job
                        WHERE workspace_id=%s AND actor_id=%s AND request_key=%s''',
                        (workspace_id, UUID(auth.actor_id), command.request_key)).fetchone()
            if row['subject'] != current.subject:
                raise AccessDenied()
            if (row['document_id'], row['section_id'],  row['outline_version_id'], row['context_version_id'], row['document_version_id'], row['document_revision']) != (
                    document_id, command.section_id, command.outline_version_id, command.context_version_id, command.document_version_id, command.document_revision):
                raise ApiError(409, 'EVIDENCE_REQUEST_CONFLICT', '幂等键已用于其他章节或版本')
        if row['state'] == 'QUEUED':
            _schedule(settings, background, row['id'], workspace_id, document_id)
        return {'data': _status(row)}

    @router.get('/jobs/{job_id}')
    def job_status(workspace_id: UUID, document_id: UUID, job_id: UUID, background: BackgroundTasks,
                   response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            row = load(conn, workspace_id, document_id, job_id, current)
            db_now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            restart = (row['state'] == 'RETRY_WAIT' and row['next_retry_at'] is not None and row['next_retry_at'] <= db_now
                       or row['state'] == 'RUNNING' and row['lease_until'] is not None and row['lease_until'] < db_now)
            if row['state'] == 'QUEUED' and (db_now - row['updated_at']).total_seconds() >= 10:
                claimed = conn.execute('''UPDATE section_evidence_job SET updated_at=clock_timestamp()
                    WHERE id=%s AND state='QUEUED' AND updated_at=%s RETURNING id''',
                    (job_id, row['updated_at'])).fetchone()
                restart = bool(claimed)
            if restart and row['attempt'] >= 3:
                row = conn.execute("""UPDATE section_evidence_job SET state='FAILED',stage='failed',
                    error_code='ATTEMPTS_EXHAUSTED',fence=NULL,lease_until=NULL,next_retry_at=NULL,
                    updated_at=clock_timestamp() WHERE id=%s AND state=%s AND attempt>=3 RETURNING *""",
                    (job_id, row['state'])).fetchone()
                if row is None:
                    row = load(conn, workspace_id, document_id, job_id, current)
                restart = False
            # Old finished Pack is not exposed without checking live sources and pinned prerequisites.
            state = _status(row)
        if restart:
            _schedule(settings, background, job_id, workspace_id, document_id)
        if row['state'] == 'SUCCEEDED':
            try:
                state['pack'] = visible(settings, row)
            except AccessDenied as exc:
                raise ApiError(404, 'EVIDENCE_NOT_FOUND', '章节证据不存在或不可访问') from exc
        return {'data': state}

    @router.post('/jobs/{job_id}/wake', include_in_schema=False)
    def wake(workspace_id: UUID, document_id: UUID, job_id: UUID, background: BackgroundTasks,
             x_evidence_time: str = Header(default=''), x_evidence_mac: str = Header(default='')):
        # Broker messages contain identifiers only; worker cannot query excerpts or assume actor authority.
        try:
            timestamp = int(x_evidence_time)
        except ValueError:
            timestamp = 0
        message = f'{workspace_id}:{document_id}:{job_id}:{timestamp}'.encode('ascii')
        expected = hmac.new(settings.evidence_wake_key.encode(), message, hashlib.sha256).hexdigest()
        if (len(settings.evidence_wake_key) < 32 or abs(time.time()-timestamp) > 30
                or not hmac.compare_digest(expected, x_evidence_mac)):
            raise ApiError(404, 'EVIDENCE_NOT_FOUND', '任务不存在或不可访问')
        with database() as conn:
            row = conn.execute('SELECT id FROM section_evidence_job WHERE id=%s AND workspace_id=%s AND document_id=%s',
                               (job_id, workspace_id, document_id)).fetchone()
            if not row:
                raise AccessDenied()
        background.add_task(_run, settings, job_id, workspace_id)
        return {'data': {'accepted': True}}

    @router.get('/similar')
    def similar(workspace_id: UUID, document_id: UUID, section_id: UUID, outline_version_id: UUID,
                context_version_id: UUID, document_version_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            section, _, anchor, _, _ = pinned(conn, current.subject, workspace_id, document_id,
                section_id, outline_version_id, context_version_id, document_version_id)
            # Actual section-term overlap in current indexed attachment content, not fabricated recommendations.
            ids = conn.execute('''SELECT DISTINCT r.id,i.attachment_id FROM access_resource r
                JOIN attachment_search_index i ON i.document_id=r.id
                JOIN attachment a ON a.id=i.attachment_id AND a.sha256=i.source_sha256
                JOIN attachment_parse p ON p.attachment_id=a.id AND p.source_sha256=i.source_sha256
                    AND p.parser_version=i.parser_version AND p.state IN ('SUCCEEDED','PARTIAL')
                JOIN attachment_chunk c ON c.attachment_id=a.id AND c.page_number=i.page_number
                    AND c.ordinal=i.ordinal AND c.content_hash=i.content_hash
                WHERE r.workspace_id=%s AND r.project_id=%s AND r.id<>%s AND r.kind='document'
                    AND i.tokens @@ plainto_tsquery('simple',%s)
                ORDER BY r.id LIMIT 101''', (workspace_id, anchor['project_id'], document_id,
                                            section['title'])).fetchall()
            results = []
            for item in ids[:100]:
                try:
                    _, resource, auth = checked(conn, current.subject, workspace_id, 'resource:read', item['id'])
                    if resource['project_id'] != anchor['project_id'] or any(d['document_id'] == str(item['id']) for d in results):
                        continue
                    row = conn.execute('''SELECT d.head_version_id,a.classification FROM document d
                        JOIN attachment a ON a.document_id=d.id AND a.id=%s
                        WHERE d.id=%s AND d.workspace_id=%s''',
                                       (item['attachment_id'], item['id'], workspace_id)).fetchone()
                    if row and row['head_version_id'] and row['classification'] <= auth.classification:
                        results.append({'document_id': str(item['id']), 'version': str(row['head_version_id']),
                                        'locator': f'document:{item["id"]}', 'basis': 'section_keyword_overlap'})
                except AccessDenied:
                    continue
                if len(results) >= 5:
                    break
            return {'data': {'items': results, 'limited': True}}  # never reveal denied candidate counts

    return router
