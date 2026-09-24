"""在专属本地数据库的唯一空 schema 中执行真实迁移链；事务结束时整体回滚。"""

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from time import monotonic, sleep
import uuid

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import psycopg
from psycopg import sql
import sqlalchemy as sa
from sqlalchemy.pool import NullPool
from psycopg.rows import dict_row

from scripts.verify_local_environment import development_database_url, verify_migration_target
from edw_api.access.repository import first_workspace
from edw_api.documents import repository as documents
from edw_api.documents.schemas import CreateDocument
from edw_api.errors import ApiError


pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1", reason="需要显式隔离环境验收"
)
ROOT = Path(__file__).parents[2]
REQUIRED_0008_TABLES = {
    "alembic_version",
    "identity_account",
    "workspace",
    "workspace_membership",
    "access_workspace", "access_member", "access_resource", "access_audit",
    "access_invalidation", "access_delegation", "access_current_facts",
    "discovery_record", "discovery_participant", "discovery_favorite",
    "discovery_restore_policy", "discovery_receipt",
    "durable_task", "task_dependency", "task_event", "task_outbox", "task_inbox",
    "task_attempt", "task_result", "task_receipt", "task_quarantine",
}
NEW_0009_TABLES = {"task_attempt_stage", "task_effect_intent", "task_scheduler_lease"}
NEW_0010_TABLES = {"task_notification", "task_observation_binding"}
NEW_0011_TABLES = {"template", "template_version", "template_version_state",
                   "template_workspace", "document_knowledge_scope_grant",
                   "document", "document_version", "document_creation_receipt"}
