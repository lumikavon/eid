"""Read-only fixture manifest preflight; optionally hold the seed's process lock.

The only filesystem mutation is the existing advisory lock file. This entry point
never seeds fixtures, repairs receipts, or writes to an identity/database service.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from scripts.seed_access_fixtures import fixture_lock
from scripts.verify_local_environment import (
    _recorded_owner_nonce, development_database_url, environment_state_directory, verify_migration_target,
)

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("author", "expert", "quality", "template_admin", "knowledge_admin",
         "approver", "system_admin")
RECOVERY_MARKER = "access-ux-recovery-required.json"


def _require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate fixture JSON field")
        result[key] = value
    return result


def read_document(path):
    _require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
             "Missing or linked fixture evidence: " + path.name)
    _require(path.stat().st_size <= 64 * 1024, "Fixture evidence is too large")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError):
        raise RuntimeError("Invalid fixture JSON: " + path.name) from None


def validate_manifest(manifest, receipts, nonce):
    """Validate the exact seed output against the selected environment's owner."""
    _require(isinstance(nonce, str) and bool(nonce), "Missing fixture owner nonce")
    _require(isinstance(manifest, dict) and set(manifest) == {"fixture", "workspaces", "users"},
             "Unexpected fixture manifest fields")
    _require(manifest["fixture"] == "local-acceptance-only", "Invalid fixture marker")
    def identifier(name):
        return str(uuid5(NAMESPACE_URL, "eid-access-fixture:" + nonce + ":" + name))
    _require(manifest["workspaces"] == [identifier("workspace-a"), identifier("workspace-b")],
             "Fixture workspaces do not match the current owner")
    users = manifest["users"]
    _require(isinstance(users, dict) and set(users) == set(ROLES), "Expected exactly seven fixture roles")
    usernames = {"eid-access-" + role.replace("_", "-") for role in ROLES}
    _require(isinstance(receipts, dict) and set(receipts) == usernames,
             "Expected exactly seven fixture identity receipts")
    subjects = set()
    for role in ROLES:
        user = users[role]
        username = "eid-access-" + role.replace("_", "-")
        _require(isinstance(user, dict) and set(user) == {"username", "subject", "actor_id", "resource_id"},
                 "Unexpected fixture identity fields")
        subject = user["subject"]
        try:
            _require(isinstance(subject, str) and str(UUID(subject)) == subject,
                     "Invalid fixture subject")
        except ValueError:
            raise RuntimeError("Invalid fixture subject") from None
        _require(subject not in subjects, "Duplicate fixture subject")
        subjects.add(subject)
        _require(user == {"username": username, "subject": subject,
                          "actor_id": identifier(role), "resource_id": identifier("resource-" + role)},
                 "Fixture identity does not match the current owner")
        _require(receipts[username] == {"id": subject, "nonce": nonce},
                 "Fixture subject has no matching current ownership receipt")
    return manifest


def preflight(state_directory=None):
    selector = os.environ.get("EID_ENVIRONMENT_CONFIG")
    state = environment_state_directory(ROOT)
    _require(state_directory is None or state == state_directory, "Fixture environment changed")
    _require(not (state / RECOVERY_MARKER).exists(),
             "Unresolved UX fixture recovery evidence; review before further fixture use")
    nonce = _recorded_owner_nonce()
    manifest = read_document(state / "access-fixtures.json")
    receipts = read_document(state / "access-fixture-receipts.json")
    validate_manifest(manifest, receipts, nonce)
    # This guard proves the selected host, owned services and dedicated DB boundary.
    verify_migration_target(development_database_url())
    _require(os.environ.get("EID_ENVIRONMENT_CONFIG") == selector
             and environment_state_directory(ROOT) == state and _recorded_owner_nonce() == nonce,
             "Fixture environment or ownership changed during preflight")
    _require(read_document(state / "access-fixtures.json") == manifest
             and read_document(state / "access-fixture-receipts.json") == receipts,
             "Fixture evidence changed during preflight")
    return {"fixtures": manifest, "state_directory": str(state.resolve()), "nonce": nonce}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold-lock", action="store_true")
    args = parser.parse_args()
    # Resolve before touching a lock: malformed remote selectors never fall back locally.
    state = environment_state_directory(ROOT)
    if args.hold_lock:
        with fixture_lock(state / "access-fixtures.lock"):
            result = preflight(state)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            # Parent stdin is a lifetime pipe: normal release, crash and exit close it.
            _require(sys.stdin.read() == "", "Unexpected fixture lock control input")
    else:
        print(json.dumps(preflight(state), ensure_ascii=False))


if __name__ == "__main__":
    main()
