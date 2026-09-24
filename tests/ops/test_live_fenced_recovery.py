"""Story 1.5 PostgreSQL acceptance source; execution requires separate authorization.

Every future run verifies the project database, creates a unique private schema,
and rolls its migration and synthetic rows back. This file does not exercise a
Broker, a service, a process crash, or a real external effect.
"""

from contextlib import contextmanager
import os
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg.errors import InsufficientPrivilege, RaiseException, UniqueViolation
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb
import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from edw_api.task_contract import SubmitTask, payload_hash
from edw_api.tasks.repository import submit
from scripts.verify_local_environment import development_database_url, verify_migration_target


pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1",
    reason="Requires renewed isolated PostgreSQL test authorization",
)
ROOT = Path(__file__).parents[2]
ACTOR = UUID("11111111-1111-4111-8111-111111111111")
WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
SUBJECT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
WORKER_FUNCTIONS = frozenset({
    "eid_task_claim_v2", "eid_task_heartbeat_v2", "eid_task_stage_inventory_v2",
    "eid_task_finish_inventory_v2", "eid_task_fail_v2", "eid_task_stop_v2",
    "eid_task_scheduler_lease_v2", "eid_task_schedule_v2",
    "eid_task_relay_claim", "eid_task_relay_quarantine",
})


@pytest.fixture
def database():
    verify_migration_target(development_database_url())
    engine = sa.create_engine(
        development_database_url("postgres"), poolclass=NullPool,
        connect_args={"connect_timeout": 3,
                      "options": "-c statement_timeout=10000 -c lock_timeout=2000"},
    )
    schema = "eid_fenced_recovery_test_" + uuid4().hex
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert connection.exec_driver_sql(
                    "SELECT current_database(),current_user,shobj_description(oid,'pg_database') "
                    "FROM pg_database WHERE datname=current_database()"
                ).one() == ("eid_local_dev", "postgres", "eid-local-dev-v1")
                connection.exec_driver_sql("SET LOCAL ROLE eid_migrator")
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO eid_api,eid_worker')
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                config = Config(str(ROOT / "alembic.ini"))
                config.set_main_option("script_location", str(ROOT / "migrations"))
                scripts = ScriptDirectory.from_config(config)
                context = MigrationContext.configure(connection, opts={"fn": lambda heads, _:
                    scripts._upgrade_revs("0009_fenced_recovery", heads)})
                with Operations.context(context):
                    context.run_migrations()
                conn = connection.connection.driver_connection
                conn.row_factory = dict_row
                try:
                    yield conn
                finally:
                    conn.row_factory = tuple_row
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@contextmanager
def identity(conn, role):
    assert role in {"eid_worker", "eid_api"}
    try:
        with conn.transaction():
            conn.execute("RESET ROLE")
            conn.execute(f"SET LOCAL SESSION AUTHORIZATION {role}")
            assert conn.execute("SELECT current_user,session_user").fetchone() == {
                "current_user": role, "session_user": role}
            yield
    finally:
        conn.execute("RESET SESSION AUTHORIZATION")
        conn.execute("SET LOCAL ROLE eid_migrator")


def worker_call(conn, function, *parameters):
    assert function in WORKER_FUNCTIONS
    placeholders = ",".join(["%s"] * len(parameters))
    with identity(conn, "eid_worker"):
        return conn.execute(f"SELECT {function}({placeholders}) AS value", parameters
                            ).fetchone()["value"]


def cancel(conn, task_id, actor=ACTOR):
    with identity(conn, "eid_api"):
        return conn.execute("SELECT eid_task_cancel_v2(%s,%s,%s) AS value",
                            (task_id, actor, uuid4().hex)).fetchone()["value"]


@contextmanager
def api_identity(conn):
    try:
        with conn.transaction():
            conn.execute("SET LOCAL ROLE eid_api")
            yield
    finally:
        conn.execute("SET LOCAL ROLE eid_migrator")