REQUIRED_TABLES = REQUIRED_0008_TABLES | NEW_0009_TABLES | NEW_0010_TABLES | NEW_0011_TABLES


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
            upgrade("0008_durable_submission")
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "0008_durable_submission"
            assert set(
                connection.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = :schema"
                    ),
                    {"schema": schema},
                ).scalars()
            ) == REQUIRED_0008_TABLES
            upgrade("0009_fenced_recovery")
            actor_id, workspace_id = connection.exec_driver_sql(
                "SELECT i.id,w.id FROM identity_account i "
                "JOIN workspace_membership m ON m.identity_id=i.id "
                "JOIN workspace w ON w.id=m.workspace_id "
                "WHERE i.subject='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' "
                "AND w.slug='eid-local'"
            ).one()

            def insert_blocked_task(task_id):
                delegation_id = uuid.uuid4()
                connection.execute(sa.text(
                    "INSERT INTO access_delegation(id,actor_id,workspace_id,operation,purpose,"
                    "service_id,expires_at,issued_epoch) "
                    "VALUES (:delegation,:actor,:workspace,'inventory','migration-test',"
                    "'eid-worker',CURRENT_TIMESTAMP + interval '1 hour',1)"
                ), {"delegation": delegation_id, "actor": actor_id, "workspace": workspace_id})
                connection.execute(sa.text(
                    "INSERT INTO durable_task(id,workspace_id,actor_id,delegation_id,input,"
                    "input_hash,state,stage,current_seq,error_code,request_id,trace_id,"
                    "created_at,updated_at) VALUES "
                    "(:task,:workspace,:actor,:delegation,'{}'::jsonb,:hash,'BLOCKED',"
                    "'blocked',2,'DEPENDENCY_BLOCKED','migration-test',:trace,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"task": task_id, "workspace": workspace_id, "actor": actor_id,
                    "delegation": delegation_id, "hash": "a" * 64, "trace": "b" * 32})
                connection.execute(sa.text(
                    "INSERT INTO task_event(event_id,task_id,seq,event_type,state) VALUES "
                    "(:event,:task,1,'task.queued','QUEUED')"
                ), {"event": uuid.uuid4(), "task": task_id})

            historical_task, new_task = uuid.uuid4(), uuid.uuid4()
            insert_blocked_task(historical_task)
            connection.execute(sa.text(
                "INSERT INTO task_event(event_id,task_id,seq,event_type,state) VALUES "
                "(:event,:task,2,'task.blocked','BLOCKED')"
            ), {"event": uuid.uuid4(), "task": historical_task})
            upgrade("head")

            historic_event = connection.execute(sa.text(
                "SELECT e.event_type,e.state,e.occurred_at,n.event_type,n.state,n.created_at "
                "FROM task_event e JOIN task_notification n "
                "ON n.task_id=e.task_id AND n.event_seq=e.seq "
                "WHERE e.task_id=:task AND e.seq=2"
            ), {"task": historical_task}).one()
            assert historic_event[:2] == historic_event[3:5] == ("task.blocked", "BLOCKED")
            assert historic_event[2] == historic_event[5]
            assert connection.execute(sa.text(
                "SELECT count(*) FROM task_notification WHERE task_id=:task AND event_seq=2"
            ), {"task": historical_task}).scalar_one() == 1

            insert_blocked_task(new_task)
            connection.execute(sa.text(
                "INSERT INTO task_event(event_id,task_id,seq,event_type,state) VALUES "
                "(:event,:task,2,'task.blocked','BLOCKED')"
            ), {"event": uuid.uuid4(), "task": new_task})
            assert connection.execute(sa.text(
                "SELECT count(*) FROM task_notification WHERE task_id=:task AND event_seq=2 "
                "AND workspace_id=:workspace AND actor_id=:actor "
                "AND event_type='task.blocked' AND state='BLOCKED'"
            ), {"task": new_task, "workspace": workspace_id, "actor": actor_id}).scalar_one() == 1
            replay = connection.execute(sa.text(
                "INSERT INTO task_notification(workspace_id,actor_id,task_id,event_seq,"
                "event_type,state,created_at) "
                "SELECT workspace_id,actor_id,task_id,event_seq,event_type,state,created_at "
                "FROM task_notification WHERE task_id=:task AND event_seq=2 "
                "ON CONFLICT(task_id,event_seq) DO NOTHING"
            ), {"task": new_task})
            assert replay.rowcount == 0
            assert connection.execute(sa.text(
                "SELECT count(*) FROM task_notification WHERE task_id IN (:old,:new)"
            ), {"old": historical_task, "new": new_task}).scalar_one() == 2

            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "0011_template_creation"
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
                        "access_audit", "access_invalidation", "access_delegation",
                        "task_outbox", "task_inbox", "task_attempt", "task_quarantine",
                        "task_scheduler_lease"})
                    assert allowed is expected

            for table in NEW_0009_TABLES | NEW_0010_TABLES:
                qualified_table = f'"{schema}"."{table}"'
                for role in ("eid_api", "eid_worker"):
                    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                        assert not connection.execute(
                            sa.text("SELECT has_table_privilege(:role, :table, :privilege)"),
                            {"role": role, "table": qualified_table, "privilege": privilege},
                        ).scalar_one()

            for table in NEW_0011_TABLES:
                qualified_table = f'"{schema}"."{table}"'
                for role in ("eid_api", "eid_worker"):
                    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE",
                                      "REFERENCES", "TRIGGER"):
                        allowed = connection.execute(
                            sa.text("SELECT has_table_privilege(:role, :table, :privilege)"),
                            {"role": role, "table": qualified_table, "privilege": privilege},
                        ).scalar_one()
                        assert allowed is (role == "eid_api" and privilege == "INSERT"
                                           and table in {"document", "document_version",
                                                         "document_creation_receipt"})

            insert_columns = {
                "access_resource": {"id", "workspace_id", "title", "kind", "project_id",
                                    "customer_id", "product_id", "department", "owner_id",
                                    "classification", "approval_state", "publication_state",
                                    "head_ref", "valid_from"},
                "discovery_record": {"resource_id", "kind", "created_by", "created_at",
                                     "updated_at", "document_type", "lifecycle",
                                     "version_label", "visibility", "revision"},
            }
            for table, granted_columns in insert_columns.items():
                columns = set(connection.execute(sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=:schema AND table_name=:table"
                ), {"schema": schema, "table": table}).scalars())
                assert granted_columns <= columns
                qualified_table = f'"{schema}"."{table}"'
                for role in ("eid_api", "eid_worker"):
                    assert not connection.execute(sa.text(
                        "SELECT has_table_privilege(:role,:table,'INSERT')"
                    ), {"role": role, "table": qualified_table}).scalar_one()
                    for column in columns:
                        allowed = connection.execute(sa.text(
                            "SELECT has_column_privilege(:role,:table,:column,'INSERT')"
                        ), {"role": role, "table": qualified_table, "column": column}).scalar_one()
                        assert allowed is (role == "eid_api" and column in granted_columns)

            worker_only = (
                "eid_task_claim_v2(uuid,jsonb,text,uuid)",
                "eid_task_heartbeat_v2(uuid,uuid,bigint)",
                "eid_task_stage_inventory_v2(uuid,uuid,bigint)",
                "eid_task_finish_inventory_v2(uuid,uuid,bigint,text,text)",
                "eid_task_fail_v2(uuid,uuid,bigint,text)",
                "eid_task_stop_v2(uuid,uuid,bigint)",
                "eid_task_scheduler_lease_v2(uuid)",
                "eid_task_schedule_v2(uuid,bigint)",
            )
            api_only = (
                "eid_task_cancel_observed_v1(uuid,uuid,text)",
                "eid_notification_mark_read_v1(uuid,uuid)",
                "eid_task_scheduler_ready_v2()",
            )
            revoked = (
                "eid_task_claim(uuid,jsonb,text,uuid)",
                "eid_task_finish_inventory(uuid,uuid)",
                "eid_task_cancel_v2(uuid,uuid,text)",
            )
            internal = (
                "eid_task_bind_initial_event()",
                "eid_task_envelope_hash(jsonb)",
                "eid_task_isolate_poison_v2(uuid,jsonb,text,text,uuid)",
                "eid_task_notification_v1()",
                "eid_immutable_template_document_version()",
            )
            template_api_only = (
                "eid_lock_document_knowledge_scope_v1(uuid,text)",
                "eid_lock_template_creation_v1(uuid,uuid)",
            )
            for function in worker_only + api_only + template_api_only + revoked + internal:
                qualified_function = f'"{schema}".{function}'
                for role in ("eid_api", "eid_worker"):
                    allowed = connection.execute(
                        sa.text("SELECT has_function_privilege(:role, :function, 'EXECUTE')"),
                        {"role": role, "function": qualified_function},
                    ).scalar_one()
                    assert allowed is (function in worker_only and role == "eid_worker"
                                       or function in api_only + template_api_only
                                       and role == "eid_api")

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


