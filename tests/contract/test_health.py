import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import edw_api.main as main
import edw_api.db as db


ROOT = Path(__file__).parents[2]
PUBLIC_OIDC_ISSUER = "http://localhost:18080/realms/eid-local"


@main.app.get("/_contract/validation/{value}")
def validation_probe(value: int):
    return {"value": value}


CLIENT = TestClient(main.app)
REAL_SCHEDULER_STATUS = main._scheduler_status


@pytest.fixture(autouse=True)
def ready_scheduler_for_unrelated_health_contracts(monkeypatch):
    monkeypatch.setattr(main, "_scheduler_status", lambda: "ready")


def assert_contract(name: str, payload: dict) -> None:
    schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def ready_checks() -> dict[str, str]:
    return {
        "postgres": "ready",
        "redis": "ready",
        "rabbitmq": "ready",
        "s3": "ready",
        "keycloak": "ready",
        "worker": "ready",
        "scheduler": "ready",
    }


class QueryResult:
    def __init__(self, row=None, *, rows=None):
        self.row = row
        self.rows = ([] if row is None else [row]) if rows is None else rows

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_live_is_process_only():
    response = CLIENT.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["X-Request-ID"]
    assert response.headers["traceparent"].split("-")[1]
    assert_contract("health.schema.json", response.json())


def test_ready_success_matches_checked_in_schema(monkeypatch):
    monkeypatch.setattr(main, "readiness", lambda: (True, ready_checks()))

    response = CLIENT.get("/health/ready")

    assert response.status_code == 200
    assert_contract("health.schema.json", response.json())


def test_me_success_matches_schema_and_includes_workspace_fields(monkeypatch):
    account = {
        "actor_id": "11111111-1111-4111-8111-111111111111",
        "subject": "actor",
        "display_name": "本地项目成员",
        "department": "产品部",
        "workspace_id": "22222222-2222-4222-8222-222222222222",
        "workspace_slug": "eid-local",
        "workspace_name": "企业智能文档工作区",
    }
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject="actor"))
    monkeypatch.setattr(main, "current_account", lambda _settings, _subject: account)

    response = CLIENT.get("/api/v1/me", headers={"Authorization": "Bearer valid"})

    assert response.status_code == 200
    assert set(response.json()["data"]) >= {
        "workspace_id",
        "workspace_slug",
        "workspace_name",
    }
    assert_contract("me.schema.json", response.json())


