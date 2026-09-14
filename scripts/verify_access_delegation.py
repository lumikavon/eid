"""Read-only actual Worker supervisor authorization probe; no user credentials on the wire."""
import json
import sys
from uuid import UUID

from celery import Celery

from scripts.verify_local_environment import (
    _recorded_owner_nonce, verify_database, _runtime_container_id, RUNTIME_IMAGE_MANIFEST,
)


def probe(delegation_id, operation, purpose):
    UUID(delegation_id)
    nonce = _recorded_owner_nonce()
    record = json.loads(RUNTIME_IMAGE_MANIFEST.read_text())["services"]["worker"]
    container = _runtime_container_id("worker", record["image_id"], expected_owner=nonce)
    verify_database("postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev")
    app = Celery("access_acceptance_probe",
                 broker="amqp://eid_api:local-api-broker-only@localhost:55672/eid-local")
    try:
        replies = app.control.broadcast("current_access", destination=["eid-worker@worker"],
                arguments={"delegation_id": delegation_id, "operation": operation, "purpose": purpose},
                reply=True, timeout=5)
    finally:
        app.close()
    if _recorded_owner_nonce() != nonce:
        raise RuntimeError("Ownership changed")
    if _runtime_container_id("worker", record["image_id"], expected_owner=nonce) != container:
        raise RuntimeError("Worker instance changed")
    if len(replies) != 1 or "eid-worker@worker" not in replies[0]:
        raise RuntimeError("Worker reply unavailable")
    return replies[0]["eid-worker@worker"]


if __name__ == "__main__":
    try:
        print(json.dumps(probe(*sys.argv[1:])))
    except Exception:
        print(json.dumps({"status": "unavailable"}))
        raise SystemExit(1)