@pytest.fixture
def isolated_template_schema():
    """A committed, test-owned schema is required for two independent sessions."""
    if os.getenv("EID_RUN_LIVE_TESTS") != "1":
        raise RuntimeError("Explicit isolated live-test opt-in is required")
    url = development_database_url()
    verify_migration_target(url)
    schema = "eid_template_race_" + uuid.uuid4().hex
    marker = "eid-story-2.1-test:" + schema
    engine = sa.create_engine(url, poolclass=NullPool, connect_args={
        "connect_timeout": 3, "options": "-c statement_timeout=10000 -c lock_timeout=5000",
    })
    created = False
    try:
        with engine.begin() as connection:
            identity = connection.exec_driver_sql(
                "SELECT current_database(),current_user,shobj_description(oid,'pg_database') "
                "FROM pg_database WHERE datname=current_database()"
            ).one()
            if identity != ("eid_local_dev", "eid_migrator", "eid-local-dev-v1"):
                raise RuntimeError("Migration target is not the isolated EID test database")
            public_before = _public_state(connection)
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'")
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO eid_api,eid_worker')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "migrations"))
            scripts = ScriptDirectory.from_config(config)
            context = MigrationContext.configure(connection, opts={
                "fn": lambda heads, _: scripts._upgrade_revs("head", heads),
            })
            with Operations.context(context):
                context.run_migrations()
            assert _public_state(connection) == public_before
        created = True
        yield schema
    finally:
        if created:
            # Only the nonce-named schema created above can be removed.
            with engine.begin() as connection:
                database_identity = connection.exec_driver_sql(
                    "SELECT current_database(),current_user,shobj_description(oid,'pg_database') "
                    "FROM pg_database WHERE datname=current_database()"
                ).one()
                if database_identity != ("eid_local_dev", "eid_migrator", "eid-local-dev-v1"):
                    raise RuntimeError("Refusing schema cleanup outside the isolated EID database")
                identity = connection.execute(sa.text(
                    "SELECT pg_get_userbyid(nspowner),obj_description(oid,'pg_namespace') "
                    "FROM pg_namespace WHERE nspname=:schema"
                ), {"schema": schema}).one()
                if identity != ("eid_migrator", marker):
                    raise RuntimeError("Refusing cleanup of a schema without this test's marker")
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
                assert _public_state(connection) == public_before
        engine.dispose()


