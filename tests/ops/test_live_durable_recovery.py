"""Story 1.4 regression SOURCE; not executed under the current development-only policy.

Future authorized runs use a verified project database, a unique private schema,
and one rollback-only transaction. Nothing is committed or removed from public.
Broker/process-crash acceptance remains separate from these SQL recovery cases.
"""
from contextlib import contextmanager
import os
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg.errors import CheckViolation, InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb
import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from edw_api.access.policy import AccessDenied
from edw_api.errors import ApiError
from edw_api.task_contract import SubmitTask, payload_hash
from edw_api.tasks.repository import read, result, submit
from scripts.verify_local_environment import development_database_url, verify_migration_target

pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1", reason="Requires renewed isolated SQL test authorization")
ROOT = Path(__file__).parents[2]
ACTOR = UUID("11111111-1111-4111-8111-111111111111")
WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
SUBJECT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture
def database():
    verify_migration_target(development_database_url())
    engine = sa.create_engine(development_database_url("postgres"), poolclass=NullPool,
        connect_args={"connect_timeout": 3,
                      "options": "-c statement_timeout=10000 -c lock_timeout=2000"})
    schema = "eid_task_recovery_test_" + uuid4().hex
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
                    scripts._upgrade_revs("0008_durable_submission", heads)})
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
def worker_identity(conn):
    try:
        with conn.transaction():
            conn.execute("RESET ROLE")
            conn.execute("SET LOCAL SESSION AUTHORIZATION eid_worker")
            assert conn.execute("SELECT current_user,session_user").fetchone() == {
                "current_user": "eid_worker", "session_user": "eid_worker"}
            yield
    finally:
        conn.execute("RESET SESSION AUTHORIZATION")
        conn.execute("SET LOCAL ROLE eid_migrator")


def worker_call(conn, function, parameters):
    assert function in {"eid_task_quarantine", "eid_task_relay_claim", "eid_task_relay_confirm",
                        "eid_task_relay_quarantine", "eid_task_claim",
                        "eid_task_finish_inventory"}
    placeholders = ",".join(["%s"] * len(parameters))
    with worker_identity(conn):
        return conn.execute(f"SELECT {function}({placeholders}) AS value", parameters
                            ).fetchone()["value"]


@contextmanager
def api_identity(conn):
    try:
        with conn.transaction():
            conn.execute("SET LOCAL ROLE eid_api")
            yield
    finally:
        conn.execute("SET LOCAL ROLE eid_migrator")


def submission(conn, *, depends_on=(), key=None, limit=50):
    with api_identity(conn):
        task = submit(conn, SUBJECT, WORKSPACE,
                      SubmitTask(operation="inventory", input={"limit": limit},
                                 depends_on=list(depends_on)),
                      key or uuid4().hex, "recovery-source-test", "a" * 32)
    row = conn.execute("SELECT envelope FROM task_outbox WHERE task_id=%s", (task.task_id,)
                       ).fetchone()
    return task.task_id, row["envelope"]


def inventory_record(conn, *, visibility="visible", project_id="eid-local"):
    """Create one private-schema candidate for a future authorized SQL run."""
    resource_id = uuid4()
    conn.execute("""INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,
                         product_id,department,owner_id,classification,approval_state,policy_epoch)
                  VALUES (%s,%s,%s,'document',%s,'local-customer','local-product','产品部',%s,1,'draft',1)""",
                 (resource_id, WORKSPACE, "inventory candidate", project_id, ACTOR))
    conn.execute("""INSERT INTO discovery_record(resource_id,kind,created_by,document_type,lifecycle,visibility)
                  VALUES (%s,'document',%s,'technical','DRAFT',%s)""",
                 (resource_id, ACTOR, visibility))
    return resource_id


def make_due(conn, event):
    # Only the row freshly created by this test; avoid sleeps or global clock changes.
    conn.execute("UPDATE task_outbox SET available_at=clock_timestamp()-interval '1 second', "
                 "lease_until=CASE WHEN owner_token IS NOT NULL "
                 "THEN clock_timestamp()-interval '1 second' END WHERE event_id=%s", (event,))


def claim(conn, envelope, owner):
    return worker_call(conn, "eid_task_claim", (UUID(envelope["event_id"]), Jsonb(envelope),
                                               payload_hash(envelope), owner))


def relay_snapshot(envelope):
    return {"event_id": envelope["event_id"], "task_id": envelope["task_id"],
            "envelope": envelope, "envelope_hash": payload_hash(envelope)}


