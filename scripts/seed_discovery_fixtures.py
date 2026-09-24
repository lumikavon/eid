"""Append run-owned Story 1.3 fixtures after the full remote isolation guard.

Never creates identities, changes credentials, resets collection state, or repairs
existing rows. A new run ID creates two new projects; all prior runs are retained.
The immutable plan is written before the transaction, so an interrupted commit
can be reconciled by exact verification, without adopting unreceipted records.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from scripts.seed_access_fixtures import SUPPORTED_FIXTURE_REVISIONS, fixture_lock, is_supported_fixture_head
from scripts.verify_access_fixtures import preflight, read_document
from scripts.verify_local_environment import (
    _recorded_owner_nonce, development_database_url, environment_state_directory,
    remote_config, verify_migration_target,
)

ROOT = Path(__file__).resolve().parents[1]
VERSION = "story-1-3-v1"
HEAD = "0007_workspace_discovery"
TABLE_KEYS = {
    "workspace": ("id",), "access_workspace": ("workspace_id",),
    "workspace_membership": ("identity_id", "workspace_id"),
    "access_member": ("identity_id", "workspace_id"),
    "access_resource": ("id",), "discovery_record": ("resource_id",),
    "discovery_participant": ("resource_id", "identity_id"),
    "discovery_restore_policy": ("workspace_id", "kind"),
}
MUTABLE_RECORD_FIELDS = {"visibility", "revision", "updated_at"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def normalized(value):
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(normalized(value), sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def validate_run_id(run_id):
    require(isinstance(run_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", run_id),
            "Run ID must be 1-32 lowercase letters, digits or hyphens")
    return run_id


def definition(nonce, run_id, users, created_at):
    """Pure, deterministic declaration; its hash includes every immutable field."""
    validate_run_id(run_id)
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce),
            "Invalid discovery fixture owner")
    start = datetime.fromisoformat(created_at)
    require(start.tzinfo is not None and start.utcoffset() == timedelta(0), "UTC receipt required")
    owner = "eid-story-1-3:" + nonce
    def identifier(name):
        return str(uuid5(NAMESPACE_URL, f"eid-discovery:{nonce}:{VERSION}:{run_id}:{name}"))
    author, expert = users["author"]["actor_id"], users["expert"]["actor_id"]
    rows = {table: [] for table in TABLE_KEYS}
    workspaces = {name: identifier("workspace-" + name) for name in ("a", "b")}
    records = {}
    valid_from = (start - timedelta(days=2)).isoformat()
    for name, wid in workspaces.items():
        project = f"discovery-{run_id}-{name}"
        rows["workspace"].append({"id": wid, "slug": project, "name": f"发现验收 {run_id} · {name.upper()}"})
        rows["access_workspace"].append({"workspace_id": wid, "tenant_id": identifier("tenant"),
            "project_id": project, "customer_id": "discovery-customer", "product_id": "discovery-product",
            "department": "验收部", "classification": 1, "policy_epoch": 1})
        for role, user in users.items():
            rows["workspace_membership"].append({"identity_id": user["actor_id"], "workspace_id": wid,
                                                  "active": True})
            rows["access_member"].append({"identity_id": user["actor_id"], "workspace_id": wid,
                "roles": [role], "project_scope": [project], "customer_scope": ["discovery-customer"],
                "product_scope": ["discovery-product"], "department_scope": ["验收部"],
                "owner_scope": "any", "approval_states": ["draft", "in_review", "approved", "rejected"],
                "clearance": 1, "valid_from": valid_from, "valid_until": None, "policy_epoch": 1})
        rows["discovery_restore_policy"].append({"workspace_id": wid, "kind": "document",
            "version": VERSION + ":" + run_id, "action": "restore_visibility",
            "required_operation": "document:edit", "owner_only": True,
            "environment_class": "isolated_development", "fixture_owner": owner,
            "fixture_version": VERSION, "active": True, "valid_from": valid_from,
            "valid_until": (start + timedelta(days=7)).isoformat()})

        labels = (["document", "other-owner", "knowledge", "reference", "archived", "recycled",
                   "recycled-other-owner", "recycled-knowledge", "classified", "expired", "future",
                   "foreign-project", "foreign-customer", "foreign-product", "foreign-department",
                   "invalid-approval"] + [f"page-{index:02}" for index in range(32)]) if name == "a" else ["document"]
        for label in labels:
            rid = identifier(name + ":" + label)
            records[name + ":" + label] = rid
            kind = "knowledge" if "knowledge" in label else "reference" if label == "reference" else "document"
            record_owner = expert if "other-owner" in label else author
            resource = {"id": rid, "workspace_id": wid, "title": f"发现验收 {run_id} {name} · {label}",
                "kind": kind, "project_id": project, "customer_id": "discovery-customer",
                "product_id": "discovery-product", "department": "验收部", "owner_id": record_owner,
                "classification": 3 if label == "classified" else 1,
                "approval_state": "unsupported" if label == "invalid-approval" else "draft",
                "publication_state": "unpublished", "head_ref": None, "policy_epoch": 1,
                "valid_from": (start + timedelta(days=1)).isoformat() if label == "future" else valid_from,
                "valid_until": (start - timedelta(days=1)).isoformat() if label == "expired" else None}
            for dimension in ("project", "customer", "product", "department"):
                if label == "foreign-" + dimension:
                    resource[dimension if dimension == "department" else dimension + "_id"] = "outside-fixture-scope"
            rows["access_resource"].append(resource)
            rows["discovery_record"].append({"resource_id": rid, "kind": kind,
                "created_by": record_owner, "created_at": created_at, "updated_at": created_at,
                "document_type": "technical" if kind == "document" else None,
                "lifecycle": "ARCHIVED" if label in {"archived", "recycled"} else
                             "IN_REVIEW" if label == "page-01" else "APPROVED" if label == "page-02" else "DRAFT",
                "version_label": None, "visibility": "recycled" if label.startswith("recycled") else "visible",
                "revision": 1, "fixture_owner": owner, "fixture_version": VERSION})
            if label in {"document", "other-owner", "reference"}:
                rows["discovery_participant"].append({"resource_id": rid, "identity_id": author})
    return {"rows": rows, "workspaces": workspaces, "records": records,
            "policy_version": VERSION + ":" + run_id}


def write_new_document(path, document):
    """Exclusive creation: a receipt is never replaced or silently repaired."""
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_receipt(path):
    # Full immutable plans exceed the access manifest's intentionally small limit.
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1
            and path.stat().st_size <= 256 * 1024, "Missing, linked or oversized discovery receipt")
    from scripts.verify_access_fixtures import _unique_object
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError):
        raise RuntimeError("Invalid discovery receipt; preserve and investigate") from None


def selected_boundary():
    config = remote_config()
    require(config is not None and config["environment"] == "seadee-develop",
            "Discovery fixtures require the explicit seadee-develop selector")
    return {"selector": os.environ.get("EID_ENVIRONMENT_CONFIG"), "config_sha256": digest(config),
            "environment": config["environment"], "remote_host": config["ssh"]["hostname"],
            "remote_root": config["remote"]["root"], "compose_project": config["remote"]["compose_project"],
            "nonce": _recorded_owner_nonce(), "state": str(environment_state_directory(ROOT).resolve())}


def verify_connection(conn):
    expected = {"database": "eid_local_dev", "role": "eid_migrator", "marker": "eid-local-dev-v1",
                "schema": "public"}
    actual = conn.execute("SELECT current_database() AS database,current_user AS role,"
        "shobj_description(oid,'pg_database') AS marker,current_schema() AS schema "
        "FROM pg_database WHERE datname=current_database()").fetchone()
    require(actual == expected, "Discovery fixture database boundary mismatch")
    revisions = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    require(is_supported_fixture_head(revisions),
            "Apply the guarded discovery migration before seeding")
    return revisions[0]["version_num"]


def guarded_schema_head(url, boundary):
    """Pin a new plan to a read-only, guarded database observation."""
    verify_migration_target(url)
    require(selected_boundary() == boundary, "Discovery fixture boundary changed before schema check")
    with psycopg.connect(url.replace("postgresql+psycopg:", "postgresql:"), row_factory=dict_row,
            connect_timeout=3, options="-c default_transaction_read_only=on "
            "-c statement_timeout=5000 -c lock_timeout=2000") as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return verify_connection(conn)


def verify_identities(conn, users):
    for role, user in users.items():
        row = conn.execute("SELECT id,subject,display_name,department,active FROM identity_account WHERE id=%s",
                           (user["actor_id"],)).fetchone()
        require(normalized(row) == {"id": user["actor_id"], "subject": user["subject"],
                "display_name": "本地验收 · " + role, "department": "验收部", "active": True},
                "Current receipted identity drifted; refusing to create discovery data")


def stored_row(conn, table, row):
    keys = TABLE_KEYS[table]
    return conn.execute(sql.SQL("SELECT * FROM {} WHERE {}").format(sql.Identifier(table),
        sql.SQL(" AND ").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in keys)),
        tuple(row[key] for key in keys)).fetchone()


def verify_rows(conn, declared):
    for table, rows in declared["rows"].items():
        for row in rows:
            stored = normalized(stored_row(conn, table, row))
            keys = set(row) - (MUTABLE_RECORD_FIELDS if table == "discovery_record" else set())
            require(stored is not None and all(stored.get(key) == row[key] for key in keys),
                    "Discovery immutable fixture drift; refusing overwrite or repair")
    # Extra immutable rows within these private projects are also drift, not adoptable data.
    wids = list(declared["workspaces"].values())
    for table in ("access_resource", "access_member", "workspace_membership", "discovery_restore_policy"):
        count = conn.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE workspace_id=ANY(%s::uuid[])")
                             .format(sql.Identifier(table)), (wids,)).fetchone()["n"]
        require(count == len(declared["rows"][table]), "Unexpected rows in run-owned fixture project")
    rids = list(declared["records"].values())
    for table in ("discovery_record", "discovery_participant"):
        count = conn.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE resource_id=ANY(%s::uuid[])")
                             .format(sql.Identifier(table)), (rids,)).fetchone()["n"]
        require(count == len(declared["rows"][table]), "Unexpected immutable discovery relations")


def apply_definition(conn, declared, *, allow_create=True, allow_existing=True):
    # A run is all-new or a complete existing transaction. Never fill missing pieces.
    existing = [stored_row(conn, table, row) is not None
                for table, rows in declared["rows"].items() for row in rows]
    if any(existing):
        require(allow_existing, "Existing discovery data has no prior run receipt; refusing adoption")
        require(all(existing), "Incomplete or colliding discovery run; preserve and investigate")
        verify_rows(conn, declared)
        return False
    require(allow_create, "Committed discovery run is missing; refusing to recreate data")
    for table, rows in declared["rows"].items():
        for row in rows:
            conn.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, row)),
                sql.SQL(",").join(sql.Placeholder() for _ in row)), tuple(row.values()))
    verify_rows(conn, declared)
    return True


def seed(run_id):
    validate_run_id(run_id)
    boundary = selected_boundary()
    state = Path(boundary["state"])
    with fixture_lock(state / "access-fixtures.lock"), fixture_lock(state / "discovery-fixtures.lock"):
        current = preflight(state)  # Includes the complete remote/DB/external isolation guard.
        require(selected_boundary() == boundary and current["nonce"] == boundary["nonce"],
                "Discovery fixture environment changed")
        users = current["fixtures"]["users"]
        identity_receipts = read_document(state / "access-fixture-receipts.json")
        directory = state / "discovery-fixtures"
        require(not directory.is_symlink() and not directory.is_junction(), "Linked discovery receipt directory")
        directory.mkdir(exist_ok=True)
        plan_path, done_path = directory / f"{run_id}.json", directory / f"{run_id}.committed.json"
        previous = read_receipt(plan_path) if plan_path.exists() else None
        created_at = previous["created_at"] if previous else datetime.now(timezone.utc).isoformat()
        declared = definition(boundary["nonce"], run_id, users, created_at)
        url = development_database_url()
        schema_version = previous.get("schema_version") if previous else 2
        require(schema_version in (1, 2), "Unsupported discovery plan receipt version")
        creation_head = None
        if schema_version == 2:
            creation_head = previous.get("creation_schema_head") if previous else guarded_schema_head(url, boundary)
            require(creation_head in SUPPORTED_FIXTURE_REVISIONS,
                    "Unsupported discovery plan creation schema revision")
        receipt = {"schema_version": schema_version, "fixture": "isolated-discovery-acceptance-only",
            "version": VERSION, "run_id": run_id, "created_at": created_at, "boundary": boundary,
            "access_manifest_sha256": digest(current["fixtures"]), "users": users,
            "identity_receipts_sha256": digest(identity_receipts),
            "definition_sha256": digest(declared), **declared}
        if schema_version == 2:
            receipt["creation_schema_head"] = creation_head
        completion = {"schema_version": schema_version, "run_id": run_id, "definition_sha256": digest(declared),
                      "boundary": boundary, "database": "eid_local_dev"}
        if schema_version == 2:
            completion["schema_head"] = creation_head
        if done_path.exists():
            existing_completion = read_receipt(done_path)
            expected_completions = ([completion | {"schema_head": revision}
                for revision in SUPPORTED_FIXTURE_REVISIONS] if schema_version == 1 else [completion])
            require(existing_completion in expected_completions, "Discovery completion receipt drift")
            completion = existing_completion
        require(previous is None or previous == receipt, "Discovery receipt drift; refusing overwrite")
        if previous is None:
            require(not done_path.exists(), "Completion receipt exists without an immutable plan")
            write_new_document(plan_path, receipt)
        if schema_version == 2:
            require(guarded_schema_head(url, boundary) == creation_head,
                    "Discovery plan schema changed; seed a NEW run")
        verify_migration_target(url)
        require(selected_boundary() == boundary, "Discovery fixture boundary changed before connect")
        with psycopg.connect(url.replace("postgresql+psycopg:", "postgresql:"), row_factory=dict_row,
                connect_timeout=3, options="-c statement_timeout=5000 -c lock_timeout=2000") as conn:
            current_revision = verify_connection(conn)
            if schema_version == 2:
                require(current_revision == creation_head,
                        "Discovery plan schema changed; seed a NEW run")
            elif "schema_head" in completion:
                # Preserve the original receipt across an explicitly supported expand migration.
                require(SUPPORTED_FIXTURE_REVISIONS.index(completion["schema_head"])
                        <= SUPPORTED_FIXTURE_REVISIONS.index(current_revision),
                        "Discovery completion receipt schema is newer than the guarded database")
            else:
                completion["schema_head"] = current_revision
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         ("eid-discovery-seed:" + boundary["nonce"],))
            verify_identities(conn, users)
            created = apply_definition(conn, declared, allow_create=not done_path.exists(),
                                       allow_existing=previous is not None)
            # Recheck full guard and immutable local evidence before committing any writes.
            verify_migration_target(url)
            require(selected_boundary() == boundary and read_receipt(plan_path) == receipt
                    and read_document(state / "access-fixtures.json") == current["fixtures"],
                    "Discovery fixture evidence changed before commit")
            require(read_document(state / "access-fixture-receipts.json") == identity_receipts,
                    "Identity receipts changed before discovery fixture commit")
        if done_path.exists():
            require(read_receipt(done_path) == completion, "Discovery completion receipt drift")
        else:
            write_new_document(done_path, completion)
        return {"receipt": str(plan_path), "completion_receipt": str(done_path),
                "created": created, "mutable_state": "preserved; read via current API",
                "run_id": run_id, "workspaces": declared["workspaces"], "records": declared["records"],
                "policy_version": declared["policy_version"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="New ID for each fresh restore acceptance; old runs retained")
    args = parser.parse_args()
    print(json.dumps(seed(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
