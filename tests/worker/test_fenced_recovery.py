"""Fenced Worker boundary test source; DB/Broker acceptance is still not run."""
import json
from pathlib import Path
from uuid import UUID

from celery.exceptions import Reject
from psycopg import errors
import pytest

from edw_worker import inventory, relay, task_store


@pytest.fixture
def envelope():
    return json.loads((Path(__file__).parents[2] / "contracts/vectors/task-envelope-v1.json")
                      .read_text("utf8"))


def _claim(envelope):
    return {"status": "claimed", "task_id": envelope["task_id"],
            "attempt": 2, "fence_token": 8}


def test_stale_delivery_never_stages_or_finishes(monkeypatch, envelope):
    calls = []

    def call(sql, _args):
        calls.append(sql)
        return {"status": "stale"}

    monkeypatch.setattr(inventory, "call", call)
    with pytest.raises(Reject) as error:
        inventory.consume(envelope)
    assert error.value.requeue is False
    assert len(calls) == 1 and "claim_v2" in calls[0]


def test_false_finish_cannot_ack_success(monkeypatch, envelope):
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        if "claim_v2" in sql:
            return _claim(envelope)
        if "heartbeat_v2" in sql:
            return {"status": "renewed"}
        if "stage_inventory_v2" in sql:
            return {"status": "staged", "content_hash": "a" * 64}
        if "finish_inventory_v2" in sql:
            return {"status": "lost"}
        pytest.fail(f"Unexpected database call: {sql}")

    monkeypatch.setattr(inventory, "call", call)
    with pytest.raises(Reject) as error:
        inventory.consume(envelope)
    assert error.value.requeue is False
    assert [sql.split("eid_task_")[1].split("(")[0] for sql, _ in calls] == [
        "claim_v2", "heartbeat_v2", "stage_inventory_v2", "heartbeat_v2",
        "finish_inventory_v2",
    ]
    assert calls[-1][1][2:] == (8, envelope["input_hash"], "a" * 64)
    assert all(args[1] == calls[0][1][3] for sql, args in calls[1:]
               if "heartbeat_v2" in sql or "stage_inventory_v2" in sql
               or "finish_inventory_v2" in sql)


def test_success_returns_only_after_finish_connection_commits(monkeypatch, envelope):
    order = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, error_type, _error, _traceback):
            order.append("rollback" if error_type else "commit")

        def execute(self, sql, _args=None):
            if "current_user,session_user" in sql:
                self.value = ("eid_worker", "eid_worker")
            else:
                order.append(sql)
                if "claim_v2" in sql:
                    reply = _claim(envelope)
                elif "heartbeat_v2" in sql:
                    reply = {"status": "renewed"}
                elif "stage_inventory_v2" in sql:
                    reply = {"status": "staged", "content_hash": "a" * 64}
                elif "finish_inventory_v2" in sql:
                    reply = {"status": "SUCCEEDED", "result_id": str(UUID(int=1))}
                else:
                    pytest.fail(f"Unexpected database call: {sql}")
                self.value = (reply,)
            return self

        def fetchone(self):
            return self.value

    monkeypatch.setenv("EID_DATABASE_URL", "postgresql://unused/fenced-source")
    monkeypatch.setattr(task_store.psycopg, "connect", lambda *_args, **_kwargs: FakeConnection())
    assert inventory.consume(envelope) == "SUCCEEDED"
    order.append("ack")
    assert "finish_inventory_v2" in order[-3]
    assert order[-2:] == ["commit", "ack"]
    assert order.count("commit") == 5 and "rollback" not in order


def test_cancel_request_stops_before_staging(monkeypatch, envelope):
    calls = []

    def call(sql, _args):
        calls.append(sql)
        if "claim_v2" in sql:
            return _claim(envelope)
        if "heartbeat_v2" in sql:
            return {"status": "cancel_requested"}
        if "stop_v2" in sql:
            return {"status": "CANCELLED", "external_effect_state": "none"}
        pytest.fail(f"Cancelled attempt reached {sql}")

    monkeypatch.setattr(inventory, "call", call)
    assert inventory.consume(envelope) == "CANCELLED"
    assert len(calls) == 3 and "stop_v2" in calls[-1]


def test_invalid_input_is_classified_by_database_before_ack(monkeypatch, envelope):
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        if "claim_v2" in sql:
            return _claim(envelope)
        if "heartbeat_v2" in sql:
            return {"status": "renewed"}
        if "stage_inventory_v2" in sql:
            return {"status": "invalid_input"}
        if "fail_v2" in sql:
            return {"status": "FAILED", "error_code": "INVALID_INVENTORY_INPUT"}
        pytest.fail(f"Unexpected database call: {sql}")

    monkeypatch.setattr(inventory, "call", call)
    assert inventory.consume(envelope) == "FAILED"
    assert "fail_v2" in calls[-1][0] and calls[-1][1][-1] == "invalid_input"
    assert not any("finish_inventory_v2" in sql for sql, _ in calls)


def test_rolled_back_stage_timeout_uses_only_db_retry_plan(monkeypatch, envelope):
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        if "claim_v2" in sql:
            return _claim(envelope)
        if "heartbeat_v2" in sql:
            return {"status": "renewed"}
        if "stage_inventory_v2" in sql:
            raise errors.QueryCanceled("statement timeout")
        if "fail_v2" in sql:
            return {"status": "RETRY_WAIT", "next_retry_at": "DB-owned"}
        pytest.fail(f"Unexpected database call: {sql}")

    monkeypatch.setattr(inventory, "call", call)
    assert inventory.consume(envelope) == "RETRY_WAIT"
    assert "fail_v2" in calls[-1][0]
    assert calls[-1][1][-1] == "transient_dependency"
    assert not any("finish_inventory_v2" in sql for sql, _ in calls)


def test_two_schedulers_cannot_both_write_with_one_live_db_lease(monkeypatch):
    calls = []
    first = UUID(int=1)
    second = UUID(int=2)

    def call(sql, args):
        calls.append((sql, args))
        if "scheduler_lease_v2" in sql:
            return {"status": "leased", "fence_token": 7} if args[0] == first else {
                "status": "busy"}
        if "schedule_v2" in sql:
            assert args == (first, 7)
            return {"status": "queued"}
        pytest.fail(f"Unexpected database call: {sql}")

    monkeypatch.setattr(relay, "call", call)
    assert relay.scheduler_once(first) is True
    assert relay.scheduler_once(second) is False
    assert sum("schedule_v2" in sql for sql, _ in calls) == 1


def test_lost_scheduler_fence_never_claims_local_retry(monkeypatch):
    calls = []

    def call(sql, _args):
        calls.append(sql)
        if "scheduler_lease_v2" in sql:
            return {"status": "leased", "fence_token": 7}
        return {"status": "lost"}

    monkeypatch.setattr(relay, "call", call)
    assert relay.scheduler_once(UUID(int=3)) is False
    assert len(calls) == 2 and "schedule_v2" in calls[-1]
