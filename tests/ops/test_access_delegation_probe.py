"""Delegation probe contracts with closed I/O; no live broker, Docker, SSH, or database."""

import copy
from datetime import datetime, timedelta, timezone
import json
import socket
import subprocess
from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest

from scripts import remote_environment as remote
from scripts import verify_access_delegation as probe
from scripts import verify_local_environment as guard
from test_remote_manifest_integration import (
    production_io,  # noqa: F401 -- shared fixture executes production guard/manifest code
    record_generated_manifest,
)


IDENTIFIER = "11111111-1111-4111-8111-111111111111"
ARGUMENTS = (IDENTIFIER, "resource:read", "stage-check")


@pytest.fixture(autouse=True)
def closed_io(monkeypatch, tmp_path):
    monkeypatch.delenv("EID_ENVIRONMENT_CONFIG", raising=False)
    monkeypatch.setattr(guard, "STATE", tmp_path / "ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")

    def forbidden(*args, **kwargs):
        pytest.fail("Delegation probe tests forbid unmocked process/network/database access")

    for name in ("run", "check_output", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)


@pytest.fixture
def broker(monkeypatch):
    context = {
        "actor_id": IDENTIFIER, "service_id": "eid-worker", "tenant_id": IDENTIFIER,
        "workspace_id": IDENTIFIER, "policy_epoch": [1, 1, 1], "classification": 1,
        "operation": ARGUMENTS[1], "purpose": ARGUMENTS[2], "delegation_scope": IDENTIFIER,
        "request_id": "stored-request", "trace_id": "a" * 32,
    }
    state = SimpleNamespace(replies=[{probe.DESTINATION: {"status": "allowed", "context": context}}],
                            created=0, closed=0, calls=[], on_create=None, on_broadcast=None,
                            on_close=None)

    def broadcast(command, **kwargs):
        assert command == "current_access"
        assert kwargs == {
            "destination": ["eid-worker@worker"],
            "arguments": dict(zip(("delegation_id", "operation", "purpose"), ARGUMENTS)),
            "reply": True, "timeout": 5,
        }
        state.calls.append(command)
        if state.on_broadcast:
            state.on_broadcast()
        return copy.deepcopy(state.replies)

    def close():
        state.closed += 1
        if state.on_close:
            state.on_close()

    def create(name, **kwargs):
        assert name == "access_acceptance_probe"
        assert kwargs == {
            "broker": "amqp://eid_api:local-api-broker-only@localhost:55672/eid-local"}
        state.created += 1
        if state.on_create:
            state.on_create()
        return SimpleNamespace(control=SimpleNamespace(broadcast=broadcast), close=close)

    monkeypatch.setattr(probe, "Celery", create)
    return state


@pytest.fixture
def remote_probe(production_io, monkeypatch, broker):  # noqa: F811
    fixture = production_io
    record_generated_manifest(fixture)

    def forbidden(*args, **kwargs):
        pytest.fail("Remote delegation probe must never consume local runtime evidence or Docker")

    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", SimpleNamespace(read_text=forbidden))
    monkeypatch.setattr(guard, "_runtime_container_id", forbidden)
    started_at = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    database = SimpleNamespace(
        row=("eid_local_dev", "eid_migrator", "eid-local-dev-v1"), reads=0,
        clock=started_at, expires_at=started_at + timedelta(minutes=5),
        sample_connections=0, sample_reads=0, sample_identities={}, sample_rows={},
        closed_connections=0, queries=[], on_sample=None,
    )

    class Connection:
        def __init__(self, sample_index):
            self.sample_index = sample_index
            self.identity_checked = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            database.closed_connections += 1
            return None

        def execute(self, sql, params=None):
            database.queries.append((self.sample_index, sql, params))
            if "current_database(), current_user, shobj_description" in sql:
                assert params is None
                database.reads += 1
                self.identity_checked = True
                row = database.sample_identities.get(self.sample_index, database.row)
            else:
                assert self.sample_index and self.identity_checked
                assert sql == (
                    "SELECT id, operation, purpose, expires_at, clock_timestamp() "
                    "FROM access_delegation WHERE id=%s AND operation=%s AND purpose=%s "
                    "AND service_id='eid-worker'")
                assert params == (UUID(IDENTIFIER), ARGUMENTS[1], ARGUMENTS[2])
                database.sample_reads += 1
                row = database.sample_rows.get(self.sample_index, (
                    UUID(IDENTIFIER), ARGUMENTS[1], ARGUMENTS[2],
                    database.expires_at, database.clock))
                if database.on_sample:
                    database.on_sample(self.sample_index)
            return SimpleNamespace(fetchone=lambda: row)

    def connect(value, **kwargs):
        assert value == "postgresql://eid_migrator:local-migrate-only@localhost:15432/eid_local_dev"
        options = "-c statement_timeout=5000 -c lock_timeout=2000"
        if "default_transaction_read_only" in kwargs.get("options", ""):
            assert kwargs == {"connect_timeout": 3,
                              "options": "-c default_transaction_read_only=on " + options}
            database.sample_connections += 1
            return Connection(database.sample_connections)
        assert kwargs == {"connect_timeout": 3, "options": options}
        return Connection(0)

    monkeypatch.setattr(psycopg, "connect", connect)
    fixture.database = database
    return fixture