def stored_fingerprint(conn, event):
    # Diagnostic of exact persisted JSONB text; it is not the canonical wire hash.
    return conn.execute("SELECT encode(sha256(convert_to(envelope::text,'UTF8')),'hex') "
                        "AS fingerprint FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["fingerprint"]


@pytest.mark.parametrize("revoked", [False, True])
def test_completion_commits_consistent_result_or_blocked_state(database, revoked):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    if revoked:
        conn.execute("UPDATE access_delegation SET active=false WHERE id=%s",
                     (UUID(envelope["delegation_id"]),))
    expected = "BLOCKED" if revoked else "SUCCEEDED"
    assert worker_call(conn, "eid_task_finish_inventory", (event, owner)) == expected
    state = conn.execute("SELECT t.state,t.result_id,i.state AS inbox_state,a.state AS attempt_state "
                         "FROM durable_task t JOIN task_inbox i ON i.task_id=t.id "
                         "JOIN task_attempt a ON a.task_id=t.id AND a.attempt=t.attempt WHERE t.id=%s",
                         (task_id,)).fetchone()
    assert state["state"] == state["attempt_state"] == expected
    assert state["inbox_state"] == "processed"
    results = conn.execute("SELECT id,payload FROM task_result WHERE task_id=%s", (task_id,)).fetchall()
    assert len(results) == (0 if revoked else 1)
    if not revoked:
        assert results[0]["id"] == state["result_id"]
        assert results[0]["payload"]["result_id"] == str(state["result_id"])
    assert claim(conn, envelope, uuid4()) == "processed"
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None


def test_confirmed_publication_without_inbox_is_replayed_on_schedule(database):
    conn = database
    _, envelope = submission(conn)
    event, first, second = UUID(envelope["event_id"]), uuid4(), uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (first,)) == relay_snapshot(envelope)
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, first, Jsonb(envelope), payload_hash(envelope))) is True
    assert worker_call(conn, "eid_task_relay_claim", (second,)) is None
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (second,)) == relay_snapshot(envelope)
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, first, Jsonb(envelope), payload_hash(envelope))) is False
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, second, Jsonb(envelope), payload_hash(envelope))) is True
    assert conn.execute("SELECT publish_attempts FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["publish_attempts"] == 2


def test_expired_received_recovers_with_one_result_and_fenced_old_owner(database):
    conn = database
    task_id, envelope = submission(conn)
    event, relay_owner, old, new = UUID(envelope["event_id"]), uuid4(), uuid4(), uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (relay_owner,)) == relay_snapshot(envelope)
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, relay_owner, Jsonb(envelope), payload_hash(envelope))) is True
    assert claim(conn, envelope, old) == "claimed"
    assert claim(conn, envelope, new) == "busy"
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None
    conn.execute("UPDATE task_inbox SET lease_until=clock_timestamp()-interval '1 second' "
                 "WHERE event_id=%s", (event,))
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(envelope)
    assert claim(conn, envelope, new) == "claimed"
    assert worker_call(conn, "eid_task_finish_inventory", (event, old)) == "lost"
    assert worker_call(conn, "eid_task_finish_inventory", (event, new)) == "SUCCEEDED"
    assert conn.execute("SELECT state FROM task_attempt WHERE task_id=%s ORDER BY attempt", (task_id,)
                       ).fetchall() == [{"state": "ABANDONED"}, {"state": "SUCCEEDED"}]
    assert conn.execute("SELECT count(*) AS count FROM task_result WHERE task_id=%s", (task_id,)
                       ).fetchone()["count"] == 1


def test_lease_expiring_during_projection_rolls_back_and_remains_reclaimable(database):
    conn = database
    task_id, envelope = submission(conn)
    event, old, new = UUID(envelope["event_id"]), uuid4(), uuid4()
    assert claim(conn, envelope, old) == "claimed"
    # Future authorized execution only: a private-schema trigger lets time pass
    # at the result boundary, reaching the real late-lease guard without a mock.
    conn.execute("""
        CREATE FUNCTION wait_for_test_inventory_lease() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE lease_end timestamptz;
        BEGIN
          SELECT lease_until INTO lease_end FROM task_inbox WHERE task_id=NEW.task_id;
          PERFORM pg_sleep(greatest(0,extract(epoch FROM (lease_end-clock_timestamp())))+0.01);
          RETURN NEW;
        END $$;
        CREATE TRIGGER wait_for_test_inventory_lease BEFORE INSERT ON task_result
        FOR EACH ROW EXECUTE FUNCTION wait_for_test_inventory_lease();
    """)
    conn.execute("UPDATE task_inbox SET lease_until=clock_timestamp()+interval '1 second' "
                 "WHERE event_id=%s", (event,))
    before = task_counts(conn)
    with pytest.raises(RaiseException, match="Inventory lease expired"):
        worker_call(conn, "eid_task_finish_inventory", (event, old))
    assert task_counts(conn) == before
    assert conn.execute("SELECT state,error_code,result_id FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "RUNNING", "error_code": None, "result_id": None}
    assert conn.execute("SELECT state,processed_at FROM task_inbox WHERE task_id=%s", (task_id,)
                        ).fetchone() == {"state": "received", "processed_at": None}
    assert conn.execute("SELECT count(*) AS count FROM task_quarantine").fetchone()["count"] == 0
    conn.execute("ALTER TABLE task_result DISABLE TRIGGER wait_for_test_inventory_lease")
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(envelope)
    assert claim(conn, envelope, new) == "claimed"
    assert worker_call(conn, "eid_task_finish_inventory", (event, old)) == "lost"
    assert worker_call(conn, "eid_task_finish_inventory", (event, new)) == "SUCCEEDED"
    assert conn.execute("SELECT state FROM task_attempt WHERE task_id=%s ORDER BY attempt", (task_id,)
                        ).fetchall() == [{"state": "ABANDONED"}, {"state": "SUCCEEDED"}]


def test_unconfirmed_publication_can_be_reclaimed_but_stale_confirm_cannot_overwrite(database):
    conn = database
    _, envelope = submission(conn)
    event, old, new = UUID(envelope["event_id"]), uuid4(), uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (old,)) == relay_snapshot(envelope)
    assert worker_call(conn, "eid_task_relay_claim", (new,)) is None
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (new,)) == relay_snapshot(envelope)
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, old, Jsonb(envelope), payload_hash(envelope))) is False
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, new, Jsonb(envelope), payload_hash(envelope))) is True


