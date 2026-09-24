"""Story 1.6 observation contract source; test execution is deferred."""
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from edw_api import main
from edw_api.access.policy import AccessDenied
from edw_api.errors import ApiError
from edw_api.task_contract import EventPage, NotificationPage, TaskPage
from edw_api.tasks import repository, routes


WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("33333333-3333-4333-8333-333333333333")
TASK = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)
PREFIX = f"/api/v1/workspaces/{WORKSPACE}/tasks"


def row(**changes):
    return {
        "id": TASK, "workspace_id": WORKSPACE, "actor_id": ACTOR,
        "state": "SUCCEEDED", "stage": "done", "category": "integration",
        "operation": "inventory", "attempt": 1, "fence_token": 1,
        "current_seq": 3, "event_floor_seq": 1, "parent_task_id": None,
        "result_id": uuid4(), "error_code": None, "error_class": None,
        "next_retry_at": None, "cancel_requested": False,
        "external_effect_state": "none", "created_at": NOW, "updated_at": NOW,
        "input": {"operation": "inventory", "input": {"limit": 1}, "depends_on": []},
    } | changes


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class EventConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return Rows(self.rows)


def test_event_cursor_rejects_future_and_resets_missing_history(monkeypatch):
    task = row(event_floor_seq=2)
    monkeypatch.setattr(repository, "_owned", lambda *_: ({}, SimpleNamespace(), task))
    conn = EventConnection([])
    with pytest.raises(ApiError) as error:
        repository.event_page(conn, "verified", WORKSPACE, TASK, 4)
    assert error.value.code == "INVALID_EVENT_CURSOR"
    assert conn.calls == []
    reset = repository.event_page(conn, "verified", WORKSPACE, TASK, 0)
    assert reset == {"data": [], "current_seq": 3, "retention_floor": 2,
                     "reset_required": True}
    assert conn.calls == []


def test_event_replay_is_task_scoped_ordered_and_rejects_internal_gap(monkeypatch):
    monkeypatch.setattr(repository, "_owned", lambda *_: ({}, SimpleNamespace(), row()))
    event = {"task_id": TASK, "seq": 3, "event_type": "task.succeeded",
             "state": "SUCCEEDED", "occurred_at": NOW}
    conn = EventConnection([event])
    gap = repository.event_page(conn, "verified", WORKSPACE, TASK, 1, limit=1)
    assert gap["reset_required"] is True
    assert conn.calls[0][1] == (TASK, 1, 3, 1)
    accepted = repository.event_page(conn, "verified", WORKSPACE, TASK, 2, limit=1)
    assert EventPage.model_validate(accepted).data[0].seq == 3


def test_snapshot_preserves_result_identity_and_unknown_progress():
    value = repository.snapshot(row())
    assert value.progress is None
    assert value.result_ref is not None
    assert value.can_retry is True
    assert value.parent_task_id is None


def test_unsupported_or_unknown_effect_disables_both_actions():
    for changes, reason in (({"operation": "future_handler"}, "OPERATION_UNAVAILABLE"),
                            ({"external_effect_state": "unknown"}, "EXTERNAL_EFFECT_UNKNOWN")):
        cancel, retry, actual = repository._capabilities(row(**changes))
        assert (cancel, retry, actual) == (False, False, reason)


def test_notification_read_does_not_transition_task(monkeypatch):
    notification_id = uuid4()
    note = {"notification_id": notification_id, "task_id": TASK, "event_seq": 3,
            "event_type": "task.succeeded", "state": "SUCCEEDED",
            "created_at": NOW, "read_at": None}
    monkeypatch.setattr(repository, "checked", lambda *_: (
        {}, None, SimpleNamespace(actor_id=str(ACTOR))))
    monkeypatch.setattr(repository, "read", lambda *_: repository.snapshot(row()))

    class NotificationConnection:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))
            if "AS accepted" in sql:
                return SimpleNamespace(fetchone=lambda: {"accepted": True})
            if "SELECT read_at" in sql:
                return SimpleNamespace(fetchone=lambda: {"read_at": NOW})
            return SimpleNamespace(fetchone=lambda: note)

    conn = NotificationConnection()
    marked, task = repository.notification(conn, "verified", WORKSPACE, notification_id,
                                           mark_read=True)
    assert marked["read_at"] == NOW
    assert task.state == "SUCCEEDED" and task.result_ref is not None
    assert all("UPDATE durable_task" not in sql for sql, _ in conn.calls)


def test_notification_open_checks_current_result_before_marking_read(monkeypatch):
    notification_id = uuid4()
    note = {"notification_id": notification_id, "task_id": TASK, "event_seq": 3,
            "event_type": "task.succeeded", "state": "SUCCEEDED",
            "created_at": NOW, "read_at": None}
    monkeypatch.setattr(repository, "checked", lambda *_: (
        {}, None, SimpleNamespace(actor_id=str(ACTOR))))
    monkeypatch.setattr(repository, "read", lambda *_: repository.snapshot(row()))
    calls = []

    def denied_result(*_args):
        calls.append("result")
        raise AccessDenied()

    monkeypatch.setattr(repository, "result", denied_result)

    class NotificationConnection:
        def execute(self, sql, _params):
            calls.append(sql)
            assert "eid_notification_mark_read_v1" not in sql
            return SimpleNamespace(fetchone=lambda: note)

    with pytest.raises(AccessDenied):
        repository.notification(NotificationConnection(), "verified", WORKSPACE,
                                notification_id, mark_read=True, open_target=True)
    assert calls[-1] == "result"