def test_missing_bearer_is_structured_and_correlated():
    traceparent = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    response = CLIENT.get(
        "/api/v1/me",
        headers={"X-Request-ID": "contract-1", "traceparent": traceparent},
    )

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "contract-1"
    assert response.headers["traceparent"] == traceparent
    assert response.json()["error"]["trace_id"] == traceparent.split("-")[1]
    assert response.json()["error"]["retryable"] is False
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize(
    ("method", "path", "status_code", "code"),
    [
        ("GET", "/api/v1/does-not-exist", 404, "ROUTE_NOT_FOUND"),
        ("POST", "/api/v1/me", 405, "METHOD_NOT_ALLOWED"),
    ],
)
def test_framework_http_errors_are_structured_and_correlated(
    method,
    path,
    status_code,
    code,
):
    traceparent = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    response = CLIENT.request(
        method,
        path,
        headers={"X-Request-ID": "framework-error", "traceparent": traceparent},
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == "framework-error"
    assert response.json()["error"]["trace_id"] == traceparent.split("-")[1]
    assert "detail" not in response.json()
    if status_code == 405:
        assert response.headers["allow"] == "GET"
    assert_contract("error.schema.json", response.json())


def test_framework_validation_error_is_redacted_structured_and_correlated():
    response = CLIENT.get(
        "/_contract/validation/not-an-integer",
        headers={"X-Request-ID": "validation-error"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.json()["error"]["request_id"] == "validation-error"
    assert "not-an-integer" not in response.text
    assert "input" not in response.text
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize(
    "incoming",
    [
        "invalid",
        "00-" + "0" * 32 + "-1234567890abcdef-01",
        "00-1234567890abcdef1234567890abcdef-" + "0" * 16 + "-01",
    ],
)
def test_invalid_traceparent_is_replaced_by_valid_correlated_trace(incoming):
    response = CLIENT.get("/api/v1/me", headers={"traceparent": incoming})

    generated = response.headers["traceparent"]
    assert main.TRACEPARENT_RE.fullmatch(generated)
    assert generated != incoming
    assert generated.split("-")[1] != "0" * 32
    assert generated.split("-")[2] != "0" * 16
    assert response.json()["error"]["trace_id"] == generated.split("-")[1]
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize("incoming", ["a" * 129, "bad request/id"])
def test_invalid_request_id_is_replaced_and_correlated(incoming):
    response = CLIENT.get("/api/v1/me", headers={"X-Request-ID": incoming})
    generated = response.headers["X-Request-ID"]
    assert generated != incoming
    assert 0 < len(generated) <= 128
    assert main.re.fullmatch(r"[A-Za-z0-9._-]+", generated)
    assert response.json()["error"]["request_id"] == generated
    assert_contract("error.schema.json", response.json())


def test_missing_workspace_is_structured_403(monkeypatch):
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject="actor"))
    monkeypatch.setattr(main, "current_account", lambda _settings, _subject: None)

    response = CLIENT.get("/api/v1/me", headers={"Authorization": "Bearer valid"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WORKSPACE_ACCESS_DENIED"
    assert_contract("error.schema.json", response.json())


def test_dependency_failure_is_structured_retryable_503(monkeypatch):
    checks = ready_checks()
    checks["worker"] = "unavailable"
    monkeypatch.setattr(main, "readiness", lambda: (False, checks))

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"checks": checks}
    assert response.json()["error"]["retryable"] is True
    assert_contract("error.schema.json", response.json())


def test_probe_timeout_is_structured_retryable_503_with_exact_checks(monkeypatch):
    release = threading.Event()

    monkeypatch.setattr(main, "READINESS_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(main, "_postgres_status", lambda: release.wait(timeout=1) or "ready")
    for name in ("redis", "rabbitmq", "s3", "keycloak", "worker"):
        monkeypatch.setattr(main, f"_{name}_status", lambda: "ready")

    try:
        response = CLIENT.get("/health/ready")
    finally:
        release.set()

    checks = response.json()["error"]["details"]["checks"]
    assert response.status_code == 503
    assert tuple(checks) == main.READINESS_PROBE_NAMES
    assert checks["postgres"] == "timeout"
    assert response.json()["error"]["retryable"] is True
    assert_contract("error.schema.json", response.json())


def test_simultaneous_stalled_readiness_calls_share_deadline_and_cancel_queued_probes(
    monkeypatch,
):
    release = threading.Event()
    all_workers_started = threading.Event()
    started = 0
    started_lock = threading.Lock()
    first_result = []

    def stalled_probe():
        nonlocal started
        with started_lock:
            started += 1
            if started == len(main.READINESS_PROBE_NAMES):
                all_workers_started.set()
        release.wait(timeout=2)
        return "ready"

    monkeypatch.setattr(main, "READINESS_DEADLINE_SECONDS", 0.2)
    for name in main.READINESS_PROBE_NAMES:
        monkeypatch.setattr(main, f"_{name}_status", stalled_probe)

    first = threading.Thread(target=lambda: first_result.append(main.readiness()))
    first.start()
    try:
        assert all_workers_started.wait(timeout=1)
        started_at = time.monotonic()
        second_result = main.readiness()
        elapsed = time.monotonic() - started_at
        first.join(timeout=1)

        expected = dict.fromkeys(main.READINESS_PROBE_NAMES, "timeout")
        assert not first.is_alive()
        assert first_result == [(False, expected)]
        assert second_result == (False, expected)
        assert elapsed < 0.8
        assert started == len(main.READINESS_PROBE_NAMES)
    finally:
        release.set()
        first.join(timeout=1)


@pytest.mark.parametrize(
    ("marker", "revision"),
    [
        ("foreign-environment", main.settings.required_schema_revision),
        (main.settings.environment_marker, "0000_stale"),
        ("foreign-environment", "0000_stale"),
    ],
)
def test_postgres_marker_and_revision_mismatch_degrade_readiness(
    monkeypatch,
    marker,
    revision,
):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            if "WITH required(name, privilege)" in query:
                value = True
            else:
                value = revision if "alembic_version" in query else None
            row = (
                ("eid_local_dev", "eid_api", marker)
                if "current_database()" in query
                else (value,)
            )
            return QueryResult(row)

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())
    for name in ("_redis_status", "_rabbitmq_status", "_s3_status", "_keycloak_status", "_worker_status"):
        monkeypatch.setattr(main, name, lambda: "ready")

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert (
        response.json()["error"]["details"]["checks"]["postgres"]
        == "marker_schema_or_privilege_mismatch"
    )
    assert_contract("error.schema.json", response.json())


def test_postgres_probe_applies_connect_and_statement_timeouts(monkeypatch):
    observed = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, *_params):
            if "WITH required(name, privilege)" in query:
                value = True
            else:
                value = (
                    main.settings.required_schema_revision
                    if "alembic_version" in query
                    else None
                )
            row = (
                ("eid_local_dev", "eid_api", main.settings.environment_marker)
                if "current_database()" in query
                else (value,)
            )
            return QueryResult(row)

    def connect(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return Connection()

    monkeypatch.setattr(main.psycopg, "connect", connect)

    assert main._postgres_status() == "ready"
    assert observed["kwargs"]["connect_timeout"] == 2
    assert observed["kwargs"]["options"] == "-c statement_timeout=2000"


@pytest.mark.parametrize(
    ("lease_row", "expected"),
    [
        pytest.param((True,), "ready", id="live-lease"),
        pytest.param((False,), "lease_inactive", id="scheduler-absent-or-lease-expired"),
        pytest.param(None, "unavailable", id="malformed-sql-result"),
        pytest.param((1,), "unavailable", id="non-boolean-sql-result"),
    ],
)
def test_scheduler_probe_requires_live_database_lease(monkeypatch, lease_row, expected):
    observed = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            observed.setdefault("queries", []).append(query)
            if "current_database()" in query:
                return QueryResult(("eid_local_dev", "eid_api", main.settings.environment_marker))
            assert query == "SELECT eid_task_scheduler_ready_v2()"
            return QueryResult(lease_row)

    def connect(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return Connection()

    monkeypatch.setattr(main.psycopg, "connect", connect)

    assert REAL_SCHEDULER_STATUS() == expected
    assert observed["args"] == (main.settings.database_url,)
    assert observed["kwargs"] == {
        "connect_timeout": 2,
        "options": "-c statement_timeout=2000",
    }
    assert observed["queries"][-1] == "SELECT eid_task_scheduler_ready_v2()"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (main.psycopg.errors.UndefinedFunction("scheduler function missing"), "marker_schema_or_privilege_mismatch"),
        (main.psycopg.errors.InsufficientPrivilege("scheduler function denied"), "marker_schema_or_privilege_mismatch"),
        (main.psycopg.OperationalError("scheduler query failed"), "unavailable"),
    ],
)
def test_scheduler_probe_fails_closed_on_sql_error(monkeypatch, error, expected):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            if "current_database()" in query:
                return QueryResult(("eid_local_dev", "eid_api", main.settings.environment_marker))
            assert query == "SELECT eid_task_scheduler_ready_v2()"
            raise error

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert REAL_SCHEDULER_STATUS() == expected


def test_scheduler_probe_rejects_wrong_live_database_before_sql_function(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            assert "current_database()" in query
            return QueryResult(("foreign", "eid_api", main.settings.environment_marker))

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert REAL_SCHEDULER_STATUS() == "marker_schema_or_privilege_mismatch"


@pytest.mark.parametrize("scheduler_status", ["lease_inactive", "unavailable"])
def test_scheduler_failure_degrades_api_readiness_separately(monkeypatch, scheduler_status):
    for name in ("postgres", "redis", "rabbitmq", "s3", "keycloak", "worker"):
        monkeypatch.setattr(main, f"_{name}_status", lambda: "ready")
    monkeypatch.setattr(main, "_scheduler_status", lambda: scheduler_status)

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    checks = response.json()["error"]["details"]["checks"]
    assert tuple(checks) == main.READINESS_PROBE_NAMES
    assert checks["scheduler"] == scheduler_status
    assert checks["postgres"] == checks["worker"] == "ready"
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize(
    "revision_rows",
    [
        pytest.param([], id="empty"),
        pytest.param(
            [
                (main.settings.required_schema_revision,),
                ("0002_divergent_head",),
            ],
            id="additional-head",
        ),
        pytest.param([("0000_stale",)], id="wrong-head"),
    ],
)
def test_postgres_probe_requires_exactly_one_expected_alembic_version(
    monkeypatch,
    revision_rows,
):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, *_params):
            if "current_database()" in query:
                return QueryResult(
                    ("eid_local_dev", "eid_api", main.settings.environment_marker)
                )
            if "alembic_version" in query:
                return QueryResult(rows=revision_rows)
            if "WITH required(name, privilege)" in query:
                return QueryResult((True,))
            pytest.fail("account query plan must not run for an invalid migration head set")

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert main._postgres_status() == "marker_schema_or_privilege_mismatch"


@pytest.mark.parametrize("required_access", [False, None])
def test_postgres_probe_requires_identity_tables_and_select_privileges(
    monkeypatch,
    required_access,
):
    queries = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            queries.append(query)
            if "WITH required(name, privilege)" in query:
                value = required_access
            elif "alembic_version" in query:
                value = main.settings.required_schema_revision
            else:
                value = None
            row = (
                ("eid_local_dev", "eid_api", main.settings.environment_marker)
                if "current_database()" in query
                else (value,)
            )
            return QueryResult(row)

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert main._postgres_status() == "marker_schema_or_privilege_mismatch"
    privilege_query = next(query for query in queries if "WITH required(name, privilege)" in query)
    assert "identity_account" in privilege_query
    assert "workspace_membership" in privilege_query
    assert "workspace" in privilege_query
    assert "has_table_privilege" in privilege_query
    for table in ("identity_account", "workspace_membership", "workspace", "access_workspace",
                  "access_member", "access_resource", "access_current_facts"):
        assert f"('{table}','SELECT')" in privilege_query
    for table in ("access_audit", "access_invalidation", "access_delegation"):
        assert f"('{table}','SELECT')" not in privilege_query
    for table, privilege in [("workspace_membership", "UPDATE"), ("access_member", "UPDATE"),
                             ("access_workspace", "UPDATE"), ("access_audit", "INSERT"),
                             ("access_invalidation", "INSERT"), ("access_delegation", "INSERT")]:
        assert f"('{table}','{privilege}')" in privilege_query
    assert "SELECT *" not in privilege_query.upper()


@pytest.mark.parametrize(
    ("failing_query", "error"),
    [
        ("alembic_version", main.psycopg.errors.UndefinedTable("missing alembic_version")),
        (
            "WITH required(name, privilege)",
            main.psycopg.errors.InsufficientPrivilege("cannot inspect required tables"),
        ),
    ],
)
def test_postgres_probe_classifies_schema_and_privilege_errors(
    monkeypatch,
    failing_query,
    error,
):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            if failing_query in query:
                raise error
            row = (
                ("eid_local_dev", "eid_api", main.settings.environment_marker)
                if "current_database()" in query
                else (main.settings.required_schema_revision,)
            )
            return QueryResult(row)

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert main._postgres_status() == "marker_schema_or_privilege_mismatch"


def test_postgres_probe_keeps_connection_failures_unavailable(monkeypatch):
    def connect(*_args, **_kwargs):
        raise main.psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main.psycopg, "connect", connect)

    assert main._postgres_status() == "unavailable"


