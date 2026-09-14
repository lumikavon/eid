import importlib
import os
import threading
import time

import pytest
from botocore.exceptions import ClientError


os.environ.setdefault(
    "EID_RABBITMQ_URL",
    "amqp://eid_worker:local-worker-only@rabbitmq:5672/eid-local",
)

worker_app = importlib.import_module("edw_worker.app")
worker_main = importlib.import_module("edw_worker.__main__")
worker_health = importlib.import_module("edw_worker.health")


class QueryResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        if isinstance(self.value, tuple):
            return self.value
        return (self.value,)

    def fetchall(self):
        return self.value


class Connection:
    def __init__(
        self,
        marker: str,
        revision: str | list[tuple[str]] = "0006_api_write_only",
        user: str = "eid_worker",
        database: str = "eid_local_dev",
    ):
        self.marker = marker
        self.revisions = [(revision,)] if isinstance(revision, str) else revision
        self.user = user
        self.database = database
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, params=None):
        self.queries.append(sql)
        if "current_database(), current_user" in sql:
            return QueryResult((self.database, self.user))
        if "shobj_description" in sql:
            return QueryResult(self.marker)
        if "alembic_version" in sql:
            return QueryResult(self.revisions)
        if "eid_worker_access" in sql:
            assert params == ("00000000-0000-0000-0000-000000000000",)
            return QueryResult(None)
        raise AssertionError(f"unexpected query: {sql}")


def configure_non_database_dependencies(monkeypatch):
    class RedisClient:
        def ping(self):
            return True

    class S3Client:
        def head_bucket(self, *, Bucket):
            assert Bucket == "eid-local-artifacts"

    monkeypatch.setattr(worker_app.redis, "from_url", lambda *_args, **_kwargs: RedisClient())
    monkeypatch.setattr(worker_app.boto3, "client", lambda *_args, **_kwargs: S3Client())
    monkeypatch.setenv("EID_DATABASE_URL", "postgresql://worker@postgres/eid_local_dev")
    monkeypatch.setenv("EID_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("EID_S3_ENDPOINT_URL", "http://seaweedfs:8333")
    monkeypatch.setenv("EID_S3_ACCESS_KEY", "eid-s3-worker")
    monkeypatch.setenv("EID_S3_SECRET_KEY", "local-s3-worker-read-only")
    monkeypatch.setenv("EID_S3_BUCKET", "eid-local-artifacts")


def test_worker_dependency_gate_accepts_exact_marker_and_revision(monkeypatch):
    configure_non_database_dependencies(monkeypatch)
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(
            "eid-local-dev-v1",
            "0006_api_write_only",
        ),
    )

    worker_app.verify_dependencies()


def test_worker_readiness_rejects_missing_authorization_execute(monkeypatch):
    configure_non_database_dependencies(monkeypatch)
    class MissingExecute(Connection):
        def execute(self, sql, params=None):
            if "eid_worker_access" in sql:
                raise worker_app.psycopg.errors.InsufficientPrivilege()
            return super().execute(sql, params)
    monkeypatch.setattr(worker_app.psycopg, "connect", lambda *a, **k: MissingExecute("eid-local-dev-v1"))
    with pytest.raises(worker_app.psycopg.errors.InsufficientPrivilege):
        worker_app._database_probe(1)


def test_worker_effective_configuration_preserves_delivery_guarantees():
    expected_queues = {
        "generation",
        "retrieval",
        "review",
        "parse_ocr",
        "render",
        "integration",
    }
    queues = worker_app.app.conf.task_queues

    assert len(queues) == 6
    assert {queue.name for queue in queues} == expected_queues
    assert all(queue.durable is True for queue in queues)
    assert all(queue.queue_arguments == {"x-queue-type": "quorum"} for queue in queues)
    assert worker_app.app.conf.task_default_queue == "integration"
    assert worker_app.app.conf.broker_transport_options["confirm_publish"] is True
    assert worker_app.app.conf.task_serializer == "json"
    assert worker_app.app.conf.accept_content == ["json"]
    assert worker_app.app.conf.worker_send_task_events is True


def test_control_readiness_rechecks_dependencies_after_startup_failure_and_recovery(
    monkeypatch,
):
    configure_non_database_dependencies(monkeypatch)
    database = {
        "marker": "eid-local-dev-v1",
        "revision": "0006_api_write_only",
    }
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(database["marker"], database["revision"]),
    )

    assert worker_app.dependency_readiness(None) == {"status": "ready"}
    database["revision"] = "0000_stale"
    assert worker_app.dependency_readiness(None) == {"status": "unavailable"}
    database["revision"] = "0006_api_write_only"
    assert worker_app.dependency_readiness(None) == {"status": "ready"}


