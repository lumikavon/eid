"""Fenced Inbox acknowledgement boundary for the inventory task."""
from uuid import UUID, uuid4

from celery.exceptions import Reject
from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from edw_api.task_contract import parse_envelope, payload_hash
from .task_store import call


def _status(reply):
    if not isinstance(reply, dict) or not isinstance(reply.get("status"), str):
        raise RuntimeError("Invalid task storage reply")
    return reply["status"]


def _pending():
    # The durable Outbox and DB lease, rather than a hot broker requeue, recover work.
    raise Reject("Task ownership changed; durable replay pending", requeue=False)


def _stop(event_id, owner, fence):
    reply = call("SELECT eid_task_stop_v2(%s,%s,%s)", (event_id, owner, fence))
    if _status(reply) == "CANCELLED":
        return "CANCELLED"
    _pending()


def _heartbeat(event_id, owner, fence):
    reply = call("SELECT eid_task_heartbeat_v2(%s,%s,%s)", (event_id, owner, fence))
    status = _status(reply)
    if status == "renewed":
        return None
    if status == "cancel_requested":
        return _stop(event_id, owner, fence)
    _pending()


def _fail(event_id, owner, fence, kind):
    # SQL reclassifies against current authorization and stored input, then owns
    # the sole next_retry_at plan. Celery never schedules a business retry.
    reply = call("SELECT eid_task_fail_v2(%s,%s,%s,%s)",
                 (event_id, owner, fence, kind))
    status = _status(reply)
    if status in {"RETRY_WAIT", "FAILED", "DEAD_LETTER"}:
        return status
    _pending()


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
    reply = call("SELECT eid_task_claim_v2(%s,%s,%s,%s)",
                 (parsed.event_id, Jsonb(envelope), digest, owner))
    status = _status(reply)
    if status in {"processed", "quarantined", "blocked"}:
        return status
    if status != "claimed":
        _pending()
    fence = reply.get("fence_token")
    attempt = reply.get("attempt")
    if (reply.get("task_id") != str(parsed.task_id)
            or type(fence) is not int or not 1 <= fence <= 9007199254740991
            or type(attempt) is not int or not 1 <= attempt <= 3):
        raise RuntimeError("Invalid fenced claim reply")

    stopped = _heartbeat(parsed.event_id, owner, fence)
    if stopped is not None:
        return stopped
    # Each call is its own short transaction. SQL owns the attempt-specific,
    # immutable staging row and rechecks current access before accepting it.
    try:
        staged = call("SELECT eid_task_stage_inventory_v2(%s,%s,%s)",
                      (parsed.event_id, owner, fence))
    except (errors.LockNotAvailable, errors.QueryCanceled):
        # A rolled-back short DB operation may be retried only through the
        # guarded DB plan. An unknown commit/network outcome is left to recovery.
        return _fail(parsed.event_id, owner, fence, "transient_dependency")
    stage_status = _status(staged)
    if stage_status in {"authorization_denied", "invalid_input",
                        "format_repairable", "transient_dependency"}:
        return _fail(parsed.event_id, owner, fence, stage_status)
    if stage_status != "staged":
        _pending()
    content_hash = staged.get("content_hash")
    if (not isinstance(content_hash, str) or len(content_hash) != 64
            or any(char not in "0123456789abcdef" for char in content_hash)):
        raise RuntimeError("Invalid staging content hash")
    stopped = _heartbeat(parsed.event_id, owner, fence)
    if stopped is not None:
        return stopped
    finished = call("SELECT eid_task_finish_inventory_v2(%s,%s,%s,%s,%s)",
                    (parsed.event_id, owner, fence, parsed.input_hash, content_hash))
    finish_status = _status(finished)
    if finish_status == "SUCCEEDED":
        return finish_status
    if finish_status == "cancel_requested":
        return _stop(parsed.event_id, owner, fence)
    if finish_status == "authorization_denied":
        return _fail(parsed.event_id, owner, fence, "authorization_denied")
    _pending()


def register(app):
    @app.task(name="eid.inventory.v1", acks_late=True, acks_on_failure_or_timeout=False,
              reject_on_worker_lost=True, ignore_result=True, typing=True)
    def inventory(envelope):
        try:
            return consume(envelope)
        except Reject:
            raise
        except Exception as exc:
            # Unknown DB commit results are recovered or deduplicated by the
            # durable Outbox scanner after the DB lease expires.
            raise Reject("Durable task storage unavailable; replay pending", requeue=False) from exc

    return inventory
