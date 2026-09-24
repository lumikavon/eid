"""Offline provenance/consumption tests; no network, SSH, browser or database."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest

from scripts import seed_discovery_fixtures as seed
from scripts import verify_discovery_fixtures as guard
from scripts.verify_access_fixtures import ROLES
from tests.ops.test_discovery_fixture_safety import FakeRows, Result

NOW = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
NONCE = "a" * 32


def evidence(schema_head=seed.HEAD):
    def identifier(label):
        return str(uuid5(NAMESPACE_URL, "eid-access-fixture:" + NONCE + ":" + label))
    users = {role: {"username": "eid-access-" + role.replace("_", "-"),
                   "subject": str(uuid5(NAMESPACE_URL, "subject:" + role)),
                   "actor_id": identifier(role), "resource_id": identifier("resource-" + role)}
             for role in ROLES}
    identities = {user["username"]: {"id": user["subject"], "nonce": NONCE} for user in users.values()}
    manifest = {"fixture": "local-acceptance-only", "users": users,
                "workspaces": [identifier("workspace-a"), identifier("workspace-b")]}
    boundary = {"selector": guard.SELECTOR, "state": "isolated-state", "nonce": NONCE,
                "config_sha256": "c" * 64, "environment": "seadee-develop",
                "remote_host": "172.27.0.38", "remote_root": "/opt/eid", "compose_project": "eid-remote-dev"}
    current = {"state_directory": boundary["state"], "nonce": NONCE, "fixtures": manifest}
    declared = seed.definition(NONCE, "ux-safe", users, NOW.isoformat())
    plan = {"schema_version": 2, "fixture": "isolated-discovery-acceptance-only", "version": seed.VERSION,
            "run_id": "ux-safe", "created_at": NOW.isoformat(), "boundary": boundary,
            "users": users, "access_manifest_sha256": seed.digest(manifest),
            "identity_receipts_sha256": seed.digest(identities), "definition_sha256": seed.digest(declared),
            **declared, "creation_schema_head": schema_head}
    done = {"schema_version": 2, "run_id": "ux-safe", "definition_sha256": seed.digest(declared),
            "boundary": boundary, "database": "eid_local_dev", "schema_head": schema_head}
    # Independent documents, as they would be separately read from disk.
    return tuple(deepcopy(part) for part in (current, boundary, identities, plan, done))


def validate(parts):
    return guard.validate_evidence("ux-safe", *parts, NOW)


@pytest.mark.parametrize("schema_head", ["0007_workspace_discovery", "0009_fenced_recovery",
                                          "0010_task_observation"])
def test_v2_plan_and_completion_bind_supported_creation_head(schema_head):
    parts = evidence(schema_head)
    assert validate(parts)["records"] == parts[3]["records"]


def test_legacy_v1_plan_and_completion_cannot_authorize_ux():
    parts = evidence("0007_workspace_discovery")
    parts[3]["schema_version"] = parts[4]["schema_version"] = 1
    parts[3].pop("creation_schema_head")
    with pytest.raises(RuntimeError, match="new v2 discovery plan"):
        validate(parts)


@pytest.mark.parametrize("field", ["definition_sha256", "access_manifest_sha256", "identity_receipts_sha256"])
def test_self_consistent_hash_strings_do_not_replace_rederivation(field):
    parts = evidence()
    parts[3][field] = "f" * 64
    if field == "definition_sha256":
        parts[4][field] = "f" * 64
    with pytest.raises(RuntimeError, match="deterministic provenance"):
        validate(parts)


@pytest.mark.parametrize("target", ["records", "workspaces", "rows"])
def test_well_formed_foreign_uuid_rejected_even_after_attacker_rehashes(target):
    parts = evidence()
    plan, done = parts[3:]
    foreign = str(uuid5(NAMESPACE_URL, "foreign-resource"))
    if target == "records":
        plan[target]["a:document"] = foreign
    elif target == "workspaces":
        plan[target]["a"] = foreign
    else:
        plan["rows"]["access_resource"][0]["id"] = foreign
    declared = {key: plan[key] for key in ("rows", "workspaces", "records", "policy_version")}
    plan["definition_sha256"] = done["definition_sha256"] = seed.digest(declared)
    with pytest.raises(RuntimeError, match="deterministic provenance"):
        validate(parts)


@pytest.mark.parametrize("field,value", [("config_sha256", "f" * 64), ("nonce", "b" * 32),
    ("remote_root", "/opt/foreign"), ("selector", "seadee-develop"), ("state", "foreign-state")])
def test_current_boundary_drift_rejects_old_plan_and_completion(field, value):
    parts = evidence()
    parts[1][field] = value
    with pytest.raises(RuntimeError):
        validate(parts)


@pytest.mark.parametrize("field,value", [("subject", str(uuid5(NAMESPACE_URL, "new-subject"))),
    ("actor_id", str(uuid5(NAMESPACE_URL, "foreign-actor"))), ("username", "foreign-user")])
def test_current_identity_mapping_must_match_creation_receipts(field, value):
    parts = evidence()
    parts[0]["fixtures"]["users"]["author"][field] = value
    with pytest.raises(RuntimeError):
        validate(parts)


def test_current_identity_receipt_nonce_cannot_be_replaced_by_plan_hash():
    parts = evidence()
    parts[2]["eid-access-author"]["nonce"] = "b" * 32
    with pytest.raises(RuntimeError, match="ownership receipt"):
        validate(parts)


@pytest.mark.parametrize("change", [{}, {"schema_head": "0006_api_write_only"},
    {"schema_head": "0008_durable_submission"}, {"schema_head": "0011_future_revision"},
    {"schema_head": "unknown_head"}, {"database": "foreign"},
    {"run_id": "different"}, {"extra": True}])
def test_missing_or_drifted_completion_is_rejected(change):
    parts = list(evidence())
    parts[4] = parts[4] | change if change else {}
    with pytest.raises(RuntimeError, match="completion receipt"):
        validate(parts)


@pytest.mark.parametrize("receipt_head,current_head,accepted", [
    ("0007_workspace_discovery", "0010_task_observation", True),
    ("0008_durable_submission", "0009_fenced_recovery", True),
    ("0009_fenced_recovery", "0010_task_observation", True),
    ("0010_task_observation", "0010_task_observation", True),
    ("0009_fenced_recovery", "0008_durable_submission", False),
    ("0010_task_observation", "0007_workspace_discovery", False),
    ("0011_future_revision", "0010_task_observation", False),
    ("0007_workspace_discovery", "unknown_head", False),
])
def test_receipt_revision_must_not_exceed_guarded_database(receipt_head, current_head, accepted):
    if accepted:
        guard.validate_receipt_revision(receipt_head, current_head)
    else:
        with pytest.raises(RuntimeError, match="schema revision|newer than"):
            guard.validate_receipt_revision(receipt_head, current_head)


@pytest.mark.parametrize("offset", [-1, 6 * 3600 + 1])
def test_future_or_old_seed_is_not_a_fresh_run(offset):
    parts = evidence()
    with pytest.raises(RuntimeError, match="newly seeded"):
        guard.validate_evidence("ux-safe", *parts, NOW + timedelta(seconds=offset))


class FreshRows(FakeRows):
    def __init__(self, declared):
        super().__init__(declared)
        self.favorite_count = 0
        self.receipt_count = 0

    def execute(self, query, params=()):
        if isinstance(query, str) and "FROM discovery_favorite " in query:
            return Result([{"n": self.favorite_count}])
        if isinstance(query, str) and "FROM discovery_receipt " in query:
            return Result([{"n": self.receipt_count}])
        return super().execute(query, params)


def test_fresh_database_comparison_is_read_only():
    declared = validate(evidence())
    conn = FreshRows(declared)
    guard.verify_fresh_rows(conn, declared)
    assert conn.writes == []


@pytest.mark.parametrize("field,value", [("revision", 2), ("visibility", "recycled"),
    ("updated_at", "2026-09-18T12:01:00+00:00")])
def test_preserved_but_mutated_run_cannot_be_reused_for_ux(field, value):
    declared = validate(evidence())
    conn = FreshRows(declared)
    conn.rows["discovery_record"][0][field] = value
    before = deepcopy(conn.rows)
    with pytest.raises(RuntimeError, match="already changed"):
        guard.verify_fresh_rows(conn, declared)
    assert conn.rows == before


@pytest.mark.parametrize("field", ["favorite_count", "receipt_count"])
def test_any_previous_command_or_favorite_state_is_rejected(field):
    declared = validate(evidence())
    conn = FreshRows(declared)
    setattr(conn, field, 1)
    with pytest.raises(RuntimeError, match="previous favorites"):
        guard.verify_fresh_rows(conn, declared)


def test_usage_is_exclusive_durable_and_never_adopts_unknown_outcome(tmp_path):
    path = tmp_path / "ux-safe.ux-used.json"
    guard.require_unused(path)
    guard.consume_run(path, {"status": "consumed"})
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match="unknown outcome"):
        guard.require_unused(path)
    with pytest.raises(FileExistsError):
        guard.consume_run(path, {"status": "reset"})
    assert path.read_bytes() == original
    path.write_bytes(b'{"interrupted":')
    with pytest.raises(RuntimeError, match="unknown outcome"):
        guard.require_unused(path)


@pytest.mark.parametrize("selector,opt_in", [(None, "1"), ("seadee-develop", "1"),
    (guard.SELECTOR, None), (guard.SELECTOR, "0")])
def test_invalid_opt_in_stops_before_any_environment_lookup(monkeypatch, selector, opt_in):
    for name, value in (("EID_ENVIRONMENT_CONFIG", selector), ("EID_RUN_DISCOVERY_UX", opt_in)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    # No network function is patched: the invalid input must stop before boundary resolution.
    with pytest.raises(RuntimeError, match="selector|opt-in"):
        guard.hold_run("ux-safe")
