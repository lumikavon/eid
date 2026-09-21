"""No network/database: prove append-only fixture planning and refusal paths."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from uuid import NAMESPACE_URL, uuid5

import pytest

from scripts import seed_discovery_fixtures as fixtures
from scripts.verify_access_fixtures import ROLES

NONCE = "b" * 32
NOW = datetime(2026, 9, 18, 12, tzinfo=timezone.utc).isoformat()


def users():
    return {role: {"actor_id": str(uuid5(NAMESPACE_URL, "safety-actor:" + role)),
                   "subject": str(uuid5(NAMESPACE_URL, "safety-subject:" + role)),
                   "username": "eid-access-" + role.replace("_", "-"),
                   "resource_id": str(uuid5(NAMESPACE_URL, "old-access-resource:" + role))}
            for role in ROLES}


def declaration(run="safety-1"):
    return fixtures.definition(NONCE, run, users(), NOW)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeRows:
    """Minimal table storage for receipt/reconciliation tests, never an SQL oracle."""
    def __init__(self, declared):
        self.rows = deepcopy(declared["rows"])
        self.writes = []

    def execute(self, query, params=()):
        query = query.as_string() if hasattr(query, "as_string") else query
        assert query.startswith("SELECT"), "Existing fixture verification must not write"
        table = next(table for table in self.rows if f'FROM "{table}" ' in query)
        if "count(*)" in query:
            key = "workspace_id" if "workspace_id=ANY" in query else "resource_id"
            return Result([{"n": sum(row[key] in params[0] for row in self.rows[table])}])
        keys = fixtures.TABLE_KEYS[table]
        return Result([row for row in self.rows[table] if tuple(row[key] for key in keys) == params])


def test_run_definition_is_deterministic_disjoint_and_does_not_adopt_access_resources():
    a, b = declaration(), declaration("safety-2")
    assert a == declaration()
    assert set(a["records"].values()).isdisjoint(b["records"].values())
    assert set(a["workspaces"].values()).isdisjoint(b["workspaces"].values())
    assert set(a["records"].values()).isdisjoint(user["resource_id"] for user in users().values())
    assert set(a["rows"]) == set(fixtures.TABLE_KEYS)
    assert "identity_account" not in a["rows"] and "discovery_favorite" not in a["rows"]
    assert {row["kind"] for row in a["rows"]["access_resource"]} == {"document", "knowledge", "reference"}
    for policy in a["rows"]["discovery_restore_policy"]:
        assert policy["fixture_owner"] == "eid-story-1-3:" + NONCE
        assert policy["fixture_version"] == fixtures.VERSION
        assert policy["environment_class"] == "isolated_development"
        assert policy["owner_only"] is True and policy["active"] is True
        assert policy["required_operation"] == "document:edit"
        assert policy["valid_from"] < NOW < policy["valid_until"]


@pytest.mark.parametrize("run", ["", "../foreign", "A", "a/b", "a\\b", "x" * 33, "a.json", " a"])
def test_unsafe_run_ids_rejected_before_environment_access(monkeypatch, run):
    monkeypatch.setattr(fixtures, "selected_boundary", lambda: pytest.fail("must validate ID first"))
    with pytest.raises(RuntimeError, match="Run ID"):
        fixtures.seed(run)


def test_implicit_local_environment_is_rejected_before_any_database_access(monkeypatch):
    monkeypatch.setattr(fixtures, "remote_config", lambda: None)
    monkeypatch.setattr(fixtures, "preflight", lambda *_: pytest.fail("must not access local services"))
    with pytest.raises(RuntimeError, match="explicit seadee-develop"):
        fixtures.seed("safe")


def test_migration_guard_failure_never_creates_plan_or_connects(monkeypatch, tmp_path):
    monkeypatch.setattr(fixtures, "selected_boundary", lambda: {"state": str(tmp_path), "nonce": NONCE})
    def denied(_):
        raise RuntimeError("remote isolation rejected")
    monkeypatch.setattr(fixtures, "preflight", denied)
    monkeypatch.setattr(fixtures.psycopg, "connect", lambda *a, **k: pytest.fail("must not connect"))
    with pytest.raises(RuntimeError, match="isolation rejected"):
        fixtures.seed("safe")
    assert not (tmp_path / "discovery-fixtures").exists()


def test_receipts_are_exclusive_and_existing_bytes_never_replaced(tmp_path):
    path = tmp_path / "run.json"
    fixtures.write_new_document(path, {"status": "plan"})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        fixtures.write_new_document(path, {"status": "replacement"})
    assert path.read_bytes() == original
    path.write_text('{"run":1,"run":2}')
    with pytest.raises(RuntimeError, match="Duplicate fixture JSON"):
        fixtures.read_receipt(path)


def test_duplicate_run_preserves_mutable_collection_state_and_is_read_only():
    declared = declaration()
    conn = FakeRows(declared)
    for row in conn.rows["discovery_record"]:
        row.update(visibility="visible", revision=8, updated_at="2026-09-19T12:00:00+00:00")
    assert fixtures.apply_definition(conn, declared) is False
    assert all(row["revision"] == 8 for row in conn.rows["discovery_record"])
    assert conn.writes == []


@pytest.mark.parametrize("table,field,value", [
    ("access_resource", "kind", "local-policy-fixture"),
    ("access_resource", "owner_id", "foreign"),
    ("access_member", "clearance", 3),
    ("workspace_membership", "active", False),
    ("discovery_record", "fixture_owner", "foreign"),
    ("discovery_record", "lifecycle", "APPROVED"),
    ("discovery_restore_policy", "active", False),
    ("discovery_restore_policy", "valid_until", "2026-01-01T00:00:00+00:00"),
    ("discovery_restore_policy", "environment_class", "production"),
])
def test_immutable_drift_rejected_without_reset(table, field, value):
    declared = declaration()
    conn = FakeRows(declared)
    conn.rows[table][0][field] = value
    original = deepcopy(conn.rows)
    with pytest.raises(RuntimeError, match="immutable fixture drift"):
        fixtures.apply_definition(conn, declared)
    assert conn.rows == original


def test_missing_record_rejected_without_partial_repair():
    declared = declaration()
    conn = FakeRows(declared)
    conn.rows["discovery_record"].pop()
    with pytest.raises(RuntimeError, match="Incomplete or colliding"):
        fixtures.apply_definition(conn, declared)


def test_existing_rows_cannot_be_adopted_without_prior_run_receipt():
    declared = declaration()
    with pytest.raises(RuntimeError, match="no prior run receipt"):
        fixtures.apply_definition(FakeRows(declared), declared, allow_existing=False)


def test_committed_run_cannot_be_recreated_when_rows_are_missing():
    declared = declaration()
    conn = FakeRows(declared)
    conn.rows = {table: [] for table in conn.rows}
    with pytest.raises(RuntimeError, match="refusing to recreate"):
        fixtures.apply_definition(conn, declared, allow_create=False)


@pytest.mark.parametrize("field,value", [("database", "enterprise"), ("role", "postgres"),
    ("marker", None), ("schema", "foreign")])
def test_real_connection_identity_checked_before_schema_or_writes(field, value):
    class Connection:
        def execute(self, query):
            assert "pg_database" in query
            return Result([{"database": "eid_local_dev", "role": "eid_migrator",
                "marker": "eid-local-dev-v1", "schema": "public"} | {field: value}])
    with pytest.raises(RuntimeError, match="database boundary mismatch"):
        fixtures.verify_connection(Connection())


def test_current_receipted_identity_drift_rejected_without_identity_write():
    class Connection:
        def execute(self, query, _params):
            assert query.startswith("SELECT")
            return Result([])
    with pytest.raises(RuntimeError, match="identity drifted"):
        fixtures.verify_identities(Connection(), users())


def test_seeder_source_has_no_identity_password_mutation_or_cleanup():
    source = Path(fixtures.__file__).read_text(encoding="utf8")
    assert "ON CONFLICT" not in source and "UPDATE " not in source and "DELETE " not in source
    assert "httpx" not in source and "DROP " not in source


class SeedConnection(FakeRows):
    """Transaction/event double for seeder ordering, not live SQL acceptance."""
    def __init__(self, declared):
        super().__init__(declared)
        self.rows = {table: [] for table in self.rows}
        self.committed = False
        self.identity = {"database": "eid_local_dev", "role": "eid_migrator",
                         "marker": "eid-local-dev-v1", "schema": "public"}

    def __enter__(self):
        self.before = deepcopy(self.rows)
        return self

    def __exit__(self, error, *_):
        if error:
            self.rows = self.before
        else:
            self.committed = True

    def execute(self, query, params=()):
        query = query.as_string() if hasattr(query, "as_string") else query
        if "FROM pg_database" in query:
            return Result([self.identity])
        if "FROM alembic_version" in query:
            return Result([{"version_num": fixtures.HEAD}])
        if "pg_advisory_xact_lock" in query:
            return Result([{}])
        if "FROM identity_account" in query:
            role, user = next((role, user) for role, user in users().items() if user["actor_id"] == params[0])
            return Result([{"id": user["actor_id"], "subject": user["subject"],
                "display_name": "本地验收 · " + role, "department": "验收部", "active": True}])
        if query.startswith("INSERT"):
            match = re.fullmatch(r'INSERT INTO "([a-z_]+)" \((.+)\) VALUES \(.+\)', query)
            assert match
            table, columns = match.groups()
            self.rows[table].append(dict(zip(columns.replace('"', '').split(','), params, strict=True)))
            self.writes.append(table)
            return Result([])
        return super().execute(query, params)


def setup_seed(monkeypatch, tmp_path):
    boundary = {"state": str(tmp_path), "nonce": NONCE, "environment": "seadee-develop"}
    manifest = {"users": users()}
    (tmp_path / "access-fixtures.json").write_text(json.dumps(manifest))
    (tmp_path / "access-fixture-receipts.json").write_text(json.dumps({"owner": NONCE}))
    monkeypatch.setattr(fixtures, "selected_boundary", lambda: boundary.copy())
    monkeypatch.setattr(fixtures, "preflight", lambda _state: {"fixtures": manifest, "nonce": NONCE})
    monkeypatch.setattr(fixtures, "verify_migration_target", lambda _url: None)
    monkeypatch.setattr(fixtures, "development_database_url", lambda: "guarded-development-url")
    conn = SeedConnection(declaration())
    monkeypatch.setattr(fixtures.psycopg, "connect", lambda *_a, **_k: conn)
    return conn


def test_seed_plan_precedes_transaction_and_second_run_never_resets(monkeypatch, tmp_path):
    conn = setup_seed(monkeypatch, tmp_path)
    def connect(*_args, **_kwargs):
        assert (tmp_path / "discovery-fixtures/safe.json").is_file()
        return conn
    monkeypatch.setattr(fixtures.psycopg, "connect", connect)
    result = fixtures.seed("safe")
    assert result["created"] is True and conn.committed
    assert Path(result["completion_receipt"]).is_file()
    first_writes = len(conn.writes)
    conn.rows["discovery_record"][0].update(visibility="visible", revision=6, updated_at=NOW)
    original_plan = Path(result["receipt"]).read_bytes()
    repeated = fixtures.seed("safe")
    assert repeated["created"] is False and len(conn.writes) == first_writes
    assert conn.rows["discovery_record"][0]["revision"] == 6
    assert Path(result["receipt"]).read_bytes() == original_plan


def test_second_full_guard_failure_rolls_back_and_preserves_uncompleted_plan(monkeypatch, tmp_path):
    conn = setup_seed(monkeypatch, tmp_path)
    calls = []
    def guard(_url):
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError("changed remote target")
    monkeypatch.setattr(fixtures, "verify_migration_target", guard)
    with pytest.raises(RuntimeError, match="changed remote"):
        fixtures.seed("safe")
    assert not conn.committed and all(not rows for rows in conn.rows.values())
    assert (tmp_path / "discovery-fixtures/safe.json").is_file()
    assert not (tmp_path / "discovery-fixtures/safe.committed.json").exists()


def test_schema_identity_failure_happens_before_first_insert(monkeypatch, tmp_path):
    conn = setup_seed(monkeypatch, tmp_path)
    conn.identity["marker"] = "foreign"
    with pytest.raises(RuntimeError, match="database boundary mismatch"):
        fixtures.seed("safe")
    assert not conn.writes and not conn.committed


def test_complete_receipt_drift_is_rejected_before_any_connection(monkeypatch, tmp_path):
    setup_seed(monkeypatch, tmp_path)
    result = fixtures.seed("safe")
    path = Path(result["completion_receipt"])
    changed = json.loads(path.read_text()) | {"database": "foreign"}
    path.write_text(json.dumps(changed))
    monkeypatch.setattr(fixtures.psycopg, "connect", lambda *a, **k: pytest.fail("drift must stop before connection"))
    with pytest.raises(RuntimeError, match="completion receipt drift"):
        fixtures.seed("safe")


def test_live_schema_helpers_require_opt_in_before_environment_or_connections(monkeypatch):
    from tests.ops import discovery_live_support as live
    monkeypatch.delenv("EID_RUN_LIVE_TESTS", raising=False)
    monkeypatch.setattr(live.fixture, "selected_boundary", lambda: pytest.fail("must stop before environment lookup"))
    with pytest.raises(AssertionError, match="opt-in"), live.isolated_store():
        pytest.fail("must not create schema")
    with pytest.raises(AssertionError, match="opt-in"), live.fresh_connection(None):
        pytest.fail("must not connect")