@pytest.mark.parametrize("change,reason,version", [
    ({"message_schema_version": "2.0"}, "UNSUPPORTED_VERSION", "2.0"),
    ({"event_id": "corrupt"}, "INVALID_ENVELOPE", "1.0"),
])
def test_invalid_stored_outbox_quarantine_is_bound_to_event_hash_and_current_lease(
        database, change, reason, version):
    conn = database
    task_id, envelope = submission(conn)
    event = UUID(envelope["event_id"])
    stored = envelope | change
    digest = payload_hash(stored)
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE task_id=%s",
                 (Jsonb(stored), digest, task_id))
    old, current = uuid4(), uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (old,)) == {
        **relay_snapshot(envelope), "envelope": stored, "envelope_hash": digest}
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (current,)) == {
        **relay_snapshot(envelope), "envelope": stored, "envelope_hash": digest}
    fingerprint = stored_fingerprint(conn, event)
    parameters = (event, Jsonb(stored), digest, reason, version)
    assert worker_call(conn, "eid_task_relay_quarantine", (old, *parameters)) is False
    assert conn.execute("SELECT count(*) AS count FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["count"] == 0
    assert worker_call(conn, "eid_task_relay_quarantine", (current, *parameters)) is True
    assert conn.execute("SELECT event_id,payload_hash,reason,schema_version FROM task_quarantine "
                        "WHERE event_id=%s", (event,)).fetchall() == [{
                            "event_id": event, "payload_hash": fingerprint,
                            "reason": reason, "schema_version": version}]
    row = conn.execute("SELECT quarantined_at,owner_token,lease_until,published_at "
                       "FROM task_outbox WHERE event_id=%s", (event,)).fetchone()
    assert row["quarantined_at"] is not None
    assert (row["owner_token"], row["lease_until"], row["published_at"]) == (None, None, None)
    assert conn.execute("SELECT count(*) AS count FROM task_inbox WHERE task_id=%s", (task_id,)
                        ).fetchone()["count"] == 0
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None


def test_relay_cannot_quarantine_a_repaired_outbox_body(database):
    conn = database
    task_id, valid = submission(conn)
    event = UUID(valid["event_id"])
    invalid = valid | {"message_schema_version": "2.0"}
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE task_id=%s",
                 (Jsonb(invalid), payload_hash(invalid), task_id))
    owner = uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (owner,)) == {
        **relay_snapshot(valid), "envelope": invalid, "envelope_hash": payload_hash(invalid)}
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE task_id=%s",
                 (Jsonb(valid), payload_hash(valid), task_id))
    assert worker_call(conn, "eid_task_relay_quarantine",
                       (owner, event, Jsonb(invalid), payload_hash(invalid),
                        "UNSUPPORTED_VERSION", "2.0")) is False
    assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["quarantined_at"] is None
    assert conn.execute("SELECT count(*) AS count FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["count"] == 0
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(valid)


def test_relay_cannot_quarantine_an_outbox_after_hash_only_repair(database):
    conn = database
    _, valid = submission(conn)
    event = UUID(valid["event_id"])
    good_hash = payload_hash(valid)
    bad_hash = "0" * 64 if good_hash != "0" * 64 else "1" * 64
    conn.execute("UPDATE task_outbox SET envelope_hash=%s WHERE event_id=%s", (bad_hash, event))
    owner = uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (owner,)) == {
        **relay_snapshot(valid), "envelope_hash": bad_hash}
    conn.execute("UPDATE task_outbox SET envelope_hash=%s WHERE event_id=%s", (good_hash, event))
    assert worker_call(conn, "eid_task_relay_quarantine",
                       (owner, event, Jsonb(valid), bad_hash,
                        "STORED_ENVELOPE_HASH_MISMATCH", "1.0")) is False
    assert conn.execute("SELECT quarantined_at,owner_token FROM task_outbox WHERE event_id=%s",
                        (event,)).fetchone() == {"quarantined_at": None, "owner_token": owner}
    assert conn.execute("SELECT count(*) AS count FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["count"] == 0
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(valid)


def test_inbound_diagnostic_matching_valid_outbox_does_not_suppress_relay_claim(database):
    conn = database
    _, valid = submission(conn)
    event = UUID(valid["event_id"])
    digest = payload_hash(valid)
    assert worker_call(conn, "eid_task_quarantine",
                       (event, digest, "BINDING_MISMATCH", "1.0")) is None
    assert conn.execute("SELECT payload_hash FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchone()["payload_hash"] == digest
    assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["quarantined_at"] is None
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(valid)


@pytest.mark.parametrize("change", [
    {"event_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    {"task_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
     "aggregate_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
     "input_ref": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
])
def test_valid_wrong_uuid_binding_is_quarantined_against_database_event(database, change):
    conn = database
    task_id, valid = submission(conn)
    event = UUID(valid["event_id"])
    stored = valid | change
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE event_id=%s",
                 (Jsonb(stored), payload_hash(stored), event))
    owner = uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (owner,)) == {
        **relay_snapshot(valid), "envelope": stored, "envelope_hash": payload_hash(stored)}
    fingerprint = stored_fingerprint(conn, event)
    assert worker_call(conn, "eid_task_relay_quarantine",
                       (owner, UUID(stored["event_id"]), Jsonb(stored), payload_hash(stored),
                        "BINDING_MISMATCH", "1.0")) is (stored["event_id"] == valid["event_id"])
    if stored["event_id"] != valid["event_id"]:
        assert worker_call(conn, "eid_task_relay_quarantine",
                           (owner, event, Jsonb(stored), payload_hash(stored),
                            "BINDING_MISMATCH", "1.0")) is True
    assert conn.execute("SELECT event_id,payload_hash,reason FROM task_quarantine WHERE event_id=%s",
                        (event,)).fetchall() == [{"event_id": event, "payload_hash": fingerprint,
                                                "reason": "BINDING_MISMATCH"}]
    assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE task_id=%s", (task_id,)
                        ).fetchone()["quarantined_at"] is not None