def test_postgres_probe_rejects_present_tables_with_missing_account_column(monkeypatch):
    from edw_api.access import repository
    queries = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            queries.append((query, params))
            if "current_database()" in query:
                return QueryResult(
                    ("eid_local_dev", "eid_api", main.settings.environment_marker)
                )
            if "alembic_version" in query:
                return QueryResult(rows=[(main.settings.required_schema_revision,)])
            if "WITH required(name, privilege)" in query:
                return QueryResult((True,))
            if query == f"EXPLAIN {repository.CURRENT_WORKSPACE_SQL}":
                assert params == repository.workspace_discovery_params("__readiness_probe__")
                raise main.psycopg.errors.UndefinedColumn(
                    "access_current_facts.approval_states is missing"
                )
            pytest.fail(f"unexpected query: {query}")

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert main.CURRENT_WORKSPACE_SQL is repository.CURRENT_WORKSPACE_SQL
    assert main._postgres_status() == "marker_schema_or_privilege_mismatch"
    assert any(query == f"EXPLAIN {repository.CURRENT_WORKSPACE_SQL}" for query, _params in queries)


@pytest.mark.parametrize(
    ("database_name", "database_user", "marker"),
    [
        ("foreign", "eid_api", "eid-local-dev-v1"),
        ("eid_local_dev", "postgres", "eid-local-dev-v1"),
        ("eid_local_dev", "eid_api", "foreign-marker"),
    ],
)
def test_postgres_probe_rejects_wrong_live_connection_before_schema_queries(
    monkeypatch,
    database_name,
    database_user,
    marker,
):
    queries = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            queries.append(query)
            if "current_database()" in query:
                return QueryResult((database_name, database_user, marker))
            pytest.fail("schema and privilege queries must not run for a wrong database identity")

    monkeypatch.setattr(main.psycopg, "connect", lambda *_args, **_kwargs: Connection())

    assert main._postgres_status() == "marker_schema_or_privilege_mismatch"
    assert len(queries) == 1


