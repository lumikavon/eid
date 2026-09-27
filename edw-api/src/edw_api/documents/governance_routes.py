"""模板治理 API：受限上传、可观察校验状态、显式开发版本发布。"""
import base64
import re
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
import psycopg

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from . import governance_repository as repository
from .governance_schemas import CandidateMetadata, DeprecateVersion, PublishCandidate
from .routes import IdempotencyKey


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/template-governance")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(403, "ACCESS_DENIED", "当前权限不允许模板管理") from exc
        except psycopg.Error as exc:
            raise ApiError(503, "TEMPLATE_STORAGE_UNAVAILABLE", "模板存储暂不可用", retryable=True) from exc

    def no_store(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"

    @router.post("/candidates", status_code=201)
    async def upload(workspace_id: UUID, metadata: Annotated[CandidateMetadata, Query()],
                     request: Request, response: Response, idempotency_key: IdempotencyKey,
                     current=Depends(actor)):
        with database() as conn:
            repository._admin(conn, current.subject, workspace_id)
        if request.headers.get("content-type", "").split(";")[0] != "application/zip":
            raise ApiError(415, "TEMPLATE_PACKAGE_FORMAT", "只接受受限模板 ZIP 包")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 5 * 1024 * 1024:
                raise ApiError(413, "TEMPLATE_PACKAGE_LIMIT", "模板包最大 5 MiB")
            raw.extend(chunk)
        with database() as conn:
            data = repository.upload_candidate(conn, current.subject, workspace_id, metadata,
                    bytes(raw), idempotency_key, request.state.request_id, request.state.trace_id)
        no_store(response)
        return {"data": data}

    @router.get("/operations/{key}")
    def operation(workspace_id: UUID, key: str, response: Response, current=Depends(actor)):
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key) is None:
            raise ApiError(422, "IDEMPOTENCY_KEY_INVALID", "操作标识无效")
        with database() as conn:
            data = repository.lookup_operation(conn, current.subject, workspace_id, key)
        no_store(response)
        return {"data": data}

    @router.get("/candidates")
    def candidates(workspace_id: UUID, response: Response, after: UUID | None = None,
                   current=Depends(actor)):
        with database() as conn:
            data = repository.list_candidates(conn, current.subject, workspace_id, after)
        no_store(response)
        return {"data": data}

    @router.get("/candidates/{candidate_id}")
    def candidate(workspace_id: UUID, candidate_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            data = repository.read_candidate(conn, current.subject, workspace_id, candidate_id)
        no_store(response)
        return {"data": data}

    @router.get("/candidates/{candidate_id}/assets/{index}")
    def asset(workspace_id: UUID, candidate_id: UUID, index: int, current=Depends(actor)):
        with database() as conn:
            facts = repository._admin(conn, current.subject, workspace_id)
            row = repository._candidate(conn, facts, workspace_id, candidate_id)
            report = repository._report(row)
            if not 0 <= index < len(report.assets):
                raise repository._hidden()
            data = base64.b64decode(report.assets[index].png_base64, validate=True)
        return Response(data, media_type="image/png", headers={"Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff"})

    @router.post("/candidates/{candidate_id}/publish", status_code=201)
    def publish(workspace_id: UUID, candidate_id: UUID, command: PublishCandidate, request: Request,
                response: Response, idempotency_key: IdempotencyKey, current=Depends(actor)):
        with database() as conn:
            data = repository.publish_candidate(conn, current.subject, workspace_id, candidate_id,
                command, idempotency_key, request.state.request_id, request.state.trace_id)
        no_store(response)
        return {"data": data}

    @router.get("/versions/{version_id}")
    def version(workspace_id: UUID, version_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            data = repository.version_detail(conn, current.subject, workspace_id, version_id)
        no_store(response)
        return {"data": data}

    @router.get("/versions/{version_id}/references")
    def references(workspace_id: UUID, version_id: UUID, response: Response,
                   after: UUID | None = None, current=Depends(actor)):
        with database() as conn:
            data = repository.pinned_references(conn, current.subject, workspace_id, version_id, after)
        no_store(response)
        return {"data": data}

    @router.post("/versions/{version_id}/deprecate")
    def deprecate(workspace_id: UUID, version_id: UUID, command: DeprecateVersion,
                  request: Request, response: Response, idempotency_key: IdempotencyKey,
                  current=Depends(actor)):
        with database() as conn:
            data = repository.deprecate_version(conn, current.subject, workspace_id, version_id,
                command, idempotency_key, request.state.request_id, request.state.trace_id)
        no_store(response)
        return {"data": data}

    return router
