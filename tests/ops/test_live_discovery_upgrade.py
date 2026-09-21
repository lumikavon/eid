"""Upgrade populated 0006 to exactly 0007 inside one rolled-back private schema.

This is opt-in real PostgreSQL evidence. Collection never connects to a database;
the shared remote isolation guard must pass before the test opens its connection.
"""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg import sql
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb
import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from scripts import seed_discovery_fixtures as fixture
from scripts.verify_access_fixtures import ROLES
from scripts.verify_local_environment import development_database_url, verify_migration_target
from tests.ops.discovery_live_support import verify_database_identity

pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1",
    reason="Explicit guarded remote PostgreSQL upgrade acceptance required",
)

ROOT = Path(__file__).resolve().parents[2]
OLD_HEAD = "0006_api_write_only"
NEW_HEAD = "0007_workspace_discovery"
OLD_RELATIONS = {
    "alembic_version", "identity_account", "workspace", "workspace_membership",
    "access_workspace", "access_member", "access_resource", "access_audit",
    "access_invalidation", "access_delegation", "access_current_facts",
}
NEW_TABLES = {
    "discovery_record", "discovery_participant", "discovery_favorite",
    "discovery_restore_policy", "discovery_receipt",
}
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")
SERVICE_ROLES = ("eid_api", "eid_worker")


def _relations(conn, schema):
    return conn.execute(
        "SELECT c.relname,c.relkind,c.relowner,c.relacl::text AS acl "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relkind IN ('r','p','v') ORDER BY c.relname",
        (schema,),
    ).fetchall()


def _schema_snapshot(conn, schema, *, omit_version_rows=False):
    """Keep every column and row, including nulls, arrays, JSON and old timestamps."""
    namespace = conn.execute(
        "SELECT nspowner,nspacl::text AS acl FROM pg_namespace WHERE nspname=%s", (schema,),
    ).fetchone()
    relations = _relations(conn, schema)
    columns = conn.execute(
        "SELECT to_jsonb(c) AS definition FROM information_schema.columns c "
        "WHERE table_schema=%s ORDER BY table_name,ordinal_position", (schema,),
    ).fetchall()
    column_acls = conn.execute(
        "SELECT c.relname,a.attname,a.attacl::text AS acl "
        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relkind IN ('r','p','v') "
        "AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum", (schema,),
    ).fetchall()
    rows = {}
    for relation in relations:
        table = relation["relname"]
        if omit_version_rows and table == "alembic_version":
            continue
        rows[table] = conn.execute(sql.SQL(
            "SELECT to_jsonb(r) AS row FROM {} r ORDER BY to_jsonb(r)::text"
        ).format(sql.Identifier(schema, table))).fetchall()
    return {"namespace": namespace, "relations": relations, "columns": columns,
            "column_acls": column_acls, "rows": rows}


def _functions_snapshot(conn, schema):
    return conn.execute(
        "SELECT p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,"
        "pg_get_functiondef(p.oid) AS definition,p.proowner,p.proacl::text AS acl,"
        "p.prosecdef,p.proconfig,has_function_privilege('eid_api',p.oid,'EXECUTE') AS api,"
        "has_function_privilege('eid_worker',p.oid,'EXECUTE') AS worker "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname=%s ORDER BY p.proname,p.oid", (schema,),
    ).fetchall()


def _roles_snapshot(conn):
    names = ["eid_api", "eid_worker", "eid_migrator"]
    # pg_roles does not expose password hashes; include role inheritance as well.
    roles = conn.execute(
        "SELECT oid,rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,"
        "rolreplication,rolbypassrls,rolconnlimit,rolvaliduntil,rolconfig "
        "FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname", (names,),
    ).fetchall()
    assert {role["rolname"] for role in roles} == set(names)
    for role in roles:
        if role["rolname"] in SERVICE_ROLES:
            assert all(role[key] is False for key in (
                "rolsuper", "rolcreaterole", "rolcreatedb", "rolreplication", "rolbypassrls",
            ))
    memberships = conn.execute(
        "SELECT to_jsonb(m) AS membership FROM pg_auth_members m "
        "WHERE roleid=ANY(%s::oid[]) OR member=ANY(%s::oid[]) ORDER BY to_jsonb(m)::text",
        ([role["oid"] for role in roles], [role["oid"] for role in roles]),
    ).fetchall()
    return roles, memberships


