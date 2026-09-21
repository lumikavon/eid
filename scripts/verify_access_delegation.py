"""Read-only actual Worker supervisor authorization probe; no user credentials on the wire.

Runtime/database guards are separate from the five-second broadcast timeout and may
be expensive remotely. Optional evidence bounds the broadcast with governed database
clock samples inside the unchanged delegation TTL; the postflight may finish later.
A denied reply merges access denial and internal Worker errors. Evidence proves only
an in-TTL observed denial, not its strict cause or successful revocation enforcement.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import os
from uuid import UUID

from celery import Celery
import psycopg

from scripts import verify_local_environment as guard
from scripts.remote_service_operations import captured_runtime


DESTINATION = "eid-worker@worker"


def _reply(replies, delegation_id, operation, purpose):
    if (not isinstance(replies, list) or len(replies) != 1
            or not isinstance(replies[0], dict) or set(replies[0]) != {DESTINATION}):
        raise RuntimeError("Worker reply unavailable")
    result = replies[0][DESTINATION]
    if not isinstance(result, dict):
        raise RuntimeError("Worker reply malformed")
    if result == {"status": "denied"}:
        return result
    context = result.get("context")
    if (set(result) != {"status", "context"} or result.get("status") != "allowed"
            or not isinstance(context, dict)
            or context.get("service_id") != "eid-worker"
            or context.get("delegation_scope") != str(UUID(delegation_id))
            or context.get("operation") != operation or context.get("purpose") != purpose):
        raise RuntimeError("Worker reply malformed")
    return result


def _delegation_sample(delegation_id, operation, purpose, database_url):
    """Read the exact delegation and wall clock only after checking database identity."""
    with psycopg.connect(
        database_url.replace("postgresql+psycopg:", "postgresql:"), connect_timeout=3,
        options=("-c default_transaction_read_only=on "
                 "-c statement_timeout=5000 -c lock_timeout=2000"),
    ) as conn:
        identity = conn.execute(
            "SELECT current_database(), current_user, shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        guard.require(identity == ("eid_local_dev", "eid_migrator", guard.EXPECTED["marker"]),
                      "实际数据库名称/身份/marker不匹配")
        row = conn.execute(
            "SELECT id, operation, purpose, expires_at, clock_timestamp() "
            "FROM access_delegation WHERE id=%s AND operation=%s AND purpose=%s "
            "AND service_id='eid-worker'",
            (UUID(delegation_id), operation, purpose),
        ).fetchone()
    if (not isinstance(row, tuple) or len(row) != 5
            or str(row[0]) != str(UUID(delegation_id))
            or row[1] != operation or row[2] != purpose):
        raise RuntimeError("Delegation evidence unavailable or mismatched")
    expires_at, sampled_at = row[3:]
    if any(not isinstance(value, datetime) or value.utcoffset() is None
           for value in (expires_at, sampled_at)):
        raise RuntimeError("Delegation evidence timestamps unavailable")
    if sampled_at >= expires_at:
        raise RuntimeError("Delegation expired during broadcast evidence window")
    return expires_at.astimezone(timezone.utc), sampled_at.astimezone(timezone.utc)


def probe(delegation_id, operation, purpose, *, evidence=False):
    UUID(delegation_id)
    selector = os.environ.get("EID_ENVIRONMENT_CONFIG")
    config = copy.deepcopy(guard.remote_config())
    runtime = captured_runtime() if config is not None else None
    if runtime is not None:
        if runtime.config != config:
            raise RuntimeError("Runtime environment selection changed")
        manifest = runtime.manifest
    else:
        nonce = guard._recorded_owner_nonce()
        manifest = guard.verify_runtime_images()

    def verify_selection():
        if (os.environ.get("EID_ENVIRONMENT_CONFIG") != selector
                or guard.remote_config() != config):
            raise RuntimeError("Runtime environment selection changed")

    def verify_binding():
        verify_selection()
        if guard.verify_runtime_images() != manifest:
            raise RuntimeError("Runtime image or source binding changed")
        if runtime is not None:
            runtime.verify_unchanged()
        else:
            if guard._recorded_owner_nonce() != nonce:
                raise RuntimeError("Ownership changed")
            record = manifest["services"]["worker"]
            container = guard._runtime_container_id("worker", record["image_id"],
                                                    expected_owner=nonce)
            if container != record["container_id"]:
                raise RuntimeError("Worker instance changed")
        verify_selection()

    verify_selection()
    database_url = guard.development_database_url()
    guard.verify_database(database_url)
    app = Celery("access_acceptance_probe",
                 broker="amqp://eid_api:local-api-broker-only@localhost:55672/eid-local")
    try:
        verify_binding()
        if evidence:
            expires_at, started_at = _delegation_sample(delegation_id, operation, purpose, database_url)
        replies = app.control.broadcast("current_access", destination=[DESTINATION],
                arguments={"delegation_id": delegation_id, "operation": operation, "purpose": purpose},
                reply=True, timeout=5)
        try:
            result = _reply(replies, delegation_id, operation, purpose)
            if evidence:
                final_expiry, finished_at = _delegation_sample(delegation_id, operation, purpose, database_url)
                if final_expiry != expires_at or finished_at < started_at:
                    raise RuntimeError("Delegation expiry or database clock changed")
        finally:
            verify_binding()
    finally:
        app.close()
    if evidence:
        return {"reply": result, "delegation_id": str(UUID(delegation_id)),
                "operation": operation, "purpose": purpose,
                "broadcast_started_at": started_at.isoformat(),
                "broadcast_finished_at": finished_at.isoformat(),
                "expires_at": expires_at.isoformat()}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delegation_id")
    parser.add_argument("operation")
    parser.add_argument("purpose")
    parser.add_argument("--evidence", action="store_true",
                        help="Include database-clock broadcast bounds within the delegation TTL")
    args = parser.parse_args(argv)
    try:
        result = probe(args.delegation_id, args.operation, args.purpose, evidence=args.evidence)
    except Exception:
        print(json.dumps({"status": "unavailable"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
