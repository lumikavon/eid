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
from kombu import Queue
from botocore.config import Config

broker = os.environ["EID_RABBITMQ_URL"]
app = Celery("edw_worker", broker=broker)
app.conf.update(
    task_default_queue="integration",
    task_queues=tuple(
        Queue(name, durable=True, queue_arguments={"x-queue-type": "quorum"})
        for name in ("generation", "retrieval", "review", "parse_ocr", "render", "integration")
    ),
    broker_transport_options={"confirm_publish": True},
    task_serializer="json",
    accept_content=["json"],
    worker_send_task_events=True,
)

DEPENDENCY_PROBE_NAMES = ("postgres", "redis", "s3")
DEPENDENCY_PROBE_CAPACITY = len(DEPENDENCY_PROBE_NAMES) * 2
_DEPENDENCY_EXECUTOR = ThreadPoolExecutor(max_workers=len(DEPENDENCY_PROBE_NAMES))
_DEPENDENCY_CAPACITY = threading.BoundedSemaphore(DEPENDENCY_PROBE_CAPACITY)


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
    marker = marker_row[0] if marker_row else None
    expected_marker = os.getenv("EID_ENVIRONMENT_MARKER", "eid-local-dev-v1")
    expected_revision = os.getenv("EID_REQUIRED_SCHEMA_REVISION", "0002_worker_metadata_only")
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
        verify_dependencies(timeout_seconds=timeout_seconds)
    except Exception:
        return {"status": "unavailable"}
    return {"status": "ready"}