def submission(conn, *, depends_on=()):
    with api_identity(conn):
        task = submit(
            conn, SUBJECT, WORKSPACE,
            SubmitTask(operation="inventory", input={"limit": 50}, depends_on=list(depends_on)),
            uuid4().hex, "fenced-recovery-source-test", "a" * 32,
        )
    row = conn.execute("SELECT envelope FROM task_outbox WHERE task_id=%s",
                       (task.task_id,)).fetchone()
    return task.task_id, row["envelope"]


def claim(conn, envelope, owner):
    return worker_call(conn, "eid_task_claim_v2", UUID(envelope["event_id"]),
                       Jsonb(envelope), payload_hash(envelope), owner)


def stage(conn, event, owner, fence):
    return worker_call(conn, "eid_task_stage_inventory_v2", event, owner, fence)


def finish(conn, event, owner, fence, base_hash, content_hash):
    return worker_call(conn, "eid_task_finish_inventory_v2", event, owner, fence,
                       base_hash, content_hash)


def scheduler(conn, owner):
    leased = worker_call(conn, "eid_task_scheduler_lease_v2", owner)
    assert leased["status"] == "leased"
    return leased["fence_token"]


def due(conn, task_id):
    # Mutation is confined to a task created in this rollback-only private schema.
    conn.execute("UPDATE durable_task SET next_retry_at=clock_timestamp()-interval '1 second' "
                 "WHERE id=%s AND state='RETRY_WAIT'", (task_id,))


def advance_retry(conn, task_id, owner, scheduler_fence):
    due(conn, task_id)
    planned = worker_call(conn, "eid_task_schedule_v2", owner, scheduler_fence)
    assert planned["status"] == "queued" and planned["task_id"] == task_id
    envelope = conn.execute("SELECT envelope FROM task_outbox WHERE event_id=%s",
                            (planned["event_id"],)).fetchone()["envelope"]
    return envelope


def rows(conn, task_id):
    return {
        table: conn.execute(f"SELECT count(*) AS n FROM {table} WHERE task_id=%s", (task_id,)
                            ).fetchone()["n"]
        for table in ("task_attempt", "task_attempt_stage", "task_inbox", "task_result",
                      "task_event", "task_outbox")
    }


def inventory_record(conn):
    # Only a synthetic row in the fixture's rollback-only private schema.
    resource_id = uuid4()
    conn.execute("""INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,
                         product_id,department,owner_id,classification,approval_state,policy_epoch)
                  VALUES (%s,%s,'inventory candidate','document','eid-local','local-customer',
                          'local-product','产品部',%s,1,'draft',1)""",
                 (resource_id, WORKSPACE, ACTOR))
    conn.execute("""INSERT INTO discovery_record(resource_id,kind,created_by,document_type,lifecycle,visibility)
                  VALUES (%s,'document',%s,'technical','DRAFT','visible')""",
                 (resource_id, ACTOR))
    return resource_id


