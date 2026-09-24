import json
import subprocess
import sys

import httpx
import pytest

from scripts import seed_access_fixtures as fixtures


@pytest.mark.parametrize("revision", ["0010_task_observation", "0011_template_creation"])
def test_access_fixture_guard_accepts_current_migration_heads(revision):
    assert fixtures.is_supported_fixture_head([{"version_num": revision}])


@pytest.mark.parametrize("revisions", [[], [{"version_num": "0012_unknown"}],
                                     [{"version_num": "0010_task_observation"},
                                      {"version_num": "0011_template_creation"}]])
def test_access_fixture_guard_rejects_invalid_migration_heads(revisions):
    assert not fixtures.is_supported_fixture_head(revisions)


def test_receipt_replace_failure_preserves_previous_complete_document(monkeypatch, tmp_path):
    receipt = tmp_path/"receipts.json"
    original = {"first": {"id": "one", "nonce": "owner"}}
    fixtures.write_receipts(receipt, original)
    old = receipt.read_bytes()
    def fail(*_):
        raise OSError("injected replace failure")
    monkeypatch.setattr(fixtures.os, "replace", fail)
    with pytest.raises(OSError):
        fixtures.write_receipts(receipt, original | {"second": {"id": "two", "nonce": "owner"}})
    assert receipt.read_bytes() == old
    assert list(tmp_path.iterdir()) == [receipt]


def test_fixture_lock_excludes_another_process_and_releases_on_exit(tmp_path):
    lock = tmp_path/"fixtures.lock"
    script = "from pathlib import Path; import sys; from scripts.seed_access_fixtures import fixture_lock\nwith fixture_lock(Path(sys.argv[1])): pass"
    with fixtures.fixture_lock(lock):
        other = subprocess.run([sys.executable, "-c", script, str(lock)], capture_output=True, text=True, timeout=10)
        assert other.returncode != 0
        assert "Another local fixture seed is running" in other.stderr
    with fixtures.fixture_lock(lock):
        pass


def test_concurrent_seed_stops_before_external_operations(monkeypatch, tmp_path):
    monkeypatch.setattr(fixtures, "__file__", str(tmp_path/"scripts/seed_access_fixtures.py"))
    monkeypatch.setattr(fixtures, "verify_migration_target", lambda _: None)
    monkeypatch.setattr(fixtures, "_seed_verified", lambda: pytest.fail("must not contact external services"))
    with fixtures.fixture_lock(tmp_path/".local/access-fixtures.lock"):
        with pytest.raises(RuntimeError, match="Another local fixture seed"):
            fixtures.seed()


def test_unverified_database_never_contacts_identity_service(monkeypatch):
    def deny(_url):
        raise RuntimeError("unverified")
    monkeypatch.setattr(fixtures, "verify_migration_target", deny)
    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_: pytest.fail("must not contact Keycloak"))
    with pytest.raises(RuntimeError, match="unverified"):
        fixtures.seed()


@pytest.mark.parametrize("foreign,attribute_permissions", [
    (True, {"view": ["admin"], "edit": ["admin"]}),
    (False, {"view": ["admin", "user"], "edit": ["admin", "user"]}),
])
def test_foreign_user_or_user_editable_ownership_marker_blocks_database_writes(monkeypatch, tmp_path,
                                                                            foreign, attribute_permissions):
    monkeypatch.setattr(fixtures, "__file__", str(tmp_path/"scripts/seed_access_fixtures.py"))
    monkeypatch.setattr(fixtures, "verify_migration_target", lambda _: None)
    monkeypatch.setattr(fixtures, "ownership", lambda **_: {"nonce": "current-owner"})
    monkeypatch.setattr(fixtures, "service_container", lambda *_: "container")
    monkeypatch.setattr(fixtures, "_keycloak_admin_headers", lambda _: {})
    monkeypatch.setattr(fixtures.psycopg, "connect", lambda *_a, **_k: pytest.fail("no database write"))
    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def get(self, path, **_):
            data = {"attributes": [{"name": "eid_fixture_owner", "permissions": attribute_permissions}]}
            if not path.endswith("profile"):
                data = [{"id": "existing", "username": "eid-access-author", "enabled": True,
                         "attributes": {"eid_fixture_owner": ["foreign-owner" if foreign else "current-owner"]}}]
            return httpx.Response(200, json=data, request=httpx.Request("GET", "http://local"+path))
        def put(self, *_a, **_k):
            pytest.fail("must not overwrite identity or profile")
        def post(self, *_a, **_k):
            pytest.fail("must not create or overwrite identity")
    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_: Client())
    with pytest.raises(RuntimeError):
        fixtures.seed()