def test_control_readiness_returns_only_sanitized_failure(monkeypatch):
    monkeypatch.setattr(
        worker_app,
        "verify_dependencies",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("password=worker-database-secret")),
    )

    result = worker_app.dependency_readiness(None)

    assert result == {"status": "unavailable"}
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    ("marker", "revision", "message"),
    [
        ("foreign-environment", "0006_api_write_only", "environment marker"),
        ("eid-local-dev-v1", "0000_stale", "schema revision"),
    ],
)
def test_worker_dependency_gate_rejects_wrong_database_identity(
    monkeypatch,
    marker,
    revision,
    message,
):
    configure_non_database_dependencies(monkeypatch)
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(marker, revision),
    )

    with pytest.raises(RuntimeError, match=message):
        worker_app.verify_dependencies()


@pytest.mark.parametrize(
    ("database", "user"),
    [
        ("foreign_database", "eid_worker"),
        ("eid_local_dev", "postgres"),
    ],
)
def test_worker_dependency_gate_rejects_wrong_connection_identity_before_schema_queries(
    monkeypatch,
    database,
    user,
):
    configure_non_database_dependencies(monkeypatch)
    connection = Connection(
        "eid-local-dev-v1",
        "0006_api_write_only",
        user=user,
        database=database,
    )
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: connection,
    )

    with pytest.raises(RuntimeError, match="Worker database identity mismatch"):
        worker_app._database_probe(1.0)

    assert connection.queries == ["SELECT current_database(), current_user"]


@pytest.mark.parametrize(
    "revisions",
    [
        [],
        [("0000_stale",)],
        [("0006_api_write_only",), ("0002_divergent",)],
    ],
)
def test_worker_dependency_gate_requires_exactly_one_expected_revision(
    monkeypatch,
    revisions,
):
    configure_non_database_dependencies(monkeypatch)
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection("eid-local-dev-v1", revisions),
    )

    with pytest.raises(RuntimeError, match="schema revision"):
        worker_app.verify_dependencies()


def test_worker_dependency_gate_rejects_redis_failure(monkeypatch):
    configure_non_database_dependencies(monkeypatch)
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(
            "eid-local-dev-v1",
            "0006_api_write_only",
        ),
    )
    monkeypatch.setattr(
        worker_app.redis,
        "from_url",
        lambda *_args, **_kwargs: type("RedisClient", (), {"ping": lambda self: False})(),
    )

    with pytest.raises(RuntimeError, match="Redis readiness probe failed"):
        worker_app.verify_dependencies()


def test_worker_dependency_gate_rejects_s3_client_error(monkeypatch):
    configure_non_database_dependencies(monkeypatch)
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(
            "eid-local-dev-v1",
            "0006_api_write_only",
        ),
    )

    class S3Client:
        def head_bucket(self, *, Bucket):
            raise ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "missing"}},
                "HeadBucket",
            )

    monkeypatch.setattr(worker_app.boto3, "client", lambda *_args, **_kwargs: S3Client())

    with pytest.raises(ClientError) as exc_info:
        worker_app.verify_dependencies()
    assert exc_info.value.response["Error"]["Code"] == "NoSuchBucket"


def test_worker_dependency_clients_close_after_success(monkeypatch):
    configure_non_database_dependencies(monkeypatch)
    observed = set()
    monkeypatch.setattr(
        worker_app.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(
            "eid-local-dev-v1",
            "0006_api_write_only",
        ),
    )

    class RedisClient:
        def ping(self):
            return True

        def close(self):
            observed.add("redis")

    class S3Client:
        def head_bucket(self, *, Bucket):
            assert Bucket == "eid-local-artifacts"

        def close(self):
            observed.add("s3")

    monkeypatch.setattr(worker_app.redis, "from_url", lambda *_args, **_kwargs: RedisClient())
    monkeypatch.setattr(worker_app.boto3, "client", lambda *_args, **_kwargs: S3Client())

    worker_app.verify_dependencies()

    assert observed == {"redis", "s3"}