def test_remote_probe_consumes_current_remote_manifest_and_exact_worker_reply(remote_probe, broker):
    assert probe.probe(*ARGUMENTS) == broker.replies[0][probe.DESTINATION]
    assert remote_probe.database.reads == 1
    assert broker.calls == ["current_access"] and broker.closed == 1
    assert remote_probe.observed["collect"] > 2
    assert remote_probe.observed["operate"] == 0 and remote_probe.commands == []


def mutate_remote(fixture, change, monkeypatch):
    worker = fixture.host.containers["worker-id"]
    if change == "owner":
        worker["Config"]["Labels"]["io.eid.owner"] = "f" * 32
    elif change == "worker":
        worker["Id"] = "f" * 64
    elif change == "volume":
        next(iter(fixture.host.volumes.values()))["Labels"]["io.eid.owner"] = "f" * 32
    elif change == "network":
        worker["NetworkSettings"]["Networks"]["foreign"] = {}
    elif change == "source":
        path = fixture.root / "edw-worker/src/edw_worker/access.py"
        path.write_bytes(path.read_bytes() + b"\n# changed source\n")
    elif change == "candidate":
        path = fixture.root / "deployment/compose.yaml"
        data = remote.yaml.safe_load(path.read_bytes())
        data["x-reviewed-candidate"] = "changed"
        path.write_text(remote.yaml.safe_dump(data), encoding="utf-8")
    elif change == "environment":
        monkeypatch.delenv("EID_ENVIRONMENT_CONFIG")
    elif change == "selector":
        monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    elif change == "tunnel":
        fixture.tunnel_alive = False
    elif change == "manifest":
        path = fixture.directory / "runtime-images.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["provenance"]["compose_sha256"] = "f" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        raise AssertionError("Unknown fixture mutation")


@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("change", ["owner", "worker", "source", "candidate", "environment",
                                   "selector", "tunnel", "manifest"])
def test_remote_drift_is_rejected_and_transport_closed(
        remote_probe, broker, monkeypatch, phase, change):
    def mutate():
        mutate_remote(remote_probe, change, monkeypatch)

    if phase == "before":
        broker.on_create = mutate
    else:
        broker.on_broadcast = mutate
    with pytest.raises((RuntimeError, guard.IsolationError, remote.RemoteEnvironmentError)):
        probe.probe(*ARGUMENTS)
    assert broker.closed == 1
    assert len(broker.calls) == (phase == "after")


def test_remote_database_identity_mismatch_prevents_broadcast(remote_probe, broker):
    remote_probe.database.row = ("foreign_database", "eid_migrator", "eid-local-dev-v1")
    with pytest.raises(guard.IsolationError, match="marker"):
        probe.probe(*ARGUMENTS)
    assert broker.created == 0 and not broker.calls


def test_environment_drift_during_capture_prevents_database_or_local_fallback(
        remote_probe, broker, monkeypatch):
    capture = probe.captured_runtime

    def changed_capture():
        runtime = capture()
        monkeypatch.delenv("EID_ENVIRONMENT_CONFIG")
        return runtime

    monkeypatch.setattr(probe, "captured_runtime", changed_capture)
    with pytest.raises(RuntimeError, match="environment selection changed"):
        probe.probe(*ARGUMENTS)
    assert remote_probe.database.reads == 0 and broker.created == 0


