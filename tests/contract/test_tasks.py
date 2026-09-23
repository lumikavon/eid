"""Story 1.4 contract test SOURCE. Execution requires renewed test authorization."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import jsonschema
import psycopg
import pytest
from pydantic import ValidationError

from edw_api import main
from edw_api.access.policy import AccessDenied
from edw_api.errors import ApiError
from edw_api.task_contract import (
    SubmitTask, TaskResponse, TaskSnapshot, contract_schema, parse_envelope, payload_hash,
)
from edw_api.tasks import repository, routes

ROOT = Path(__file__).parents[2]
WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
PREFIX = f"/api/v1/workspaces/{WORKSPACE}/tasks"
CLIENT = TestClient(main.app)


@pytest.fixture
def envelope():
    return json.loads((ROOT / "contracts/vectors/task-envelope-v1.json").read_text("utf8"))


def test_generated_contract_matches_wire_schema(envelope):
    schema = json.loads((ROOT / "contracts/task.schema.json").read_text("utf8"))
    assert schema == contract_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(envelope, schema, format_checker=jsonschema.FormatChecker())
    assert parse_envelope(envelope).task_id == UUID(envelope["task_id"])


@pytest.mark.parametrize("update", [
    {"message_schema_version": "2.0"}, {"category": "generation"}, {"source": "web"},
    {"actor_id": "unknown"}, {"access_token": "must-never-be-carried"},
    {"trace_id": "0" * 32}, {"occurred_at": "2026-09-22T12:00:00"},
    {"aggregate_id": "99999999-9999-4999-8999-999999999999"},
])
def test_envelope_rejects_unknown_contract_or_unbound_context(envelope, update):
    with pytest.raises((ValueError, ValidationError)):
        parse_envelope(envelope | update)


@pytest.mark.parametrize("value", [True, 0, 51, "10", 1.5])
def test_inventory_has_strict_bounded_input(value):
    with pytest.raises(ValidationError):
        SubmitTask.model_validate({"operation": "inventory", "input": {"limit": value}})


def test_submission_hash_normalizes_defaults_and_dependency_order():
    short = SubmitTask.model_validate({"operation": "inventory"})
    explicit = SubmitTask.model_validate({"operation": "inventory", "input": {"limit": 50},
                                         "depends_on": []})
    assert payload_hash(short.model_dump(mode="json")) == payload_hash(explicit.model_dump(mode="json"))
    assert payload_hash(short.model_dump(mode="json")) != payload_hash(
        SubmitTask(operation="inventory", input={"limit": 1}).model_dump(mode="json"))


def test_dependency_order_is_idempotent_but_duplicate_or_unbounded_edges_are_rejected():
    edges = [uuid4(), uuid4()]
    first = SubmitTask(operation="inventory", depends_on=edges)
    reverse = SubmitTask(operation="inventory", depends_on=list(reversed(edges)))
    assert payload_hash(first.model_dump(mode="json")) == payload_hash(reverse.model_dump(mode="json"))
    for invalid in ([edges[0], edges[0]], [uuid4() for _ in range(9)]):
        with pytest.raises(ValidationError):
            SubmitTask(operation="inventory", depends_on=invalid)


@pytest.fixture
def task_snapshot():
    task_id = uuid4()
    now = datetime(2026, 9, 23, tzinfo=timezone.utc)
    return TaskSnapshot(task_id=task_id, state="QUEUED", stage="waiting", category="integration",
                        operation="inventory", attempt=0, current_seq=1, result_ref=None,
                        error=None, created_at=now, updated_at=now,
                        status_url=f"{PREFIX}/{task_id}", result_url=f"{PREFIX}/{task_id}/result")


@pytest.fixture
def authenticated_task_api(monkeypatch):
    monkeypatch.setattr(main.verifier, "verify", lambda _: SimpleNamespace(subject="verified"))

    @contextmanager
    def connection(_settings):
        yield object()

    monkeypatch.setattr(routes, "connection", connection)
    return {"Authorization": "Bearer checked", "Idempotency-Key": "task-1",
            "X-Request-ID": "task-contract", "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"}


def test_submit_returns_202_identity_only_after_transaction_commit(
        authenticated_task_api, task_snapshot, monkeypatch):
    events = []

    @contextmanager
    def connection(_settings):
        yield object()
        events.append("committed")

    def submit(conn, subject, workspace, command, key, request_id, trace_id):
        assert (subject, workspace, key, request_id, trace_id) == (
            "verified", WORKSPACE, "task-1", "task-contract", "1" * 32)
        assert command == SubmitTask(operation="inventory")
        events.append("submitted")
        return task_snapshot

    monkeypatch.setattr(routes, "connection", connection)
    monkeypatch.setattr(repository, "submit", submit)
    response = CLIENT.post(PREFIX, headers=authenticated_task_api, json={"operation": "inventory"})
    assert response.status_code == 202
    assert events == ["submitted", "committed"]
    assert response.json()["data"]["task_id"] == str(task_snapshot.task_id)
    jsonschema.validate(response.json(), contract_schema(), format_checker=jsonschema.FormatChecker())


@pytest.mark.parametrize("error,status,code", [
    (AccessDenied(), 403, "ACCESS_DENIED"),
    (ApiError(409, "IDEMPOTENCY_KEY_REUSED", "conflict"), 409, "IDEMPOTENCY_KEY_REUSED"),
])
def test_replay_denial_or_payload_conflict_keeps_api_error_contract(
        authenticated_task_api, monkeypatch, error, status, code):
    def denied(*args):
        raise error

    monkeypatch.setattr(repository, "submit", denied)
    response = CLIENT.post(PREFIX, headers=authenticated_task_api, json={"operation": "inventory"})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_failed_commit_never_returns_accepted_identity(
        authenticated_task_api, task_snapshot, monkeypatch):
    @contextmanager
    def failed_commit(_settings):
        yield object()
        raise psycopg.OperationalError("private database diagnostic")

    monkeypatch.setattr(routes, "connection", failed_commit)
    monkeypatch.setattr(repository, "submit", lambda *args: task_snapshot)
    response = CLIENT.post(PREFIX, headers=authenticated_task_api, json={"operation": "inventory"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TASK_STORAGE_UNAVAILABLE"
    assert str(task_snapshot.task_id) not in response.text
    assert "private database diagnostic" not in response.text


def test_task_submission_requires_verified_bearer_before_database(monkeypatch):
    monkeypatch.setattr(routes, "connection", lambda *_: pytest.fail("Unauthenticated database access"))
    response = CLIENT.post(PREFIX, headers={"Idempotency-Key": "task-1"}, json={"operation": "inventory"})
    assert response.status_code == 401


def test_dependency_block_is_a_serializable_terminal_failure(task_snapshot):
    blocked = task_snapshot.model_copy(update={"state": "BLOCKED", "stage": "blocked",
                                               "error": "DEPENDENCY_BLOCKED", "current_seq": 2})
    response = TaskResponse.model_validate({"data": blocked.model_dump()}).model_dump(mode="json")
    jsonschema.validate(response, contract_schema(), format_checker=jsonschema.FormatChecker())
    assert response["data"]["result_ref"] is None
    assert response["data"]["attempt"] == 0


def test_invalid_inventory_input_is_a_serializable_blocked_failure(task_snapshot):
    blocked = task_snapshot.model_copy(update={"state": "BLOCKED", "stage": "blocked",
        "error": "INVALID_INVENTORY_INPUT", "attempt": 1, "current_seq": 3})
    response = TaskResponse.model_validate({"data": blocked.model_dump()}).model_dump(mode="json")
    jsonschema.validate(response, contract_schema(), format_checker=jsonschema.FormatChecker())
    assert response["data"]["error"] == "INVALID_INVENTORY_INPUT"
    assert response["data"]["result_ref"] is None