def _effective_grants(conn, schema, tables):
    table_grants = conn.execute(
        "SELECT c.relname,r.role,p.privilege,"
        "has_table_privilege(r.role,c.oid,p.privilege) AS allowed "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN unnest(%s::text[]) r(role) CROSS JOIN unnest(%s::text[]) p(privilege) "
        "WHERE n.nspname=%s AND c.relname=ANY(%s) ORDER BY c.relname,r.role,p.privilege",
        (list(SERVICE_ROLES), list(TABLE_PRIVILEGES), schema, sorted(tables)),
    ).fetchall()
    column_grants = conn.execute(
        "SELECT c.relname,a.attname,r.role,p.privilege,"
        "has_column_privilege(r.role,c.oid,a.attnum,p.privilege) AS allowed "
        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN unnest(%s::text[]) r(role) CROSS JOIN unnest(%s::text[]) p(privilege) "
        "WHERE n.nspname=%s AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped "
        "ORDER BY c.relname,a.attnum,r.role,p.privilege",
        (list(SERVICE_ROLES), list(COLUMN_PRIVILEGES), schema, sorted(tables)),
    ).fetchall()
    return table_grants, column_grants


def _assert_grants(conn, schema, tables, expected, column_updates=None):
    """Assert effective privileges, including inherited and table-wide column grants."""
    table_grants, column_grants = _effective_grants(conn, schema, tables)
    assert len(table_grants) == len(tables) * len(SERVICE_ROLES) * len(TABLE_PRIVILEGES)
    for grant in table_grants:
        allowed = grant["privilege"] in expected.get((grant["role"], grant["relname"]), set())
        assert grant["allowed"] is allowed, grant
    for grant in column_grants:
        allowed = grant["privilege"] in expected.get((grant["role"], grant["relname"]), set())
        if grant["role"] == "eid_api" and grant["privilege"] == "UPDATE":
            allowed |= grant["attname"] in (column_updates or {}).get(grant["relname"], set())
        assert grant["allowed"] is allowed, grant
    return table_grants, column_grants


def _old_expected_grants():
    append_only = {"access_audit", "access_invalidation", "access_delegation"}
    expected = {("eid_api", table): {"SELECT"} for table in OLD_RELATIONS - append_only}
    expected.update({("eid_api", table): {"INSERT"} for table in append_only})
    for table in ("workspace_membership", "access_workspace", "access_member"):
        expected[("eid_api", table)].add("UPDATE")
    expected[("eid_worker", "alembic_version")] = {"SELECT"}
    return expected


def _insert(conn, table, row):
    conn.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, row)),
        sql.SQL(",").join(sql.Placeholder() for _ in row),
    ), tuple(row.values()))