def test_expired_lease_advances_fence_and_old_staging_cannot_finish(database):
    conn = database
    task_id, first_envelope = submission(conn)
    first_event, old_owner = UUID(first_envelope["event_id"]), uuid4()
    old = claim(conn, first_envelope, old_owner)
    assert old["status"] == "claimed"
    old_hash = stage(conn, first_event, old_owner, old["fence_token"])["content_hash"]
    old_stage = conn.execute("SELECT * FROM task_attempt_stage WHERE task_id=%s AND attempt=1",
                             (task_id,)).fetchone()
    conn.execute("UPDATE task_attempt SET lease_until=clock_timestamp()-interval '1 second' "
                 "WHERE task_id=%s AND attempt=1", (task_id,))
    leader, wrong_owner = uuid4(), uuid4()
    leader_fence = scheduler(conn, leader)
    assert worker_call(conn, "eid_task_schedule_v2", wrong_owner, leader_fence)["status"] == "lost"
    recovered = worker_call(conn, "eid_task_schedule_v2", leader, leader_fence)
    assert recovered["status"] == "RETRY_WAIT"
    assert recovered["fence_token"] > old["fence_token"]
    before = rows(conn, task_id)
    assert finish(conn, first_event, old_owner, old["fence_token"],
                  first_envelope["input_hash"], old_hash)["status"] == "lost"
    assert rows(conn, task_id) == before
    second_envelope = advance_retry(conn, task_id, leader, leader_fence)
    second_event, new_owner = UUID(second_envelope["event_id"]), uuid4()
    new = claim(conn, second_envelope, new_owner)
    assert new["status"] == "claimed" and new["fence_token"] > recovered["fence_token"]
    new_hash = stage(conn, second_event, new_owner, new["fence_token"])["content_hash"]
    assert conn.execute("SELECT * FROM task_attempt_stage WHERE task_id=%s AND attempt=1",
                        (task_id,)).fetchone() == old_stage
    assert conn.execute("SELECT attempt,fence_token,event_id FROM task_attempt_stage "
                        "WHERE task_id=%s ORDER BY attempt", (task_id,)).fetchall() == [
        {"attempt": 1, "fence_token": old["fence_token"], "event_id": first_event},
        {"attempt": 2, "fence_token": new["fence_token"], "event_id": second_event},
    ]
    assert finish(conn, second_event, new_owner, new["fence_token"],
                  second_envelope["input_hash"], new_hash)["status"] == "SUCCEEDED"
    finished = conn.execute("SELECT state,result_id FROM durable_task WHERE id=%s", (task_id,)
                            ).fetchone()
    assert finished["state"] == "SUCCEEDED" and finished["result_id"] is not None
    assert rows(conn, task_id)["task_result"] == 1


@pytest.mark.parametrize("guard", ["fence", "base_hash", "content_hash", "lease", "policy",
                                    "delegation"])
