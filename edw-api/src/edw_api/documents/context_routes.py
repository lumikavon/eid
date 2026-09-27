"""Manual project-context API; responses are never cacheable."""
from contextlib import contextmanager
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Request, Response

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from .context_repository import (confirm_context, list_context_versions, read_context,
                                 read_context_version, save_context)
from .context_schemas import ConfirmContext, SaveContext


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/documents/{document_id}/context")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(403, "ACCESS_DENIED", "当前权限不允许此访问") from exc
        except psycopg.Error as exc:
            raise ApiError(503, "CONTEXT_STORAGE_UNAVAILABLE", "上下文存储暂不可用", retryable=True) from exc

    @router.get("")
    def read(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            result = read_context(conn, current.subject, workspace_id, document_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.get("/eligibility")
    def eligibility(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            result = read_context(conn, current.subject, workspace_id, document_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": {key: result[key] for key in ("version_id", "revision", "state", "reasons")}}

    @router.get("/versions")
    def versions(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            result = list_context_versions(conn, current.subject, workspace_id, document_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.get("/versions/{version_id}")
    def version(workspace_id: UUID, document_id: UUID, version_id: UUID, response: Response,
                current=Depends(actor)):
        with database() as conn:
            result = read_context_version(conn, current.subject, workspace_id, document_id, version_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.put("")
    def save(workspace_id: UUID, document_id: UUID, command: SaveContext, request: Request,
             response: Response, current=Depends(actor)):
        with database() as conn:
            result = save_context(conn, current.subject, workspace_id, document_id, command,
                                  request.state.request_id, request.state.trace_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.post("/confirm")
    def confirm(workspace_id: UUID, document_id: UUID, command: ConfirmContext, request: Request,
                response: Response, current=Depends(actor)):
        with database() as conn:
            result = confirm_context(conn, current.subject, workspace_id, document_id, command,
                                     request.state.request_id, request.state.trace_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    return router