@pytest.mark.parametrize("drift", [False, True])
def test_receipt_recovery_preserves_complete_user_profile_and_rejects_drift(monkeypatch, tmp_path, drift):
    monkeypatch.setattr(fixtures, "verify_fixture_login", lambda *_: None)
    monkeypatch.setattr(fixtures, "__file__", str(tmp_path/"scripts/seed_access_fixtures.py"))
    (tmp_path/".local").mkdir()
    (tmp_path/".local/access-fixture-receipts.json").write_text(json.dumps({
        "eid-access-author": {"id": "created-id", "nonce": "current-owner"}}))
    monkeypatch.setattr(fixtures, "ROLE_OPERATIONS", {"author": {"document:edit"}})
    monkeypatch.setattr(fixtures, "verify_migration_target", lambda _: None)
    monkeypatch.setattr(fixtures, "ownership", lambda **_: {"nonce": "current-owner"})
    monkeypatch.setattr(fixtures, "service_container", lambda *_: "container")
    monkeypatch.setattr(fixtures, "_keycloak_admin_headers", lambda _: {})
    class ReachedDatabase(Exception):
        pass
    def stop(*_a, **_k):
        raise ReachedDatabase()
    monkeypatch.setattr(fixtures.psycopg, "connect", stop)
    user = {"id": "created-id", "username": "eid-access-author", "enabled": True,
            "firstName": "Keep" if drift else "本地验收", "lastName": "author",
            "email": "eid-access-author@eid.invalid", "emailVerified": True}
    updates = []
    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def get(self, path, **_):
            data = {"attributes": [{"name": "eid_fixture_owner",
                    "permissions": {"view": ["admin"], "edit": ["admin"]}}]} if path.endswith("profile") else (
                    user if path.endswith("created-id") else [user])
            return httpx.Response(200, json=data, request=httpx.Request("GET", "http://local"+path))
        def put(self, path, **kwargs):
            updates.append(kwargs["json"])
            user.update(kwargs["json"])
            return httpx.Response(204, request=httpx.Request("PUT", "http://local"+path))
    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_: Client())
    with pytest.raises(RuntimeError if drift else ReachedDatabase):
        fixtures.seed()
    assert len(updates) == 1
    assert updates[0]["firstName"] == ("Keep" if drift else "本地验收")
    assert updates[0]["lastName"] == "author"
    assert updates[0]["email"] == "eid-access-author@eid.invalid"
    assert updates[0]["emailVerified"] is True
    assert updates[0]["attributes"] == {"eid_fixture_owner": ["current-owner"]}


@pytest.mark.parametrize("field,value", [("roles", ["expert"]), ("active", False),
    ("customer_id", "foreign"), ("clearance", 3), ("already_valid", False), ("valid_until", "expired")])
def test_database_fixture_drift_is_reported_without_overwrite(field, value):
    expected = {"roles": ["author"], "active": True, "customer_id": "local",
                "clearance": 1, "already_valid": True, "valid_until": None}
    row = expected | {field: value}
    with pytest.raises(RuntimeError, match="refusing overwrite"):
        fixtures.require_fixture(row, expected)
    assert row[field] == value
    fixtures.require_fixture(expected | {"policy_epoch": 42}, expected)


@pytest.mark.parametrize("failure", [None, "password", "foreign-action", "wrong-state"])
def test_password_verification_requires_local_form_and_correlated_success(monkeypatch, failure):
    calls = []
    state = None
    def handler(request):
        nonlocal state
        calls.append(request.method)
        if request.method == "GET":
            state = request.url.params["state"]
            assert request.url.params["code_challenge_method"] == "S256"
            origin = "https://foreign.invalid" if failure == "foreign-action" else "http://localhost:18080"
            return httpx.Response(200, headers=[
                ("Set-Cookie", "AUTH_SESSION_ID=local-session; Secure; Path=/realms/eid-local/"),
                ("Set-Cookie", "OTHER_PATH=private; Path=/admin/"),
                ("Set-Cookie", "EXPIRED=private; Path=/; Max-Age=0")],
                text=f'<form id="kc-form-login" method="post" action="{origin}/realms/eid-local/login-actions/authenticate?session_code=private"></form>')
        assert request.headers["Cookie"] == "AUTH_SESSION_ID=local-session"
        if failure == "password":
            return httpx.Response(200, text="Login failed")
        selected = "wrong" if failure == "wrong-state" else state
        return httpx.Response(302, headers={"Location": f"http://localhost:18080/auth/callback?code=private&state={selected}"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(fixtures.httpx, "Client", lambda **_: client)
    boundaries = []
    if failure:
        with pytest.raises(RuntimeError, match="refusing overwrite") as error:
            fixtures.verify_fixture_login("eid-access-author", lambda: boundaries.append(True))
        assert "private" not in str(error.value)
        assert fixtures.FIXTURE_PASSWORD not in str(error.value)
    else:
        fixtures.verify_fixture_login("eid-access-author", lambda: boundaries.append(True))
    assert calls == (["GET"] if failure == "foreign-action" else ["GET", "POST"])
    assert len(boundaries) == len(calls)
