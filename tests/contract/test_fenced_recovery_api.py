"""Story 1.5 API contract test source; execution awaits test authorization."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import json

from fastapi.testclient import TestClient
import jsonschema
import pytest
from pydantic import ValidationError

from edw_api import main
from edw_api.access.policy import AccessDenied
from edw_api.errors import ApiError
from edw_api.task_contract import TaskResponse, TaskSnapshot, contract_schema
from edw_api.tasks import repository, routes


WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("33333333-3333-4333-8333-333333333333")
TASK = UUID("44444444-4444-4444-8444-444444444444")
PATH = f"/api/v1/workspaces/{WORKSPACE}/tasks/{TASK}/cancel"
NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


def task_row(**changes):
    return {
        "id": TASK, "workspace_id": WORKSPACE, "actor_id": ACTOR,
        "state": "RUNNING", "stage": "inventory", "category": "integration",
        "operation": "inventory", "attempt": 1, "fence_token": 1, "current_seq": 2,
        "result_id": None, "error_code": None, "error_class": None,
        "next_retry_at": None, "cancel_requested": False,
        "external_effect_state": "none", "created_at": NOW, "updated_at": NOW,
    } | changes


class OneRow:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class CancelConnection:
    def __init__(self, row, outcome):
        self.row = row
        self.outcome = outcome
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "FROM durable_task" in sql:
            assert params == (TASK, WORKSPACE, ACTOR)
            return OneRow(self.row)
        assert sql == "SELECT eid_task_cancel_v2(%s,%s,%s) AS outcome"
        assert params == (TASK, ACTOR, "cancel-request")
        return OneRow({"outcome": self.outcome})


def current_owner(monkeypatch):
    def checked(_conn, subject, workspace_id, operation):
        assert (subject, workspace_id, operation) == ("verified", WORKSPACE, "inventory:read")
        return {}, None, SimpleNamespace(actor_id=str(ACTOR))

    monkeypatch.setattr(repository, "checked", checked)


def test_cancel_calls_db_function_only_after_current_owner_check(monkeypatch):
    current_owner(monkeypatch)
    conn = CancelConnection(task_row(cancel_requested=True, current_seq=3),
                            {"status": "cancel_requested", "state": "RUNNING"})
    snapshot = repository.cancel(conn, "verified", WORKSPACE, TASK, "cancel-request")
    assert snapshot.state == "RUNNING"
    assert snapshot.cancel_requested is True
    assert snapshot.external_effect_state == "none"
    assert ["eid_task_cancel_v2" in sql for sql, _ in conn.calls] == [False, True, False]


def test_cross_workspace_or_other_owner_cannot_invoke_cancel_function(monkeypatch):
    current_owner(monkeypatch)
    conn = CancelConnection(None, {"status": "cancel_requested"})
    with pytest.raises(ApiError) as error:
        repository.cancel(conn, "verified", WORKSPACE, TASK, "cancel-request")
    assert (error.value.status_code, error.value.code) == (404, "TASK_NOT_FOUND")
    assert len(conn.calls) == 1

    monkeypatch.setattr(repository, "checked", lambda *_: (_ for _ in ()).throw(AccessDenied()))
    conn.calls.clear()
    with pytest.raises(AccessDenied):
        repository.cancel(conn, "verified", WORKSPACE, TASK, "cancel-request")
    assert conn.calls == []


@pytest.mark.parametrize("outcome,code", [
    ({"status": "too_late", "state": "SUCCEEDED"}, "TASK_CANCEL_TOO_LATE"),
    ({"status": "forbidden"}, "TASK_NOT_FOUND"),
    ({"status": "not_found"}, "TASK_NOT_FOUND"),
])
def test_cancel_result_does_not_claim_success_after_completion_or_denial(
        monkeypatch, outcome, code):
    current_owner(monkeypatch)
    conn = CancelConnection(task_row(), outcome)
    with pytest.raises(ApiError) as error:
        repository.cancel(conn, "verified", WORKSPACE, TASK, "cancel-request")
    assert error.value.code == code
    assert error.value.details == ({"status": "too_late"} if code == "TASK_CANCEL_TOO_LATE" else {})


@pytest.mark.parametrize("state,stage,error,error_class,retry_at", [
    ("RETRY_WAIT", "retry_wait", None, "TRANSIENT", NOW + timedelta(seconds=2)),
    ("FAILED", "failed", "INVALID_INVENTORY_INPUT", "PERMANENT", None),
    ("DEAD_LETTER", "dead_letter", "OUTBOX_POISONED", "FORMAT", None),
    ("CANCELLED", "cancelled", None, None, None),
])
def test_new_snapshot_states_match_generated_wire_schema(
        state, stage, error, error_class, retry_at):
    row = task_row(state=state, stage=stage, error_code=error, error_class=error_class,
                   next_retry_at=retry_at, cancel_requested=state == "CANCELLED",
                   external_effect_state="unknown")
    payload = TaskResponse(data=repository.snapshot(row)).model_dump(mode="json")
    jsonschema.validate(payload, contract_schema(), format_checker=jsonschema.FormatChecker())
    assert payload["data"]["external_effect_state"] == "unknown"
    if state == "RETRY_WAIT":
        assert payload["data"]["next_retry_at"] is not None
    else:
        assert payload["data"]["next_retry_at"] is None


def test_snapshot_rejects_inconsistent_retry_result_or_failure():
    for changes in (
        {"state": "RETRY_WAIT", "stage": "retry_wait"},
        {"state": "SUCCEEDED", "stage": "done"},
        {"state": "FAILED", "stage": "failed"},
    ):
        with pytest.raises(ValidationError):
            repository.snapshot(task_row(**changes))


@pytest.mark.parametrize("state", ["RETRY_WAIT", "FAILED", "CANCELLED", "DEAD_LETTER"])
def test_result_never_reads_payload_for_non_successful_task(monkeypatch, state):
    row = task_row(state=state, result_id=None)
    monkeypatch.setattr(repository, "_owned", lambda *_: ({}, SimpleNamespace(), row))

    class NoPayloadRead:
        def execute(self, *_):
            pytest.fail("No result payload may be loaded for a non-successful task")

    with pytest.raises(ApiError) as error:
        repository.result(NoPayloadRead(), "verified", WORKSPACE, TASK)
    assert (error.value.status_code, error.value.code) == (409, "TASK_RESULT_UNAVAILABLE")


def test_checked_in_schema_tracks_new_snapshot_contract():
    file = Path(__file__).parents[2] / "contracts/task.schema.json"
    assert json.loads(file.read_text("utf8")) == contract_schema()


def test_cancel_route_commits_before_reporting_request_and_preserves_running_state(monkeypatch):
    events = []
    monkeypatch.setattr(main.verifier, "verify", lambda _: SimpleNamespace(subject="verified"))

    @contextmanager
    def connection(_settings):
        yield object()
        events.append("committed")

    def cancel(_conn, subject, workspace_id, task_id, request_id):
        assert (subject, workspace_id, task_id, request_id) == (
            "verified", WORKSPACE, TASK, "cancel-request")
        events.append("requested")
        return TaskSnapshot.model_validate({
            "task_id": TASK, "state": "RUNNING", "stage": "inventory",
            "category": "integration", "operation": "inventory", "attempt": 1,
            "fence_token": 1, "current_seq": 3, "result_ref": None, "error": None,
            "cancel_requested": True, "external_effect_state": "receipt_pending",
            "created_at": NOW, "updated_at": NOW,
            "status_url": PATH[:-7], "result_url": PATH[:-7] + "/result",
        })

    monkeypatch.setattr(routes, "connection", connection)
    monkeypatch.setattr(repository, "cancel", cancel)
    response = TestClient(main.app).post(PATH, headers={
        "Authorization": "Bearer checked", "X-Request-ID": "cancel-request"})
    assert response.status_code == 202
    assert events == ["requested", "committed"]
    assert response.json()["data"]["state"] == "RUNNING"
    assert response.json()["data"]["cancel_requested"] is True
    assert response.json()["data"]["external_effect_state"] == "receipt_pending"