def test_worker_dependency_gate_has_shared_deadline_and_bounded_capacity(monkeypatch):
    release = threading.Event()
    all_finished = threading.Event()
    finished = 0
    lock = threading.Lock()

    def stalled(_operation_timeout):
        nonlocal finished
        try:
            release.wait(timeout=2)
        finally:
            with lock:
                finished += 1
                if finished == len(worker_app.DEPENDENCY_PROBE_NAMES):
                    all_finished.set()

    monkeypatch.setattr(worker_app, "_database_probe", stalled)
    monkeypatch.setattr(worker_app, "_redis_probe", stalled)
    monkeypatch.setattr(worker_app, "_s3_probe", stalled)

    started_at = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match="deadline exceeded"):
            worker_app.verify_dependencies(timeout_seconds=0.5)
        assert time.monotonic() - started_at < 0.8
        assert worker_app.DEPENDENCY_PROBE_CAPACITY == 6
    finally:
        release.set()
        assert all_finished.wait(timeout=1)


def test_worker_entrypoint_injects_stable_node_name(monkeypatch):
    monkeypatch.setenv("EID_WORKER_NODE_NAME", "eid-worker@worker")

    assert worker_main.worker_arguments(["worker", "--concurrency=1"]) == [
        "worker",
        "--concurrency=1",
        "--hostname=eid-worker@worker",
    ]
    custom_arguments = worker_main.worker_arguments(
        ["worker", "--hostname=custom@node", "--concurrency=1"]
    )
    assert "--hostname=eid-worker@worker" not in custom_arguments


def test_worker_main_runs_dependency_gate_before_consumer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker_main,
        "register_worker_log_safety",
        lambda: calls.append("log-safety"),
    )
    monkeypatch.setattr(worker_main, "verify_dependencies", lambda: calls.append("gate"))
    monkeypatch.setattr(
        worker_main.app,
        "worker_main",
        lambda arguments: calls.append(("consumer", arguments)),
    )
    monkeypatch.setattr(worker_main.sys, "argv", ["edw-worker", "worker", "--concurrency=1"])

    worker_main.main()

    assert calls == [
        "log-safety",
        "gate",
        ("consumer", ["worker", "--concurrency=1", "--hostname=eid-worker@worker"]),
    ]


def test_worker_main_gate_failure_blocks_consumer(monkeypatch):
    consumer_started = False

    def reject_dependencies():
        raise RuntimeError("dependency gate rejected startup")

    def start_consumer(_arguments):
        nonlocal consumer_started
        consumer_started = True

    monkeypatch.setattr(worker_main, "verify_dependencies", reject_dependencies)
    monkeypatch.setattr(worker_main.app, "worker_main", start_consumer)

    with pytest.raises(RuntimeError, match="dependency gate rejected startup"):
        worker_main.main()
    assert consumer_started is False


def test_worker_health_requires_directed_dependency_readiness(monkeypatch):
    monkeypatch.setenv("EID_WORKER_NODE_NAME", "eid-worker@worker")
    observed = {}

    def broadcast(*args, **kwargs):
        observed["command"] = args[0]
        observed.update(kwargs)
        return [{"eid-worker@worker": {"status": "ready"}}]

    monkeypatch.setattr(
        worker_health.app.control,
        "broadcast",
        broadcast,
    )
    assert worker_health.worker_is_ready() is True
    assert observed["command"] == "dependency_readiness"
    assert observed["destination"] == ["eid-worker@worker"]
    assert observed["reply"] is True
    assert observed["arguments"]["timeout_seconds"] < observed["timeout"]

    monkeypatch.setattr(
        worker_health.app.control,
        "broadcast",
        lambda *_args, **_kwargs: [{"eid-worker@worker": {"status": "unavailable"}}],
    )
    assert worker_health.worker_is_ready() is False


@pytest.mark.parametrize(
    "reply",
    [
        [],
        [{"other@worker": {"status": "ready"}}],
        [{"eid-worker@worker": {"ok": "pong"}}],
        [{"eid-worker@worker": {"status": "ready", "detail": "secret"}}],
        [
            {"eid-worker@worker": {"status": "ready"}},
            {"eid-worker@worker": {"status": "ready"}},
        ],
    ],
)
def test_worker_health_fails_closed_for_unexpected_control_reply(monkeypatch, reply):
    monkeypatch.setattr(
        worker_health.app.control,
        "broadcast",
        lambda *_args, **_kwargs: reply,
    )

    assert worker_health.worker_is_ready() is False


def test_worker_health_rejects_deadline_too_short_for_dependency_probe(monkeypatch):
    monkeypatch.setenv("EID_WORKER_HEALTH_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr(
        worker_health.app.control,
        "broadcast",
        lambda *_args, **_kwargs: pytest.fail("control command must not be dispatched"),
    )

    assert worker_health.worker_is_ready() is False
