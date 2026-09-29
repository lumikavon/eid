"""API-only authorization, model execution and final fenced commit."""
from contextlib import contextmanager
from hashlib import sha256
import hmac
import time
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from .policy import GenerateInput, PolicyDraft, decide
from .repository import active, activate, admin, audit, create_version, current_document, public, reserve, status
from .transport import endpoint_for, generate


class Switch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version_id: UUID | None
    expected_revision: int = Field(ge=0)


def _run(settings, workspace_id, document_id, run_id):
    fence = uuid4()
    try:
        with connection(settings) as conn:
            conn.execute('SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR SHARE',
                         (workspace_id,)).fetchone()
            job = conn.execute('''UPDATE model_generation_run SET state='RUNNING',stage='classifying',
                attempt=attempt+1,fence=%s,lease_until=clock_timestamp()+interval '90 seconds',
                next_retry_at=NULL,next_wake_at=clock_timestamp()+interval '90 seconds',
                updated_at=clock_timestamp() WHERE id=%s AND workspace_id=%s
                AND document_id=%s AND attempt<3 AND (state='QUEUED' OR
                (state='RETRY_WAIT' AND next_retry_at<=clock_timestamp()) OR
                (state='RUNNING' AND lease_until<clock_timestamp())) RETURNING *''',
                (fence, run_id, workspace_id, document_id)).fetchone()
            if not job:
                conn.execute('''UPDATE model_generation_run SET state='FAILED',stage='failed',
                    error_code='MODEL_RETRY_EXHAUSTED',safe_input=NULL,fence=NULL,lease_until=NULL,
                    next_retry_at=NULL,updated_at=clock_timestamp()
                    WHERE id=%s AND workspace_id=%s AND document_id=%s
                    AND state='RUNNING' AND attempt>=3 AND lease_until<clock_timestamp()''',
                    (run_id, workspace_id, document_id))
                return
        with connection(settings) as conn:
            auth = current_document(conn, job['subject'], workspace_id, document_id,
                                    job['document_version_id'], job['document_revision'])
            if tuple(job['policy_epoch']) != auth.policy_epoch or str(job['actor_id']) != auth.actor_id:
                raise AccessDenied()
            pointer, policy_row = active(conn, workspace_id)
            if (not policy_row or policy_row['id'] != job['policy_version_id']
                    or pointer['revision'] != job['policy_revision']):
                raise AccessDenied()
            policy = PolicyDraft.model_validate({field: policy_row[field] for field in PolicyDraft.model_fields})
            if (job['safe_input'] is None or len(job['safe_input']) != job['input_char_count']
                    or sha256(job['safe_input'].encode()).hexdigest() != job['safe_input_sha256']):
                raise AccessDenied()
            command = GenerateInput(request_key=str(job['request_key']),
                document_version_id=str(job['document_version_id']), document_revision=job['document_revision'],
                capability=job['capability'], text=job['safe_input'], source_classifications=[])
            if policy.provider == 'external':
                raise AccessDenied()
            decision = decide(policy, command, auth.classification)
            if decision.route != job['route']:
                raise AccessDenied()
            endpoint_for(settings, decision.route)
        from .copilot_routes import attest_run, fenced_run
        attest_run(settings, workspace_id, document_id, run_id)
        # Never keep a database transaction open during a model request.
        output, usage, repairs = generate(settings, policy, decision)
        attestation = attest_run(settings, workspace_id, document_id, run_id)
        with connection(settings) as conn:
            # Match access policy's workspace-first lock order before locking the head.
            conn.execute('SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR SHARE',
                         (workspace_id,)).fetchone()
            conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                         (document_id, workspace_id)).fetchone()
            row = conn.execute('''SELECT * FROM model_generation_run WHERE id=%s AND workspace_id=%s
                AND document_id=%s FOR UPDATE''', (run_id, workspace_id, document_id)).fetchone()
            if (not row or row['fence'] != fence or row['state'] != 'RUNNING'
                    or row['lease_until'] is None
                    or row['lease_until'] <= conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']):
                return
            auth = current_document(conn, row['subject'], workspace_id, document_id,
                                    row['document_version_id'], row['document_revision'])
            pointer, policy_row = active(conn, workspace_id)
            if (str(row['actor_id']) != auth.actor_id or tuple(row['policy_epoch']) != auth.policy_epoch
                    or not policy_row or policy_row['id'] != row['policy_version_id']
                    or pointer['revision'] != row['policy_revision']
                    or row['safe_input'] is None or len(row['safe_input']) != row['input_char_count']
                    or sha256(row['safe_input'].encode()).hexdigest() != row['safe_input_sha256']):
                raise AccessDenied()
            if row['route'] == 'external':
                raise AccessDenied()
            # Validate again against current policy immediately before persisting the proposal.
            command = GenerateInput(request_key=str(row['request_key']),
                document_version_id=str(row['document_version_id']), document_revision=row['document_revision'],
                capability=row['capability'], text=row['safe_input'], source_classifications=[])
            if decide(PolicyDraft.model_validate({field: policy_row[field] for field in PolicyDraft.model_fields}),
                      command, auth.classification).route != row['route']:
                raise AccessDenied()
            if attestation:
                fenced_run(conn, workspace_id, document_id, run_id, output, attestation[1])
            from ..task_contract import canonical
            digest = sha256(canonical(output)).hexdigest()
            audit(conn, row['actor_id'], workspace_id, run_id, 'model:run:completed', {},
                  {'policy_version_id': str(row['policy_version_id']), 'route': row['route'],
                   'input_sha256': row['input_sha256'], 'output_sha256': digest,
                   'usage': usage, 'repair_count': repairs}, str(run_id), str(fence))
            conn.execute('''UPDATE model_generation_run SET state='SUCCEEDED',stage='done',output=%s,
                output_sha256=%s,usage=%s,repair_count=%s,safe_input=NULL,fence=NULL,lease_until=NULL,
                updated_at=clock_timestamp() WHERE id=%s AND fence=%s''',
                (Jsonb(output), digest, Jsonb(usage), repairs, run_id, fence))
    except Exception as exc:
        blocked = isinstance(exc, AccessDenied) or (isinstance(exc, ApiError) and exc.code in {
            'MODEL_DOCUMENT_CHANGED', 'MODEL_SCOPE_UNCONFIRMED', 'MODEL_POLICY_DENIED',
            'MODEL_DLP_REJECTED', 'MODEL_CLASSIFICATION', 'MODEL_CONTEXT_LIMIT',
            'MODEL_ROUTE_MISSING', 'MODEL_REDACTION_REQUIRED', 'MODEL_REDACTION_INCOMPLETE',
            'COPILOT_SCOPE_CHANGED', 'COPILOT_EVIDENCE_CHANGED',
        })
        retryable = not isinstance(exc, ApiError) or exc.retryable
        try:
            with connection(settings) as conn:
                conn.execute('SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR SHARE',
                             (workspace_id,)).fetchone()
                row = conn.execute('SELECT attempt FROM model_generation_run WHERE id=%s AND fence=%s FOR UPDATE',
                                   (run_id, fence)).fetchone()
                if not row:
                    return
                state = ('BLOCKED' if blocked else 'FAILED' if row['attempt'] >= 3
                         or isinstance(exc, ApiError) and not exc.retryable else 'RETRY_WAIT')
                error = exc.code if isinstance(exc, ApiError) else 'ACCESS_OR_POLICY_CHANGED' if blocked else 'MODEL_DEPENDENCY_UNAVAILABLE'
                conn.execute('''UPDATE model_generation_run SET state=%s,stage=%s,error_code=%s,
                    repair_count=%s,
                    next_retry_at=CASE WHEN %s='RETRY_WAIT' THEN clock_timestamp()+interval '10 seconds' ELSE NULL END,
                    next_wake_at=clock_timestamp()+interval '10 seconds',
                    safe_input=CASE WHEN %s='RETRY_WAIT' THEN safe_input ELSE NULL END,
                    fence=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE id=%s AND fence=%s''',
                    (state, state.lower(), error,
                     exc.details.get('repair_count', 0) if isinstance(exc, ApiError) else 0,
                     state, state, run_id, fence))
        except psycopg.Error:
            # A failed state write leaves the fenced row reclaimable at lease expiry.
            pass


def _schedule(settings, background, workspace_id, document_id, run_id):
    if len(settings.model_wake_key) >= 32:
        from celery import Celery
        try:
            broker = Celery(broker=settings.rabbitmq_url)
            broker.send_task('eid.model.wake.v1', args=[str(workspace_id), str(document_id), str(run_id)],
                             queue='generation', expires=120, retry=False, ignore_result=True)
            return
        except Exception:
            # A lost broker notification never removes the persisted job.
            pass
    background.add_task(_run, settings, workspace_id, document_id, run_id)


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/model-governance')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(403, 'MODEL_ACCESS_DENIED', '模型操作未授权') from exc
        except psycopg.Error as exc:
            raise ApiError(503, 'MODEL_STORAGE_UNAVAILABLE', '模型存储不可用', retryable=True) from exc

    def no_store(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'

    @router.get('/policy')
    def policy_view(workspace_id: UUID, response: Response, current=Depends(actor)):
        no_store(response)
        with database() as conn:
            admin(conn, current.subject, workspace_id)
            pointer, row = active(conn, workspace_id)
            return {'data': {'revision': pointer['revision'] if pointer else 0, 'active': public(row)}}

    @router.post('/versions', status_code=201)
    def version(workspace_id: UUID, draft: PolicyDraft, request: Request, response: Response, current=Depends(actor)):
        no_store(response)
        with database() as conn:
            data = create_version(conn, current.subject, workspace_id, draft,
                                  request.state.request_id, request.state.trace_id)
            return {'data': data}

    @router.put('/policy')
    def switch(workspace_id: UUID, command: Switch, request: Request, response: Response, current=Depends(actor)):
        no_store(response)
        with database() as conn:
            return {'data': activate(conn, current.subject, workspace_id, command.version_id,
                command.expected_revision, request.state.request_id, request.state.trace_id)}

    @router.post('/documents/{document_id}/runs', status_code=202)
    def submit(workspace_id: UUID, document_id: UUID, command: GenerateInput, request: Request,
               response: Response, background: BackgroundTasks, current=Depends(actor)):
        no_store(response)
        with database() as conn:
            row = reserve(conn, current.subject, workspace_id, document_id, command,
                          request.state.request_id, request.state.trace_id)
        if row['state'] == 'QUEUED':
            _schedule(settings, background, workspace_id, document_id, row['id'])
        return {'data': status(row)}

    @router.get('/documents/{document_id}/runs/{run_id}')
    def observe(workspace_id: UUID, document_id: UUID, run_id: UUID, response: Response,
                background: BackgroundTasks, current=Depends(actor)):
        no_store(response)
        with database() as conn:
            row = conn.execute('SELECT * FROM model_generation_run WHERE id=%s AND workspace_id=%s AND document_id=%s',
                               (run_id, workspace_id, document_id)).fetchone()
            if not row:
                raise AccessDenied()
            auth = current_document(conn, current.subject, workspace_id, document_id,
                                    row['document_version_id'], row['document_revision'])
            if str(row['actor_id']) != auth.actor_id or row['subject'] != current.subject:
                raise AccessDenied()
            payload = status(row)
            if row['state'] == 'SUCCEEDED':
                pointer, policy_row = active(conn, workspace_id)
                if (not policy_row or policy_row['id'] != row['policy_version_id']
                        or pointer['revision'] != row['policy_revision']
                        or tuple(row['policy_epoch']) != auth.policy_epoch):
                    raise AccessDenied()
                payload['output'] = row['output']
            now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            restart = (row['state'] == 'RETRY_WAIT' and row['next_retry_at'] and row['next_retry_at'] <= now
                       or row['state'] == 'RUNNING' and row['lease_until'] and row['lease_until'] < now)
        if restart:
            _schedule(settings, background, workspace_id, document_id, run_id)
        return {'data': payload}

    @router.post('/documents/{document_id}/runs/{run_id}/wake', include_in_schema=False)
    def wake(workspace_id: UUID, document_id: UUID, run_id: UUID, background: BackgroundTasks,
             x_model_time: str = Header(default=''), x_model_mac: str = Header(default='')):
        try:
            timestamp = int(x_model_time)
        except ValueError:
            timestamp = 0
        message = f'{workspace_id}:{document_id}:{run_id}:{timestamp}'.encode('ascii')
        expected = hmac.new(settings.model_wake_key.encode(), message, sha256).hexdigest()
        if (len(settings.model_wake_key) < 32 or abs(time.time() - timestamp) > 30
                or not hmac.compare_digest(expected, x_model_mac)):
            raise ApiError(404, 'MODEL_RUN_NOT_FOUND', '模型运行不存在或不可访问')
        with database() as conn:
            row = conn.execute('''SELECT id FROM model_generation_run WHERE id=%s AND workspace_id=%s
                AND document_id=%s''', (run_id, workspace_id, document_id)).fetchone()
            if not row:
                raise AccessDenied()
        background.add_task(_run, settings, workspace_id, document_id, run_id)
        return {'data': {'accepted': True}}

    return router