@contextmanager
def _template_session(schema, role):
    if not (schema.startswith("eid_template_race_") and len(schema) == 50
            and all(char in "0123456789abcdef" for char in schema[18:])):
        raise RuntimeError("Refusing a non-test schema")
    if role not in {"eid_api", "eid_worker", "eid_migrator", "postgres"}:
        raise RuntimeError("Unsupported database role")
    login = role if role in {"eid_migrator", "postgres"} else "postgres"
    url = development_database_url(login).replace("postgresql+psycopg:", "postgresql:")
    with psycopg.connect(url, connect_timeout=3, row_factory=dict_row,
                         options="-c statement_timeout=10000 -c lock_timeout=5000") as conn:
        identity = conn.execute(
            "SELECT current_database() AS db,current_user AS actor,"
            "shobj_description(oid,'pg_database') AS marker "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        if identity != {"db": "eid_local_dev", "actor": login,
                        "marker": "eid-local-dev-v1"}:
            raise RuntimeError("Database session is not isolated EID development")
        schema_marker = conn.execute(
            "SELECT obj_description(oid,'pg_namespace') AS marker "
            "FROM pg_namespace WHERE nspname=%s", (schema,)
        ).fetchone()
        if schema_marker != {"marker": "eid-story-2.1-test:" + schema}:
            raise RuntimeError("Database session is not using this test's schema")
        conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
        if role != login:
            conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        assert conn.execute("SELECT current_user AS actor").fetchone()["actor"] == role
        yield conn


def _wait_for_database_lock(schema, pid, future):
    deadline = monotonic() + 3
    with _template_session(schema, "postgres") as observer:
        while monotonic() < deadline:
            row = observer.execute(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,)
            ).fetchone()
            if row is not None and row["wait_event_type"] == "Lock":
                return
            assert not future.done(), "The competing transaction did not wait for the lock"
            sleep(0.02)
    pytest.fail("The competing transaction never waited for the template lock")


def _template_version():
    return uuid.uuid5(uuid.NAMESPACE_URL, "eid-story-2.1-version-technical_solution")


def _create_under_api_role(schema, name, started=None, pids=None):
    with _template_session(schema, "eid_api") as conn:
        if started is not None:
            pids.append(conn.info.backend_pid)
            started.set()
        return documents.create_document(
            conn, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            uuid.UUID("22222222-2222-4222-8222-222222222222"),
            CreateDocument(name=name, document_type="technical_solution",
                           knowledge_scope="project_only", template_version_id=_template_version()),
            idempotency_key="race-" + name[-8:], request_id="template-race",
            trace_id="1" * 32,
        )


