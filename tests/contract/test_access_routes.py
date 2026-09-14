from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4
from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import jsonschema
import psycopg
import pytest

from edw_api import main
from edw_api.access import routes, repository
from edw_api.access.policy import AccessDenied, AuthContext

CLIENT = TestClient(main.app)
WORKSPACE = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def authenticated(monkeypatch):
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject="verified"))
    @contextmanager
    def connection(_settings):
        yield object()
    monkeypatch.setattr(routes, "connection", connection)
    return {"Authorization": "Bearer checked", "X-Request-ID": "access-test",
            "traceparent": "00-"+"1"*32+"-"+"2"*16+"-01"}


def test_missing_bearer_never_reaches_policy(monkeypatch):
    monkeypatch.setattr(repository, "workspace_page", lambda *_: pytest.fail("unauthenticated access"))
    assert CLIENT.get("/api/v1/access/workspaces").status_code == 401


def test_workspace_page_uses_verified_subject_and_uuid_cursor(authenticated, monkeypatch):
    cursor = uuid4()
    seen = []
    def page(_conn, subject, after):
        seen.append((subject, after))
        return {"workspaces": [], "next_cursor": str(cursor)}
    monkeypatch.setattr(repository, "workspace_page", page)
    response = CLIENT.get("/api/v1/access/workspaces", params={"after": str(cursor)}, headers=authenticated)
    assert response.status_code == 200
    assert response.json() == {"data": {"workspaces": [], "next_cursor": str(cursor)}}
    assert seen == [("verified", cursor)]
    assert CLIENT.get("/api/v1/access/workspaces?after=invalid", headers=authenticated).status_code == 422
    assert len(seen) == 1


def test_unknown_and_forbidden_resources_share_error(authenticated, monkeypatch):
    def reject(*_args, **_kwargs):
        raise AccessDenied()
    monkeypatch.setattr(repository, "checked", reject)
    results = [CLIENT.get(f"/api/v1/access/workspaces/{WORKSPACE}/resources/{uuid4()}",
                          headers=authenticated) for _ in range(2)]
    assert all(response.status_code == 403 for response in results)
    assert results[0].json() == results[1].json()


@pytest.mark.parametrize("failure_phase", ["connect", "query"])
def test_policy_storage_failure_is_retryable_and_not_forbidden(authenticated, monkeypatch, failure_phase):
    def fail(*_args):
        raise psycopg.OperationalError("private database diagnostic")

    if failure_phase == "connect":
        monkeypatch.setattr(routes, "connection", fail)
    else:
        monkeypatch.setattr(repository, "workspace_page", fail)

    response = CLIENT.get("/api/v1/access/workspaces", headers=authenticated)
    assert response.status_code == 503
    assert response.json() == {"error": {
        "code": "POLICY_UNAVAILABLE", "message": "当前权限存储不可用", "details": {},
        "request_id": "access-test", "trace_id": "1" * 32, "retryable": True,
    }}


def test_resource_context_retains_request_trace_and_matches_c1(authenticated, monkeypatch):
    resource = uuid4()
    context = AuthContext(str(uuid4()), "eid-api", str(uuid4()), WORKSPACE,
                          (1, 2, 3), 1, "resource:read", "interactive", None)
    seen = []
    def checked(_conn, subject, workspace_id, operation, resource_id):
        seen.append((subject, workspace_id, operation, resource_id))
        return None, {"id": resource, "title": "Authorized resource", "kind": "policy"}, context
    monkeypatch.setattr(repository, "checked", checked)
    response = CLIENT.get(f"/api/v1/access/workspaces/{WORKSPACE}/resources/{resource}",
                          headers=authenticated)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(resource)
    assert seen == [("verified", UUID(WORKSPACE), "resource:read", resource)]
    result = response.json()["data"]["context"]
    schema = json.loads((Path(__file__).parents[2]/"contracts/access-context.schema.json").read_text())
    jsonschema.validate(result, schema, format_checker=jsonschema.FormatChecker())
    assert result["request_id"] == "access-test"
    assert result["trace_id"] == "1"*32


def test_member_body_cannot_supply_actor_or_unbounded_scope(authenticated, monkeypatch):
    monkeypatch.setattr(repository, "change_member", lambda *_: pytest.fail("invalid body reached write"))
    body = {"expected_epoch": [1, 1, 1], "active": True, "roles": ["author"],
            "project_scope": ["p"], "customer_scope": ["c"], "product_scope": ["x"],
            "department_scope": ["d"], "owner_scope": "self", "approval_states": ["draft"],
            "clearance": 1, "valid_from": datetime.now(timezone.utc).isoformat(), "valid_until": None}
    for extra in [{"actor_id": str(uuid4())}, {"roles": ["superuser"]}, {"clearance": 4},
                  {"expected_epoch": [True, 2, 3]}, {"expected_epoch": [1, "2", 3]},
                  {"expected_epoch": [1, 2, 3.0]}, {"active": "false"}, {"active": 0},
                  {"approval_states": ["draft", "draft"]}, {"approval_states": ["draft"]*50000},
                  {"project_scope": ["x"*129]}, {"valid_from": "2026-09-01T00:00:00"},
                  *[{key: ["valid\x00invalid"]} for key in
                    ("project_scope", "customer_scope", "product_scope", "department_scope")]]:
        response = CLIENT.put(f"/api/v1/access/workspaces/{WORKSPACE}/members/{uuid4()}",
                              json=body|extra, headers=authenticated)
        assert response.status_code == 422


def test_delegation_nul_purpose_is_rejected_before_database_write(authenticated, monkeypatch):
    monkeypatch.setattr(repository, "create_delegation", lambda *_: pytest.fail("invalid purpose reached write"))
    response = CLIENT.post(f"/api/v1/access/workspaces/{WORKSPACE}/delegations",
                           json={"operation": "workspace:read", "purpose": "stage\x00one"}, headers=authenticated)
    assert response.status_code == 422
