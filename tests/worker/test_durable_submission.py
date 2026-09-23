"""Failure-boundary test SOURCE; does not replace PostgreSQL/Broker acceptance."""
import json
from pathlib import Path

from celery.exceptions import Reject
import pytest

from edw_api.task_contract import payload_hash
from edw_worker import inventory, relay, task_store


@pytest.fixture
def envelope():
    return json.loads((Path(__file__).parents[2] / "contracts/vectors/task-envelope-v1.json")
                      .read_text("utf8"))


def relay_snapshot(envelope):
    return {"event_id": envelope["event_id"], "task_id": envelope["task_id"],
            "envelope": envelope, "envelope_hash": payload_hash(envelope)}


def test_relay_publishes_only_after_claim_returns_and_confirms_after_publish(monkeypatch, envelope):
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        return relay_snapshot(envelope) if "claim" in sql else True

    monkeypatch.setattr(relay, "call", call)
    def publish(value):
        assert value == envelope
        assert len(calls) == 1 and "claim" in calls[0][0]
        calls.append(("published", ()))
    assert relay.relay_once(publish) is True
    assert "confirm" in calls[2][0]
    assert calls[0][1][0] == calls[2][1][1]
    assert calls[2][1][0] == envelope["event_id"]
    assert calls[2][1][2].obj == envelope
    assert calls[2][1][3] == payload_hash(envelope)


def test_claim_connection_commits_before_publisher_and_confirm_uses_second_transaction(
        monkeypatch, envelope):
    order = []
    monkeypatch.setenv("EID_DATABASE_URL", "postgresql://unused/claim-order-source")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, error_type, _error, _traceback):
            order.append("commit" if error_type is None else "rollback")

        def execute(self, sql, _parameters=None):
            if "current_user,session_user" in sql:
                order.append("identity")
                return self
            order.append("claim" if "relay_claim" in sql else "confirm")
            self.value = relay_snapshot(envelope) if "relay_claim" in sql else True
            return self

        def fetchone(self):
            return (self.value,) if hasattr(self, "value") else ("eid_worker", "eid_worker")

    def fake_connect(*_args, **_kwargs):
        return FakeConnection()

    monkeypatch.setattr(task_store.psycopg, "connect", fake_connect)

    def publish(value):
        assert value == envelope
        assert order == ["identity", "claim", "commit"]
        order.append("publish")

    assert relay.relay_once(publish) is True
    assert order == ["identity", "claim", "commit", "publish",
                     "identity", "confirm", "commit"]


def test_ambiguous_publish_never_marks_outbox_confirmed(monkeypatch, envelope):
    calls = []
    monkeypatch.setattr(relay, "call", lambda sql, args: calls.append(sql) or relay_snapshot(envelope))
    def unavailable(_value):
        raise TimeoutError("confirmation unknown")
    with pytest.raises(TimeoutError):
        relay.relay_once(unavailable)
    assert len(calls) == 1 and "claim" in calls[0]


@pytest.mark.parametrize("changes,reason,version", [
    ({"message_schema_version": "2.0"}, "UNSUPPORTED_VERSION", "2.0"),
    ({"event_id": "corrupt"}, "INVALID_ENVELOPE", "1.0"),
])
def test_invalid_persisted_outbox_is_quarantined_without_publish_or_confirm(
        monkeypatch, envelope, changes, reason, version):
    stored = envelope | changes
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        return {**relay_snapshot(envelope), "envelope": stored,
                "envelope_hash": payload_hash(stored)} if "relay_claim" in sql else True

    monkeypatch.setattr(relay, "call", call)

    def publish(_value):
        pytest.fail("Invalid stored Outbox must not reach the broker")

    assert relay.relay_once(publish) is False
    assert len(calls) == 2
    assert "relay_claim" in calls[0][0]
    assert "relay_quarantine" in calls[1][0]
    assert calls[1][1][0] == calls[0][1][0]
    assert calls[1][1][1] == envelope["event_id"]
    assert calls[1][1][2].obj == stored
    assert calls[1][1][3:] == (payload_hash(stored), reason, version)


def test_invalid_relay_quarantine_loses_lease_without_publish(monkeypatch, envelope):
    stored = envelope | {"message_schema_version": "2.0"}
    calls = []

    def call(sql, args):
        calls.append(sql)
        return {**relay_snapshot(envelope), "envelope": stored,
                "envelope_hash": payload_hash(stored)} if "relay_claim" in sql else False

    monkeypatch.setattr(relay, "call", call)
    with pytest.raises(RuntimeError, match="lease or body changed"):
        relay.relay_once(lambda _value: pytest.fail("Stale owner cannot publish"))
    assert len(calls) == 2 and "relay_quarantine" in calls[1]