def test_relay_confirm_fences_body_hash_and_quarantine(database):
    conn = database
    _, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    assert worker_call(conn, "eid_task_relay_claim", (owner,)) == relay_snapshot(envelope)
    altered = envelope | {"request_id": "repaired-request"}
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, owner, Jsonb(altered), payload_hash(envelope))) is False
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, owner, Jsonb(envelope), "0" * 64)) is False
    conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE event_id=%s",
                 (Jsonb(altered), payload_hash(altered), event))
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, owner, Jsonb(envelope), payload_hash(envelope))) is False
    assert conn.execute("SELECT published_at,owner_token FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone() == {"published_at": None, "owner_token": owner}
    conn.execute("UPDATE task_outbox SET quarantined_at=clock_timestamp() WHERE event_id=%s", (event,))
    assert worker_call(conn, "eid_task_relay_confirm",
                       (event, owner, Jsonb(altered), payload_hash(altered))) is False
    assert conn.execute("SELECT published_at FROM task_outbox WHERE event_id=%s", (event,)
                        ).fetchone()["published_at"] is None


def task_counts(conn):
    return {table: conn.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"]
            for table in ("durable_task", "task_receipt", "task_outbox", "task_event",
                          "task_dependency", "task_inbox", "task_attempt", "task_result",
                          "access_audit", "access_delegation")}


def block_inventory(conn, envelope):
    owner = uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    conn.execute("UPDATE access_delegation SET active=false WHERE id=%s",
                 (UUID(envelope["delegation_id"]),))
    assert worker_call(conn, "eid_task_finish_inventory", (UUID(envelope["event_id"]), owner)) == "BLOCKED"


def test_replay_reauthorizes_and_preserves_single_task_outbox_and_audit(database):
    conn, key = database, uuid4().hex
    first, _ = submission(conn, key=key)
    accepted = task_counts(conn)
    second, _ = submission(conn, key=key)
    assert second == first
    assert task_counts(conn) == accepted
    with pytest.raises(ApiError) as conflict:
        submission(conn, key=key, limit=1)
    assert (conflict.value.status_code, conflict.value.code) == (409, "IDEMPOTENCY_KEY_REUSED")
    assert task_counts(conn) == accepted
    conn.execute("UPDATE workspace_membership SET active=false WHERE identity_id=%s AND workspace_id=%s",
                 (ACTOR, WORKSPACE))
    for limit in (50, 1):
        with pytest.raises(AccessDenied):
            submission(conn, key=key, limit=limit)
    with pytest.raises(AccessDenied), api_identity(conn):
        read(conn, SUBJECT, WORKSPACE, first)
    assert task_counts(conn) == accepted


def test_api_audit_failure_rolls_back_every_submission_intent(database):
    conn = database
    before = task_counts(conn)
    conn.execute("ALTER TABLE access_audit ADD CONSTRAINT reject_test_task_audit "
                 "CHECK (action<>'task.inventory.submit') NOT VALID")
    with pytest.raises(CheckViolation):
        submission(conn)
    assert task_counts(conn) == before


def test_completed_result_is_unavailable_after_current_membership_revocation(database):
    conn = database
    task_id, envelope = submission(conn)
    owner = uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    assert worker_call(conn, "eid_task_finish_inventory", (UUID(envelope["event_id"]), owner)) == "SUCCEEDED"
    with api_identity(conn):
        assert result(conn, SUBJECT, WORKSPACE, task_id).task_id == task_id
    conn.execute("UPDATE workspace_membership SET active=false WHERE identity_id=%s AND workspace_id=%s",
                 (ACTOR, WORKSPACE))
    with pytest.raises(AccessDenied), api_identity(conn):
        result(conn, SUBJECT, WORKSPACE, task_id)
    assert conn.execute("SELECT state FROM durable_task WHERE id=%s", (task_id,)).fetchone()["state"] == "SUCCEEDED"


def test_inventory_projection_returns_only_authorized_visible_records(database):
    conn = database
    visible = inventory_record(conn)
    invisible = inventory_record(conn, visibility="recycled")
    outside_scope = inventory_record(conn, project_id="outside-current-scope")
    task_id, envelope = submission(conn)
    owner = uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    assert worker_call(conn, "eid_task_finish_inventory", (UUID(envelope["event_id"]), owner)) == "SUCCEEDED"
    payload = conn.execute("SELECT payload FROM task_result WHERE task_id=%s", (task_id,)).fetchone()["payload"]
    assert payload["items"] == [{"resource_id": str(visible), "kind": "document",
                                  "revision": 1, "resource_epoch": 1}]
    returned = {item["resource_id"] for item in payload["items"]}
    assert str(invisible) not in returned
    assert str(outside_scope) not in returned


@pytest.mark.parametrize("policy_change", ["resource", "workspace"])
def test_completed_result_reauthorizes_after_resource_or_workspace_policy_change(database, policy_change):
    conn = database
    resource_id = inventory_record(conn)
    task_id, envelope = submission(conn)
    owner = uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    assert worker_call(conn, "eid_task_finish_inventory", (UUID(envelope["event_id"]), owner)) == "SUCCEEDED"
    with api_identity(conn):
        assert result(conn, SUBJECT, WORKSPACE, task_id).task_id == task_id
    if policy_change == "resource":
        conn.execute("UPDATE access_resource SET policy_epoch=policy_epoch+1 WHERE id=%s", (resource_id,))
    else:
        conn.execute("UPDATE access_workspace SET policy_epoch=policy_epoch+1 WHERE workspace_id=%s", (WORKSPACE,))
    with pytest.raises(AccessDenied), api_identity(conn):
        result(conn, SUBJECT, WORKSPACE, task_id)
    assert conn.execute("SELECT state FROM durable_task WHERE id=%s", (task_id,)).fetchone()["state"] == "SUCCEEDED"


def test_successor_waits_without_attempt_then_runs_only_after_success(database):
    conn = database
    parent, envelope = submission(conn)
    child, child_envelope = submission(conn, depends_on=[parent])
    assert claim(conn, child_envelope, uuid4()) == "busy"
    assert conn.execute("SELECT count(*) AS count FROM task_inbox WHERE task_id=%s", (child,)
                        ).fetchone()["count"] == 0
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(envelope)
    owner = uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    assert worker_call(conn, "eid_task_finish_inventory", (UUID(envelope["event_id"]), owner)) == "SUCCEEDED"
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(child_envelope)
    assert claim(conn, child_envelope, uuid4()) == "claimed"
    assert conn.execute("SELECT attempt,state FROM durable_task WHERE id=%s", (child,)
                        ).fetchone() == {"attempt": 1, "state": "RUNNING"}


def test_blocked_dependency_propagates_through_chain_with_no_execution(database):
    conn = database
    parent, envelope = submission(conn)
    child, child_envelope = submission(conn, depends_on=[parent])
    grandchild, grandchild_envelope = submission(conn, depends_on=[child])
    block_inventory(conn, envelope)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None
    for task_id, delivery in ((child, child_envelope), (grandchild, grandchild_envelope)):
        row = conn.execute("SELECT state,stage,error_code,attempt,current_seq,result_id "
                           "FROM durable_task WHERE id=%s", (task_id,)).fetchone()
        assert row == {"state": "BLOCKED", "stage": "blocked", "error_code": "DEPENDENCY_BLOCKED",
                       "attempt": 0, "current_seq": 2, "result_id": None}
        assert conn.execute("SELECT seq,event_type,state FROM task_event WHERE task_id=%s ORDER BY seq",
                            (task_id,)).fetchall() == [
            {"seq": 1, "event_type": "task.queued", "state": "QUEUED"},
            {"seq": 2, "event_type": "task.blocked", "state": "BLOCKED"}]
        assert conn.execute("SELECT count(*) AS count FROM task_attempt WHERE task_id=%s", (task_id,)
                            ).fetchone()["count"] == 0
        assert conn.execute("SELECT publish_attempts FROM task_outbox WHERE task_id=%s", (task_id,)
                            ).fetchone()["publish_attempts"] == 0
        assert claim(conn, delivery, uuid4()) == "processed"
        assert claim(conn, delivery, uuid4()) == "processed"
        assert conn.execute("SELECT state,processed_at FROM task_inbox WHERE task_id=%s", (task_id,)
                            ).fetchone()["processed_at"] is not None
        with api_identity(conn):
            assert read(conn, SUBJECT, WORKSPACE, task_id).error == "DEPENDENCY_BLOCKED"
    assert conn.execute("SELECT count(*) AS count FROM task_result").fetchone()["count"] == 0


def test_direct_delivery_blocks_on_any_blocked_predecessor_before_relay_scan(database):
    conn = database
    blocked, envelope = submission(conn)
    pending, _ = submission(conn)
    child, child_envelope = submission(conn, depends_on=[blocked, pending])
    block_inventory(conn, envelope)
    assert claim(conn, child_envelope, uuid4()) == "processed"
    assert conn.execute("SELECT state,attempt,error_code FROM durable_task WHERE id=%s", (child,)
                        ).fetchone() == {"state": "BLOCKED", "attempt": 0, "error_code": "DEPENDENCY_BLOCKED"}
    assert conn.execute("SELECT count(*) AS count FROM task_attempt WHERE task_id=%s", (child,)
                        ).fetchone()["count"] == 0
    assert worker_call(conn, "eid_task_finish_inventory", (UUID(child_envelope["event_id"]), uuid4())) == "lost"


def test_block_propagation_is_bounded_and_resumes_from_durable_state(database):
    conn = database
    parent, envelope = submission(conn)
    children = [submission(conn, depends_on=[parent])[0] for _ in range(70)]
    block_inventory(conn, envelope)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None
    assert conn.execute("SELECT count(*) AS count FROM durable_task WHERE id=ANY(%s) AND state='BLOCKED'",
                        (children,)).fetchone()["count"] == 64
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None
    assert conn.execute("SELECT count(*) AS count FROM durable_task "
                        "WHERE id=ANY(%s) AND state='BLOCKED' AND attempt=0", (children,)
                        ).fetchone()["count"] == 70
    assert conn.execute("SELECT count(*) AS count FROM task_event "
                        "WHERE task_id=ANY(%s) AND event_type='task.blocked'", (children,)
                        ).fetchone()["count"] == 70


def test_propagation_event_failure_rolls_back_state_and_leaves_intent_recoverable(database):
    conn = database
    parent, envelope = submission(conn)
    child, _ = submission(conn, depends_on=[parent])
    block_inventory(conn, envelope)
    before = task_counts(conn)
    conn.execute("ALTER TABLE task_event ADD CONSTRAINT reject_test_block_event "
                 "CHECK (event_type<>'task.blocked') NOT VALID")
    with pytest.raises(CheckViolation):
        worker_call(conn, "eid_task_relay_claim", (uuid4(),))
    assert task_counts(conn) == before
    assert conn.execute("SELECT state,current_seq,error_code FROM durable_task WHERE id=%s", (child,)
                        ).fetchone() == {"state": "QUEUED", "current_seq": 1, "error_code": None}
    assert conn.execute("SELECT owner_token,publish_attempts FROM task_outbox WHERE task_id=%s", (child,)
                        ).fetchone() == {"owner_token": None, "publish_attempts": 0}


@pytest.mark.parametrize("failure", ["event_write", "attempt_binding", "invalid_input_event_write"])
def test_completion_failure_rolls_back_result_terminal_event_and_processed_marker(database, failure):
    conn = database
    task_id, envelope = submission(conn)
    owner = uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    if failure in {"event_write", "invalid_input_event_write"}:
        if failure == "invalid_input_event_write":
            conn.execute("UPDATE durable_task SET input=%s WHERE id=%s",
                         (Jsonb({"operation": "inventory", "input": {"limit": 0}}), task_id))
        terminal_event = "task.blocked" if failure == "invalid_input_event_write" else "task.succeeded"
        conn.execute("ALTER TABLE task_event ADD CONSTRAINT reject_test_success_event "
                     f"CHECK (event_type<>'{terminal_event}') NOT VALID")
        error = CheckViolation
    else:
        conn.execute("UPDATE task_attempt SET owner_token=%s WHERE task_id=%s", (uuid4(), task_id))
        error = RaiseException
    before = task_counts(conn)
    with pytest.raises(error):
        worker_call(conn, "eid_task_finish_inventory", (UUID(envelope["event_id"]), owner))
    assert task_counts(conn) == before
    assert conn.execute("SELECT state,result_id,current_seq FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "RUNNING", "result_id": None, "current_seq": 2}
    assert conn.execute("SELECT state,processed_at FROM task_inbox WHERE task_id=%s", (task_id,)
                        ).fetchone() == {"state": "received", "processed_at": None}
    assert conn.execute("SELECT state,completed_at FROM task_attempt WHERE task_id=%s", (task_id,)
                        ).fetchone() == {"state": "RUNNING", "completed_at": None}


@pytest.mark.parametrize("mismatch", ["delivered_body", "delivered_numeric", "stored_binding"])
def test_unbound_message_is_quarantined_without_inbox_or_execution(database, mismatch):
    conn = database
    task_id, envelope = submission(conn)
    altered = envelope | {"delegation_id": str(uuid4())}
    if mismatch == "delivered_numeric":
        # PostgreSQL JSONB equality equates 1 and 1.0; the wire digest does not.
        altered = envelope | {"aggregate_version": 1.0}
    if mismatch == "stored_binding":
        conn.execute("UPDATE task_outbox SET envelope=%s,envelope_hash=%s WHERE task_id=%s",
                     (Jsonb(altered), payload_hash(altered), task_id))
    assert claim(conn, altered, uuid4()) == "quarantined"
    assert conn.execute("SELECT reason FROM task_quarantine WHERE event_id=%s",
                        (UUID(envelope["event_id"]),)).fetchall() == [{"reason": "BINDING_MISMATCH"}]
    assert conn.execute("SELECT state,attempt FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "QUEUED", "attempt": 0}
    assert conn.execute("SELECT count(*) AS count FROM task_inbox").fetchone()["count"] == 0
    assert conn.execute("SELECT count(*) AS count FROM task_attempt").fetchone()["count"] == 0
    assert conn.execute("SELECT count(*) AS count FROM task_result").fetchone()["count"] == 0
    make_due(conn, UUID(envelope["event_id"]))
    delivery = worker_call(conn, "eid_task_relay_claim", (uuid4(),))
    if mismatch == "stored_binding":
        assert delivery == relay_snapshot(altered)
    else:
        assert delivery == relay_snapshot(envelope)
        assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE task_id=%s", (task_id,)
                            ).fetchone()["quarantined_at"] is None
        assert claim(conn, envelope, uuid4()) == "claimed"


@pytest.mark.parametrize("corruption", ["stored_body", "stored_hash"])
def test_stored_envelope_hash_corruption_is_inspectable_and_stops_relay(database, corruption):
    conn = database
    task_id, envelope = submission(conn)
    event = UUID(envelope["event_id"])
    if corruption == "stored_body":
        envelope = envelope | {"delegation_id": str(uuid4())}
        conn.execute("UPDATE task_outbox SET envelope=%s WHERE task_id=%s", (Jsonb(envelope), task_id))
    else:
        corrupted_hash = "0" * 64 if payload_hash(envelope) != "0" * 64 else "1" * 64
        conn.execute("UPDATE task_outbox SET envelope_hash=%s WHERE task_id=%s", (corrupted_hash, task_id))
    assert claim(conn, envelope, uuid4()) == "quarantined"
    assert conn.execute("SELECT reason,payload_hash FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchall() == [{"reason": "STORED_ENVELOPE_HASH_MISMATCH",
                                         "payload_hash": payload_hash(envelope)}]
    assert conn.execute("SELECT quarantined_at FROM task_outbox WHERE task_id=%s", (task_id,)
                        ).fetchone()["quarantined_at"] is not None
    assert conn.execute("SELECT state,attempt FROM durable_task WHERE id=%s", (task_id,)
                        ).fetchone() == {"state": "QUEUED", "attempt": 0}
    for table in ("task_inbox", "task_attempt", "task_result"):
        assert conn.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"] == 0
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None
    _, legitimate = submission(conn)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) == relay_snapshot(legitimate)


