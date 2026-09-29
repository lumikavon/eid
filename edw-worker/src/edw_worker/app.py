import math
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait

import boto3
import psycopg
import redis
from celery import Celery
from celery.worker.control import Panel
from kombu import Exchange, Queue
from botocore.config import Config
from .inventory import register as register_inventory
from .attachments import register as register_attachments
from .knowledge import register as register_knowledge
from .evidence import register as register_evidence
from .model_wake import register as register_model_wake

broker = os.environ["EID_RABBITMQ_URL"]
app = Celery("edw_worker", broker=broker)
app.conf.update(
    task_default_queue="integration",
    task_default_exchange="integration",
    task_default_exchange_type="direct",
    task_default_routing_key="integration",
    task_queues=tuple(
        Queue(name, Exchange(name, type="direct", durable=True), routing_key=name,
              durable=True, queue_arguments={"x-queue-type": "quorum"})
        for name in ("generation", "retrieval", "review", "parse_ocr", "render", "integration")
    ),
    broker_transport_options={"confirm_publish": True},
    task_serializer="json",
    accept_content=["json"],
    worker_send_task_events=True,
    task_create_missing_queues=False,
    worker_prefetch_multiplier=1,
)
register_inventory(app)
register_attachments(app)
register_knowledge(app)
register_evidence(app)
register_model_wake(app)

DEPENDENCY_PROBE_NAMES = ("postgres", "redis", "s3")
DEPENDENCY_PROBE_CAPACITY = len(DEPENDENCY_PROBE_NAMES) * 2
_DEPENDENCY_EXECUTOR = ThreadPoolExecutor(max_workers=len(DEPENDENCY_PROBE_NAMES))
_DEPENDENCY_CAPACITY = threading.BoundedSemaphore(DEPENDENCY_PROBE_CAPACITY)
_RELAY_READY = None


def set_relay_readiness(ready_event):
    global _RELAY_READY
    _RELAY_READY = ready_event


