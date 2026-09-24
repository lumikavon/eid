"""Bearer-authenticated template and initial document HTTP boundary."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import ValidationError

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from . import repository
from .schemas import (
    CatalogResponse, CreateDocument, CreateDocumentAtWorkspace, CreateDocumentFromTemplate,
    DocumentResponse, TemplateDetailResponse, TemplateFilters, TemplateListResponse,
)


IdempotencyKey = Annotated[str, Header(min_length=1, max_length=128,
                                       pattern=r"^[A-Za-z0-9._:-]+$")]


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(403, "ACCESS_DENIED", "当前权限不允许此访问") from exc
        except (psycopg.Error, ValidationError) as exc:
            raise ApiError(503, "POLICY_UNAVAILABLE", "当前权限存储不可用",
                           retryable=True) from exc

    @router.get("/document-types", response_model=CatalogResponse)
    def document_types(workspace_id: UUID, current=Depends(actor)):
        with database() as conn:
            return CatalogResponse(data=repository.type_catalog(conn, current.subject, workspace_id))

    @router.get("/templates", response_model=TemplateListResponse)
    def templates(workspace_id: UUID, filters: Annotated[TemplateFilters, Query()],
                  current=Depends(actor)):
        with database() as conn:
            return TemplateListResponse(
                data=repository.list_templates(conn, current.subject, workspace_id, filters))

    @router.get("/templates/{template_version_id}", response_model=TemplateDetailResponse)
    def template_detail(workspace_id: UUID, template_version_id: UUID, current=Depends(actor)):
        with database() as conn:
            return TemplateDetailResponse(
                data=repository.template_detail(conn, current.subject, workspace_id,
                                                template_version_id))

    @router.post("/documents", status_code=201, response_model=DocumentResponse)
    def create_document(workspace_id: UUID, body: CreateDocument, request: Request,
                        idempotency_key: IdempotencyKey, current=Depends(actor)):
        with database() as conn:
            return DocumentResponse(data=repository.create_document(
                conn, current.subject, workspace_id, body,
                idempotency_key=idempotency_key, request_id=request.state.request_id,
                trace_id=request.state.trace_id))

    @router.get("/documents/{document_id}", response_model=DocumentResponse)
    def document_detail(workspace_id: UUID, document_id: UUID, current=Depends(actor)):
        with database() as conn:
            return DocumentResponse(data=repository.read_document(
                conn, current.subject, workspace_id, document_id))

    return router


def create_canonical_router(settings, verify):
    """Source-compatible path; workspace is still checked from current server facts."""
    router = APIRouter(prefix="/api/v1")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @router.post("/documents", status_code=201, response_model=DocumentResponse)
    def create_document(body: CreateDocumentFromTemplate | CreateDocumentAtWorkspace,
                        request: Request, idempotency_key: IdempotencyKey,
                        current=Depends(actor)):
        try:
            with connection(settings) as conn:
                return DocumentResponse(data=repository.create_document(
                    conn, current.subject, body.workspace_id, body,
                    idempotency_key=idempotency_key, request_id=request.state.request_id,
                    trace_id=request.state.trace_id))
        except AccessDenied as exc:
            raise ApiError(403, "ACCESS_DENIED", "当前权限不允许此访问") from exc
        except (psycopg.Error, ValidationError) as exc:
            raise ApiError(503, "POLICY_UNAVAILABLE", "当前权限存储不可用",
                           retryable=True) from exc

    return router