def test_bearer_sse_stops_after_current_access_is_revoked(monkeypatch):
    monkeypatch.setattr(main.verifier, "verify", lambda _: SimpleNamespace(subject="verified"))

    @contextmanager
    def connection(_settings):
        yield object()

    monkeypatch.setattr(routes, "connection", connection)
    calls = []

    def event_page(_conn, _subject, _workspace, _task, cursor, _limit):
        calls.append(cursor)
        if len(calls) == 1:
            return {"data": [], "current_seq": 2, "retention_floor": 1,
                    "reset_required": False}
        if len(calls) == 2:
            return {"data": [{"task_id": TASK, "seq": 2, "event_type": "task.running",
                              "state": "RUNNING", "occurred_at": NOW}],
                    "current_seq": 2, "retention_floor": 1, "reset_required": False}
        raise ApiError(403, "ACCESS_DENIED", "revoked")

    monkeypatch.setattr(repository, "event_page", event_page)
    response = TestClient(main.app).get(f"{PREFIX}/{TASK}/events",
        headers={"Authorization": "Bearer checked", "Last-Event-ID": "1"})
    assert response.status_code == 200
    assert "id: 2\nevent: task\n" in response.text
    assert "secret" not in response.text
    assert calls == [1, 1, 2]


def test_sse_invalid_cursor_rejected_before_database(monkeypatch):
    monkeypatch.setattr(main.verifier, "verify", lambda _: SimpleNamespace(subject="verified"))
    monkeypatch.setattr(routes, "connection", lambda *_: pytest.fail("No database access"))
    response = TestClient(main.app).get(f"{PREFIX}/{TASK}/events",
        headers={"Authorization": "Bearer checked", "Last-Event-ID": "01"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EVENT_CURSOR"


def test_observation_models_have_bounded_empty_pages():
    assert TaskPage(data=[]).next_cursor is None
    assert NotificationPage(data=[]).next_cursor is None


def test_non_inventory_snapshot_keeps_opaque_result_without_inventory_url():
    value = repository.snapshot(row(category="generation", operation="draft", result_id=uuid4()))
    assert value.result_ref is not None
    assert value.result_url is None
    assert value.can_cancel is False and value.can_retry is False
    assert value.action_reason == "OPERATION_UNAVAILABLE"


def test_non_inventory_running_stage_is_working():
    value = repository.snapshot(row(category="review", operation="review_document",
                                    state="RUNNING", stage="working", result_id=None))
    assert value.stage == "working"


def test_task_page_filters_before_pagination(monkeypatch):
    hidden = [row(id=uuid4(), category="generation", operation="draft") for _ in range(130)]
    visible = [row(id=uuid4()) for _ in range(26)]
    all_rows = hidden + visible
    monkeypatch.setattr(repository, "checked", lambda *_: (
        {}, None, SimpleNamespace(actor_id=str(ACTOR))))
    monkeypatch.setattr(repository, "_visible_task", lambda _conn, _facts, _context, task:
                        task["category"] == "integration")

    class PageConnection:
        def execute(self, sql, params):
            assert "LIMIT 128" in sql
            after = params[-1]
            position = next((index + 1 for index, task in enumerate(all_rows)
                             if task["id"] == after), 0) if after else 0
            return Rows(all_rows[position:position + 128])

    result = repository.page(PageConnection(), "verified", WORKSPACE)
    assert len(result["data"]) == 25
    assert result["next_cursor"] == visible[24]["id"]
    assert [item.task_id for item in result["data"]] == [item["id"] for item in visible[:25]]


def test_notification_page_filters_before_pagination(monkeypatch):
    tasks = [row(id=uuid4(), category="generation", operation="draft") for _ in range(130)]
    tasks += [row(id=uuid4()) for _ in range(26)]
    notes = [{"notification_id": uuid4(), "task_id": task["id"], "event_seq": 3,
              "event_type": "task.succeeded", "state": "SUCCEEDED",
              "created_at": NOW, "read_at": None} for task in tasks]
    by_task = {task["id"]: task for task in tasks}
    monkeypatch.setattr(repository, "checked", lambda *_: (
        {}, None, SimpleNamespace(actor_id=str(ACTOR))))
    monkeypatch.setattr(repository, "_visible_task", lambda _conn, _facts, _context, task:
                        task["category"] == "integration")

    class NotificationPageConnection:
        def execute(self, sql, params):
            if "SELECT * FROM durable_task" in sql:
                return SimpleNamespace(fetchone=lambda: by_task[params[0]])
            assert "LIMIT 128" in sql
            after = params[-1]
            position = next((index + 1 for index, note in enumerate(notes)
                             if note["notification_id"] == after), 0) if after else 0
            return Rows(notes[position:position + 128])

    result = repository.notification_page(NotificationPageConnection(), "verified", WORKSPACE)
    assert len(result["data"]) == 25
    assert result["next_cursor"] == notes[154]["notification_id"]
    assert [item["task_id"] for item in result["data"]] == [task["id"] for task in tasks[130:155]]


def test_revoked_owner_gets_no_event_or_notification(monkeypatch):
    monkeypatch.setattr(repository, "_owned", lambda *_: (_ for _ in ()).throw(AccessDenied()))
    with pytest.raises(AccessDenied):
        repository.event_page(EventConnection([]), "revoked", WORKSPACE, TASK, 0)