@pytest.mark.parametrize("selector", ["", "foreign", "../other.yaml"])
def test_explicit_invalid_environment_never_falls_back_to_local(monkeypatch, broker, selector):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)

    def local_forbidden():
        pytest.fail("Invalid environment must fail before local runtime inspection")

    monkeypatch.setattr(guard, "_recorded_owner_nonce", local_forbidden)
    with pytest.raises(guard.IsolationError, match="远端环境选择无效"):
        probe.probe(*ARGUMENTS)
    assert broker.created == 0


@pytest.fixture
def local_probe(monkeypatch, broker):
    applications = {name: name + ":1.0.0" for name in ("api", "worker", "web")}
    runtime_applications = {service: applications[source]
                            for service, source in guard.APPLICATION_IMAGE_SOURCE.items()}
    infrastructure = {name: name + ":1.0.0" for name in (
        "postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx")}
    services = {name: {"image_ref": reference, "image_id": "sha256:" + "a" * 64,
                       "container_id": name + "-container"}
                for name, reference in (runtime_applications | infrastructure).items()}
    for name in runtime_applications:
        services[name]["source_fingerprint"] = "sha256:" + "b" * 64
    manifest = {"schema_version": 2, "source_fingerprint_algorithm": "sha256",
                "services": services}
    guard.RUNTIME_IMAGE_MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
    state = SimpleNamespace(owner="local-owner", container="worker-container", checks=0,
                            manifest=manifest, services=services, database_calls=0)
    monkeypatch.setattr(guard, "build_images", lambda: applications)
    monkeypatch.setattr(guard, "infrastructure_images", lambda: infrastructure)
    monkeypatch.setattr(guard, "current_runtime_images", lambda: copy.deepcopy(state.services))
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: state.owner)

    def container_id(service, image_id, *, expected_owner):
        assert service == "worker" and image_id == "sha256:" + "a" * 64
        assert expected_owner == "local-owner"
        state.checks += 1
        return state.container

    def database(value):
        state.database_calls += 1

    monkeypatch.setattr(guard, "_runtime_container_id", container_id)
    monkeypatch.setattr(guard, "verify_database", database)
    return state


def test_local_probe_preserves_verified_manifest_owner_and_worker_checks(local_probe, broker):
    assert probe.probe(*ARGUMENTS) == broker.replies[0][probe.DESTINATION]
    assert local_probe.checks == 2 and local_probe.database_calls == 1
    assert broker.closed == 1


@pytest.mark.parametrize("change", ["owner", "worker", "source", "manifest"])
def test_local_binding_drift_rejects_reply(local_probe, broker, change):
    def mutate():
        if change == "owner":
            local_probe.owner = "foreign-owner"
        elif change == "worker":
            local_probe.container = "replacement-worker"
        elif change == "source":
            local_probe.services["worker"]["source_fingerprint"] = "sha256:" + "f" * 64
        else:
            local_probe.manifest["schema_version"] = 1
            guard.RUNTIME_IMAGE_MANIFEST.write_text(json.dumps(local_probe.manifest), encoding="utf-8")

    broker.on_broadcast = mutate
    with pytest.raises(RuntimeError):
        probe.probe(*ARGUMENTS)
    assert broker.closed == 1


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_broadcast_failure_closes_transport(local_probe, broker, failure):
    def fail():
        raise failure("Transport interrupted")

    broker.on_broadcast = fail
    with pytest.raises(failure):
        probe.probe(*ARGUMENTS)
    assert broker.closed == 1


@pytest.mark.parametrize("reply", [
    None, {}, [], [None], ["eid-worker@worker"], [{"other-worker": {"status": "denied"}}],
    [{"eid-worker@worker": {"status": "denied"}, "other-worker": {"status": "denied"}}],
    [{"eid-worker@worker": {"status": "denied"}}] * 2,
    [{"eid-worker@worker": None}], [{"eid-worker@worker": {"status": "unavailable"}}],
    [{"eid-worker@worker": {"status": "denied", "context": {}}}],
    [{"eid-worker@worker": {"status": "allowed"}}],
    [{"eid-worker@worker": {"status": "allowed", "context": {}}}],
])
def test_malformed_or_ambiguous_reply_is_never_accepted(local_probe, broker, reply):
    broker.replies = reply
    with pytest.raises(RuntimeError, match="Worker reply"):
        probe.probe(*ARGUMENTS)
    assert broker.closed == 1


