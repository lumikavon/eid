"""Bounded X-11 governance; never return persisted text without live source access."""
from uuid import UUID
from datetime import datetime, timezone

import psycopg
from fastapi import APIRouter, Depends, Response

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from ..task_contract import SourceRegistration, ConflictDecision
from .routes import scope
from .governance import enterprise_proofs, local_source, register, side
from .gateway import verify_source


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/knowledge')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    def missing():
        raise ApiError(404, 'KNOWLEDGE_NOT_FOUND', '来源不存在或不可访问')

    def db():
        return connection(settings)

    def anchor_state(conn, subject, workspace_id, document_id, context_version_id, manage=False):
        anchor, context, state = scope(conn, subject, workspace_id, document_id, context_version_id)
        if manage:
            checked(conn, subject, workspace_id, 'knowledge:manage', document_id)
        return anchor, context, state

    def unchanged(old, new):
        return (old[0]['project_id'] == new[0]['project_id'] and
                old[1].policy_epoch == new[1].policy_epoch and
                old[2]['head_version_id'] == new[2]['head_version_id'] and
                old[2]['context_version'] == new[2]['context_version'])

    @router.post('/assertions')
    def add(workspace_id: UUID, command: SourceRegistration, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            with db() as conn:
                initial = anchor_state(conn, current.subject, workspace_id, command.context_document_id,
                                       command.context_version_id, True)
                anchor, context, state = initial
                if (command.project_id != anchor['project_id'] or
                        command.product_id not in (None, anchor['product_id']) or
                        command.customer_id not in (None, anchor['customer_id']) or
                        (command.effective_until is not None and command.effective_until <= datetime.now(timezone.utc))
                        or command.classification > context.classification):
                    missing()
            # Never hold a database transaction over gateway I/O.
            text = None
            if command.chain == 'enterprise':
                text = verify_source(settings, current.subject, workspace_id, anchor, context,
                                     command.model_dump(), state['context_version'])
            with db() as conn:
                # Serialize registrations so two competing versions cannot both miss the other.
                checked(conn, current.subject, workspace_id, 'workspace:read', exclusive=True)
                fresh = anchor_state(conn, current.subject, workspace_id, command.context_document_id,
                                     command.context_version_id, True)
                if not unchanged(initial, fresh):
                    missing()
                if command.chain == 'attachment':
                    text = local_source(conn, workspace_id, fresh[0], command.source_id, command.version,
                                        command.chunk_hash, command.locator, command.classification,
                                        command.page, command.ordinal, current.subject)
                    source = conn.execute('SELECT document_id FROM attachment WHERE id=%s AND workspace_id=%s',
                                          (UUID(command.source_id), workspace_id)).fetchone()
                    if not source or source['document_id'] != command.document_id:
                        missing()
                if text is None:
                    missing()
                return {'data': {'assertion_id': register(conn, workspace_id, context.actor_id, command, text)}}
        except (AccessDenied, ValueError):
            missing()
        except psycopg.Error as exc:
            raise ApiError(503, 'KNOWLEDGE_UNAVAILABLE', '来源治理暂不可用', retryable=True) from exc

    def view(workspace_id, conflict_id, document_id, version_id, subject, *, manage=False, decision=None):
        try:
            with db() as conn:
                initial = anchor_state(conn, subject, workspace_id, document_id, version_id, manage)
                conflict = conn.execute('SELECT * FROM knowledge_conflict WHERE workspace_id=%s AND id=%s',
                                        (workspace_id, conflict_id)).fetchone()
                if not conflict:
                    missing()
                rows = [conn.execute('SELECT * FROM knowledge_assertion WHERE workspace_id=%s AND id=%s',
                                     (workspace_id, conflict[key])).fetchone() for key in ('left_id', 'right_id')]
            proof = enterprise_proofs(settings, subject, workspace_id, initial[0], initial[1], rows,
                                      initial[2]['context_version'])
            with db() as conn:
                fresh = anchor_state(conn, subject, workspace_id, document_id, version_id, manage)
                if not unchanged(initial, fresh):
                    missing()
                conflict = conn.execute('SELECT * FROM knowledge_conflict WHERE workspace_id=%s AND id=%s FOR UPDATE',
                                        (workspace_id, conflict_id)).fetchone() if decision else conn.execute(
                    'SELECT * FROM knowledge_conflict WHERE workspace_id=%s AND id=%s',
                    (workspace_id, conflict_id)).fetchone()
                if not conflict or conflict['left_id'] != rows[0]['id'] or conflict['right_id'] != rows[1]['id']:
                    missing()
                visible = [side(conn, settings, subject, workspace_id, fresh[0], fresh[1], row, proof) for row in rows]
                if all(x['state'] != 'current' for x in visible):
                    missing()
                if decision:
                    if any(x['state'] != 'current' for x in visible):
                        missing()
                    if (decision.expected_revision != conflict['revision'] or
                            decision.left_id != conflict['left_id'] or decision.right_id != conflict['right_id']):
                        raise ApiError(409, 'KNOWLEDGE_CONFLICT_STALE', '来源或裁定版本已失效')
                    updated = conn.execute('''UPDATE knowledge_conflict SET revision=revision+1,status=%s,
                      updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s AND revision=%s RETURNING revision''',
                      (decision.status, workspace_id, conflict_id, decision.expected_revision)).fetchone()
                    if not updated:
                        raise ApiError(409, 'KNOWLEDGE_CONFLICT_STALE', '裁定版本已失效')
                    conn.execute('''INSERT INTO knowledge_disposition(id,workspace_id,conflict_id,revision,status,reason,
                      actor_id,left_id,right_id) VALUES (gen_random_uuid(),%s,%s,%s,%s,%s,%s,%s,%s)''',
                      (workspace_id, conflict_id, updated['revision'], decision.status, decision.reason.strip(),
                       fresh[1].actor_id, conflict['left_id'], conflict['right_id']))
                    conn.execute('''UPDATE knowledge_dependency SET needs_review=true
                      WHERE workspace_id=%s AND conflict_id=%s''', (workspace_id, conflict_id))
                    conflict = {**conflict, 'revision': updated['revision'], 'status': decision.status}
                history = conn.execute('''SELECT revision,status,reason,actor_id,decided_at FROM knowledge_disposition
                  WHERE workspace_id=%s AND conflict_id=%s ORDER BY revision DESC LIMIT 30''',
                  (workspace_id, conflict_id)).fetchall() if all(x['state'] == 'current' for x in visible) else []
                both_current = all(x['state'] == 'current' for x in visible)
                return {'data': {'id': str(conflict_id), 'revision': conflict['revision'] if both_current else 0,
                                 'status': conflict['status'] if both_current else 'forbidden',
                                 'sides': visible, 'history': history}}
        except AccessDenied:
            missing()
        except psycopg.Error as exc:
            raise ApiError(503, 'KNOWLEDGE_UNAVAILABLE', '来源治理暂不可用', retryable=True) from exc

    @router.get('/conflicts/{conflict_id}')
    def inspect(workspace_id: UUID, conflict_id: UUID, context_document_id: UUID,
                response: Response, context_version_id: UUID | None = None, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        return view(workspace_id, conflict_id, context_document_id, context_version_id, current.subject)

    @router.post('/conflicts/{conflict_id}/dispositions')
    def decide(workspace_id: UUID, conflict_id: UUID, command: ConflictDecision,
               response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        return view(workspace_id, conflict_id, command.context_document_id, command.context_version_id,
                    current.subject, manage=True, decision=command)

    return router