def test_account_connection_applies_statement_timeout(monkeypatch):
    observed = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            assert query == "SELECT current_user"
            return QueryResult({"current_user": "eid_api"})

    def connect(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return Connection()

    monkeypatch.setattr(db.psycopg, "connect", connect)

    with db.connection(main.settings):
        pass

    assert observed["kwargs"]["connect_timeout"] == 3
    assert observed["kwargs"]["options"] == "-c statement_timeout=2000"


def test_current_account_uses_current_authorized_workspace_projection(monkeypatch):
    from edw_api.access import repository
    observed = {}
    available = [{"actor_id": "a", "workspace_id": "w", "slug": "project", "name": "Project",
                  "display_name": "Member", "department": "Dept"}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def current_workspaces(conn, subject):
        observed["subject"] = subject
        assert isinstance(conn, Connection)
        return available[0] if available else None

    monkeypatch.setattr(db, "connection", lambda _settings: Connection())
    monkeypatch.setattr(repository, "first_workspace", current_workspaces)
    assert db.current_account(main.settings, "actor") == {
        "actor_id": "a", "subject": "actor", "display_name": "Member", "department": "Dept",
        "workspace_id": "w", "workspace_slug": "project", "workspace_name": "Project"}
    assert observed == {"subject": "actor"}
    available.clear()
    assert db.current_account(main.settings, "actor") is None


def test_account_connection_rejects_wrong_actual_role_before_protected_read(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            assert query == "SELECT current_user"
            return QueryResult({"current_user": "postgres"})

        def cursor(self):
            pytest.fail("protected account query must not run for a wrong database role")

    monkeypatch.setattr(db.psycopg, "connect", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject="actor"))

    response = CLIENT.get("/api/v1/me", headers={"Authorization": "Bearer valid"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert_contract("error.schema.json", response.json())


def test_rabbitmq_exception_degrades_readiness(monkeypatch):
    for name in ("_postgres_status", "_redis_status", "_s3_status", "_keycloak_status", "_worker_status"):
        monkeypatch.setattr(main, name, lambda: "ready")
    monkeypatch.setattr(
        main,
        "BrokerConnection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("broker secret")),
    )

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["rabbitmq"] == "unavailable"
    assert "broker secret" not in response.text
    assert_contract("error.schema.json", response.json())


def test_unexpected_endpoint_exception_is_redacted_correlated_and_safely_logged(
    monkeypatch,
    caplog,
):
    traceparent = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    monkeypatch.setattr(
        main,
        "readiness",
        lambda: (_ for _ in ()).throw(RuntimeError("password=do-not-leak")),
    )

    with caplog.at_level("ERROR", logger=main.__name__):
        response = CLIENT.get(
            "/health/ready",
            headers={"X-Request-ID": "unexpected-500", "traceparent": traceparent},
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "unexpected-500"
    assert response.headers["traceparent"] == traceparent
    assert response.json()["error"] == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "服务暂时无法处理该请求",
        "details": {},
        "request_id": "unexpected-500",
        "trace_id": traceparent.split("-")[1],
        "retryable": False,
    }
    assert "do-not-leak" not in response.text
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "error_type=RuntimeError" in message
        and "request_id=unexpected-500" in message
        and f"trace_id={traceparent.split('-')[1]}" in message
        for message in messages
    )
    assert all("do-not-leak" not in message for message in messages)
    assert_contract("error.schema.json", response.json())


class JwksResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def oidc_response(jwks_payload, discovery_payload=None):
    discovery = (
        {
            "issuer": PUBLIC_OIDC_ISSUER,
            "jwks_uri": f"{PUBLIC_OIDC_ISSUER}/protocol/openid-connect/certs",
        }
        if discovery_payload is None
        else discovery_payload
    )

    def response(url, **_kwargs):
        payload = discovery if url.endswith("/.well-known/openid-configuration") else jwks_payload
        return JwksResponse(payload)

    return response


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"keys": "invalid"},
        {"keys": [{}]},
        {"keys": [{"kid": ["invalid"], "kty": "RSA"}]},
        {"keys": [{"kid": "key-1", "kty": 42}]},
        {"keys": [{"kid": "key-1", "kty": "RSA", "use": ["sig"]}]},
        {"keys": [{"kid": "key-1", "kty": "RSA", "alg": ["RS256"]}]},
        {"keys": [{"kid": "key-1", "kty": "RSA", "key_ops": "verify"}]},
        {"keys": [{"kid": "key-1", "kty": "RSA", "use": "sig", "alg": "RS256"}]},
    ],
)
def test_malformed_jwks_fails_readiness_with_structured_503(monkeypatch, payload):
    for name in (
        "_postgres_status",
        "_redis_status",
        "_rabbitmq_status",
        "_s3_status",
        "_worker_status",
    ):
        monkeypatch.setattr(main, name, lambda: "ready")
    monkeypatch.setattr(main.httpx, "get", oidc_response(payload))

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["keycloak"] == "malformed_jwks"
    assert_contract("error.schema.json", response.json())


