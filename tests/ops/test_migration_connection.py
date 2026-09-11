import runpy
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import sqlalchemy

import scripts.verify_local_environment as guard


ROOT = Path(__file__).parents[2]


def run_migration_env(monkeypatch, connection_identity, calls=None):
    calls = [] if calls is None else calls

    class Config:
        config_ini_section = "alembic"

        def set_main_option(self, _name, _value):
            return None

        def get_main_option(self, name):
            assert name == "sqlalchemy.url"
            return "postgresql+psycopg://configured-but-untrusted/eid_local_dev"

        def get_section(self, name):
            assert name == self.config_ini_section
            return {"sqlalchemy.url": self.get_main_option("sqlalchemy.url")}

    class Result:
        def one_or_none(self):
            return connection_identity

    class Connection:
        def exec_driver_sql(self, sql):
            calls.append("connection-identity")
            assert "current_database()" in sql
            assert "current_user" in sql
            assert "shobj_description" in sql
            return Result()

    class ConnectionContext:
        def __enter__(self):
            calls.append("connect")
            return Connection()

        def __exit__(self, *_args):
            return None

    class Engine:
        def begin(self):
            return ConnectionContext()

    @contextmanager
    def transaction():
        calls.append("transaction")
        yield

    fake_context = SimpleNamespace(
        config=Config(),
        is_offline_mode=lambda: False,
        configure=lambda **_kwargs: calls.append("configure"),
        begin_transaction=transaction,
        run_migrations=lambda: calls.append("run-migrations"),
    )
    alembic = ModuleType("alembic")
    alembic.context = fake_context

    monkeypatch.setitem(sys.modules, "alembic", alembic)
    monkeypatch.setattr(
        guard,
        "verify_migration_target",
        lambda _url: calls.append("full-environment-guard"),
    )
    def engine_from_config(*_args, **kwargs):
        assert kwargs["connect_args"] == {
            "connect_timeout": 3,
            "options": "-c statement_timeout=5000 -c lock_timeout=2000",
        }
        return Engine()

    monkeypatch.setattr(sqlalchemy, "engine_from_config", engine_from_config)

    runpy.run_path(str(ROOT / "migrations" / "env.py"), run_name="migration_env_test")
    return calls


def test_migration_connection_is_verified_after_full_guard_before_migrations(monkeypatch):
    calls = run_migration_env(
        monkeypatch,
        ("eid_local_dev", "eid_migrator", "eid-local-dev-v1"),
    )

    assert calls == [
        "full-environment-guard",
        "connect",
        "connection-identity",
        "configure",
        "transaction",
        "run-migrations",
    ]


@pytest.mark.parametrize(
    "connection_identity",
    [
        ("foreign_database", "eid_migrator", "eid-local-dev-v1"),
        ("eid_local_dev", "postgres", "eid-local-dev-v1"),
        ("eid_local_dev", "eid_migrator", "foreign-marker"),
        None,
    ],
)
def test_wrong_migration_connection_never_configures_or_runs_ddl(
    monkeypatch,
    connection_identity,
):
    calls = []
    with pytest.raises(RuntimeError, match="Migration database connection identity mismatch"):
        run_migration_env(monkeypatch, connection_identity, calls)

    assert calls == ["full-environment-guard", "connect", "connection-identity"]