def test_completion_guards_leave_every_accepted_row_unchanged(database, guard):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    content_hash = stage(conn, event, owner, ticket["fence_token"])["content_hash"]
    fence, base_hash = ticket["fence_token"], envelope["input_hash"]
    if guard == "fence":
        fence += 1
    elif guard == "base_hash":
        base_hash = "0" * 64 if base_hash != "0" * 64 else "1" * 64
    elif guard == "content_hash":
        content_hash = "0" * 64 if content_hash != "0" * 64 else "1" * 64
    elif guard == "lease":
        conn.execute("UPDATE task_attempt SET lease_until=clock_timestamp()-interval '1 second' "
                     "WHERE task_id=%s", (task_id,))
    elif guard == "policy":
        conn.execute("UPDATE access_workspace SET policy_epoch=policy_epoch+1 "
                     "WHERE workspace_id=%s", (WORKSPACE,))
    else:
        conn.execute("UPDATE access_delegation SET active=false WHERE id=%s",
                     (UUID(envelope["delegation_id"]),))
    before = rows(conn, task_id)
    status = finish(conn, event, owner, fence, base_hash, content_hash)["status"]
    assert status == ("authorization_denied" if guard in {"policy", "delegation"} else "lost")
    assert rows(conn, task_id) == before
    assert conn.execute("SELECT state,result_id FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "RUNNING", "result_id": None}
    assert conn.execute("SELECT state FROM task_inbox WHERE event_id=%s", (event,)
                        ).fetchone()["state"] == "received"


@pytest.mark.parametrize("kind", ["transient_dependency", "format_repairable"])
def test_retry_is_bounded_by_one_persisted_due_time(database, kind):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    result = worker_call(conn, "eid_task_fail_v2", event, owner, ticket["fence_token"], kind)
    assert result["status"] == "RETRY_WAIT" and result["next_retry_at"] is not None
    row = conn.execute("SELECT next_retry_at,updated_at,format_repairs,error_class "
                       "FROM durable_task WHERE id=%s", (task_id,)).fetchone()
    seconds = (row["next_retry_at"] - row["updated_at"]).total_seconds()
    assert 2 <= seconds < 3
    assert row["format_repairs"] == (1 if kind == "format_repairable" else 0)
    assert row["error_class"] == ("FORMAT" if kind == "format_repairable" else "TRANSIENT")
    leader = uuid4()
    fence = scheduler(conn, leader)
    assert worker_call(conn, "eid_task_schedule_v2", leader, fence)["status"] == "idle"
    next_envelope = advance_retry(conn, task_id, leader, fence)
    assert worker_call(conn, "eid_task_schedule_v2", leader, fence)["status"] == "idle"
    assert claim(conn, next_envelope, uuid4())["status"] == "claimed"
    assert conn.execute("SELECT count(*) AS n FROM task_outbox WHERE task_id=%s", (task_id,)
                        ).fetchone()["n"] == 2


def test_format_repair_is_attempted_once_then_dead_letter(database):
    conn = database
    task_id, envelope = submission(conn)
    leader = uuid4()
    leader_fence = scheduler(conn, leader)
    for attempt in (1, 2):
        event, owner = UUID(envelope["event_id"]), uuid4()
        ticket = claim(conn, envelope, owner)
        assert ticket["status"] == "claimed" and ticket["attempt"] == attempt
        outcome = worker_call(conn, "eid_task_fail_v2", event, owner,
                              ticket["fence_token"], "format_repairable")
        if attempt == 1:
            assert outcome["status"] == "RETRY_WAIT"
            envelope = advance_retry(conn, task_id, leader, leader_fence)
        else:
            assert outcome["status"] == "DEAD_LETTER"
            assert outcome["error_code"] == "ATTEMPTS_EXHAUSTED"
    assert conn.execute("SELECT format_repairs,next_retry_at FROM durable_task WHERE id=%s",
                        (task_id,)).fetchone() == {"format_repairs": 1, "next_retry_at": None}
    assert rows(conn, task_id)["task_outbox"] == 2


def test_transient_attempt_budget_exhausts_without_hot_loop(database):
    conn = database
    task_id, envelope = submission(conn)
    leader = uuid4()
    leader_fence = scheduler(conn, leader)
    for attempt in (1, 2, 3):
        event, owner = UUID(envelope["event_id"]), uuid4()
        ticket = claim(conn, envelope, owner)
        assert ticket["status"] == "claimed" and ticket["attempt"] == attempt
        outcome = worker_call(conn, "eid_task_fail_v2", event, owner,
                              ticket["fence_token"], "transient_dependency")
        if attempt < 3:
            assert outcome["status"] == "RETRY_WAIT"
            envelope = advance_retry(conn, task_id, leader, leader_fence)
        else:
            assert (outcome["status"], outcome["error_code"], outcome["next_retry_at"]) == (
                "DEAD_LETTER", "ATTEMPTS_EXHAUSTED", None)
    assert worker_call(conn, "eid_task_schedule_v2", leader, leader_fence)["status"] == "idle"
    assert rows(conn, task_id)["task_outbox"] == 3


def test_permanent_authorization_failure_has_no_retry_plan(database):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    conn.execute("UPDATE access_delegation SET active=false WHERE id=%s",
                 (UUID(envelope["delegation_id"]),))
    result = worker_call(conn, "eid_task_fail_v2", event, owner, ticket["fence_token"],
                         "transient_dependency")
    assert (result["status"], result["error_class"], result["next_retry_at"]) == (
        "FAILED", "PERMANENT", None)
    assert conn.execute("SELECT state,error_code,attempt FROM durable_task WHERE id=%s",
                        (task_id,)).fetchone() == {
        "state": "FAILED", "error_code": "AUTHORIZATION_EXPIRED_OR_REVOKED", "attempt": 1}
    leader = uuid4()
    assert worker_call(conn, "eid_task_schedule_v2", leader, scheduler(conn, leader))[
        "status"] == "idle"


def test_two_scheduler_owners_cannot_schedule_same_due_intent(database):
    # Same-connection serial calls cover SQL state guards, not concurrent scheduling.
    # The uncommitted private-schema migration is invisible to a second connection.
    conn = database
    task_id, envelope = submission(conn)
    event, worker = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, worker)
    assert worker_call(conn, "eid_task_fail_v2", event, worker,
                       ticket["fence_token"], "transient_dependency")["status"] == "RETRY_WAIT"
    first, second = uuid4(), uuid4()
    first_fence = scheduler(conn, first)
    assert worker_call(conn, "eid_task_scheduler_lease_v2", second)["status"] == "busy"
    due(conn, task_id)
    assert worker_call(conn, "eid_task_schedule_v2", second, first_fence)["status"] == "lost"
    assert worker_call(conn, "eid_task_schedule_v2", first, first_fence)["status"] == "queued"
    assert worker_call(conn, "eid_task_schedule_v2", first, first_fence)["status"] == "idle"
    assert rows(conn, task_id)["task_outbox"] == 2
    assert rows(conn, task_id)["task_attempt"] == 1