def rsa_jwk(*, kid: str, use: str, alg: str) -> dict:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    key.update({"kid": kid, "use": use, "alg": alg})
    return key


@pytest.mark.parametrize(
    "key",
    [
        pytest.param(
            lambda: rsa_jwk(kid="unsupported", use="sig", alg="RS512"),
            id="unsupported-signing-algorithm",
        ),
        pytest.param(
            lambda: rsa_jwk(kid="encryption", use="enc", alg="RSA-OAEP"),
            id="encryption-key-only",
        ),
        pytest.param(
            lambda: {
                **rsa_jwk(kid="wrong-operation", use="sig", alg="RS256"),
                "key_ops": ["encrypt"],
            },
            id="signing-key-without-verify-operation",
        ),
    ],
)
def test_jwks_without_supported_signing_key_fails_readiness(monkeypatch, key):
    monkeypatch.setattr(
        main.httpx,
        "get",
        oidc_response({"keys": [key()]}),
    )

    assert main._keycloak_status() == "usable_signing_key_missing"


def test_jwks_allows_keycloak_encryption_key_beside_usable_rs256_key(monkeypatch):
    payload = {
        "keys": [
            rsa_jwk(kid="encryption", use="enc", alg="RSA-OAEP"),
            rsa_jwk(kid="signing", use="sig", alg="RS256"),
        ]
    }
    monkeypatch.setattr(main.httpx, "get", oidc_response(payload))
    monkeypatch.setattr(main, "_keycloak_client_contract_status", lambda _deadline: "ready")

    assert main._keycloak_status() == "ready"