def _database_probe(operation_timeout: float) -> None:
    statement_timeout_ms = max(100, int(operation_timeout * 1000))
    with psycopg.connect(
        os.environ["EID_DATABASE_URL"],
        connect_timeout=max(1, math.ceil(operation_timeout)),
        options=f"-c statement_timeout={statement_timeout_ms}",
    ) as conn:
        identity_row = conn.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity_row != ("eid_local_dev", "eid_worker"):
            raise RuntimeError("Worker database identity mismatch")
        marker_row = conn.execute(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        revision_rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        # Execute the exact read-only dependency; an absent grant/function fails readiness.
        conn.execute("SELECT eid_worker_access(%s)",
                     ("00000000-0000-0000-0000-000000000000",)).fetchone()
        # Privilege inspection only: readiness never claims or completes a task.
        task_grants = conn.execute("""
            SELECT has_function_privilege(current_user,'eid_task_relay_claim(uuid)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_relay_confirm(uuid,uuid,jsonb,text)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_relay_quarantine(uuid,uuid,jsonb,text,text,text)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_claim_v2(uuid,jsonb,text,uuid)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_heartbeat_v2(uuid,uuid,bigint)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_stage_inventory_v2(uuid,uuid,bigint)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_finish_inventory_v2(uuid,uuid,bigint,text,text)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_fail_v2(uuid,uuid,bigint,text)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_stop_v2(uuid,uuid,bigint)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_scheduler_lease_v2(uuid)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_schedule_v2(uuid,bigint)','EXECUTE')
             AND has_function_privilege(current_user,'eid_task_quarantine(uuid,text,text,text)','EXECUTE')
             AND NOT has_function_privilege(current_user,'eid_task_claim(uuid,jsonb,text,uuid)','EXECUTE')
             AND NOT has_function_privilege(current_user,'eid_task_finish_inventory(uuid,uuid)','EXECUTE')
             AND NOT has_table_privilege(current_user,'durable_task','UPDATE')
             AND NOT has_table_privilege(current_user,'task_result','INSERT')
             AND NOT has_table_privilege(current_user,'task_attempt_stage','INSERT')
             AND NOT has_table_privilege(current_user,'task_scheduler_lease','UPDATE')
             AND NOT has_table_privilege(current_user,'task_effect_intent','INSERT')
             AND NOT has_table_privilege(current_user,'discovery_record','SELECT')
             AND NOT has_table_privilege(current_user,'task_notification','SELECT')
             AND NOT has_table_privilege(current_user,'task_notification','UPDATE')
             AND NOT has_table_privilege(current_user,'task_observation_binding','SELECT')
             AND NOT has_table_privilege(current_user,'task_event','SELECT')
             AND has_function_privilege(current_user,'eid_search_pending_v1(boolean,boolean)','EXECUTE')
             AND has_function_privilege(current_user,'eid_search_index_v1(uuid,integer,integer,text,text,text,text)','EXECUTE')
             AND NOT has_table_privilege(current_user,'attachment_search_index','SELECT')
             AND has_function_privilege(current_user,'eid_attachment_pending_v1()','EXECUTE')
             AND has_function_privilege(current_user,'eid_attachment_claim_v1(uuid,uuid)','EXECUTE')
             AND has_function_privilege(current_user,'eid_attachment_finish_v1(uuid,uuid,text,jsonb,text)','EXECUTE')
             AND NOT has_table_privilege(current_user,'attachment','SELECT')
             AND NOT has_table_privilege(current_user,'attachment_page','INSERT')
             AND has_function_privilege(current_user,'eid_template_validation_pending_v1()','EXECUTE')
             AND has_function_privilege(current_user,'eid_template_validation_claim_v1(uuid,uuid)','EXECUTE')
             AND has_function_privilege(current_user,'eid_template_validation_finish_v1(uuid,uuid,jsonb,text)','EXECUTE')
             AND NOT has_table_privilege(current_user,'template_candidate','SELECT')
             AND NOT has_table_privilege(current_user,'template_validation','UPDATE')
             AND NOT has_table_privilege(current_user,'template_version','SELECT')
             AND NOT has_table_privilege(current_user,'document_version','SELECT')
             AND NOT has_table_privilege(current_user,'document_outline_version','SELECT')
             AND has_function_privilege(current_user,'eid_model_pending_v1()','EXECUTE')
             AND NOT has_table_privilege(current_user,'model_generation_run','SELECT')
             AND NOT has_table_privilege(current_user,'section_generation_job','SELECT')
             AND NOT has_table_privilege(current_user,'copilot_run','SELECT')
             AND has_function_privilege(current_user,'eid_section_generation_pending_v1()','EXECUTE')
             AND has_function_privilege(current_user,'eid_review_pending_v1()','EXECUTE')
             AND NOT has_table_privilege(current_user,'review_run','SELECT')
             AND NOT has_table_privilege(current_user,'review_result','INSERT')
             AND NOT has_table_privilege(current_user,'review_issue','INSERT')
             AND NOT has_table_privilege(current_user,'model_policy_version','SELECT')
             AND NOT has_table_privilege(current_user,'model_policy_active','SELECT')
             AND NOT has_table_privilege(current_user,'section_evidence_pack','SELECT')
             AND NOT has_table_privilege(current_user,'section_evidence_job','UPDATE')
             AND NOT has_table_privilege(current_user,'document','INSERT')
             AND NOT has_function_privilege(current_user,
                 'eid_notification_mark_read_v1(uuid,uuid)','EXECUTE')
             AND NOT has_function_privilege(current_user,
                 'eid_task_cancel_observed_v1(uuid,uuid,text)','EXECUTE')
             AND NOT has_function_privilege(current_user,
                 'eid_task_bind_observation_v1(uuid,uuid,uuid[])','EXECUTE')
             AND NOT has_function_privilege(current_user,
                 'eid_lock_document_knowledge_scope_v1(uuid,text)','EXECUTE')
             AND NOT has_function_privilege(current_user,
                 'eid_lock_template_creation_v1(uuid,uuid)','EXECUTE')
            """).fetchone()
        if task_grants != (True,):
            raise RuntimeError("Worker task privileges do not match")
    marker = marker_row[0] if marker_row else None
    expected_marker = os.getenv("EID_ENVIRONMENT_MARKER", "eid-local-dev-v1")
    expected_revision = os.getenv("EID_REQUIRED_SCHEMA_REVISION", "0028_review_dispositions")
    if marker != expected_marker:
        raise RuntimeError("Worker database environment marker does not match")
    if revision_rows != [(expected_revision,)]:
        raise RuntimeError("Worker database schema revision does not match")


def _redis_probe(operation_timeout: float) -> None:
    client = None
    try:
        client = redis.from_url(
            os.environ["EID_REDIS_URL"],
            socket_connect_timeout=operation_timeout,
            socket_timeout=operation_timeout,
        )
        if not client.ping():
            raise RuntimeError("Redis readiness probe failed")
    finally:
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def _s3_probe(operation_timeout: float) -> None:
    client = None
    try:
        client = boto3.client(
            "s3",
            endpoint_url=os.environ["EID_S3_ENDPOINT_URL"],
            aws_access_key_id=os.environ["EID_S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["EID_S3_SECRET_KEY"],
            config=Config(
                connect_timeout=operation_timeout,
                read_timeout=operation_timeout,
                retries={"max_attempts": 0},
            ),
        )
        client.head_bucket(Bucket=os.environ["EID_S3_BUCKET"])
    finally:
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def _release_dependency_capacity(_future: Future[None]) -> None:
    _DEPENDENCY_CAPACITY.release()


def verify_dependencies(*, timeout_seconds: float = 2.0, **_kwargs):
    timeout_seconds = min(max(float(timeout_seconds), 0.5), 5.0)
    operation_timeout = min(timeout_seconds / 2, 1.0)
    deadline = time.monotonic() + timeout_seconds
    probes = {
        "postgres": lambda: _database_probe(operation_timeout),
        "redis": lambda: _redis_probe(operation_timeout),
        "s3": lambda: _s3_probe(operation_timeout),
    }
    futures: dict[Future[None], str] = {}

    for name in DEPENDENCY_PROBE_NAMES:
        remaining = max(0.0, deadline - time.monotonic())
        if not _DEPENDENCY_CAPACITY.acquire(timeout=remaining):
            for future in futures:
                future.cancel()
            raise RuntimeError("Worker dependency probe capacity exhausted")
        try:
            future = _DEPENDENCY_EXECUTOR.submit(probes[name])
        except Exception:
            _DEPENDENCY_CAPACITY.release()
            for submitted in futures:
                submitted.cancel()
            raise
        future.add_done_callback(_release_dependency_capacity)
        futures[future] = name

    remaining = max(0.0, deadline - time.monotonic())
    completed, pending = wait(futures, timeout=remaining)
    if pending:
        for future in pending:
            future.cancel()
        raise RuntimeError("Worker dependency probe deadline exceeded")
    for name in DEPENDENCY_PROBE_NAMES:
        next(future for future, probe_name in futures.items() if probe_name == name).result()


@Panel.register(name="dependency_readiness")
def dependency_readiness(_state, timeout_seconds: float = 2.0, **_kwargs):
    try:
        if _RELAY_READY is None or not _RELAY_READY.is_set():
            raise RuntimeError("Durable relay is unavailable")
        verify_dependencies(timeout_seconds=timeout_seconds)
    except Exception:
        return {"status": "unavailable"}
    return {"status": "ready"}


@Panel.register(name="current_access")
def check_current_access(_state, delegation_id: str, operation: str, purpose: str, **_kwargs):
    from .access import current_access
    try:
        context = current_access(delegation_id, operation, purpose)
    except Exception:
        return {"status": "denied"}
    return {"status": "allowed", "context": context.payload()}
