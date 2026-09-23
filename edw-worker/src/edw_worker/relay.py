"""Independent Outbox pump: python -m edw_worker.relay (never run during compilation).

No Celery/Beat schedule is required to reach an unavailable Broker. Each claim is
committed before publication; ambiguous confirmation keeps the row reclaimable.
"""
import logging
import multiprocessing
import os
import signal
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from kombu import Connection, Exchange, Producer, Queue
from psycopg.types.json import Jsonb

from edw_api.task_contract import TASK_NAME, parse_envelope, payload_hash
from .task_store import call

logger = logging.getLogger(__name__)
RELAY_PROGRESS_TIMEOUT = 15.0
CHILD_STOP_TIMEOUT = 10.0


def publish(envelope):
    parsed = parse_envelope(envelope)
    url = os.environ["EID_RABBITMQ_URL"]
    if urlsplit(url).scheme not in {"amqp", "amqps"}:
        raise ValueError("Publisher confirm requires AMQP")

    def returned(*_args, **_kwargs):
        raise RuntimeError("Durable task message was unroutable")

    exchange = Exchange("integration", type="direct", durable=True)
    queue = Queue("integration", exchange, routing_key="integration", durable=True,
                  queue_arguments={"x-queue-type": "quorum"})
    with Connection(url, connect_timeout=3, transport_options={
        "confirm_publish": True, "read_timeout": 3, "write_timeout": 3,
    }) as broker:
        if broker.transport.driver_name != "py-amqp":
            raise RuntimeError("Unverified publisher-confirm transport")
        with Producer(broker, on_return=returned) as producer:
            # Fixed Celery protocol 2; no callbacks, arbitrary task names or result backend.
            producer.publish(
                [[], {"envelope": envelope},
                 {"callbacks": None, "errbacks": None, "chain": None, "chord": None}],
                headers={"lang": "py", "task": TASK_NAME, "id": str(parsed.event_id),
                         "argsrepr": "()", "kwargsrepr": "<durable task reference>",
                         "origin": "eid-api", "ignore_result": True},
                correlation_id=str(parsed.event_id), serializer="json", delivery_mode=2,
                exchange=exchange, routing_key="integration", mandatory=True, retry=False,
                timeout=3, confirm_timeout=3,
                declare=[queue],
            )
    # py-amqp basic_publish_confirm synchronously waits for Ack/Nack. basic.return
    # invokes returned before Ack; a Nack, timeout or close raises and never confirms DB.


def relay_once(publisher=publish):
    owner = uuid4()
    claimed = call("SELECT eid_task_relay_claim(%s)", (owner,))
    if claimed is None:
        return False
    if not isinstance(claimed, dict):
        raise RuntimeError("Invalid Outbox claim snapshot")
    event_id = claimed.get("event_id")
    task_id = claimed.get("task_id")
    envelope = claimed.get("envelope")
    stored_hash = claimed.get("envelope_hash")
    version = None
    if isinstance(envelope, dict):
        candidate = envelope.get("message_schema_version")
        if isinstance(candidate, str) and 0 < len(candidate) <= 32 and candidate.isascii():
            if all(char in "0123456789." for char in candidate):
                version = candidate
    try:
        parsed = parse_envelope(envelope)
    except (ValueError, TypeError, RecursionError):
        reason = "UNSUPPORTED_VERSION" if version and version != "1.0" else "INVALID_ENVELOPE"
    else:
        if str(parsed.event_id) != event_id or str(parsed.task_id) != task_id:
            reason = "BINDING_MISMATCH"
        elif payload_hash(envelope) != stored_hash:
            reason = "STORED_ENVELOPE_HASH_MISMATCH"
        else:
            publisher(envelope)
            # A stale publisher may have delivered, but cannot confirm a newer
            # lease, a repaired body, or a quarantined row.
            confirmed = call("SELECT eid_task_relay_confirm(%s,%s,%s,%s)",
                             (parsed.event_id, owner, Jsonb(envelope), stored_hash))
            if not confirmed:
                raise RuntimeError("Outbox lease or body changed before confirmation")
            return True
    try:
        quarantined = call("SELECT eid_task_relay_quarantine(%s,%s,%s,%s,%s,%s)",
                           (owner, event_id, Jsonb(envelope), stored_hash, reason, version))
    except (ValueError, TypeError, RecursionError) as exc:
        raise RuntimeError("Invalid Outbox quarantine snapshot") from exc
    if not quarantined:
        raise RuntimeError("Outbox lease or body changed before quarantine")
    logger.warning("task_relay_quarantined reason=%s", reason)
    return False


def main(status_sender=None):
    from .log_safety import register_worker_log_safety
    register_worker_log_safety()
    logging.basicConfig(level=logging.INFO)
    while True:
        published = False
        try:
            published = relay_once()
            healthy = True
        except Exception as exc:
            healthy = False
            logger.warning("task_relay_pending error_type=%s", type(exc).__name__)
        if status_sender is not None:
            # Fixed-size local status only; no envelope or credentials cross this pipe.
            status_sender.send((time.monotonic(), healthy))
        if not published:
            time.sleep(1)


def _run_worker(arguments, ready_event):
    from .app import app, set_relay_readiness, verify_dependencies
    from .log_safety import register_worker_log_safety
    register_worker_log_safety()
    set_relay_readiness(ready_event)
    verify_dependencies()
    # Celery.worker_main discards start's exit code in the pinned version.
    raise SystemExit(app.start(arguments) or 0)


def _stop_children(children):
    for child in children:
        if child.is_alive():
            child.terminate()
    deadline = time.monotonic() + CHILD_STOP_TIMEOUT
    for child in children:
        child.join(timeout=max(0.0, deadline - time.monotonic()))
    for child in children:
        if child.is_alive():
            child.kill()
            child.join(timeout=1)


def supervise(arguments):
    """Run one consumer and one independent relay; either child's loss fails the pair.

    A fresh private IPC event carries readiness. No previous process/file can report
    a replacement relay ready. A stuck DB/broker operation also loses readiness and
    exits the container after a bounded interval, leaving the DB leases reclaimable.
    """
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    stopped = threading.Event()
    reader, writer = context.Pipe(duplex=False)
    children = []
    previous_handlers = {}

    def stop(_signum, _frame):
        ready.clear()
        stopped.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, stop)
        publisher = context.Process(target=main, args=(writer,), name="eid-outbox-relay")
        publisher.start()
        children.append(publisher)
        writer.close()
        consumer = context.Process(target=_run_worker, args=(arguments, ready), name="eid-consumer")
        consumer.start()
        children.append(consumer)
        last_progress = time.monotonic()
        while not stopped.is_set():
            if any(child.exitcode is not None for child in children):
                return 1
            # Bound work per supervisor turn even while the relay drains a backlog.
            for _ in range(64):
                if not reader.poll():
                    break
                last_progress, healthy = reader.recv()
                if healthy:
                    ready.set()
                else:
                    ready.clear()
            if time.monotonic() - last_progress > RELAY_PROGRESS_TIMEOUT:
                return 1
            stopped.wait(0.1)
        return 0
    except Exception as exc:
        logger.error("task_supervisor_failed error_type=%s", type(exc).__name__)
        return 1
    finally:
        ready.clear()
        _stop_children(children)
        reader.close()
        writer.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    main()
