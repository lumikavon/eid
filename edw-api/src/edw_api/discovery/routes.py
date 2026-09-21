"""当前主体由 Bearer 校验推导，所有请求和返回值均使用有界契约。"""
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
    CommandResponse, DetailResponse, FavoriteCommand, Filters, ListResponse,
    RestoreCommand, SearchRequest, SearchResponse, SummaryResponse,
)

IdempotencyKey = Annotated[str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]


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
            raise ApiError(503, "POLICY_UNAVAILABLE", "当前权限存储不可用", retryable=True) from exc

    @router.get("/discovery", response_model=ListResponse)
    def list_records(workspace_id: UUID, filters: Annotated[Filters, Query()], current=Depends(actor)):
        with database() as conn:
            return ListResponse(data=repository.list_records(conn, current.subject, workspace_id, filters))

    @router.get("/discovery/summary", response_model=SummaryResponse)
    def summary(workspace_id: UUID, filters: Annotated[Filters, Query()], current=Depends(actor)):
        with database() as conn:
            return SummaryResponse(data=repository.summary(conn, current.subject, workspace_id, filters))

    @router.get("/discovery/{resource_id}", response_model=DetailResponse)
    def detail(workspace_id: UUID, resource_id: UUID, current=Depends(actor)):
        with database() as conn:
            return DetailResponse(data=repository.detail(
                conn, current.subject, workspace_id, resource_id,
                environment=settings.discovery_policy_environment))

    @router.post("/search", response_model=SearchResponse)
    def search(workspace_id: UUID, body: SearchRequest, current=Depends(actor)):
        with database() as conn:
            return SearchResponse(data=repository.search_records(conn, current.subject, workspace_id, body))

    @router.put("/favorites/{resource_id}", response_model=CommandResponse)
    def favorite(workspace_id: UUID, resource_id: UUID, body: FavoriteCommand,
                 request: Request, idempotency_key: IdempotencyKey, current=Depends(actor)):
        with database() as conn:
            return CommandResponse(data=repository.collection_command(
                conn, current.subject, workspace_id, resource_id, body, action="favorite.set",
                idempotency_key=idempotency_key, request_id=request.state.request_id,
                trace_id=request.state.trace_id, environment=settings.discovery_policy_environment))

    @router.post("/recycle/{resource_id}:restore", response_model=CommandResponse)
    def restore(workspace_id: UUID, resource_id: UUID, body: RestoreCommand,
                request: Request, idempotency_key: IdempotencyKey, current=Depends(actor)):
        with database() as conn:
            return CommandResponse(data=repository.collection_command(
                conn, current.subject, workspace_id, resource_id, body, action="restore_visibility",
                idempotency_key=idempotency_key, request_id=request.state.request_id,
                trace_id=request.state.trace_id, environment=settings.discovery_policy_environment))

    return router
