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
from psycopg.rows import dict_row

from scripts.verify_local_environment import development_database_url, verify_migration_target
from edw_api.access.repository import first_workspace


pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1", reason="需要显式隔离环境验收"
)
ROOT = Path(__file__).parents[2]
REQUIRED_TABLES = {
    "alembic_version",
    "identity_account",
    "workspace",
    "workspace_membership",
    "access_workspace", "access_member", "access_resource", "access_audit",
    "access_invalidation", "access_delegation", "access_current_facts",
    "discovery_record", "discovery_participant", "discovery_favorite",
    "discovery_restore_policy", "discovery_receipt",
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


@pytest.mark.parametrize("legacy_members", [False, True])
def test_checked_in_migration_builds_clean_isolated_schema_and_rolls_back(legacy_members):
    url = development_database_url()
    verify_migration_target(url)
    schema = f"eid_migration_test_{uuid.uuid4().hex}"
    engine = sa.create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})

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

            def upgrade(target):
                migration_context = MigrationContext.configure(
                    connection, opts={"fn": lambda heads, _: scripts._upgrade_revs(target, heads)}
                )
                with Operations.context(migration_context):
                    migration_context.run_migrations()

            legacy = []
            if legacy_members:
                upgrade("0002_worker_metadata_only")
                for index in range(3):
                    identity, workspace = uuid.uuid4(), uuid.uuid4()
                    subject = f"legacy-{identity}"
                    connection.execute(sa.text(
                        "INSERT INTO identity_account(id,subject,display_name,department) "
                        "VALUES (:id,:subject,'Legacy member','产品部')"
                    ), {"id": identity, "subject": subject})
                    connection.execute(sa.text(
                        "INSERT INTO workspace(id,slug,name) VALUES (:id,:slug,'Legacy project')"
                    ), {"id": workspace, "slug": f"legacy-{index}"})
                    connection.execute(sa.text(
                        "INSERT INTO workspace_membership(identity_id,workspace_id,active) "
                        "VALUES (:identity,:workspace,:active)"
                    ), {"identity": identity, "workspace": workspace, "active": index != 2})
                    legacy.append((subject, workspace, index != 2))
            upgrade("head")

            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "0007_workspace_discovery"
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
                "JOIN workspace AS w ON w.id = m.workspace_id "
                "WHERE i.subject='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'"
            ).one() == ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "eid-local", True)

            assert connection.exec_driver_sql(
                "SELECT count(*) FROM workspace w LEFT JOIN access_workspace p "
                "ON p.workspace_id=w.id WHERE p.workspace_id IS NULL"
            ).scalar_one() == 0
            assert connection.exec_driver_sql(
                "SELECT count(*) FROM workspace_membership m LEFT JOIN access_member p "
                "USING (identity_id,workspace_id) WHERE p.identity_id IS NULL"
            ).scalar_one() == 0
            raw = connection.connection.driver_connection
            previous_factory = raw.row_factory
            try:
                raw.row_factory = dict_row
                for subject, workspace, active in legacy:
                    current = first_workspace(raw, subject)
                    if active:
                        assert current["workspace_id"] == str(workspace)
                        assert current["roles"] == ["author"]
                        assert current["clearance"] == 1
                    else:
                        assert current is None
            finally:
                raw.row_factory = previous_factory

            for role in ("eid_api", "eid_worker"):
                for table in REQUIRED_TABLES:
                    qualified_table = f'"{schema}"."{table}"'
                    allowed = connection.execute(
                        sa.text("SELECT has_table_privilege(:role, :table, 'SELECT')"),
                        {"role": role, "table": qualified_table},
                    ).scalar_one()
                    expected = table == "alembic_version" or (role == "eid_api" and table not in {
                        "access_audit", "access_invalidation", "access_delegation"})
                    assert allowed is expected

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