@pytest.mark.parametrize("revoked", [False, True])
@pytest.mark.parametrize("inbox_fault", ["missing", "unfinished"])
def test_terminal_without_processed_inbox_is_quarantined_without_reexecution(
        database, revoked, inbox_fault):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    if revoked:
        conn.execute("UPDATE access_delegation SET active=false WHERE id=%s",
                     (UUID(envelope["delegation_id"]),))
    assert worker_call(conn, "eid_task_finish_inventory", (event, owner)) == (
        "BLOCKED" if revoked else "SUCCEEDED")
    # Corrupt only this fixture's private-schema row inside the rollback-only transaction.
    if inbox_fault == "missing":
        conn.execute("DELETE FROM task_inbox WHERE task_id=%s", (task_id,))
    else:
        conn.execute("UPDATE task_inbox SET state='received',processed_at=NULL,"
                     "lease_until=clock_timestamp()+interval '30 seconds' WHERE task_id=%s", (task_id,))
    before = task_counts(conn)
    terminal = conn.execute("SELECT * FROM durable_task WHERE id=%s", (task_id,)).fetchone()
    for _ in range(2):
        assert claim(conn, envelope, uuid4()) == "quarantined"
    assert task_counts(conn) == before
    assert conn.execute("SELECT * FROM durable_task WHERE id=%s", (task_id,)).fetchone() == terminal
    assert conn.execute("SELECT reason FROM task_quarantine WHERE event_id=%s", (event,)
                        ).fetchall() == [{"reason": "TERMINAL_INBOX_INCONSISTENT"}]
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None


