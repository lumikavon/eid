"""在专属本地数据库的唯一空 schema 中执行真实迁移链；事务结束时整体回滚。"""

import os
from pathlib import Path
import uuid

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from scripts.verify_local_environment import verify_migration_target


pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1", reason="需要显式隔离环境验收"
)
ROOT = Path(__file__).parents[2]
GUARDED_URL = (
    "postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev"
)
REQUIRED_TABLES = {
    "alembic_version",
    "identity_account",
    "workspace",
    "workspace_membership",
}


def _public_state(connection):
    tables = tuple(
        connection.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        ).scalars()
    )
    tracked = {}
    for table in REQUIRED_TABLES:
        if table in tables:
            tracked[table] = connection.exec_driver_sql(
                f'SELECT count(*) FROM public."{table}"'
            ).scalar_one()
    versions = ()
    if "alembic_version" in tables:
        versions = tuple(
            connection.exec_driver_sql(
                "SELECT version_num FROM public.alembic_version ORDER BY version_num"
            ).scalars()
        )
    return tables, tracked, versions


def test_checked_in_migration_builds_clean_isolated_schema_and_rolls_back():
    verify_migration_target(GUARDED_URL)
    schema = f"eid_migration_test_{uuid.uuid4().hex}"
    engine = sa.create_engine(GUARDED_URL, poolclass=NullPool, connect_args={"connect_timeout": 3})

    with engine.connect() as connection:
        public_before = _public_state(connection)
        connection.commit()
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO eid_api, eid_worker')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "migrations"))
            scripts = ScriptDirectory.from_config(config)

            def migrations_from(current_heads, _context):
                return scripts._upgrade_revs("head", current_heads)

            migration_context = MigrationContext.configure(
                connection, opts={"fn": migrations_from}
            )
            with Operations.context(migration_context):
                migration_context.run_migrations()

            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "0002_worker_metadata_only"
            assert set(
                connection.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = :schema"
                    ),
                    {"schema": schema},
                ).scalars()
            ) == REQUIRED_TABLES
            assert connection.exec_driver_sql(
                "SELECT i.subject, w.slug, m.active "
                "FROM identity_account AS i "
                "JOIN workspace_membership AS m ON m.identity_id = i.id "
                "JOIN workspace AS w ON w.id = m.workspace_id"
            ).one() == ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "eid-local", True)

            for role in ("eid_api", "eid_worker"):
                for table in REQUIRED_TABLES:
                    qualified_table = f'"{schema}"."{table}"'
                    allowed = connection.execute(
                        sa.text("SELECT has_table_privilege(:role, :table, 'SELECT')"),
                        {"role": role, "table": qualified_table},
                    ).scalar_one()
                    assert allowed is (role == "eid_api" or table == "alembic_version")

            assert _public_state(connection) == public_before
        finally:
            transaction.rollback()

        assert connection.execute(
            sa.text(
                "SELECT NOT EXISTS ("
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema)"
            ),
            {"schema": schema},
        ).scalar_one()
        assert _public_state(connection) == public_before

    engine.dispose()
