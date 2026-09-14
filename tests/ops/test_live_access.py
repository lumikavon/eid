"""Real PostgreSQL policy transactions in unique schemas, rolled back without touching public data."""
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import psycopg
from psycopg.rows import dict_row, tuple_row
import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from edw_api.access import repository
from edw_api.access.policy import AccessDenied, ROLE_OPERATIONS
from scripts.verify_local_environment import verify_migration_target

pytestmark = pytest.mark.skipif(os.getenv("EID_RUN_LIVE_TESTS") != "1",
                                reason="Explicit isolated PostgreSQL acceptance required")
URL = "postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev"
ACTOR = "11111111-1111-4111-8111-111111111111"
WORKSPACE = "22222222-2222-4222-8222-222222222222"
SUBJECT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture(scope="module", autouse=True)
def isolated_target():
    verify_migration_target(URL)


@pytest.fixture
def database():
    admin_url = URL.replace("eid_migrator:local-migrate-only", "postgres:local-postgres-admin-only")
    engine = sa.create_engine(admin_url, poolclass=NullPool,
                              connect_args={"connect_timeout": 3,
                                            "options": "-c statement_timeout=5000 -c lock_timeout=2000"})
    schema = "eid_access_test_" + uuid4().hex
    with engine.connect() as sql:
        tx = sql.begin()
        assert sql.exec_driver_sql("SELECT current_database(),current_user,"
                   "shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
                   ).one() == ("eid_local_dev", "postgres", "eid-local-dev-v1")
        # The verified local test administrator may SET ROLE without broadening migrator grants.
        sql.exec_driver_sql("SET LOCAL ROLE eid_migrator")
        sql.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        sql.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO eid_api,eid_worker')
        sql.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        config = Config(str(Path(__file__).parents[2]/"alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).parents[2]/"migrations"))
        scripts = ScriptDirectory.from_config(config)
        context = MigrationContext.configure(sql, opts={"fn": lambda heads, _: scripts._upgrade_revs("head", heads)})
        with Operations.context(context):
            context.run_migrations()
        conn = sql.connection.driver_connection
        conn.row_factory = dict_row
        try:
            yield conn
        finally:
            conn.row_factory = tuple_row
            tx.rollback()
    engine.dispose()


def add_member(conn):
    identity = uuid4()
    subject = "test-" + identity.hex
    conn.execute("INSERT INTO identity_account(id,subject,display_name,department) VALUES (%s,%s,'测试作者','产品部')",
                 (identity, subject))
    conn.execute("INSERT INTO workspace_membership(identity_id,workspace_id) VALUES (%s,%s)",
                 (identity, WORKSPACE))
    conn.execute("""INSERT INTO access_member SELECT %s,workspace_id,roles,project_scope,
                 customer_scope,product_scope,department_scope,owner_scope,approval_states,
                 clearance,valid_from,valid_until,1 FROM access_member WHERE identity_id=%s""",
                 (identity, ACTOR))
    return identity, subject


def make_admin(conn):
    conn.execute("UPDATE access_member SET roles=ARRAY['system_admin'],clearance=3,owner_scope='any',"
                 "approval_states=ARRAY['draft','in_review','approved','rejected'] WHERE identity_id=%s", (ACTOR,))


def policy(conn, target):
    row = conn.execute("SELECT * FROM access_member WHERE identity_id=%s", (target,)).fetchone()
    return {key: row[key] for key in ("roles", "project_scope", "customer_scope", "product_scope",
                                     "department_scope", "owner_scope", "approval_states", "clearance",
                                     "valid_from", "valid_until")} | {"active": True}


def as_api(conn):
    conn.execute("SET LOCAL ROLE eid_api")
    assert conn.execute("SELECT current_user").fetchone()["current_user"] == "eid_api"


def test_current_rbac_matrix_uses_stored_facts(database):
    conn = database
    resource = uuid4()
    conn.execute("""INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,
                 product_id,department,owner_id,classification) VALUES (%s,%s,'矩阵资源','policy',
                 'eid-local','local-customer','local-product','产品部',%s,1)""", (resource, WORKSPACE, ACTOR))
    for role, allowed in ROLE_OPERATIONS.items():
        conn.execute("RESET ROLE")
        conn.execute("UPDATE access_member SET roles=%s WHERE identity_id=%s", ([role], ACTOR))
        as_api(conn)
        for other, operations in ROLE_OPERATIONS.items():
            for operation in operations:
                if operation in allowed:
                    assert repository.checked(conn, SUBJECT, WORKSPACE, operation, resource)[2].actor_id == ACTOR
                else:
                    with pytest.raises(AccessDenied):
                        repository.checked(conn, SUBJECT, WORKSPACE, operation, resource)
        assert repository.first_workspace(conn, SUBJECT)["roles"] == [role]
    for states in ([], ["approved"], ["draft"]):
        conn.execute("RESET ROLE")
        conn.execute("UPDATE access_member SET roles=ARRAY['author'],approval_states=%s WHERE identity_id=%s",
                     (states, ACTOR))
        as_api(conn)
        if "draft" in states:
            assert repository.checked(conn, SUBJECT, WORKSPACE, "document:create")[2].operation == "document:create"
        else:
            with pytest.raises(AccessDenied):
                repository.create_delegation(conn, SUBJECT, WORKSPACE, None, "document:create",
                                             "stage", "creation-check", "1"*32)


def test_change_epoch_audit_invalidation_and_revocation_are_atomic(database):
    conn = database
    target, subject = add_member(conn)
    update = policy(conn, target)
    original_row = conn.execute("SELECT * FROM access_member WHERE identity_id=%s", (target,)).fetchone()
    make_admin(conn)
    as_api(conn)
    before = repository.checked(conn, subject, WORKSPACE)[2]
    expected = list(repository.checked(conn, SUBJECT, WORKSPACE, "membership:manage")[2].policy_epoch)
    update["active"] = False
    result = repository.change_member(conn, SUBJECT, WORKSPACE, target, update, expected, "test-change", "1"*32)
    assert result["workspace_epoch"] == before.policy_epoch[0] + 1
    conn.execute("RESET ROLE")  # Test administrator inspects append-only evidence; API cannot read it.
    audit = conn.execute("SELECT * FROM access_audit WHERE id=%s", (result["audit_id"],)).fetchone()
    def serialized(row):
        return {key: value.isoformat() if isinstance(value, datetime) else
                str(value) if key in {"identity_id", "workspace_id"} else value for key, value in row.items()}
    assert str(audit["workspace_id"]) == WORKSPACE
    assert str(audit["actor_id"]) == ACTOR
    assert audit["target_id"] == target
    assert audit["action"] == "membership.change"
    assert audit["before_policy"] == serialized(original_row | {"active": True})
    after_row = conn.execute("SELECT * FROM access_member WHERE identity_id=%s", (target,)).fetchone()
    assert after_row["policy_epoch"] == original_row["policy_epoch"] + 1
    assert audit["after_policy"] == serialized(after_row | {"active": False})
    assert audit["request_id"] == "test-change"
    assert audit["trace_id"] == "1"*32
    assert conn.execute("SELECT count(*) AS n FROM access_invalidation WHERE id=%s", (result["audit_id"],)).fetchone()["n"] == 1
    as_api(conn)
    assert repository.first_workspace(conn, subject) is None
    with pytest.raises(AccessDenied):
        repository.checked(conn, subject, WORKSPACE, before.operation)


def test_audit_failure_rolls_back_permission_and_epoch(database):
    conn = database
    target, _ = add_member(conn)
    update = policy(conn, target)
    make_admin(conn)
    # Inject a real database constraint failure on this transaction's private audit table.
    conn.execute("ALTER TABLE access_audit ADD CONSTRAINT reject_audit CHECK (false)")
    as_api(conn)
    expected = list(repository.checked(conn, SUBJECT, WORKSPACE, "membership:manage")[2].policy_epoch)
    update["active"] = False
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        repository.change_member(conn, SUBJECT, WORKSPACE, target, update, expected, "audit-failure", "1"*32)
    assert conn.execute("SELECT active FROM workspace_membership WHERE identity_id=%s", (target,)).fetchone()["active"]
    assert conn.execute("SELECT policy_epoch FROM access_workspace").fetchone()["policy_epoch"] == expected[0]
    conn.execute("RESET ROLE")
    assert conn.execute("SELECT count(*) AS n FROM access_invalidation").fetchone()["n"] == 0


def test_conflicting_epoch_and_manager_scope_expansion_deny(database):
    conn = database
    target, _ = add_member(conn)
    update = policy(conn, target)
    make_admin(conn)
    as_api(conn)
    expected = list(repository.checked(conn, SUBJECT, WORKSPACE, "membership:manage")[2].policy_epoch)
    assert repository.change_member(conn, SUBJECT, WORKSPACE, target, update, [99, 99, 99], "stale", "1"*32) is None
    update["customer_scope"] = ["foreign-customer"]
    with pytest.raises(AccessDenied):
        repository.change_member(conn, SUBJECT, WORKSPACE, target, update, expected, "scope", "1"*32)
    conn.execute("RESET ROLE")
    assert conn.execute("SELECT count(*) AS n FROM access_audit").fetchone()["n"] == 0


def test_database_rejects_worker_acl_head_approval_publication_and_delegation_writes(database):
    conn = database
    conn.execute("SET LOCAL ROLE eid_worker")
    assert conn.execute("SELECT current_user").fetchone()["current_user"] == "eid_worker"
    statements = ["UPDATE access_member SET clearance=3", "UPDATE workspace_membership SET active=true",
                  "UPDATE access_resource SET head_ref=NULL", "UPDATE access_resource SET approval_state='approved'",
                  "UPDATE access_resource SET publication_state='published'", "UPDATE access_delegation SET active=true",
                  "DELETE FROM access_audit", "SELECT * FROM access_current_facts"]
    for statement in statements:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
            conn.execute(statement)
    for table in ("access_workspace", "access_member", "workspace_membership", "access_resource",
                  "access_delegation", "access_audit", "access_invalidation"):
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert conn.execute("SELECT has_table_privilege(current_user,%s,%s) AS allowed",
                                 (table, privilege)).fetchone()["allowed"] is False
        for statement in (f"INSERT INTO {table} DEFAULT VALUES", f"DELETE FROM {table} WHERE false"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute(statement)


def test_api_cannot_read_append_only_authorization_records(database):
    as_api(database)
    for table in ("access_audit", "access_invalidation", "access_delegation"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), database.transaction():
            database.execute(f"SELECT * FROM {table}")


def test_actual_resource_abac_classification_and_expiry(database):
    conn = database
    foreign_owner, _ = add_member(conn)
    resource = uuid4()
    conn.execute("""INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,
                 product_id,department,owner_id,classification) VALUES (%s,%s,'测试资源','policy',
                 'eid-local','local-customer','local-product','产品部',%s,1)""", (resource, WORKSPACE, ACTOR))
    as_api(conn)
    assert repository.checked(conn, SUBJECT, WORKSPACE, "resource:read", resource)[1]["title"] == "测试资源"
    for column, value in [("project_id", "foreign"), ("customer_id", "foreign"),
                          ("product_id", "foreign"), ("department", "foreign"),
                          ("owner_id", foreign_owner), ("classification", 3),
                          ("approval_state", "approved"), ("valid_until", datetime.now(timezone.utc)-timedelta(hours=1))]:
        conn.execute("RESET ROLE")
        with conn.transaction(force_rollback=True):
            if column == "valid_until":
                conn.execute("UPDATE access_resource SET valid_from=CURRENT_TIMESTAMP-interval '2 days'")
            conn.execute(f"UPDATE access_resource SET {column}=%s", (value,))
            as_api(conn)
            with pytest.raises(AccessDenied):
                repository.checked(conn, SUBJECT, WORKSPACE, "resource:read", resource)


def test_members_pagination_reaches_beyond_200_and_rechecks_access(database):
    conn = database
    make_admin(conn)
    conn.execute("""INSERT INTO identity_account(id,subject,display_name,department)
                 SELECT gen_random_uuid(),'page-'||n,'分页成员'||n,'产品部'
                 FROM generate_series(1,205) n""")
    conn.execute("""INSERT INTO workspace_membership(identity_id,workspace_id)
                 SELECT id,%s FROM identity_account WHERE subject LIKE 'page-%%'""", (WORKSPACE,))
    conn.execute("""INSERT INTO access_member SELECT i.id,p.workspace_id,p.roles,p.project_scope,
                 p.customer_scope,p.product_scope,p.department_scope,p.owner_scope,p.approval_states,
                 p.clearance,p.valid_from,p.valid_until,1 FROM identity_account i
                 CROSS JOIN access_member p WHERE i.subject LIKE 'page-%%' AND p.identity_id=%s""", (ACTOR,))
    as_api(conn)
    seen = []
    cursor = None
    for _ in range(6):
        page = repository.members(conn, SUBJECT, WORKSPACE, cursor)
        seen.extend(str(row["identity_id"]) for row in page["members"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert len(seen)==len(set(seen))==206
    conn.execute("RESET ROLE")
    conn.execute("UPDATE workspace_membership SET active=false WHERE identity_id=%s", (ACTOR,))
    as_api(conn)
    with pytest.raises(AccessDenied):
        repository.members(conn, SUBJECT, WORKSPACE, seen[50])


def test_readiness_detects_each_missing_access_grant_in_real_database(database, monkeypatch):
    from edw_api import main
    conn = database
    class Borrowed:
        def __enter__(self): return conn
        def __exit__(self, *_): return None
    monkeypatch.setattr(main.psycopg, "connect", lambda *a, **k: Borrowed())
    conn.row_factory = tuple_row
    try:
        conn.execute("SET LOCAL ROLE eid_api")
        assert main._postgres_status()=="ready"
        read_grants = [(table, "SELECT") for table in ("identity_account", "workspace_membership",
            "workspace", "access_workspace", "access_member", "access_resource", "access_current_facts")]
        for table, permission in read_grants + [("workspace_membership","UPDATE"), ("access_member","UPDATE"),
                                  ("access_workspace","UPDATE"), ("access_audit","INSERT"),
                                  ("access_invalidation","INSERT"), ("access_delegation","INSERT")]:
            conn.execute("RESET ROLE")
            with conn.transaction(force_rollback=True):
                conn.execute(f"REVOKE {permission} ON {table} FROM eid_api")
                conn.execute("SET LOCAL ROLE eid_api")
                assert main._postgres_status()=="marker_schema_or_privilege_mismatch"
        conn.execute("RESET ROLE")
        with conn.transaction(force_rollback=True):
            conn.execute("ALTER VIEW access_current_facts RENAME COLUMN approval_states TO missing_approval_states")
            conn.execute("SET LOCAL ROLE eid_api")
            assert main._postgres_status()=="marker_schema_or_privilege_mismatch"
    finally:
        conn.row_factory = dict_row


def test_worker_function_does_not_revive_delegation_after_disable_reenable(database):
    conn = database
    target, subject = add_member(conn)
    original = policy(conn, target)
    make_admin(conn)
    as_api(conn)
    issued = repository.create_delegation(conn, subject, WORKSPACE, None,
                                          "workspace:read", "stage", "request", "a"*32)
    def worker_read(identifier):
        conn.execute("RESET ROLE")
        conn.execute("SET LOCAL SESSION AUTHORIZATION eid_worker")
        try:
            assert conn.execute("SELECT session_user AS name").fetchone()["name"] == "eid_worker"
            return conn.execute("SELECT eid_worker_access(%s) AS context", (identifier,)).fetchone()["context"]
        finally:
            conn.execute("RESET SESSION AUTHORIZATION")
            as_api(conn)
    assert worker_read(issued["delegation_id"]) is not None
    for active in (False, True):
        epoch = list(repository.checked(conn, SUBJECT, WORKSPACE, "membership:manage")[2].policy_epoch)
        repository.change_member(conn, SUBJECT, WORKSPACE, target, original | {"active": active},
                                 epoch, "change", "b"*32)
        assert worker_read(issued["delegation_id"]) is None
    renewed = repository.create_delegation(conn, subject, WORKSPACE, None,
                                           "workspace:read", "stage", "renewed", "c"*32)
    assert worker_read(renewed["delegation_id"]) is not None


def test_workspace_pagination_reads_all_current_memberships_in_real_database(database):
    conn = database
    conn.execute("""INSERT INTO workspace(id,slug,name)
        SELECT gen_random_uuid(),'pagination-'||n,'分页项目'||n FROM generate_series(1,205) n""")
    conn.execute("""INSERT INTO access_workspace
        SELECT w.id,p.tenant_id,p.project_id,p.customer_id,p.product_id,p.department,p.classification,1
        FROM workspace w CROSS JOIN access_workspace p WHERE w.slug LIKE 'pagination-%%'""")
    conn.execute("""INSERT INTO workspace_membership(identity_id,workspace_id)
        SELECT %s,id FROM workspace WHERE slug LIKE 'pagination-%%'""", (ACTOR,))
    conn.execute("""INSERT INTO access_member SELECT p.identity_id,w.id,p.roles,p.project_scope,
        p.customer_scope,p.product_scope,p.department_scope,p.owner_scope,p.approval_states,
        p.clearance,p.valid_from,p.valid_until,1 FROM workspace w CROSS JOIN access_member p
        WHERE w.slug LIKE 'pagination-%%'""")
    as_api(conn)
    seen = []
    cursor = None
    for _ in range(5):
        page = repository.workspace_page(conn, SUBJECT, cursor)
        assert len(page["workspaces"]) <= 50
        seen.extend(row["workspace_id"] for row in page["workspaces"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert len(seen) == len(set(seen)) == 206
    # Account discovery must not lock or return the whole inventory. All but the
    # last candidate fail current ABAC, exercising the SQL discovery predicate.
    conn.execute("RESET ROLE")
    conn.execute("UPDATE access_member SET customer_scope=ARRAY['denied'] WHERE workspace_id<>%s", (seen[-1],))
    as_api(conn)
    class Counted:
        def __init__(self): self.queries = []
        def execute(self, query, args=None):
            self.queries.append(query)
            return conn.execute(query, args)
    counted = Counted()
    assert repository.first_workspace(counted, SUBJECT)["workspace_id"] == seen[-1]
    assert len(counted.queries) == 3
