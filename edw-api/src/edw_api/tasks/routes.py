from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from ..task_contract import ResultResponse, SubmitTask, TaskResponse
from . import repository


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/tasks")

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
            raise ApiError(503, "TASK_STORAGE_UNAVAILABLE", "任务存储不可用", retryable=True) from exc

    @router.post("", status_code=202, response_model=TaskResponse)
    def submit(workspace_id: UUID, body: SubmitTask, request: Request,
               idempotency_key: Annotated[str, Header(min_length=1, max_length=128,
                                                     pattern=r"^[A-Za-z0-9._:-]+$")],
               current=Depends(actor)):
        with database() as conn:
            response = TaskResponse(data=repository.submit(conn, current.subject, workspace_id,
                body, idempotency_key, request.state.request_id, request.state.trace_id))
        # The connection's commit completed before the 202 leaves this function.
        return response

    @router.get("/{task_id}", response_model=TaskResponse)
    def read(workspace_id: UUID, task_id: UUID, current=Depends(actor)):
        with database() as conn:
            return TaskResponse(data=repository.read(conn, current.subject, workspace_id, task_id))

    @router.get("/{task_id}/result", response_model=ResultResponse)
    def result(workspace_id: UUID, task_id: UUID, current=Depends(actor)):
        with database() as conn:
            return ResultResponse(data=repository.result(conn, current.subject, workspace_id, task_id))

    @router.post("/{task_id}/cancel", status_code=202, response_model=TaskResponse)
    def cancel(workspace_id: UUID, task_id: UUID, request: Request, current=Depends(actor)):
        with database() as conn:
            response = TaskResponse(data=repository.cancel(
                conn, current.subject, workspace_id, task_id, request.state.request_id))
        return response

    return router
