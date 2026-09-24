from contextlib import contextmanager
import asyncio
import json
import re
import time
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ..access.policy import AccessDenied
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from ..task_contract import (EventPage, NotificationPage, NotificationResponse,
                             NotificationUnreadResponse, ResultResponse, SubmitTask,
                             TaskPage, TaskResponse, wire_time)
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

    @router.get("", response_model=TaskPage)
    def page(workspace_id: UUID, after: UUID | None = None, current=Depends(actor)):
        with database() as conn:
            return TaskPage.model_validate(repository.page(conn, current.subject, workspace_id, after))

    @router.get("/notifications", response_model=NotificationPage)
    def notifications(workspace_id: UUID, after: UUID | None = None, current=Depends(actor)):
        with database() as conn:
            return NotificationPage.model_validate(
                repository.notification_page(conn, current.subject, workspace_id, after))

    @router.get("/notifications/unread", response_model=NotificationUnreadResponse)
    def unread_notifications(workspace_id: UUID, current=Depends(actor)):
        with database() as conn:
            return NotificationUnreadResponse(has_unread=repository.has_unread_notification(
                conn, current.subject, workspace_id))

    @router.get("/notifications/{notification_id}", response_model=NotificationResponse)
    def notification(workspace_id: UUID, notification_id: UUID, current=Depends(actor)):
        with database() as conn:
            row, _ = repository.notification(conn, current.subject, workspace_id, notification_id)
            return NotificationResponse(data=row)

    @router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
    def mark_notification_read(workspace_id: UUID, notification_id: UUID, current=Depends(actor)):
        with database() as conn:
            row, _ = repository.notification(conn, current.subject, workspace_id,
                                             notification_id, mark_read=True)
            return NotificationResponse(data=row)

    @router.post("/notifications/{notification_id}/open", response_model=TaskResponse)
    def open_notification(workspace_id: UUID, notification_id: UUID, current=Depends(actor)):
        with database() as conn:
            _, task = repository.notification(conn, current.subject, workspace_id,
                                              notification_id, mark_read=True,
                                              open_target=True)
            return TaskResponse(data=task)

    @router.get("/{task_id}", response_model=TaskResponse)
    def read(workspace_id: UUID, task_id: UUID, current=Depends(actor)):
        with database() as conn:
            return TaskResponse(data=repository.read(conn, current.subject, workspace_id, task_id))

    @router.get("/{task_id}/event-page", response_model=EventPage)
    def event_page(workspace_id: UUID, task_id: UUID,
                   after: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
                   current=Depends(actor)):
        with database() as conn:
            return EventPage.model_validate(repository.event_page(
                conn, current.subject, workspace_id, task_id, after))

    @router.get("/{task_id}/events")
    def events(workspace_id: UUID, task_id: UUID,
               last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
               token: str = Depends(bearer_token)):
        current = verify(token)
        if last_event_id is None:
            cursor = 0
        elif re.fullmatch(r"(?:0|[1-9][0-9]{0,15})", last_event_id):
            cursor = int(last_event_id)
        else:
            raise ApiError(400, "INVALID_EVENT_CURSOR", "事件游标无效")
        if cursor > 9007199254740991:
            raise ApiError(400, "INVALID_EVENT_CURSOR", "事件游标无效")
        with database() as conn:
            initial = repository.event_page(conn, current.subject, workspace_id, task_id, cursor, 1)
        if initial["reset_required"]:
            raise ApiError(409, "TASK_EVENT_RESET_REQUIRED", "事件已超出保留窗口",
                           details={"current_seq": initial["current_seq"]})

        def poll(next_cursor):
            fresh = verify(token)
            if fresh.subject != current.subject:
                raise AccessDenied()
            with database() as conn:
                return repository.event_page(conn, fresh.subject, workspace_id,
                                             task_id, next_cursor, 1)

        async def stream():
            next_cursor = cursor
            delivered = 0
            started = last_heartbeat = time.monotonic()
            while delivered < 256 and time.monotonic() - started < 300:
                try:
                    page = await run_in_threadpool(poll, next_cursor)
                except (AccessDenied, ApiError, psycopg.Error, ValidationError):
                    return
                if page["reset_required"]:
                    yield ("event: reset_required\ndata: " +
                           json.dumps({"current_seq": page["current_seq"]}) + "\n\n")
                    return
                if page["data"]:
                    event = page["data"][0]
                    body = {"task_id": str(event["task_id"]), "seq": event["seq"],
                            "event_type": event["event_type"], "state": event["state"],
                            "occurred_at": wire_time(event["occurred_at"])}
                    next_cursor = event["seq"]
                    delivered += 1
                    yield (f"id: {next_cursor}\nevent: task\ndata: " +
                           json.dumps(body, separators=(",", ":")) + "\n\n")
                    continue
                if time.monotonic() - last_heartbeat >= 10:
                    last_heartbeat = time.monotonic()
                    yield ": keepalive\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                     "X-Content-Type-Options": "nosniff"})

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

    @router.post("/{task_id}/retry", status_code=202, response_model=TaskResponse)
    def retry(workspace_id: UUID, task_id: UUID, request: Request,
              idempotency_key: Annotated[str, Header(min_length=1, max_length=128,
                                                    pattern=r"^[A-Za-z0-9._:-]+$")],
              current=Depends(actor)):
        with database() as conn:
            response = TaskResponse(data=repository.retry(
                conn, current.subject, workspace_id, task_id, idempotency_key,
                request.state.request_id, request.state.trace_id))
        return response

    return router
