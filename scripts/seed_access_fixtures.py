"""Create explicitly named local acceptance identities; never overwrite existing policies.

Only runs against the existing guarded EID development database and owned Keycloak.
These are development fixtures, not enterprise identity mappings or business records.
"""
import json
import base64
import hashlib
import secrets
import os
import tempfile
from contextlib import contextmanager
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
import psycopg
from psycopg.rows import dict_row

from edw_api.access.policy import ROLE_OPERATIONS
from scripts.verify_local_environment import (
    _keycloak_admin_headers, ownership, service_container, verify_migration_target,
    development_database_url, environment_state_directory,
)

FIXTURE_PASSWORD = "eid-local-access"
SUPPORTED_FIXTURE_REVISIONS = ("0007_workspace_discovery", "0008_durable_submission")


@contextmanager
def fixture_lock(path):
    """Serialize fixture creation and its ownership receipts across local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another local fixture seed is running") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_receipts(path, receipts):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name+".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(receipts, indent=2)+"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_fixture_login(username, boundary):
    """Verify the advertised password with a fresh PKCE login, never reset credentials."""
    origin = "http://localhost:18080"
    callback = origin+"/auth/callback"
    class LoginForm(HTMLParser):
        def __init__(self):
            super().__init__()
            self.actions = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "form" and attrs.get("id") == "kc-form-login" and attrs.get("method", "").lower() == "post":
                self.actions.append(attrs.get("action", ""))
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    try:
        boundary()
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            response = client.get(origin+"/realms/eid-local/protocol/openid-connect/auth", params={
                "client_id": "eid-web", "redirect_uri": callback, "response_type": "code",
                "scope": "openid profile", "state": state, "code_challenge": challenge,
                "code_challenge_method": "S256", "prompt": "login"})
            form = LoginForm()
            if response.status_code != 200 or len(response.content)>256*1024:
                raise ValueError()
            form.feed(response.text)
            if len(form.actions) != 1:
                raise ValueError()
            action = urlsplit(form.actions[0])
            if (action.scheme != "http" or action.netloc != "localhost:18080" or
                    action.path != "/realms/eid-local/login-actions/authenticate" or action.fragment):
                raise ValueError()
            boundary()
            # Browsers accept Secure cookies on localhost; http.cookiejar does not.
            # Forward only this fresh local session's domain/path-matching cookies
            # to the exact owned loopback action validated above, never a redirect.
            cookies = "; ".join(f"{cookie.name}={cookie.value}" for cookie in client.cookies.jar
                if cookie.domain in {"localhost", "localhost.local", ".localhost"}
                and action.path.startswith(cookie.path.rstrip("/")+"/") and not cookie.is_expired())
            response = client.post(form.actions[0], headers={"Cookie": cookies},
                                   data={"username": username, "password": FIXTURE_PASSWORD})
            target = urlsplit(response.headers.get("Location", ""))
            query = parse_qs(target.query)
            if (response.status_code not in (302, 303) or target.scheme != "http" or
                    target.netloc != "localhost:18080" or target.path != "/auth/callback" or
                    target.fragment or query.get("state") != [state] or len(query.get("code", [])) != 1 or
                    not query["code"][0] or "error" in query):
                raise ValueError()
    except (httpx.HTTPError, ValueError):
        # Never expose password, authorization code, session URL or response body.
        raise RuntimeError("Local fixture login does not match its declaration; refusing overwrite") from None


def require_fixture(row, expected):
    if row is None or any(row.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Existing local fixture differs from its declaration; refusing overwrite")


def seed():
    database_url = development_database_url()
    verify_migration_target(database_url)
    with fixture_lock(environment_state_directory(Path(__file__).resolve().parents[1]) / "access-fixtures.lock"):
        return _seed_verified(database_url)


def _seed_verified(database_url):
    nonce = ownership(create=False)["nonce"]
    keycloak = service_container("keycloak", 8080, 58080)
    gateway = service_container("nginx", 8080, 18080)
    def boundary():
        if (ownership(create=False)["nonce"] != nonce or service_container("keycloak", 8080, 58080) != keycloak
                or service_container("nginx", 8080, 18080) != gateway):
            raise RuntimeError("Local fixture ownership changed")
    def identifier(name):
        return uuid5(NAMESPACE_URL, "eid-access-fixture:"+nonce+":"+name)
    users = {}
    receipt_path = environment_state_directory(Path(__file__).resolve().parents[1]) / "access-fixture-receipts.json"
    receipts = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    with httpx.Client(base_url="http://localhost:58080", timeout=5) as client:
        headers = _keycloak_admin_headers(client)
        profile = client.get("/admin/realms/eid-local/users/profile", headers=headers)
        profile.raise_for_status()
        profile_data = profile.json()
        attribute = {"name": "eid_fixture_owner", "displayName": "Local fixture ownership",
                     "permissions": {"view": ["admin"], "edit": ["admin"]}}
        existing = [item for item in profile_data["attributes"] if item["name"] == attribute["name"]]
        if not existing:
            boundary()
            profile_data["attributes"].append(attribute)
            response = client.put("/admin/realms/eid-local/users/profile", headers=headers, json=profile_data)
            response.raise_for_status()
        elif len(existing) != 1 or existing[0].get("permissions") != attribute["permissions"]:
            raise RuntimeError("Fixture ownership attribute is not restricted to administrators")
        for role in ROLE_OPERATIONS:
            headers = _keycloak_admin_headers(client)
            username = "eid-access-"+role.replace("_", "-")
            response = client.get("/admin/realms/eid-local/users",
                                  params={"username": username, "exact": "true"}, headers=headers)
            response.raise_for_status()
            matches = response.json()
            if not matches:
                boundary()
                headers = _keycloak_admin_headers(client)
                response = client.post("/admin/realms/eid-local/users", headers=headers, json={
                    "username": username, "enabled": True, "emailVerified": True,
                    "firstName": "本地验收", "lastName": role, "email": username+"@eid.invalid",
                    "attributes": {"eid_fixture_owner": [nonce]},
                    "credentials": [{"type": "password", "value": FIXTURE_PASSWORD, "temporary": False}],
                })
                response.raise_for_status()
                created_id = response.headers["Location"].rsplit("/", 1)[1]
                receipts[username] = {"id": created_id, "nonce": nonce}
                write_receipts(receipt_path, receipts)
                response = client.get("/admin/realms/eid-local/users",
                                      params={"username": username, "exact": "true"}, headers=headers)
                response.raise_for_status()
                matches = response.json()
            if len(matches) == 1 and matches[0].get("attributes", {}).get("eid_fixture_owner") != [nonce]:
                # Recover only this tool's successful create receipt; never adopt a named existing user.
                if receipts.get(username) != {"id": matches[0]["id"], "nonce": nonce}:
                    raise RuntimeError("No ownership proof for existing fixture identity")
                boundary()
                headers = _keycloak_admin_headers(client)
                attributes = {**matches[0].get("attributes", {}), "eid_fixture_owner": [nonce]}
                response = client.put("/admin/realms/eid-local/users/"+matches[0]["id"],
                                      headers=headers, json={**matches[0], "attributes": attributes})
                response.raise_for_status()
                response = client.get("/admin/realms/eid-local/users/"+matches[0]["id"], headers=headers)
                response.raise_for_status()
                matches = [response.json()]
            if (len(matches) != 1 or matches[0].get("attributes", {}).get("eid_fixture_owner") != [nonce]
                    or matches[0].get("enabled") is not True):
                raise RuntimeError("Existing fixture identity does not match; refusing overwrite")
            expected_profile = {"firstName": "本地验收", "lastName": role,
                                "email": username+"@eid.invalid"}
            if any(matches[0].get(key) and matches[0][key] != value
                   for key, value in expected_profile.items()):
                raise RuntimeError("Existing fixture profile differs from its declaration; refusing overwrite")
            missing = {key: value for key, value in expected_profile.items() if not matches[0].get(key)}
            if missing:
                if receipts.get(username) != {"id": matches[0]["id"], "nonce": nonce}:
                    raise RuntimeError("Missing profile has no local create receipt")
                boundary()
                headers = _keycloak_admin_headers(client)
                response = client.put("/admin/realms/eid-local/users/"+matches[0]["id"],
                                      headers=headers, json={**matches[0], **missing})
                response.raise_for_status()
            verify_fixture_login(username, boundary)
            users[role] = {"username": username, "subject": matches[0]["id"]}
    boundary()
    with psycopg.connect(database_url.replace("postgresql+psycopg:", "postgresql:"), row_factory=dict_row,
                         connect_timeout=3, options="-c statement_timeout=5000 -c lock_timeout=2000") as conn:
        actual = conn.execute("SELECT current_database(),current_user,shobj_description(oid,'pg_database') "
                              "AS marker FROM pg_database WHERE datname=current_database()").fetchone()
        if actual != {"current_database": "eid_local_dev", "current_user": "eid_migrator", "marker": "eid-local-dev-v1"}:
            raise RuntimeError("Fixture database boundary mismatch")
        revisions = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        if revisions not in [[{"version_num": revision}] for revision in SUPPORTED_FIXTURE_REVISIONS]:
            raise RuntimeError("Apply the current guarded migration before seeding fixtures")
        workspaces = [identifier("workspace-a"), identifier("workspace-b")]
        for suffix, wid in zip(("a", "b"), workspaces):
            slug = "eid-access-fixture-"+suffix
            conn.execute("INSERT INTO workspace(id,slug,name) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                         (wid, slug, "本地权限验收项目 "+suffix.upper()))
            require_fixture(conn.execute("SELECT * FROM workspace WHERE id=%s", (wid,)).fetchone(),
                            {"slug": slug, "name": "本地权限验收项目 "+suffix.upper()})
            conn.execute("""INSERT INTO access_workspace(workspace_id,tenant_id,project_id,customer_id,
                product_id,department,classification) VALUES (%s,%s,%s,'fixture-customer','fixture-product',
                '验收部',1) ON CONFLICT(workspace_id) DO NOTHING""", (wid, identifier("tenant"), "fixture-"+suffix))
            require_fixture(conn.execute("SELECT * FROM access_workspace WHERE workspace_id=%s", (wid,)).fetchone(),
                            {"tenant_id": identifier("tenant"), "project_id": "fixture-"+suffix,
                             "customer_id": "fixture-customer", "product_id": "fixture-product",
                             "department": "验收部", "classification": 1})
        for index, (role, user) in enumerate(users.items()):
            actor = identifier(role)
            user["actor_id"] = str(actor)
            conn.execute("""INSERT INTO identity_account(id,subject,display_name,department)
                VALUES (%s,%s,%s,'验收部') ON CONFLICT(id) DO NOTHING""",
                         (actor, user["subject"], "本地验收 · "+role))
            require_fixture(conn.execute("SELECT * FROM identity_account WHERE id=%s", (actor,)).fetchone(),
                            {"subject": user["subject"], "display_name": "本地验收 · "+role,
                             "department": "验收部", "active": True})
            assigned = workspaces if role in {"author", "system_admin"} else workspaces[:1]
            for wid in assigned:
                conn.execute("""INSERT INTO workspace_membership(identity_id,workspace_id)
                    VALUES (%s,%s) ON CONFLICT(identity_id,workspace_id) DO NOTHING""", (actor, wid))
                require_fixture(conn.execute("SELECT active FROM workspace_membership WHERE identity_id=%s "
                                             "AND workspace_id=%s", (actor, wid)).fetchone(), {"active": True})
                administrator = role == "system_admin"
                scopes = ["*"] if administrator else ["fixture-a", "fixture-b"]
                conn.execute("""INSERT INTO access_member(identity_id,workspace_id,roles,project_scope,
                    customer_scope,product_scope,department_scope,owner_scope,approval_states,clearance,
                    valid_from,valid_until) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    CURRENT_TIMESTAMP-interval '1 hour',NULL) ON CONFLICT(identity_id,workspace_id) DO NOTHING""",
                    (actor, wid, [role], scopes,
                     ["*"] if administrator else ["fixture-customer", f"fixture-customer-{index}"],
                     ["*"] if administrator else ["fixture-product", f"fixture-product-{index}"],
                     ["*"] if administrator else ["验收部"], "any" if administrator else "self",
                     ["draft", "in_review", "approved", "rejected"] if administrator else ["draft"],
                     3 if administrator else 1+index % 3))
                stored = conn.execute("SELECT *,valid_from<=CURRENT_TIMESTAMP AS already_valid "
                                      "FROM access_member WHERE identity_id=%s AND workspace_id=%s",
                                      (actor, wid)).fetchone()
                require_fixture(stored, {
                    "roles": [role], "project_scope": scopes,
                    "customer_scope": ["*"] if administrator else ["fixture-customer", f"fixture-customer-{index}"],
                    "product_scope": ["*"] if administrator else ["fixture-product", f"fixture-product-{index}"],
                    "department_scope": ["*"] if administrator else ["验收部"],
                    "owner_scope": "any" if administrator else "self",
                    "approval_states": ["draft", "in_review", "approved", "rejected"] if administrator else ["draft"],
                    "clearance": 3 if administrator else 1+index % 3,
                    "already_valid": True, "valid_until": None})
            rid = identifier("resource-"+role)
            conn.execute("""INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,
                product_id,department,owner_id,classification) VALUES (%s,%s,%s,'local-policy-fixture',
                'fixture-a',%s,%s,'验收部',%s,%s) ON CONFLICT(id) DO NOTHING""",
                (rid, workspaces[0], "本地授权验收资源 · "+role, f"fixture-customer-{index}",
                 f"fixture-product-{index}", actor, 1+index % 3))
            require_fixture(conn.execute("SELECT *,valid_from<=CURRENT_TIMESTAMP AS already_valid "
                                         "FROM access_resource WHERE id=%s", (rid,)).fetchone(), {
                "workspace_id": workspaces[0], "title": "本地授权验收资源 · "+role,
                "kind": "local-policy-fixture", "project_id": "fixture-a",
                "customer_id": f"fixture-customer-{index}", "product_id": f"fixture-product-{index}",
                "department": "验收部", "owner_id": actor, "classification": 1+index % 3,
                "approval_state": "draft", "publication_state": "unpublished", "head_ref": None,
                "already_valid": True, "valid_until": None})
            user["resource_id"] = str(rid)
    return {"fixture": "local-acceptance-only", "workspaces": list(map(str, workspaces)), "users": users}


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
