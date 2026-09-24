"""Read-only current-run verification, then consume one UX run under fixture locks.

No seed, reconciliation, policy repair or database writes are permitted here.
The exclusive durable .ux-used.json record is never reset, including after a
crash or an unknown browser outcome. A subsequent UX attempt needs a new seed run.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row

from scripts import seed_discovery_fixtures as seed
from scripts.seed_access_fixtures import fixture_lock
from scripts.verify_access_fixtures import preflight, read_document, validate_manifest
from scripts.verify_local_environment import development_database_url, verify_runtime_images

SELECTOR = "deployment/environments/seadee-develop.yaml"


def validate_evidence(run_id, current, boundary, identities, plan, completion, now):
    """Pure rederivation against independently supplied *current* guard facts."""
    seed.validate_run_id(run_id)
    seed.require(boundary["selector"] == SELECTOR, "Explicit remote selector required")
    seed.require(current["state_directory"] == boundary["state"]
                 and current["nonce"] == boundary["nonce"], "Current fixture boundary changed")
    users = validate_manifest(current["fixtures"], identities, boundary["nonce"])["users"]
    created_at = plan.get("created_at")
    try:
        created = datetime.fromisoformat(created_at)
        seed.require(created.tzinfo is not None and created.utcoffset() == timedelta(0),
                     "UTC discovery creation time required")
        seed.require(timedelta(0) <= now - created <= timedelta(hours=6),
                     "A newly seeded UX run within six hours is required")
    except (TypeError, ValueError):
        raise RuntimeError("Invalid discovery creation time") from None
    declared = seed.definition(boundary["nonce"], run_id, users, created_at)
    receipt_head = plan.get("creation_schema_head")
    seed.require(receipt_head in seed.SUPPORTED_FIXTURE_REVISIONS,
                 "A new v2 discovery plan with creation schema provenance is required")
    expected = {"schema_version": 2, "fixture": "isolated-discovery-acceptance-only",
        "version": seed.VERSION, "run_id": run_id, "created_at": created_at, "boundary": boundary,
        "access_manifest_sha256": seed.digest(current["fixtures"]), "users": users,
        "identity_receipts_sha256": seed.digest(identities),
        "definition_sha256": seed.digest(declared), **declared,
        "creation_schema_head": receipt_head}
    seed.require(plan == expected, "Discovery plan differs from current deterministic provenance")
    seed.require(completion == {"schema_version": 2, "run_id": run_id,
        "definition_sha256": seed.digest(declared), "boundary": boundary,
        "database": "eid_local_dev", "schema_head": receipt_head},
        "Missing or changed discovery completion receipt")
    return declared


def validate_receipt_revision(receipt_head, current_revision):
    """The guarded database may expand, but a receipt cannot name a newer schema."""
    revisions = seed.SUPPORTED_FIXTURE_REVISIONS
    seed.require(receipt_head in revisions and current_revision in revisions,
                 "Unsupported discovery receipt or guarded database schema revision")
    seed.require(revisions.index(receipt_head) <= revisions.index(current_revision),
                 "Discovery completion receipt schema is newer than the guarded database")


def verify_fresh_rows(conn, declared):
    """SELECT only; even inactive favorites or previous receipts mean a used run."""
    seed.verify_rows(conn, declared)
    for row in declared["rows"]["discovery_record"]:
        stored = seed.normalized(seed.stored_row(conn, "discovery_record", row))
        seed.require(stored is not None and all(stored.get(key) == value for key, value in row.items()),
                     "Discovery run was already changed; never reset or reuse it")
    ids = list(declared["records"].values())
    for table in ("discovery_favorite", "discovery_receipt"):
        count = conn.execute(f"SELECT count(*) AS n FROM {table} WHERE resource_id=ANY(%s::uuid[])",
                             (ids,)).fetchone()["n"]
        seed.require(count == 0, "Discovery run has previous favorites or command receipts")


def consume_run(path, value):
    """Exclusive file creation and fsync precede release of any browser permission."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def require_unused(path):
    seed.require(not path.exists() and not path.is_symlink(),
                 "Discovery UX run already consumed or has an unknown outcome; seed a NEW run")


def hold_run(run_id):
    seed.validate_run_id(run_id)
    seed.require(os.environ.get("EID_ENVIRONMENT_CONFIG") == SELECTOR,
                 "Explicit remote selector required")
    seed.require(os.environ.get("EID_RUN_DISCOVERY_UX") == "1", "Explicit discovery UX opt-in required")
    boundary = seed.selected_boundary()
    state = Path(boundary["state"])
    directory = state / "discovery-fixtures"
    seed.require(directory.is_dir() and not directory.is_symlink() and not directory.is_junction(),
                 "Missing or linked discovery receipt directory")
    used = directory / f"{run_id}.ux-used.json"
    with fixture_lock(state / "access-fixtures.lock"), fixture_lock(state / "discovery-fixtures.lock"):
        require_unused(used)
        current = preflight(state)
        identities = read_document(state / "access-fixture-receipts.json")
        plan_path, done_path = directory / f"{run_id}.json", directory / f"{run_id}.committed.json"
        plan, completion = seed.read_receipt(plan_path), seed.read_receipt(done_path)
        declared = validate_evidence(run_id, current, boundary, identities, plan, completion,
                                     datetime.now(timezone.utc))
        # Compares schema-3 evidence with current containers, source and full candidate.
        runtime = verify_runtime_images()
        seed.require(runtime.get("schema_version") == 3, "Current remote runtime manifest required")
        url = development_database_url()
        seed.require(seed.selected_boundary() == boundary, "Boundary changed before read-only connection")
        with psycopg.connect(url.replace("postgresql+psycopg:", "postgresql:"), row_factory=dict_row,
                connect_timeout=3, options="-c default_transaction_read_only=on "
                "-c statement_timeout=5000 -c lock_timeout=2000") as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            current_revision = seed.verify_connection(conn)
            validate_receipt_revision(completion["schema_head"], current_revision)
            seed.verify_identities(conn, current["fixtures"]["users"])
            verify_fresh_rows(conn, declared)
        seed.require(seed.selected_boundary() == boundary
                     and read_document(state / "access-fixtures.json") == current["fixtures"]
                     and read_document(state / "access-fixture-receipts.json") == identities
                     and seed.read_receipt(plan_path) == plan and seed.read_receipt(done_path) == completion,
                     "Fixture provenance changed before UX consumption")
        usage = {"schema_version": 1, "run_id": run_id, "definition_sha256": plan["definition_sha256"],
            "boundary": boundary, "runtime_sha256": seed.digest(runtime),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "consumed-before-browser; never reusable, even after interruption"}
        consume_run(used, usage)
        print(json.dumps({"run_id": run_id, "users": plan["users"], "workspaces": plan["workspaces"],
            "records": plan["records"], "policy_version": plan["policy_version"], "boundary": boundary,
            "definition_sha256": plan["definition_sha256"], "runtime": runtime, "usage": usage,
            "stateDirectory": boundary["state"],
            "accessWorkspaces": current["fixtures"]["workspaces"]}, ensure_ascii=False), flush=True)
        seed.require(sys.stdin.read() == "", "Unexpected discovery UX lock input")
        seed.require(seed.selected_boundary() == boundary
                     and verify_runtime_images() == runtime, "Runtime candidate changed during UX run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    hold_run(args.run_id)


if __name__ == "__main__":
    main()