def _seed_0006(conn, boundary):
    now = datetime.now(timezone.utc)
    historical = datetime(2020, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    users = {role: {"actor_id": str(uuid4()), "subject": "upgrade-" + uuid4().hex}
             for role in ROLES}
    declared = fixture.definition(
        boundary["nonce"], "upgrade-" + uuid4().hex[:20], users, now.isoformat(),
    )
    for role, user in users.items():
        _insert(conn, "identity_account", {
            "id": user["actor_id"], "subject": user["subject"],
            "display_name": "0006 升级保留 · " + role, "department": "验收部",
            "active": role != "system_admin",
        })
    # Reuse the owned synthetic definition only for tables actually present at 0006.
    for table, rows in declared["rows"].items():
        if table not in OLD_RELATIONS:
            continue
        for index, original in enumerate(rows):
            row = dict(original)
            if table == "workspace_membership":
                row["active"] = index != 0
            elif table == "access_workspace":
                row["policy_epoch"] = 7 + index
            elif table == "access_member":
                row.update(policy_epoch=3 + index, valid_from=historical,
                           valid_until=historical + timedelta(days=1) if index == 0 else None)
            elif table == "access_resource":
                row["policy_epoch"] = 11 + index
                if row["id"] in {declared["records"]["a:document"],
                                 declared["records"]["a:archived"]}:
                    # head_ref is the existing permission metadata reference, not a document AST.
                    row.update(head_ref=uuid4(), approval_state="approved",
                               publication_state="published", valid_from=historical)
            _insert(conn, table, row)
    actor = users["author"]["actor_id"]
    workspace = declared["workspaces"]["a"]
    resource = declared["records"]["a:document"]
    for index in range(2):
        audit = uuid4()
        trace = "a" * 32 if index else None
        _insert(conn, "access_audit", {
            "id": audit, "workspace_id": workspace, "actor_id": actor, "target_id": resource,
            "action": "resource.policy.updated", "before_policy": Jsonb({"classification": index}),
            "after_policy": Jsonb({"classification": index + 1, "roles": ["author", "expert"]}),
            "request_id": "upgrade-audit-" + str(index), "occurred_at": historical,
            "trace_id": trace,
        })
        _insert(conn, "access_invalidation", {
            "id": audit, "workspace_id": workspace, "actor_id": actor,
            "policy_epoch": 6 + index, "created_at": historical,
        })
        _insert(conn, "access_delegation", {
            "id": uuid4(), "actor_id": actor, "workspace_id": workspace,
            "resource_id": resource if index else None,
            "operation": "resource:read" if index else "workspace:read",
            "purpose": "0006 upgrade preservation", "service_id": "eid-worker",
            "expires_at": now + timedelta(hours=1) if index else historical + timedelta(days=1),
            "active": bool(index), "issued_epoch": 7 if index else 6, "created_at": historical,
            "request_id": "upgrade-delegation" if index else None, "trace_id": trace,
        })


def _upgrade(connection, conn, scripts, schema, target):
    # SQLAlchemy expects tuple rows; the shared psycopg guard/snapshots expect dictionaries.
    previous_factory = conn.row_factory
    conn.row_factory = tuple_row
    try:
        context = MigrationContext.configure(connection, opts={
            "version_table_schema": schema,
            "fn": lambda heads, _: scripts._upgrade_revs(target, heads),
        })
        with Operations.context(context):
            context.run_migrations()
    finally:
        conn.row_factory = previous_factory
    assert conn.execute(sql.SQL("SELECT version_num FROM {}.alembic_version").format(
        sql.Identifier(schema),
    )).fetchall() == [{"version_num": target}]


def test_0006_to_0007_preserves_all_existing_data_and_security_and_rolls_back():
    assert os.getenv("EID_RUN_LIVE_TESTS") == "1", "Explicit live-test opt-in required"
    boundary = fixture.selected_boundary()
    url = development_database_url()  # Resolves the selected runtime client port, including 15432.
    verify_migration_target(url)
    assert fixture.selected_boundary() == boundary
    schema = "eid_discovery_upgrade_" + uuid4().hex
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    engine = sa.create_engine(url, poolclass=NullPool, connect_args={
        "connect_timeout": 3, "options": "-c statement_timeout=10000 -c lock_timeout=5000",
    })
    try:
        with engine.connect() as connection:
            conn = connection.connection.driver_connection
            previous_factory = conn.row_factory
            transaction = connection.begin()
            conn.row_factory = dict_row
            try:
                verify_database_identity(conn, "eid_migrator")
                public_before = _schema_snapshot(conn, "public")
                public_functions_before = _functions_snapshot(conn, "public")
                roles_before = _roles_snapshot(conn)
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO eid_api,eid_worker").format(
                    sql.Identifier(schema),
                ))
                conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
                assert conn.execute("SELECT current_schema() AS name").fetchone() == {"name": schema}
                conn.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(
                    sql.Identifier(schema), sql.Literal("eid-discovery-upgrade:" + boundary["nonce"]),
                ))
                _upgrade(connection, conn, scripts, schema, OLD_HEAD)
                assert {row["relname"] for row in _relations(conn, schema)} == OLD_RELATIONS
                _seed_0006(conn, boundary)
                old_before = _schema_snapshot(conn, schema, omit_version_rows=True)
                assert all(old_before["rows"].values()), "Every legacy table/view must contain rows"
                functions_before = _functions_snapshot(conn, schema)
                assert len(functions_before) == 1
                assert functions_before[0]["proname"] == "eid_worker_access"
                assert functions_before[0]["api"] is False
                assert functions_before[0]["worker"] is True
                assert functions_before[0]["prosecdef"] is True
                grants_before = _assert_grants(conn, schema, OLD_RELATIONS, _old_expected_grants())

                _upgrade(connection, conn, scripts, schema, NEW_HEAD)

                after = _schema_snapshot(conn, schema, omit_version_rows=True)
                assert after["namespace"] == old_before["namespace"]
                assert {row["relname"] for row in after["relations"]} == OLD_RELATIONS | NEW_TABLES
                assert {table: rows for table, rows in after["rows"].items()
                        if table in OLD_RELATIONS} == old_before["rows"]
                assert [row for row in after["relations"]
                        if row["relname"] in OLD_RELATIONS] == old_before["relations"]
                assert [row for row in after["columns"]
                        if row["definition"]["table_name"] in OLD_RELATIONS] == old_before["columns"]
                assert [row for row in after["column_acls"]
                        if row["relname"] in OLD_RELATIONS] == old_before["column_acls"]
                assert all(after["rows"][table] == [] for table in NEW_TABLES), "No automatic backfill"
                assert _functions_snapshot(conn, schema) == functions_before
                assert _roles_snapshot(conn) == roles_before
                assert _assert_grants(conn, schema, OLD_RELATIONS,
                                      _old_expected_grants()) == grants_before
                new_grants = {("eid_api", table): {"SELECT"} for table in NEW_TABLES}
                for table in ("discovery_favorite", "discovery_receipt"):
                    new_grants[("eid_api", table)].add("INSERT")
                _assert_grants(conn, schema, NEW_TABLES, new_grants, {
                    "discovery_record": {"visibility", "revision", "updated_at"},
                    "discovery_favorite": {"active", "revision", "updated_at"},
                })
                assert conn.execute(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "CROSS JOIN LATERAL aclexplode(c.relacl) acl "
                    "WHERE n.nspname=%s AND c.relname=ANY(%s) AND ("
                    "acl.grantee NOT IN (c.relowner,'eid_api'::regrole) "
                    "OR (acl.grantee='eid_api'::regrole AND acl.is_grantable))",
                    (schema, sorted(NEW_TABLES)),
                ).fetchall() == []
                assert conn.execute(
                    "SELECT c.relname,a.attname FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid=a.attrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "CROSS JOIN LATERAL aclexplode(a.attacl) acl "
                    "WHERE n.nspname=%s AND c.relname=ANY(%s) AND ("
                    "acl.grantee NOT IN (c.relowner,'eid_api'::regrole) "
                    "OR (acl.grantee='eid_api'::regrole AND acl.is_grantable))",
                    (schema, sorted(NEW_TABLES)),
                ).fetchall() == []
                assert _schema_snapshot(conn, "public") == public_before
                assert _functions_snapshot(conn, "public") == public_functions_before
            finally:
                conn.row_factory = previous_factory
                transaction.rollback()  # The new schema, fixtures, grants and both migrations together.
            try:
                conn.row_factory = dict_row
                assert conn.execute("SELECT nspname FROM pg_namespace WHERE nspname=%s",
                                    (schema,)).fetchall() == []
                assert _schema_snapshot(conn, "public") == public_before
                assert _functions_snapshot(conn, "public") == public_functions_before
                assert _roles_snapshot(conn) == roles_before
            finally:
                conn.row_factory = previous_factory
    finally:
        engine.dispose()