@pytest.mark.parametrize("invalid_input", [
    None, {}, {"limit": None}, {"limit": True}, {"limit": "10"}, {"limit": 1.5},
    {"limit": 0}, {"limit": 51}, {"limit": 10**50},
])
def test_invalid_inventory_input_completes_as_inspectable_block_without_reclaim(database, invalid_input):
    conn = database
    task_id, envelope = submission(conn)
    event, owner = UUID(envelope["event_id"]), uuid4()
    assert claim(conn, envelope, owner) == "claimed"
    conn.execute("UPDATE durable_task SET input=%s WHERE id=%s",
                 (Jsonb({"operation": "inventory", "input": invalid_input}), task_id))
    assert worker_call(conn, "eid_task_finish_inventory", (event, owner)) == "BLOCKED"
    assert conn.execute("SELECT state,error_code,result_id,attempt,current_seq FROM durable_task "
                        "WHERE id=%s", (task_id,)).fetchone() == {
        "state": "BLOCKED", "error_code": "INVALID_INVENTORY_INPUT", "result_id": None,
        "attempt": 1, "current_seq": 3}
    assert conn.execute("SELECT state FROM task_attempt WHERE task_id=%s", (task_id,)
                        ).fetchall() == [{"state": "BLOCKED"}]
    assert conn.execute("SELECT seq,event_type FROM task_event WHERE task_id=%s ORDER BY seq", (task_id,)
                        ).fetchall() == [{"seq": 1, "event_type": "task.queued"},
                                         {"seq": 2, "event_type": "task.running"},
                                         {"seq": 3, "event_type": "task.blocked"}]
    assert conn.execute("SELECT state,processed_at FROM task_inbox WHERE task_id=%s", (task_id,)
                        ).fetchone()["processed_at"] is not None
    assert conn.execute("SELECT count(*) AS count FROM task_result").fetchone()["count"] == 0
    assert claim(conn, envelope, uuid4()) == "processed"
    make_due(conn, event)
    assert worker_call(conn, "eid_task_relay_claim", (uuid4(),)) is None
    with api_identity(conn):
        assert read(conn, SUBJECT, WORKSPACE, task_id).error == "INVALID_INVENTORY_INPUT"


