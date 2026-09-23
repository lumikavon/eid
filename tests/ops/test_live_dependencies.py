"""显式运行的隔离远端基础设施验收；不使用网络或数据库替身。"""

import os
import time

import httpx
import psycopg
import pytest
from celery import Celery

from scripts.remote_service_operations import captured_runtime, stopped_service
from scripts.verify_local_environment import (
    RABBITMQ_ADMIN_PASSWORD,
    RABBITMQ_ADMIN_USER,
    development_database_url,
    verify_database,
    verify_rabbitmq,
)

pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1", reason="需要显式隔离环境验收"
)


def test_real_dependency_health():
    verify_database(development_database_url())
    response = httpx.get("http://localhost:18080/health/ready", timeout=20)
    assert response.status_code == 200
    assert set(response.json()["checks"].values()) == {"ready"}
    denied = httpx.get(
        "http://localhost:18080/api/v1/me", headers={"Authorization": "Bearer invalid"}, timeout=10
    )
    assert denied.status_code == 401


def test_real_worker_has_stable_observable_identity():
    probe = Celery(
        "eid_live_worker_probe",
        broker="amqp://eid_worker:local-worker-only@localhost:55672/eid-local",
    )
    try:
        replies = probe.control.ping(destination=["eid-worker@worker"], timeout=5)
    finally:
        probe.close()
    assert replies == [{"eid-worker@worker": {"ok": "pong"}}]


def test_real_worker_reports_its_own_dependencies_ready():
    probe = Celery(
        "eid_live_worker_dependency_probe",
        broker="amqp://eid_worker:local-worker-only@localhost:55672/eid-local",
    )
    try:
        replies = probe.control.broadcast(
            "dependency_readiness",
            arguments={"timeout_seconds": 3},
            destination=["eid-worker@worker"],
            reply=True,
            timeout=5,
        )
    finally:
        probe.close()
    assert replies == [{"eid-worker@worker": {"status": "ready"}}]


def test_consumed_worker_queues_are_durable_quorum_queues():
    verify_database(development_database_url())
    verify_rabbitmq()
    auth = httpx.BasicAuth(RABBITMQ_ADMIN_USER, RABBITMQ_ADMIN_PASSWORD)
    with httpx.Client(
        base_url="http://localhost:55673",
        auth=auth,
        timeout=httpx.Timeout(5),
    ) as client:
        for queue_name in ("generation", "retrieval", "review", "integration"):
            response = client.get(f"/api/queues/eid-local/{queue_name}")
            assert response.status_code == 200
            queue = response.json()
            assert queue["name"] == queue_name
            assert queue["vhost"] == "eid-local"
            assert queue["durable"] is True
            assert queue["arguments"].get("x-queue-type") == "quorum"


def test_database_loss_denies_readiness_and_recovers():
    verify_database(development_database_url())
    with stopped_service("postgres"):
        assert httpx.get("http://localhost:18080/health/live", timeout=5).status_code == 200
        response = httpx.get("http://localhost:18080/health/ready", timeout=20)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DEPENDENCY_NOT_READY"
    for _ in range(30):
        if httpx.get("http://localhost:18080/health/ready", timeout=20).status_code == 200:
            break
        time.sleep(1)
    else:
        pytest.fail("数据库恢复后未重新就绪")


def test_worker_identity_can_read_metadata_but_not_identity_workspace_data():
    verify_database(development_database_url())
    with psycopg.connect(
        development_database_url("eid_worker").replace("postgresql+psycopg:", "postgresql:"),
        connect_timeout=3,
    ) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchall() == [("0008_durable_submission",)]
        for table in ("identity_account", "workspace", "workspace_membership"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {table} LIMIT 0")
            conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE workspace_membership SET active = false")
        conn.rollback()
        for statement in (
            "UPDATE access_member SET clearance=3 WHERE false",
            "UPDATE access_resource SET head_ref=NULL WHERE false",
            "UPDATE access_resource SET approval_state='approved' WHERE false",
            "UPDATE access_resource SET publication_state='published' WHERE false",
            "UPDATE access_delegation SET active=true WHERE false",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
            conn.rollback()


def test_worker_loss_denies_readiness_and_recovers():
    verify_database(development_database_url())
    with stopped_service("worker"):
        assert httpx.get("http://localhost:18080/health/live", timeout=5).status_code == 200
        response = httpx.get("http://localhost:18080/health/ready", timeout=20)
        assert response.status_code == 503
        assert response.json()["error"]["details"]["checks"]["worker"] == "unavailable"
    for _ in range(30):
        if httpx.get("http://localhost:18080/health/ready", timeout=20).status_code == 200:
            break
        time.sleep(1)
    else:
        pytest.fail("Worker 恢复后未重新就绪")


def test_public_entrypoint_preserves_request_and_trace_ids():
    request_id = "story-1-1-correlation"
    trace = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    response = httpx.get(
        "http://localhost:18080/api/v1/me",
        headers={
            "X-Request-ID": request_id,
            "traceparent": trace,
        },
        timeout=10,
    )
    assert response.status_code == 401
    assert response.headers["x-request-id"] == request_id
    assert response.headers["traceparent"] == trace
    assert response.json()["error"]["request_id"] == request_id
    assert response.json()["error"]["trace_id"] == trace.split("-")[1]


def test_running_worker_database_identity_loss_and_recovery():
    verify_database(development_database_url())
    runtime = captured_runtime()
    with psycopg.connect(
        development_database_url("postgres").replace("postgresql+psycopg:", "postgresql:"),
        connect_timeout=3,
        autocommit=True,
    ) as admin:
        assert admin.execute(
            "SELECT rolcanlogin FROM pg_roles WHERE rolname = 'eid_worker'"
        ).fetchone() == (True,)
        try:
            admin.execute("ALTER ROLE eid_worker NOLOGIN")
            assert httpx.get("http://localhost:18080/health/live", timeout=5).status_code == 200
            response = httpx.get("http://localhost:18080/health/ready", timeout=20)
            assert response.status_code == 503
            checks = response.json()["error"]["details"]["checks"]
            assert checks["postgres"] == "ready"
            assert checks["worker"] == "unavailable"
            assert runtime.run("worker", "worker-health")["returncode"] == 1
        finally:
            admin.execute("ALTER ROLE eid_worker LOGIN")
    for _ in range(15):
        if httpx.get("http://localhost:18080/health/ready", timeout=20).status_code == 200:
            break
        time.sleep(1)
    else:
        pytest.fail("Worker database identity recovery did not restore readiness")
    assert runtime.run("worker", "worker-health")["returncode"] == 0