def test_real_roles_have_only_template_creation_grants(isolated_template_schema):
    schema = isolated_template_schema
    for role in ("eid_api", "eid_worker"):
        with _template_session(schema, role) as conn:
            for table in NEW_0011_TABLES:
                allowed = conn.execute(
                    "SELECT has_table_privilege(current_user,%s,'SELECT') AS allowed",
                    (table,),
                ).fetchone()["allowed"]
                assert allowed is (role == "eid_api")
            for function in ("eid_lock_document_knowledge_scope_v1(uuid,text)",
                             "eid_lock_template_creation_v1(uuid,uuid)"):
                allowed = conn.execute(
                    "SELECT has_function_privilege(current_user,%s,'EXECUTE') AS allowed",
                    (function,),
                ).fetchone()["allowed"]
                assert allowed is (role == "eid_api")
            if role == "eid_worker":
                with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute("SELECT * FROM template_version LIMIT 1")
                with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute("SELECT eid_lock_template_creation_v1(%s,%s)",
                                 (uuid.UUID("22222222-2222-4222-8222-222222222222"),
                                  _template_version()))
            else:
                for statement in ("UPDATE template_version_state SET status='deprecated' WHERE false",
                                  "UPDATE document_knowledge_scope_grant SET active=false WHERE false",
                                  "DELETE FROM document WHERE false"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                        conn.execute(statement)


def test_deprecation_and_create_serialize_in_both_orders(isolated_template_schema):
    schema = isolated_template_schema
    name = "并发创建-" + uuid.uuid4().hex[:8]
    version = _template_version()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with _template_session(schema, "eid_migrator") as deprecator:
            assert deprecator.execute(
                "UPDATE template_version_state SET status='deprecated' WHERE version_id=%s",
                (version,),
            ).rowcount == 1
            started, pids = Event(), []
            attempt = pool.submit(_create_under_api_role, schema, name, started, pids)
            assert started.wait(2)
            _wait_for_database_lock(schema, pids[0], attempt)
        with pytest.raises(ApiError) as rejected:
            attempt.result(timeout=5)
        assert rejected.value.code == "TEMPLATE_DEPRECATED"

    with _template_session(schema, "eid_migrator") as inspector:
        assert inspector.execute("SELECT count(*) AS n FROM document").fetchone()["n"] == 0
        assert inspector.execute(
            "SELECT count(*) AS n FROM document_creation_receipt"
        ).fetchone()["n"] == 0
        inspector.execute(
            "UPDATE template_version_state SET status='active' WHERE version_id=%s", (version,)
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with _template_session(schema, "eid_api") as creator:
            result = documents.create_document(
                creator, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                uuid.UUID("22222222-2222-4222-8222-222222222222"),
                CreateDocument(name=name, document_type="technical_solution",
                               knowledge_scope="project_only", template_version_id=version),
                idempotency_key="second-" + name[-8:], request_id="template-race",
                trace_id="2" * 32,
            )
            started, pids = Event(), []

            def deprecate_after_create():
                with _template_session(schema, "eid_migrator") as deprecator:
                    pids.append(deprecator.info.backend_pid)
                    started.set()
                    return deprecator.execute(
                        "UPDATE template_version_state SET status='deprecated' WHERE version_id=%s",
                        (version,),
                    ).rowcount

            deprecation = pool.submit(deprecate_after_create)
            assert started.wait(2)
            _wait_for_database_lock(schema, pids[0], deprecation)
        assert deprecation.result(timeout=5) == 1

    with _template_session(schema, "eid_migrator") as inspector:
        assert inspector.execute(
            "SELECT count(*) AS n FROM document WHERE id=%s", (result["id"],)
        ).fetchone()["n"] == 1
        assert inspector.execute(
            "SELECT count(*) AS n FROM document_creation_receipt WHERE document_id=%s",
            (result["id"],),
        ).fetchone()["n"] == 1


def test_receipt_failure_rolls_back_every_create_write(isolated_template_schema):
    schema = isolated_template_schema
    with _template_session(schema, "eid_migrator") as migrator:
        migrator.execute(
            "ALTER TABLE document_creation_receipt ADD CONSTRAINT reject_receipt CHECK (false)"
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        _create_under_api_role(schema, "回滚检查-" + uuid.uuid4().hex[:8])
    with _template_session(schema, "eid_migrator") as inspector:
        for table in ("document", "document_version", "document_creation_receipt"):
            assert inspector.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))
            ).fetchone()["n"] == 0
        assert inspector.execute(
            "SELECT count(*) AS n FROM access_resource WHERE kind='document'"
        ).fetchone()["n"] == 0
        assert inspector.execute(
            "SELECT count(*) AS n FROM discovery_record WHERE kind='document'"
        ).fetchone()["n"] == 0
        assert inspector.execute(
            "SELECT count(*) AS n FROM access_audit WHERE action='document.create'"
        ).fetchone()["n"] == 0
