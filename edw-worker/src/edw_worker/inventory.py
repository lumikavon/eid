"""Inbox acknowledgement boundary for the only implemented business task."""
from uuid import UUID, uuid4

from celery.exceptions import Reject
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from edw_api.task_contract import parse_envelope, payload_hash
from .task_store import call


def consume(envelope):
    # Persist safe diagnostic metadata only; never echo/store arbitrary untrusted bodies.
    try:
        digest = payload_hash(envelope)
        parsed = parse_envelope(envelope)
    except (ValueError, TypeError, ValidationError, RecursionError):
        try:
            digest = payload_hash(envelope)
        except (ValueError, TypeError, RecursionError):
            digest = payload_hash({"invalid_json_value": True})
        event_id, version = None, None
        if isinstance(envelope, dict):
            try:
                event_id = UUID(str(envelope.get("event_id")))
            except ValueError:
                pass
            candidate = envelope.get("message_schema_version")
            if isinstance(candidate, str) and len(candidate) <= 32 and candidate.isascii():
                # Only numeric version diagnostics; attacker text is never retained.
                if all(char in "0123456789." for char in candidate):
                    version = candidate
        reason = "UNSUPPORTED_VERSION" if version and version != "1.0" else "INVALID_ENVELOPE"
        call("SELECT eid_task_quarantine(%s,%s,%s,%s)", (event_id, digest, reason, version))
        return "quarantined"
    owner = uuid4()
    status = call("SELECT eid_task_claim(%s,%s,%s,%s)",
                  (parsed.event_id, Jsonb(envelope), digest, owner))
    if status in {"processed", "quarantined"}:
        return status
    if status != "claimed":
        # Outbox remains durable and the relay replays after the active lease.
        # Hot requeue would exhaust quorum delivery limits before that lease expires.
        raise Reject("Task lease is not available; durable replay pending", requeue=False)
    # This separate short transaction computes a bounded read-only inventory,
    # rechecks current authorization, stores its result and marks Inbox processed.
    status = call("SELECT eid_task_finish_inventory(%s,%s)", (parsed.event_id, owner))
    if status not in {"SUCCEEDED", "BLOCKED"}:
        raise Reject("Task ownership changed; durable replay pending", requeue=False)
    return status


def register(app):
    @app.task(name="eid.inventory.v1", acks_late=True, acks_on_failure_or_timeout=False,
              reject_on_worker_lost=True, ignore_result=True, typing=True)
    def inventory(envelope):
        try:
            return consume(envelope)
        except Reject:
            raise
        except Exception as exc:
            # No success ACK and no immediate requeue. The database Outbox scanner
            # covers both absent Inbox rows and received rows whose lease expired,
            # including a previously confirmed publication. An unknown commit is
            # therefore recovered or deduplicated without depending on broker retries.
            raise Reject("Durable task storage unavailable; replay pending", requeue=False) from exc

    return inventory
