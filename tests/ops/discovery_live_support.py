"""Private-schema real PostgreSQL harness; durable race schemas are never removed.

All identities here are synthetic DB subjects, never Keycloak or public fixtures.
Route tests use a clearly injected authentication boundary and real SQL roles.
Deployed OIDC/browser acceptance remains a separate required evidence layer.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import psycopg
from psycopg import sql
from psycopg.rows import dict_row, tuple_row
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from scripts import seed_discovery_fixtures as fixture
from scripts.verify_access_fixtures import ROLES
from scripts.verify_local_environment import (
    database_client_port, development_database_url, verify_migration_target,
)

ROOT = Path(__file__).resolve().parents[2]


def verify_database_identity(conn, role):
    actual = conn.execute("SELECT current_database() AS database,current_user AS role,"
        "shobj_description(oid,'pg_database') AS marker FROM pg_database "
        "WHERE datname=current_database()").fetchone()
    assert actual == {"database": "eid_local_dev", "role": role, "marker": "eid-local-dev-v1"}


def as_role(conn, role):
    assert role in {"eid_api", "eid_worker", "eid_migrator"}
    conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    assert conn.execute("SELECT current_user AS name").fetchone()["name"] == role


@dataclass
class Store:
    schema: str
    conn: object
    declared: dict
    users: dict
    boundary: dict
    run_id: str
    schema_head: str
    retained_receipt: Path | None = None

    @property
    def workspace(self):
        return self.declared["workspaces"]["a"]

    def actor(self, role="author"):
        return self.users[role]["actor_id"]

    def subject(self, role="author"):
        return self.users[role]["subject"]

    def resource(self, label="document", project="a"):
        return self.declared["records"][project + ":" + label]


def populate(conn, declared, users):
    for role, user in users.items():
        conn.execute("INSERT INTO identity_account(id,subject,display_name,department) VALUES (%s,%s,%s,'验收部')",
                     (user["actor_id"], user["subject"], "独立事务测试 · " + role))
    fixture.apply_definition(conn, declared)


@contextmanager
def isolated_store(*, durable=False):
    # Explicit selected remote target plus full existing guard before any connection/write.
    assert os.getenv("EID_RUN_LIVE_TESTS") == "1", "Explicit live-test opt-in required"
    boundary = fixture.selected_boundary()
    verify_migration_target(development_database_url())
    assert fixture.selected_boundary() == boundary
    schema = "eid_discovery_test_" + uuid4().hex
    run_id = "live-" + uuid4().hex[:20]
    users = {role: {"actor_id": str(uuid4()), "subject": "discovery-live-" + uuid4().hex}
             for role in ROLES}
    declared = fixture.definition(boundary["nonce"], run_id, users,
                                 datetime.now(timezone.utc).isoformat())
    receipt = None
    if durable:
        directory = Path(boundary["state"]) / "discovery-live"
        assert not directory.is_symlink() and not directory.is_junction()
        directory.mkdir(exist_ok=True)
        receipt = directory / (schema + ".json")
    engine = sa.create_engine(development_database_url("postgres"), poolclass=NullPool,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000 -c lock_timeout=5000"})
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            assert connection.exec_driver_sql("SELECT current_database(),current_user,"
                "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
                ).one() == ("eid_local_dev", "postgres", "eid-local-dev-v1")
            connection.exec_driver_sql("SET LOCAL ROLE eid_migrator")
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO eid_api,eid_worker')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "migrations"))
            scripts = ScriptDirectory.from_config(config)
            context = MigrationContext.configure(connection,
                opts={"fn": lambda heads, _: scripts._upgrade_revs("head", heads)})
            with Operations.context(context):
                context.run_migrations()
            conn = connection.connection.driver_connection
            conn.row_factory = dict_row
            try:
                schema_head = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
                assert schema_head == scripts.get_current_head()
                assert schema_head in fixture.SUPPORTED_FIXTURE_REVISIONS
                populate(conn, declared, users)
                marker = "eid-discovery-live:" + boundary["nonce"] + ":" + fixture.digest(declared)
                conn.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(sql.Identifier(schema), sql.Literal(marker)))
                if durable:
                    fixture.write_new_document(receipt, {"schema": schema, "boundary": boundary,
                        "run_id": run_id, "users": users, "declaration": declared,
                        "definition_sha256": fixture.digest(declared), "schema_head": schema_head,
                        "retention": "Retain schema and all rows; no automatic drop/delete/reset"})
                store = Store(schema, conn, declared, users, boundary, run_id, schema_head, receipt)
                if durable:
                    assert fixture.selected_boundary() == boundary
                    verify_migration_target(development_database_url())
                    conn.row_factory = tuple_row
                    transaction.commit()  # Only this exclusively created, receipted schema.
                    fixture.write_new_document(receipt.with_suffix(".committed.json"), {
                        "schema": schema, "definition_sha256": fixture.digest(declared), "boundary": boundary})
                    store.conn = None
                yield store
            finally:
                conn.row_factory = tuple_row
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()


@contextmanager
def fresh_connection(store, role="eid_api"):
    assert os.getenv("EID_RUN_LIVE_TESTS") == "1", "Explicit live-test opt-in required"
    assert store.retained_receipt is not None and fixture.selected_boundary() == store.boundary
    receipt = fixture.read_receipt(store.retained_receipt)
    assert store.schema_head in fixture.SUPPORTED_FIXTURE_REVISIONS
    assert receipt == {"schema": store.schema, "boundary": store.boundary,
        "run_id": store.run_id, "users": store.users, "declaration": store.declared,
        "definition_sha256": fixture.digest(store.declared), "schema_head": store.schema_head,
        "retention": "Retain schema and all rows; no automatic drop/delete/reset"}
    completion = fixture.read_receipt(store.retained_receipt.with_suffix(".committed.json"))
    assert completion == {"schema": store.schema, "definition_sha256": fixture.digest(store.declared),
                          "boundary": store.boundary}
    # These are repository-declared development credentials, never production secrets.
    if role == "eid_api":
        url = f"postgresql://eid_api:local-api-only@localhost:{database_client_port()}/eid_local_dev"
    else:
        assert role in {"eid_worker", "eid_migrator", "postgres"}
        url = development_database_url(role).replace("postgresql+psycopg:", "postgresql:")
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=3,
            options="-c statement_timeout=10000 -c lock_timeout=5000") as conn:
        verify_database_identity(conn, role)
        owned = conn.execute("SELECT r.rolname AS owner,obj_description(n.oid,'pg_namespace') AS marker "
            "FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname=%s", (store.schema,)).fetchone()
        assert owned == {"owner": "eid_migrator", "marker": "eid-discovery-live:" + store.boundary["nonce"] + ":" + fixture.digest(store.declared)}
        conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(store.schema)))
        assert conn.execute("SELECT current_schema() AS name").fetchone()["name"] == store.schema
        assert conn.execute("SELECT version_num FROM alembic_version").fetchall() == [{"version_num": store.schema_head}]
        yield conn