@pytest.mark.parametrize("field,value", [("service_id", "eid-api"),
                                       ("delegation_scope", "22222222-2222-4222-8222-222222222222"),
                                       ("operation", "document:edit"), ("purpose", "other")])
def test_allowed_reply_must_match_requested_worker_delegation(local_probe, broker, field, value):
    broker.replies[0][probe.DESTINATION]["context"][field] = value
    with pytest.raises(RuntimeError, match="Worker reply malformed"):
        probe.probe(*ARGUMENTS)
    assert broker.closed == 1


def test_denied_reply_remains_denied_without_claiming_revocation_reason(local_probe, broker):
    broker.replies = [{probe.DESTINATION: {"status": "denied"}}]
    assert probe.probe(*ARGUMENTS) == {"status": "denied"}
    assert broker.closed == 1


def test_invalid_delegation_uuid_fails_before_runtime_io(monkeypatch, broker):
    def forbidden():
        pytest.fail("Invalid delegation UUID must fail before runtime inspection")

    monkeypatch.setattr(guard, "remote_config", forbidden)
    with pytest.raises(ValueError):
        probe.probe("invalid", *ARGUMENTS[1:])
    assert broker.created == 0


@pytest.mark.parametrize("status", ["allowed", "denied"])
def test_evidence_bounds_broadcast_before_postguard_crosses_ttl(
        remote_probe, broker, monkeypatch, capsys, status):
    database = remote_probe.database
    started_at = database.clock
    finished_at = started_at + timedelta(seconds=5)
    if status == "denied":
        broker.replies = [{probe.DESTINATION: {"status": "denied"}}]

    def broadcast():
        assert database.sample_reads == 1
        database.clock = finished_at

    def close():
        assert database.clock > database.expires_at
        assert capsys.readouterr().out == ""

    verify_images = guard.verify_runtime_images

    def postguard():
        if database.sample_reads == 2:
            database.clock = database.expires_at + timedelta(seconds=30)
        return verify_images()

    broker.on_broadcast = broadcast
    broker.on_close = close
    monkeypatch.setattr(guard, "verify_runtime_images", postguard)
    assert probe.main([*ARGUMENTS, "--evidence"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "reply": broker.replies[0][probe.DESTINATION], "delegation_id": IDENTIFIER,
        "operation": ARGUMENTS[1], "purpose": ARGUMENTS[2],
        "broadcast_started_at": started_at.isoformat(),
        "broadcast_finished_at": finished_at.isoformat(),
        "expires_at": database.expires_at.isoformat(),
    }
    assert database.reads == 3 and database.sample_reads == 2
    assert database.sample_connections == 2 and database.closed_connections == 3
    assert broker.calls == ["current_access"] and broker.closed == 1
    assert remote_probe.observed["collect"] > 2
    assert remote_probe.observed["operate"] == 0 and remote_probe.commands == []


@pytest.mark.parametrize("sample_index", [1, 2])
@pytest.mark.parametrize("offset", [timedelta(0), timedelta(microseconds=1)])
def test_expired_or_exact_expiry_boundary_cannot_produce_evidence(
        remote_probe, broker, sample_index, offset):
    database = remote_probe.database
    sample = (UUID(IDENTIFIER), ARGUMENTS[1], ARGUMENTS[2],
              database.expires_at, database.expires_at + offset)
    database.sample_rows[sample_index] = sample
    with pytest.raises(RuntimeError, match="expired"):
        probe.probe(*ARGUMENTS, evidence=True)
    assert len(broker.calls) == sample_index - 1
    assert broker.closed == 1 and database.sample_reads == sample_index


@pytest.mark.parametrize("sample_index", [1, 2])
@pytest.mark.parametrize("field,value", [
    (None, None), (0, UUID("22222222-2222-4222-8222-222222222222")),
    (1, "document:edit"), (2, "other-purpose"),
])
def test_missing_or_mismatched_delegation_evidence_fails_closed(
        remote_probe, broker, sample_index, field, value):
    database = remote_probe.database
    row = [UUID(IDENTIFIER), ARGUMENTS[1], ARGUMENTS[2], database.expires_at, database.clock]
    if field is not None:
        row[field] = value
    database.sample_rows[sample_index] = tuple(row) if field is not None else None
    with pytest.raises(RuntimeError, match="unavailable or mismatched"):
        probe.probe(*ARGUMENTS, evidence=True)
    assert len(broker.calls) == sample_index - 1
    assert broker.closed == 1 and database.closed_connections == sample_index + 1


@pytest.mark.parametrize("sample_index", [1, 2])
@pytest.mark.parametrize("field,value", [(0, "other-db"), (1, "eid_api"), (2, "foreign-marker")])
def test_each_evidence_connection_checks_database_identity_before_delegation_read(
        remote_probe, broker, sample_index, field, value):
    database = remote_probe.database
    row = list(database.row)
    row[field] = value
    database.sample_identities[sample_index] = tuple(row)
    with pytest.raises(guard.IsolationError, match="marker"):
        probe.probe(*ARGUMENTS, evidence=True)
    assert database.sample_reads == sample_index - 1
    assert len(broker.calls) == sample_index - 1 and broker.closed == 1
    assert database.closed_connections == sample_index + 1


@pytest.mark.parametrize("change", ["clock-rollback", "expiry"])
def test_changed_expiry_or_clock_rollback_is_not_accepted(remote_probe, broker, change):
    database = remote_probe.database
    expires_at, finished_at = database.expires_at, database.clock
    if change == "clock-rollback":
        finished_at -= timedelta(microseconds=1)
    else:
        expires_at += timedelta(seconds=1)
    database.sample_rows[2] = (UUID(IDENTIFIER), ARGUMENTS[1], ARGUMENTS[2],
                               expires_at, finished_at)
    with pytest.raises(RuntimeError, match="expiry or database clock changed"):
        probe.probe(*ARGUMENTS, evidence=True)
    assert broker.closed == 1 and database.sample_reads == 2


@pytest.mark.parametrize("field", [3, 4])
@pytest.mark.parametrize("value", [None, "2026-09-17T12:00:00Z", datetime(2026, 9, 17, 12)])
def test_evidence_requires_timezone_aware_database_timestamps(remote_probe, broker, field, value):
    database = remote_probe.database
    row = [UUID(IDENTIFIER), ARGUMENTS[1], ARGUMENTS[2], database.expires_at, database.clock]
    row[field] = value
    database.sample_rows[1] = tuple(row)
    with pytest.raises(RuntimeError, match="timestamps unavailable"):
        probe.probe(*ARGUMENTS, evidence=True)
    assert not broker.calls and broker.closed == 1


def test_malformed_reply_is_rejected_before_end_clock_sample(remote_probe, broker):
    broker.replies = [{probe.DESTINATION: {"status": "denied", "reason": "internal"}}]
    with pytest.raises(RuntimeError, match="Worker reply malformed"):
        probe.probe(*ARGUMENTS, evidence=True)
    assert remote_probe.database.sample_reads == 1 and broker.closed == 1


@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("change", ["owner", "worker", "volume", "network", "source", "candidate",
                                   "environment", "selector", "tunnel", "manifest"])
def test_evidence_retains_all_remote_binding_checks(
        remote_probe, broker, monkeypatch, capsys, phase, change):
    def mutate():
        mutate_remote(remote_probe, change, monkeypatch)

    if phase == "before":
        broker.on_create = mutate
    else:
        broker.on_broadcast = mutate
    assert probe.main(["--evidence", *ARGUMENTS]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "unavailable"}
    assert remote_probe.database.sample_reads == (0 if phase == "before" else 2)
    assert broker.closed == 1 and len(broker.calls) == (phase == "after")


def test_close_failure_suppresses_completed_evidence(remote_probe, broker, capsys):
    def fail():
        assert capsys.readouterr().out == ""
        raise RuntimeError("private connection failure details")

    broker.on_close = fail
    assert probe.main([*ARGUMENTS, "--evidence"]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "unavailable"}
    assert remote_probe.database.sample_reads == 2 and broker.closed == 1


def test_default_cli_preserves_plain_reply_without_extra_database_reads(remote_probe, broker, capsys):
    assert probe.main(list(ARGUMENTS)) == 0
    assert json.loads(capsys.readouterr().out) == broker.replies[0][probe.DESTINATION]
    assert remote_probe.database.reads == 1 and remote_probe.database.sample_reads == 0
