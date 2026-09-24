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
REQUIRED_TABLES = REQUIRED_0008_TABLES | NEW_0009_TABLES | NEW_0010_TABLES


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
            ).scalar_one() == "0010_task_observation"
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
            )
            for function in worker_only + api_only + revoked + internal:
                qualified_function = f'"{schema}".{function}'
                for role in ("eid_api", "eid_worker"):
                    allowed = connection.execute(
                        sa.text("SELECT has_function_privilege(:role, :function, 'EXECUTE')"),
                        {"role": role, "function": qualified_function},
                    ).scalar_one()
                    assert allowed is (function in worker_only and role == "eid_worker"
                                       or function in api_only and role == "eid_api")

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