@pytest.mark.parametrize("change", [
    {"event_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    {"task_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
     "aggregate_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
     "input_ref": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
])
def test_valid_envelope_with_wrong_stored_binding_is_quarantined(monkeypatch, envelope, change):
    stored = envelope | change
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        return {**relay_snapshot(envelope), "envelope": stored,
                "envelope_hash": payload_hash(stored)} if "relay_claim" in sql else True

    monkeypatch.setattr(relay, "call", call)
    assert relay.relay_once(lambda _value: pytest.fail("Wrong binding reached broker")) is False
    assert len(calls) == 2 and "relay_quarantine" in calls[1][0]
    assert calls[1][1][1] == envelope["event_id"]
    assert calls[1][1][2].obj == stored
    assert calls[1][1][3:] == (payload_hash(stored), "BINDING_MISMATCH", "1.0")


def test_stored_hash_mismatch_is_quarantined_before_publish(monkeypatch, envelope):
    calls = []
    wrong_hash = "0" * 64 if payload_hash(envelope) != "0" * 64 else "1" * 64

    def call(sql, args):
        calls.append((sql, args))
        return {**relay_snapshot(envelope), "envelope_hash": wrong_hash} if "relay_claim" in sql else True

    monkeypatch.setattr(relay, "call", call)
    assert relay.relay_once(lambda _value: pytest.fail("Corrupt hash reached broker")) is False
    assert len(calls) == 2 and "relay_quarantine" in calls[1][0]
    assert calls[1][1][1] == envelope["event_id"]
    assert calls[1][1][3:] == (wrong_hash, "STORED_ENVELOPE_HASH_MISMATCH", "1.0")


def test_false_confirmation_after_publish_is_pending(monkeypatch, envelope):
    calls = []

    def call(sql, args):
        calls.append(sql)
        return relay_snapshot(envelope) if "relay_claim" in sql else False

    monkeypatch.setattr(relay, "call", call)
    with pytest.raises(RuntimeError, match="lease or body changed before confirmation"):
        relay.relay_once(lambda value: calls.append("published") if value == envelope else pytest.fail())
    assert len(calls) == 3
    assert "relay_claim" in calls[0] and calls[1] == "published" and "relay_confirm" in calls[2]


@pytest.mark.parametrize("status", ["processed", "quarantined"])
def test_duplicate_or_quarantined_message_never_completes_again(monkeypatch, envelope, status):
    calls = []
    monkeypatch.setattr(inventory, "call", lambda sql, args: calls.append(sql) or status)
    assert inventory.consume(envelope) == status
    assert len(calls) == 1 and "claim" in calls[0]


@pytest.mark.parametrize("status", ["busy", "unexpected"])
def test_received_busy_rejects_delivery_without_hot_requeue(monkeypatch, envelope, status):
    monkeypatch.setattr(inventory, "call", lambda *_: status)
    with pytest.raises(Reject) as error:
        inventory.consume(envelope)
    assert error.value.requeue is False


def test_success_requires_completion_transaction_return(monkeypatch, envelope):
    calls = []
    def call(sql, args):
        calls.append((sql, args))
        return "claimed" if "claim" in sql else "SUCCEEDED"
    monkeypatch.setattr(inventory, "call", call)
    assert inventory.consume(envelope) == "SUCCEEDED"
    assert "finish_inventory" in calls[1][0]
    assert calls[0][1][-1] == calls[1][1][-1]


def test_failed_completion_does_not_ack_success(monkeypatch, envelope):
    def call(sql, args):
        if "claim" in sql:
            return "claimed"
        raise RuntimeError("commit failed")
    monkeypatch.setattr(inventory, "call", call)
    with pytest.raises(RuntimeError, match="commit failed"):
        inventory.consume(envelope)


def test_unknown_version_is_durable_diagnostic_without_execution(monkeypatch, envelope):
    calls = []
    monkeypatch.setattr(inventory, "call", lambda sql, args: calls.append((sql, args)))
    assert inventory.consume(envelope | {"message_schema_version": "2.0"}) == "quarantined"
    assert len(calls) == 1 and "quarantine" in calls[0][0]
    assert calls[0][1][2:] == ("UNSUPPORTED_VERSION", "2.0")


def test_relay_with_only_blocked_dependencies_does_not_publish_or_confirm(monkeypatch):
    calls = []
    monkeypatch.setattr(relay, "call", lambda sql, args: calls.append(sql) and None)

    def publish(_envelope):
        pytest.fail("No eligible durable work may be published")

    assert relay.relay_once(publish) is False
    assert len(calls) == 1 and "relay_claim" in calls[0]


def test_authorization_block_is_acknowledged_only_after_terminal_transaction(monkeypatch, envelope):
    calls = []

    def call(sql, args):
        calls.append(sql)
        return "claimed" if "claim" in sql else "BLOCKED"

    monkeypatch.setattr(inventory, "call", call)
    assert inventory.consume(envelope) == "BLOCKED"
    assert len(calls) == 2 and "finish_inventory" in calls[1]


def test_lost_completion_never_acknowledges_a_result(monkeypatch, envelope):
    monkeypatch.setattr(inventory, "call", lambda sql, args: "claimed" if "claim" in sql else "lost")
    with pytest.raises(Reject) as error:
        inventory.consume(envelope)
    assert error.value.requeue is False


def test_claim_keeps_numeric_representation_so_rogue_body_cannot_quarantine_storage(monkeypatch, envelope):
    calls = []
    altered = envelope | {"aggregate_version": 1.0}

    def call(sql, args):
        calls.append(sql)
        assert "eid_task_claim" in sql
        assert isinstance(args[1].obj["aggregate_version"], float)
        assert args[2] == payload_hash(altered)
        assert args[2] != payload_hash(envelope)
        return "quarantined"

    monkeypatch.setattr(inventory, "call", call)
    assert inventory.consume(altered) == "quarantined"
    assert len(calls) == 1


def test_lease_expiry_exception_remains_pending_and_is_never_poison_ack(monkeypatch, envelope):
    def call(sql, args):
        if "claim" in sql:
            return "claimed"
        raise RuntimeError("Inventory lease expired")

    monkeypatch.setattr(inventory, "call", call)
    with pytest.raises(RuntimeError, match="Inventory lease expired"):
        inventory.consume(envelope)
