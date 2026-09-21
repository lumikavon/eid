"""Client-port contracts only; all runtime, network and database I/O stays closed."""

import copy
import json
import socket
import subprocess
import sys
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import psycopg
import pytest
import yaml

from scripts import initialize_local_storage as storage
from scripts import remote_environment as remote
from scripts import verify_local_environment as guard


REMOTE_URL = "postgresql+psycopg://eid_migrator:local-migrate-only@localhost:15432/eid_local_dev"
LEGACY_URL = "postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev"


@pytest.fixture(autouse=True)
def closed_io(monkeypatch):
    monkeypatch.delenv("EID_ENVIRONMENT_CONFIG", raising=False)
    monkeypatch.delenv("EID_RUN_LIVE_TESTS", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("Client-port contract tests forbid runtime/network/database I/O")

    for name in ("run", "Popen", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(guard, "ownership", forbidden)


def test_client_endpoint_is_resolved_at_each_use_without_reimport(monkeypatch):
    assert guard.database_client_port() == 55432
    assert guard.development_database_url() == LEGACY_URL
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    assert guard.database_client_port() == 15432
    assert guard.development_database_url() == REMOTE_URL
    monkeypatch.delenv("EID_ENVIRONMENT_CONFIG")
    assert guard.development_database_url() == LEGACY_URL


@pytest.mark.parametrize("selector", ["seadee-develop", str(remote.DEFAULT_CONFIG.resolve())])
def test_remote_migration_endpoint_and_existing_roles(monkeypatch, selector):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
    guard.validate_url(REMOTE_URL)
    guard.validate_url(REMOTE_URL.replace("postgresql+psycopg:", "postgresql:"))
    assert guard.development_database_url("eid_worker") == (
        "postgresql+psycopg://eid_worker:local-worker-only@localhost:15432/eid_local_dev")
    assert guard.development_database_url("postgres") == (
        "postgresql+psycopg://postgres:local-postgres-admin-only@localhost:15432/eid_local_dev")
    with pytest.raises(guard.IsolationError, match="数据库身份"):
        guard.development_database_url("enterprise")


@pytest.mark.parametrize("value", [
    LEGACY_URL,
    REMOTE_URL.replace("localhost", "production"),
    REMOTE_URL.replace("localhost", "127.0.0.1"),
    REMOTE_URL.replace("15432", "5432"),
    REMOTE_URL.replace("eid_local_dev", "enterprise"),
    REMOTE_URL.replace("eid_migrator", "postgres"),
    REMOTE_URL.replace("eid_migrator", "eid_worker"),
    REMOTE_URL + "?host=production",
    REMOTE_URL + "#other",
])
def test_remote_rejects_unapproved_url_before_ownership_or_connection(monkeypatch, value):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    with pytest.raises(guard.IsolationError, match="localhost:15432"):
        guard.verify_database(value)


def test_legacy_selection_keeps_exact_old_port():
    guard.validate_url(LEGACY_URL)
    with pytest.raises(guard.IsolationError, match="localhost:55432"):
        guard.validate_url(REMOTE_URL)


@pytest.mark.parametrize("selector", ["", " ", "unknown", "../other/environment.yaml"])
def test_invalid_selector_never_falls_back_for_url_or_guard(monkeypatch, selector):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
    for operation in (guard.database_client_port, guard.development_database_url,
                      lambda: guard.verify_database(LEGACY_URL)):
        with pytest.raises(guard.IsolationError, match="远端环境选择无效"):
            operation()


@pytest.mark.parametrize("port", [55432, 25432])
def test_remote_selector_rejects_unapproved_client_port(monkeypatch, port):
    config = remote.load_config()
    config["tunnels"]["ports"]["postgres"] = port
    monkeypatch.setattr(remote, "load_config", lambda _: config)
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    with pytest.raises(guard.IsolationError, match="client endpoints"):
        guard.development_database_url()


@pytest.mark.parametrize("row", [
    ("eid_local_dev", "eid_migrator", "eid-local-dev-v1"),
    ("enterprise", "eid_migrator", "eid-local-dev-v1"),
    ("eid_local_dev", "postgres", "eid-local-dev-v1"),
    ("eid_local_dev", "eid_migrator", "foreign-marker"),
])
def test_remote_port_still_requires_owned_service_and_actual_database_identity(monkeypatch, row):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    events = []
    owner = {"nonce": "owned-test-target"}
    monkeypatch.setattr(guard, "ownership", lambda: events.append("owner") or owner)

    def service(config, name, container_port, client_port):
        assert config == remote.load_config()
        assert (name, container_port, client_port) == ("postgres", 5432, 15432)
        events.append("service")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql):
            assert "current_database(), current_user, shobj_description" in sql
            events.append("identity")
            return SimpleNamespace(fetchone=lambda: row)

    def connect(value, **options):
        assert events == ["owner", "service"]
        assert value == REMOTE_URL.replace("postgresql+psycopg:", "postgresql:")
        assert options == {"connect_timeout": 3,
                           "options": "-c statement_timeout=5000 -c lock_timeout=2000"}
        events.append("connect")
        return Connection()

    monkeypatch.setattr(remote, "guarded_service", service)
    monkeypatch.setattr(psycopg, "connect", connect)
    if row == ("eid_local_dev", "eid_migrator", "eid-local-dev-v1"):
        assert guard.verify_database(REMOTE_URL) == owner
    else:
        with pytest.raises(guard.IsolationError, match="数据库名称/身份/marker"):
            guard.verify_database(REMOTE_URL)
    assert events == ["owner", "service", "connect", "identity"]


@pytest.mark.parametrize("entrypoint", ["storage", "alembic"])
def test_initialization_and_migration_reject_external_old_url_before_io(monkeypatch, entrypoint):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", LEGACY_URL)
    with pytest.raises(guard.IsolationError, match="localhost:15432"):
        if entrypoint == "storage":
            storage.main()
        else:
            command.upgrade(Config(str(remote.ROOT / "alembic.ini")), "head")


def test_guard_reports_selected_client_port(monkeypatch, capsys):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", REMOTE_URL)
    monkeypatch.setattr(sys, "argv", ["verify_local_environment", "--check-only", "--skip-versions"])
    monkeypatch.setattr(guard, "ownership", lambda **_: {"nonce": "owned-test-target"})
    monkeypatch.setattr(guard, "verify_migration_target", guard.validate_url)
    guard.main()
    result = json.loads(capsys.readouterr().out)
    assert result["host"] == "localhost:15432"
    assert result["environment"] == "seadee-develop"


def test_only_postgres_client_side_of_exact_seven_tunnels_changes():
    config = remote.load_config()
    argv = remote.tunnel_command(config)
    mappings = [argv[index + 1] for index, value in enumerate(argv) if value == "-L"]
    assert mappings == [
        "127.0.0.1:15432:127.0.0.1:55432",
        "127.0.0.1:58080:127.0.0.1:58080",
        "127.0.0.1:55672:127.0.0.1:55672",
        "127.0.0.1:55673:127.0.0.1:55673",
        "127.0.0.1:16379:127.0.0.1:56379",
        "127.0.0.1:58333:127.0.0.1:58333",
        "127.0.0.1:18080:127.0.0.1:18080",
    ]
    assert "ExitOnForwardFailure=yes" in argv
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv


def test_local_port_change_preserves_remote_compose_bytes_and_internal_database_urls():
    config = remote.load_config()
    previous = copy.deepcopy(config)
    previous["tunnels"]["ports"]["postgres"] = 55432
    files = remote.source_files(remote.ROOT)
    owner = "c38d0f7481a6476ebc8b0fd2fe087db3"
    current = remote.render_compose(config, owner, files)
    assert current == remote.render_compose(previous, owner, files)
    services = yaml.safe_load(current)["services"]
    assert services["postgres"]["ports"] == ["127.0.0.1:55432:5432"]
    for service in ("api", "worker"):
        assert services[service]["environment"]["EID_DATABASE_URL"].endswith(
            "@postgres:5432/eid_local_dev")
