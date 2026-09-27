"""Manual outline API; every response rechecks current authorization and is not cacheable."""

from contextlib import contextmanager
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Request, Response

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from .outline_repository import (confirm_outline, list_outline_versions, read_outline,
                                 read_outline_version, save_outline)
from .outline_schemas import ConfirmOutline, SaveOutline


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/documents/{document_id}/outline")

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
            raise ApiError(503, "OUTLINE_STORAGE_UNAVAILABLE", "大纲存储暂不可用", retryable=True) from exc

    @router.get("")
    def read(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            result = read_outline(conn, current.subject, workspace_id, document_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.get("/eligibility")
    def eligibility(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            result = read_outline(conn, current.subject, workspace_id, document_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": {key: result[key] for key in (
            "version_id", "revision", "document_version_id", "document_revision",
            "context_version_id", "template_version_id", "required_sections", "state", "reasons")}}

    @router.get("/versions")
    def versions(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            result = list_outline_versions(conn, current.subject, workspace_id, document_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.get("/versions/{version_id}")
    def version(workspace_id: UUID, document_id: UUID, version_id: UUID, response: Response,
                current=Depends(actor)):
        with database() as conn:
            result = read_outline_version(conn, current.subject, workspace_id, document_id, version_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.put("")
    def save(workspace_id: UUID, document_id: UUID, command: SaveOutline, request: Request,
             response: Response, current=Depends(actor)):
        with database() as conn:
            result = save_outline(conn, current.subject, workspace_id, document_id, command,
                                  request.state.request_id, request.state.trace_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    @router.post("/confirm")
    def confirm(workspace_id: UUID, document_id: UUID, command: ConfirmOutline, request: Request,
                response: Response, current=Depends(actor)):
        with database() as conn:
            result = confirm_outline(conn, current.subject, workspace_id, document_id, command,
                                     request.state.request_id, request.state.trace_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": result}

    return router