@pytest.mark.parametrize(
    ("setting_name", "wrong_value", "expected"),
    [
        ("oidc_issuer", "https://wrong-issuer.invalid/realms/eid-local", "issuer_mismatch"),
        ("oidc_audience", "wrong-audience", "audience_mismatch"),
        (
            "oidc_jwks_url",
            "http://keycloak:8080/realms/other/protocol/openid-connect/certs",
            "jwks_url_mismatch",
        ),
    ],
)
def test_runtime_oidc_configuration_mismatch_fails_readiness(
    monkeypatch,
    setting_name,
    wrong_value,
    expected,
):
    for name in (
        "_postgres_status",
        "_redis_status",
        "_rabbitmq_status",
        "_s3_status",
        "_worker_status",
    ):
        monkeypatch.setattr(main, name, lambda: "ready")
    monkeypatch.setattr(main.settings, setting_name, wrong_value)
    monkeypatch.setattr(
        main.httpx,
        "get",
        oidc_response({"keys": [rsa_jwk(kid="signing", use="sig", alg="RS256")]}),
    )

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["keycloak"] == expected
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize(
    ("discovery_payload", "expected"),
    [
        ([], "malformed_discovery"),
        (
            {
                "issuer": "https://wrong-issuer.invalid/realms/eid-local",
                "jwks_uri": "http://localhost:18080/realms/eid-local/protocol/openid-connect/certs",
            },
            "issuer_mismatch",
        ),
        (
            {
                "issuer": "http://localhost:18080/realms/eid-local",
                "jwks_uri": "https://wrong-jwks.invalid/certs",
            },
            "jwks_uri_mismatch",
        ),
    ],
)
def test_public_discovery_mismatch_fails_readiness(monkeypatch, discovery_payload, expected):
    monkeypatch.setattr(
        main.httpx,
        "get",
        oidc_response(
            {"keys": [rsa_jwk(kid="signing", use="sig", alg="RS256")]},
            discovery_payload,
        ),
    )

    assert main._keycloak_status() == expected


def _monitor_token(*roles: str) -> str:
    return jwt.encode(
        {"resource_access": {"realm-management": {"roles": list(roles)}}},
        "test-only-key-material-32-bytes-long",
        algorithm="HS256",
    )


class KeycloakAdminResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.mark.parametrize(
    ("drift", "expected"),
    [
        ("client", "client_configuration_mismatch"),
        ("mapper", "audience_mapper_mismatch"),
    ],
)
def test_persisted_keycloak_client_or_mapper_drift_is_public_503(
    monkeypatch, drift, expected
):
    web_client = {
        "id": "persisted-web-id",
        "clientId": "eid-web",
        "enabled": True,
        "publicClient": True,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "redirectUris": ["http://localhost:18080/auth/callback"],
        "webOrigins": ["http://localhost:18080"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": "http://localhost:18080/",
        },
    }
    mapper = {
        "name": "audience-eid-web",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": {
            "included.client.audience": "eid-web",
            "access.token.claim": "true",
        },
    }
    if drift == "client":
        web_client["directAccessGrantsEnabled"] = True
    else:
        mapper["config"]["included.client.audience"] = "foreign-client"

    observed = {"closed": False, "timeouts": []}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            observed["closed"] = True

        def post(self, path, **kwargs):
            assert path.endswith("/protocol/openid-connect/token")
            observed["timeouts"].append(kwargs["timeout"])
            return KeycloakAdminResponse(
                {
                    "access_token": _monitor_token(
                        "query-clients", "view-clients", "view-realm"
                    )
                }
            )

        def get(self, path, **kwargs):
            observed["timeouts"].append(kwargs["timeout"])
            if path == "/admin/realms/eid-local":
                return KeycloakAdminResponse(
                    {"realm": "eid-local", "registrationAllowed": False}
                )
            if path == "/admin/realms/eid-local/clients":
                return KeycloakAdminResponse([web_client])
            return KeycloakAdminResponse([mapper])

    for name in (
        "_postgres_status",
        "_redis_status",
        "_rabbitmq_status",
        "_s3_status",
        "_worker_status",
    ):
        monkeypatch.setattr(main, name, lambda: "ready")
    monkeypatch.setattr(
        main.httpx,
        "get",
        oidc_response({"keys": [rsa_jwk(kid="signing", use="sig", alg="RS256")]}),
    )
    monkeypatch.setattr(main.httpx, "Client", Client)

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["keycloak"] == expected
    assert observed["closed"] is True
    assert observed["timeouts"] and all(
        0 < timeout <= main.KEYCLOAK_HTTP_TIMEOUT_SECONDS
        for timeout in observed["timeouts"]
    )
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize(
    ("token_status", "roles", "realm_status", "expected"),
    [
        (401, (), 200, "monitor_token_unavailable"),
        (200, ("view-realm",), 200, "monitor_role_mismatch"),
        (
            200,
            ("query-clients", "view-clients", "view-realm"),
            403,
            "monitor_permission_denied",
        ),
    ],
)
def test_keycloak_monitor_token_roles_and_permission_fail_closed(
    monkeypatch, token_status, roles, realm_status, expected
):
    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, _path, **_kwargs):
            return KeycloakAdminResponse(
                {"access_token": _monitor_token(*roles)}, token_status
            )

        def get(self, path, **_kwargs):
            assert path == "/admin/realms/eid-local"
            return KeycloakAdminResponse({}, realm_status)

    monkeypatch.setattr(main.httpx, "Client", Client)

    assert main._keycloak_client_contract_status(time.monotonic() + 4.5) == expected


def test_keycloak_admin_probe_honors_expired_deadline_and_closes_client(monkeypatch):
    observed = {"closed": False}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            observed["closed"] = True

        def post(self, *_args, **_kwargs):
            pytest.fail("expired deadline must prevent the token request")

    monkeypatch.setattr(main.httpx, "Client", Client)
    monkeypatch.setattr(main.time, "monotonic", lambda: 2.0)

    with pytest.raises(TimeoutError):
        main._keycloak_client_contract_status(1.0)
    assert observed["closed"] is True


def test_redis_failure_is_reported_in_structured_readiness_503(monkeypatch):
    for name in (
        "_postgres_status",
        "_rabbitmq_status",
        "_s3_status",
        "_keycloak_status",
        "_worker_status",
    ):
        monkeypatch.setattr(main, name, lambda: "ready")
    monkeypatch.setattr(
        main.redis,
        "from_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("redis secret")),
    )

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["redis"] == "unavailable"
    assert "redis secret" not in response.text
    assert_contract("error.schema.json", response.json())


def test_redis_probe_bounds_connect_and_read_and_closes_client(monkeypatch):
    observed = {}

    class Client:
        def ping(self):
            return True

        def close(self):
            observed["closed"] = True

    def from_url(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return Client()

    monkeypatch.setattr(main.redis, "from_url", from_url)

    assert main._redis_status() == "ready"
    assert observed["kwargs"] == {"socket_connect_timeout": 2, "socket_timeout": 2}
    assert observed["closed"] is True


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        (
            lambda: SimpleNamespace(
                head_bucket=lambda **_kwargs: (_ for _ in ()).throw(
                    main.ClientError(
                        {
                            "Error": {"Code": "NoSuchBucket", "Message": "missing"},
                            "ResponseMetadata": {"HTTPStatusCode": 404},
                        },
                        "HeadBucket",
                    )
                )
            ),
            "bucket_missing",
        ),
        (
            lambda: SimpleNamespace(
                head_bucket=lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("s3 secret"))
            ),
            "unavailable",
        ),
    ],
)
def test_s3_failure_is_reported_in_structured_readiness_503(monkeypatch, client, expected):
    for name in (
        "_postgres_status",
        "_redis_status",
        "_rabbitmq_status",
        "_keycloak_status",
        "_worker_status",
    ):
        monkeypatch.setattr(main, name, lambda: "ready")
    monkeypatch.setattr(main.boto3, "client", lambda *_args, **_kwargs: client())

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["s3"] == expected
    assert "s3 secret" not in response.text
    assert_contract("error.schema.json", response.json())