@pytest.mark.parametrize("statement", [
    "SELECT * FROM durable_task", "SELECT * FROM task_outbox", "SELECT * FROM task_result",
    "SELECT * FROM access_member", "SELECT * FROM access_resource", "SELECT * FROM discovery_record",
    "UPDATE durable_task SET state='QUEUED'", "UPDATE access_resource SET head_ref=NULL",
    "SELECT eid_task_block_dependency(NULL::uuid)",
])
def test_worker_has_no_direct_task_acl_metadata_or_internal_propagation_access(database, statement):
    with pytest.raises(InsufficientPrivilege), worker_identity(database):
        database.execute(statement)


@pytest.mark.parametrize("statement,parameters", [
    ("SELECT eid_task_relay_claim(%s)", (uuid4(),)),
    ("SELECT eid_task_relay_confirm(%s,%s,%s,%s)",
     (uuid4(), uuid4(), Jsonb({}), "0" * 64)),
    ("SELECT eid_task_relay_quarantine(%s,%s,%s,%s,%s,%s)",
     (uuid4(), uuid4(), Jsonb({}), "0" * 64, "INVALID_ENVELOPE", None)),
])
def test_definer_rejects_role_only_worker_impersonation(database, statement, parameters):
    conn = database
    with pytest.raises(RaiseException, match="Worker identity required"), conn.transaction():
        conn.execute("SET LOCAL ROLE eid_worker")
        assert conn.execute("SELECT session_user").fetchone()["session_user"] == "postgres"
        conn.execute(statement, parameters)