def test_api_scheduler_readiness_requires_a_live_lease(database):
    conn = database
    with identity(conn, "eid_api"):
        assert conn.execute("SELECT eid_task_scheduler_ready_v2() AS ready").fetchone()[
            "ready"] is False
    owner = uuid4()
    scheduler(conn, owner)
    with identity(conn, "eid_api"):
        assert conn.execute("SELECT eid_task_scheduler_ready_v2() AS ready").fetchone()[
            "ready"] is True
    conn.execute("UPDATE task_scheduler_lease SET lease_until=clock_timestamp()-interval '1 second' "
                 "WHERE singleton")
    with identity(conn, "eid_api"):
        assert conn.execute("SELECT eid_task_scheduler_ready_v2() AS ready").fetchone()[
            "ready"] is False
    with pytest.raises(InsufficientPrivilege), identity(conn, "eid_worker"):
        conn.execute("SELECT eid_task_scheduler_ready_v2()")


def test_staged_resource_expiry_rejects_completion(database):
    conn = database
    resource_id = inventory_record(conn)
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    assert ticket["status"] == "claimed"
    content_hash = stage(conn, event, owner, ticket["fence_token"])["content_hash"]
    staged = conn.execute("SELECT payload FROM task_attempt_stage WHERE task_id=%s", (task_id,)
                          ).fetchone()["payload"]
    assert any(item["resource_id"] == str(resource_id) for item in staged["items"])
    conn.execute("UPDATE access_resource SET valid_from=clock_timestamp()-interval '2 seconds', "
                 "valid_until=clock_timestamp()-interval '1 second' "
                 "WHERE id=%s", (resource_id,))
    before = rows(conn, task_id)
    assert finish(conn, event, owner, ticket["fence_token"], envelope["input_hash"],
                  content_hash)["status"] == "authorization_denied"
    assert rows(conn, task_id) == before
    assert conn.execute("SELECT state,result_id FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "RUNNING", "result_id": None}


def test_finish_event_failure_rolls_back_result_and_state(database):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    content_hash = stage(conn, event, owner, ticket["fence_token"])["content_hash"]
    next_seq = conn.execute("SELECT current_seq+1 AS seq FROM durable_task WHERE id=%s",
                            (task_id,)).fetchone()["seq"]
    # Force a unique-key failure at the final task_event insert, after result and
    # task/attempt/inbox writes. The deliberate collision is synthetic and rolled back.
    conn.execute("INSERT INTO task_event(event_id,task_id,seq,event_type,state) "
                 "VALUES(%s,%s,%s,'task.running','RUNNING')", (uuid4(), task_id, next_seq))
    before = rows(conn, task_id)
    with pytest.raises(UniqueViolation), conn.transaction():
        finish(conn, event, owner, ticket["fence_token"], envelope["input_hash"], content_hash)
    assert rows(conn, task_id) == before
    assert conn.execute("SELECT state,result_id,current_seq FROM durable_task WHERE id=%s",
                        (task_id,)).fetchone() == {
                            "state": "RUNNING", "result_id": None, "current_seq": next_seq - 1}
    assert conn.execute("SELECT state FROM task_inbox WHERE event_id=%s", (event,)
                        ).fetchone()["state"] == "received"
    assert conn.execute("SELECT state FROM task_attempt WHERE task_id=%s", (task_id,)
                        ).fetchone()["state"] == "RUNNING"


def test_completion_before_cancel_keeps_success(database):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    content_hash = stage(conn, event, owner, ticket["fence_token"])["content_hash"]
    assert finish(conn, event, owner, ticket["fence_token"], envelope["input_hash"],
                  content_hash)["status"] == "SUCCEEDED"
    before = rows(conn, task_id)
    assert cancel(conn, task_id)["status"] == "too_late"
    assert rows(conn, task_id) == before
    assert conn.execute("SELECT state,cancel_requested FROM durable_task WHERE id=%s",
                        (task_id,)).fetchone() == {"state": "SUCCEEDED", "cancel_requested": False}


def test_repeat_cancel_by_current_actor_is_idempotent(database):
    conn = database
    task_id, envelope = submission(conn)
    owner = uuid4()
    ticket = claim(conn, envelope, owner)
    assert ticket["status"] == "claimed"
    first = cancel(conn, task_id)
    assert (first["status"], first["state"]) == ("cancel_requested", "RUNNING")
    before = rows(conn, task_id)
    audit_before = conn.execute("SELECT count(*) AS n FROM access_audit "
                                "WHERE target_id=%s AND action='task.cancel_requested'",
                                (task_id,)).fetchone()["n"]
    assert audit_before == 1
    second = cancel(conn, task_id)
    assert (second["status"], second["state"]) == ("cancel_requested", "RUNNING")
    assert rows(conn, task_id) == before
    assert conn.execute("SELECT count(*) AS n FROM access_audit "
                        "WHERE target_id=%s AND action='task.cancel_requested'",
                        (task_id,)).fetchone()["n"] == audit_before


def test_cancel_before_completion_rejects_result_and_preserves_unknown_effect(database):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    ticket = claim(conn, envelope, owner)
    content_hash = stage(conn, event, owner, ticket["fence_token"])["content_hash"]
    # Synthetic already-sent effect, confined to this private transaction.
    conn.execute("INSERT INTO task_effect_intent(id,task_id,attempt,fence_token,state,effect_key) "
                 "VALUES(%s,%s,1,%s,'unknown',%s)",
                 (uuid4(), task_id, ticket["fence_token"], uuid4().hex))
    conn.execute("UPDATE durable_task SET external_effect_state='receipt_pending' WHERE id=%s",
                 (task_id,))
    requested = cancel(conn, task_id)
    assert (requested["status"], requested["state"], requested["external_effect_state"]) == (
        "cancel_requested", "RUNNING", "receipt_pending")
    before = rows(conn, task_id)
    assert finish(conn, event, owner, ticket["fence_token"], envelope["input_hash"],
                  content_hash)["status"] == "cancel_requested"
    assert rows(conn, task_id) == before
    assert worker_call(conn, "eid_task_stop_v2", event, owner, ticket["fence_token"])[
        "status"] == "CANCELLED"
    assert conn.execute("SELECT state,result_id,external_effect_state FROM durable_task WHERE id=%s",
                        (task_id,)).fetchone() == {
        "state": "CANCELLED", "result_id": None, "external_effect_state": "receipt_pending"}
    assert conn.execute("SELECT state,declared_compensation FROM task_effect_intent "
                        "WHERE task_id=%s", (task_id,)).fetchone() == {
        "state": "unknown", "declared_compensation": None}


def test_foreign_broker_body_does_not_kill_current_task(database):
    conn = database
    task_id, envelope = submission(conn)
    event = UUID(envelope["event_id"])
    foreign = envelope | {"delegation_id": str(uuid4())}
    assert claim(conn, foreign, uuid4())["status"] == "quarantined"
    assert conn.execute("SELECT state FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone()["state"] == "QUEUED"
    assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["quarantined_at"] is None
    assert rows(conn, task_id)["task_attempt"] == 0


def test_stored_poison_goes_dead_letter(database):
    conn = database
    task_id, envelope = submission(conn)
    event = UUID(envelope["event_id"])
    stored = envelope | {"message_schema_version": "2.0"}
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE event_id=%s",
                 (Jsonb(stored), payload_hash(stored), event))
    relay_owner = uuid4()
    assert worker_call(conn, "eid_task_relay_claim", relay_owner)["event_id"] == event
    assert worker_call(conn, "eid_task_relay_quarantine", relay_owner, event,
                       Jsonb(stored), payload_hash(stored), "UNSUPPORTED_VERSION", "2.0") is True
    assert conn.execute("SELECT state,error_code,next_retry_at FROM durable_task WHERE id=%s",
                        (task_id,)).fetchone() == {
        "state": "DEAD_LETTER", "error_code": "OUTBOX_POISONED", "next_retry_at": None}
    assert conn.execute("SELECT reason FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["reason"] == "UNSUPPORTED_VERSION"
    assert rows(conn, task_id)["task_attempt"] == 0


def test_valid_persisted_envelope_cannot_be_poisoned_by_false_invalid_hint(database):
    conn = database
    task_id, envelope = submission(conn)
    event, relay_owner = UUID(envelope["event_id"]), uuid4()
    assert worker_call(conn, "eid_task_relay_claim", relay_owner)["event_id"] == event
    before = rows(conn, task_id)
    assert worker_call(conn, "eid_task_relay_quarantine", relay_owner, event,
                       Jsonb(envelope), payload_hash(envelope), "INVALID_ENVELOPE", "1.0") is False
    assert rows(conn, task_id) == before
    assert conn.execute("SELECT state FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone()["state"] == "QUEUED"
    assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["quarantined_at"] is None
    assert conn.execute("SELECT count(*) AS n FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["n"] == 0


def test_invalid_persisted_envelope_can_be_isolated(database):
    conn = database
    task_id, envelope = submission(conn)
    event = UUID(envelope["event_id"])
    invalid = envelope | {"unexpected_field": "invalid shape"}
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE event_id=%s",
                 (Jsonb(invalid), payload_hash(invalid), event))
    relay_owner = uuid4()
    assert worker_call(conn, "eid_task_relay_claim", relay_owner)["event_id"] == event
    assert worker_call(conn, "eid_task_relay_quarantine", relay_owner, event,
                       Jsonb(invalid), payload_hash(invalid), "INVALID_ENVELOPE", "1.0") is True
    assert conn.execute("SELECT state,error_code FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "DEAD_LETTER", "error_code": "OUTBOX_POISONED"}
    assert conn.execute("SELECT reason FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["reason"] == "INVALID_ENVELOPE"
    assert rows(conn, task_id)["task_attempt"] == 0


@pytest.mark.parametrize("statement", [
    "SELECT * FROM task_attempt_stage", "SELECT * FROM task_effect_intent",
    "SELECT * FROM task_scheduler_lease", "UPDATE durable_task SET fence_token=1",
    "SELECT eid_task_claim(NULL::uuid,'{}'::jsonb,NULL::text,NULL::uuid)",
    "SELECT eid_task_finish_inventory(NULL::uuid,NULL::uuid)",
])
def test_worker_has_no_direct_tables_or_legacy_function_execute(database, statement):
    with pytest.raises(InsufficientPrivilege), identity(database, "eid_worker"):
        database.execute(statement)


def test_role_only_worker_impersonation_rejected(database):
    conn = database
    with pytest.raises(RaiseException, match="Worker identity required"), conn.transaction():
        conn.execute("SET LOCAL ROLE eid_worker")
        assert conn.execute("SELECT session_user").fetchone()["session_user"] == "postgres"
        conn.execute("SELECT eid_task_scheduler_lease_v2(%s)", (uuid4(),))