def test_s3_probe_closes_client(monkeypatch):
    observed = {}

    class Client:
        def head_bucket(self, *, Bucket):
            assert Bucket == main.settings.s3_bucket

        def close(self):
            observed["closed"] = True

    monkeypatch.setattr(main.boto3, "client", lambda *_args, **_kwargs: Client())

    assert main._s3_status() == "ready"
    assert observed["closed"] is True


def test_me_database_error_is_retryable_redacted_and_correlated(monkeypatch):
    traceparent = "00-abcdef1234567890abcdef1234567890-abcdef1234567890-01"
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject="actor"))
    monkeypatch.setattr(
        main,
        "current_account",
        lambda *_args: (_ for _ in ()).throw(main.psycopg.OperationalError("password=secret")),
    )

    response = CLIENT.get(
        "/api/v1/me",
        headers={
            "Authorization": "Bearer valid",
            "X-Request-ID": "database-503",
            "traceparent": traceparent,
        },
    )

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "database-503"
    assert response.headers["traceparent"] == traceparent
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert response.json()["error"]["request_id"] == "database-503"
    assert response.json()["error"]["trace_id"] == traceparent.split("-")[1]
    assert response.json()["error"]["retryable"] is True
    assert "secret" not in response.text
    assert_contract("error.schema.json", response.json())


def test_worker_probe_targets_only_the_stable_node(monkeypatch):
    observed = {}

    class Control:
        def broadcast(self, *args, **kwargs):
            observed["command"] = args[0]
            observed.update(kwargs)
            return [{main.settings.worker_node_name: {"status": "ready"}}]

    class Probe:
        control = Control()

        def close(self):
            observed["closed"] = True

    def celery(*_args, **kwargs):
        observed["celery_kwargs"] = kwargs
        return Probe()

    monkeypatch.setattr(main, "Celery", celery)

    assert main._worker_status() == "ready"
    assert observed["command"] == "dependency_readiness"
    assert observed["destination"] == [main.settings.worker_node_name]
    assert observed["reply"] is True
    assert observed["arguments"]["timeout_seconds"] < observed["timeout"]
    assert observed["celery_kwargs"]["broker_connection_timeout"] == 2.0
    assert observed["celery_kwargs"]["broker_transport_options"] == {
        "connect_timeout": 2.0,
        "socket_timeout": 2.0,
    }
    assert observed["closed"] is True


def test_absent_worker_makes_api_readiness_fail(monkeypatch):
    class Control:
        def broadcast(self, *_args, **_kwargs):
            return []

    class Probe:
        control = Control()

        def close(self):
            return None

    monkeypatch.setattr(main, "Celery", lambda *_args, **_kwargs: Probe())
    for name in (
        "_postgres_status",
        "_redis_status",
        "_rabbitmq_status",
        "_s3_status",
        "_keycloak_status",
    ):
        monkeypatch.setattr(main, name, lambda: "ready")

    response = CLIENT.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"]["checks"]["worker"] == "unavailable"
    assert_contract("error.schema.json", response.json())


@pytest.mark.parametrize(
    "reply",
    [
        [{"other@worker": {"status": "ready"}}],
        [{main.settings.worker_node_name: {"ok": "pong"}}],
        [{main.settings.worker_node_name: {"status": "unavailable"}}],
        [{main.settings.worker_node_name: {"status": "ready", "detail": "secret"}}],
    ],
)
def test_worker_dependency_failure_and_unexpected_replies_degrade_api_readiness(
    monkeypatch,
    reply,
):
    class Probe:
        control = SimpleNamespace(broadcast=lambda *_args, **_kwargs: reply)

        def close(self):
            return None

    monkeypatch.setattr(main, "Celery", lambda *_args, **_kwargs: Probe())

    assert main._worker_status() == "unavailable"


def test_worker_probe_rejects_deadline_too_short_for_dependency_checks(monkeypatch):
    monkeypatch.setattr(main.settings, "worker_health_timeout_seconds", 1.0)
    monkeypatch.setattr(
        main,
        "Celery",
        lambda *_args, **_kwargs: pytest.fail("control command must not be dispatched"),
    )

    assert main._worker_status() == "unavailable"
