"""D03/D04/D06/D07 的边界契约；真实 PostgreSQL 证明由 live 套件承担。"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
import jsonschema
import psycopg
import pytest

from edw_api import main
from edw_api.access.policy import AccessDenied
from edw_api.discovery import repository, routes, schemas
from edw_api.errors import ApiError

CLIENT = TestClient(main.app)
WID = "22222222-2222-4222-8222-222222222222"
RID = "33333333-3333-4333-8333-333333333333"
AID = "44444444-4444-4444-8444-444444444444"
PREFIX = f"/api/v1/workspaces/{WID}"
NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)
CONTEXT = {"actor_id": AID, "workspace_id": WID, "policy_epoch": [1, 2, 1]}


def item():
    return {"id": RID, "workspace_id": WID, "title": "实际文档", "kind": "document",
            "document_type": "technical", "lifecycle": "DRAFT", "visibility": "visible",
            "created_by": AID, "created_at": NOW, "updated_at": NOW, "version_label": None,
            "revision": 1, "resource_epoch": 5, "favorite": False, "favorite_revision": 0,
            "participating": False}


def page():
    return {"items": [item()], "total_count": 23, "next_cursor": None, "context": CONTEXT,
            "storage": {"metadata_bytes": 251, "measured_at": NOW,
                        "scope": "authorized_filtered_record_metadata",
                        "definition": repository.STORAGE_DEFINITION, "visibility": "visible",
                        "attachment_bytes": None, "quota_bytes": None}}


def summary():
    return {"context": CONTEXT,
            "workspace": {"id": WID, "name": "实际项目", "slug": "actual",
                          "project_id": "p", "customer_id": "c", "product_id": "x",
                          "department": "d", "classification": 1},
            "total_count": 23, "storage": page()["storage"], "todo_count": 3,
            "week_new_documents": {"value": 2, "window_start": NOW, "window_end": NOW,
                                   "definition": "authorized_filtered_documents_created_since_utc_monday"},
            "last_activity_at": NOW, "future_panels": list(repository.FUTURE_PANELS)}


@pytest.fixture
def authenticated(monkeypatch):
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject="verified"))
    @contextmanager
    def connection(_settings):
        yield object()
    monkeypatch.setattr(routes, "connection", connection)
    return {"Authorization": "Bearer checked", "X-Request-ID": "discovery-test",
            "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"}


def test_generated_shared_schema_is_current_and_checks_actual_response(authenticated, monkeypatch):
    contract = json.loads((Path(__file__).parents[2] / "contracts/discovery.schema.json").read_text("utf8"))
    assert contract == schemas.contract_schema()
    jsonschema.Draft202012Validator.check_schema(contract)
    monkeypatch.setattr(repository, "list_records", lambda *_: page())
    response = CLIENT.get(PREFIX + "/discovery", headers=authenticated)
    assert response.status_code == 200
    jsonschema.validate(response.json(), contract, format_checker=jsonschema.FormatChecker())
    assert response.json()["data"]["total_count"] == 23
    assert response.json()["data"]["items"][0]["id"] == RID


@pytest.mark.parametrize("path", ["/discovery", "/discovery/summary", f"/discovery/{RID}"])
def test_reads_require_verified_bearer(path, monkeypatch):
    monkeypatch.setattr(routes, "connection", lambda *_: pytest.fail("未认证请求接触存储"))
    assert CLIENT.get(PREFIX + path).status_code == 401


@pytest.mark.parametrize("params", [
    {"actor_id": AID}, {"scope": "*"}, {"tab": "all"}, {"visibility": "deleted"},
    {"kind": "policy"}, {"limit": "0"}, {"limit": "51"}, {"limit": "true"},
    {"cursor": "x" * 2049}, {"cursor": "a/b"}, {"document_type": "bad"},
    {"lifecycle": "bad"}, {"collection": "documents"}, {"collection": ""},
    {"collection": "TODO"}, {"collection": "true"}, {"collection": "todo", "can_edit": "true"},
])
def test_strict_get_filters_never_reach_repository(authenticated, monkeypatch, params):
    monkeypatch.setattr(repository, "list_records", lambda *_: pytest.fail("无效参数抵达查询"))
    response = CLIENT.get(PREFIX + "/discovery", params=params, headers=authenticated)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


@pytest.mark.parametrize("body", [
    {"query": " "}, {"query": "x" * 129}, {"query": "a\x00b"}, {"query": 42},
    {"query": "文档", "actor_id": AID}, {"query": "文档", "limit": True},
    {"query": "文档", "limit": "2"}, {"query": "文档", "limit": 51},
    {"query": "文档", "collection": "documents"}, {"query": "文档", "collection": None},
    {"query": "文档", "collection": True}, {"query": "文档", "collection": ["todo"]},
    {"query": "文档", "collection": "todo", "can_edit": True},
])
def test_search_is_strict_and_body_only(authenticated, monkeypatch, body):
    monkeypatch.setattr(repository, "search_records", lambda *_: pytest.fail("无效搜索抵达查询"))
    assert CLIENT.post(PREFIX + "/search", json=body, headers=authenticated).status_code == 422


def test_search_passes_trimmed_text_and_verified_subject(authenticated, monkeypatch):
    seen = []
    def search(conn, subject, workspace, filters):
        seen.append((subject, workspace, filters.query, filters.tab))
        return page() | {"functions": []}
    monkeypatch.setattr(repository, "search_records", search)
    response = CLIENT.post(PREFIX + "/search", json={"query": "  文档  ", "tab": "favorites"},
                           headers=authenticated)
    assert response.status_code == 200
    assert seen == [("verified", UUID(WID), "文档", "favorites")]


@pytest.mark.parametrize("endpoint,operation,response_body", [
    ("/discovery", "list_records", page), ("/discovery/summary", "summary", summary),
])
@pytest.mark.parametrize("collection", ["all", "todo", "references"])
@pytest.mark.parametrize("tab", ["recent", "created", "participating", "favorites"])
def test_collection_query_preserves_all_intersecting_filters(
        authenticated, monkeypatch, endpoint, operation, response_body, collection, tab):
    seen = []
    def read(conn, subject, workspace, filters):
        seen.append((subject, workspace, filters))
        return response_body()
    monkeypatch.setattr(repository, operation, read)
    params = {"collection": collection, "tab": tab, "kind": "knowledge",
              "document_type": "technical", "lifecycle": "ARCHIVED", "visibility": "recycled",
              "limit": "3"}
    response = CLIENT.get(PREFIX + endpoint, params=params, headers=authenticated)
    assert response.status_code == 200
    assert seen[0][:2] == ("verified", UUID(WID))
    assert seen[0][2].model_dump() == params | {"limit": 3, "cursor": None}


@pytest.mark.parametrize("endpoint,operation,response_body", [
    ("/discovery", "list_records", page), ("/discovery/summary", "summary", summary),
    ("/search", "search_records", lambda: page() | {"functions": []}),
])
def test_collection_is_optional_with_default_all(
        authenticated, monkeypatch, endpoint, operation, response_body):
    def read(conn, subject, workspace, filters):
        assert filters.collection == "all"
        return response_body()
    monkeypatch.setattr(repository, operation, read)
    if endpoint == "/search":
        response = CLIENT.post(PREFIX + endpoint, json={"query": "文档"}, headers=authenticated)
    else:
        response = CLIENT.get(PREFIX + endpoint, headers=authenticated)
    assert response.status_code == 200


@pytest.mark.parametrize("collection", ["all", "todo", "references"])
def test_search_body_passes_collection_with_trimmed_query_and_other_filters(
        authenticated, monkeypatch, collection):
    body = {"collection": collection, "tab": "favorites", "kind": "reference",
            "document_type": "other", "lifecycle": "DRAFT", "visibility": "visible", "limit": 2}
    def search(conn, subject, workspace, filters):
        assert subject == "verified" and workspace == UUID(WID)
        assert filters.model_dump() == body | {"query": "知识", "cursor": None}
        return page() | {"functions": []}
    monkeypatch.setattr(repository, "search_records", search)
    response = CLIENT.post(PREFIX + "/search", json=body | {"query": "  知识  "}, headers=authenticated)
    assert response.status_code == 200


def test_summary_rejects_unknown_collection_before_storage(authenticated, monkeypatch):
    monkeypatch.setattr(routes, "connection", lambda *_: pytest.fail("无效集合接触存储"))
    response = CLIENT.get(PREFIX + "/discovery/summary", params={"collection": "unknown"},
                          headers=authenticated)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


@pytest.mark.parametrize("name", ["Filters", "SearchRequest"])
def test_shared_schema_has_one_bounded_collection_enum(name):
    contract = schemas.contract_schema()
    model = contract["$defs"][name]
    assert model["properties"]["collection"] == {
        "default": "all", "enum": ["all", "todo", "references"], "title": "Collection", "type": "string"}
    validator = jsonschema.Draft202012Validator({"$defs": contract["$defs"], **model})
    base = {"query": "知识"} if name == "SearchRequest" else {}
    validator.validate(base)
    for collection in ("all", "todo", "references"):
        validator.validate(base | {"collection": collection})
    for collection in ("documents", "", "TODO", True, None, ["todo"]):
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(base | {"collection": collection})


def test_unknown_and_forbidden_detail_are_indistinguishable(authenticated, monkeypatch):
    def denied(*args, **kwargs):
        raise AccessDenied()
    monkeypatch.setattr(repository, "detail", denied)
    responses = [CLIENT.get(PREFIX + f"/discovery/{rid}", headers=authenticated)
                 for rid in (RID, AID)]
    assert responses[0].status_code == responses[1].status_code == 403
    assert responses[0].json() == responses[1].json()
    assert RID not in responses[0].text


def test_detail_distinguishes_resource_and_workspace_epochs(authenticated, monkeypatch):
    monkeypatch.setattr(repository, "detail", lambda *a, **kw: {
        "item": item(), "context": CONTEXT, "resource_context": CONTEXT | {"policy_epoch": [1, 2, 5]},
        "content_state": "metadata_only",
        "actions": {"favorite": True, "restore": False, "restore_policy_version": None}})
    response = CLIENT.get(PREFIX + f"/discovery/{RID}", headers=authenticated)
    assert response.status_code == 200
    assert response.json()["data"]["context"]["policy_epoch"] == [1, 2, 1]
    assert response.json()["data"]["resource_context"]["policy_epoch"] == [1, 2, 5]


@pytest.mark.parametrize("body", [
    {"favorite": "true", "expected_revision": 0}, {"favorite": 1, "expected_revision": 0},
    {"favorite": True, "expected_revision": True}, {"favorite": True, "expected_revision": -1},
    {"favorite": True, "expected_revision": "0"},
    {"favorite": True, "expected_revision": 0, "actor_id": AID},
])
def test_favorite_rejects_implicit_boolean_revision_and_actor(authenticated, monkeypatch, body):
    monkeypatch.setattr(repository, "collection_command", lambda *a, **kw: pytest.fail("无效命令写入"))
    response = CLIENT.put(PREFIX + f"/favorites/{RID}", json=body,
                          headers=authenticated | {"Idempotency-Key": "request-1"})
    assert response.status_code == 422


def test_commands_require_idempotency_and_bind_request_trace(authenticated, monkeypatch):
    seen = []
    def write(conn, subject, workspace, resource, command, **kwargs):
        seen.append((subject, workspace, resource, command, kwargs))
        return {"operation_id": AID, "action": "favorite.set", "resource_id": RID,
                "replayed": False, "occurred_at": NOW, "context": CONTEXT, "current": item()}
    monkeypatch.setattr(repository, "collection_command", write)
    body = {"favorite": True, "expected_revision": 0}
    assert CLIENT.put(PREFIX + f"/favorites/{RID}", json=body, headers=authenticated).status_code == 422
    response = CLIENT.put(PREFIX + f"/favorites/{RID}", json=body,
                          headers=authenticated | {"Idempotency-Key": "request-1"})
    assert response.status_code == 200
    assert seen[0][:3] == ("verified", UUID(WID), UUID(RID))
    assert seen[0][4]["request_id"] == "discovery-test"
    assert seen[0][4]["trace_id"] == "1" * 32


@pytest.mark.parametrize("error,code,status", [
    (psycopg.OperationalError("secret SQL"), "POLICY_UNAVAILABLE", 503),
    (ApiError(409, "REVISION_CONFLICT", "状态已变化"), "REVISION_CONFLICT", 409),
    (ApiError(422, "INVALID_CURSOR", "游标失效"), "INVALID_CURSOR", 422),
])
def test_failure_codes_are_safe_and_precise(authenticated, monkeypatch, error, code, status):
    def fail(*args):
        raise error
    monkeypatch.setattr(repository, "list_records", fail)
    response = CLIENT.get(PREFIX + "/discovery", headers=authenticated)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is (status == 503)
    assert "secret SQL" not in response.text


def test_invalid_database_response_rolls_back_before_return(authenticated, monkeypatch):
    events = []
    @contextmanager
    def connection(_settings):
        try:
            yield object()
        except Exception:
            events.append("rollback")
            raise
        else:
            events.append("commit")
    monkeypatch.setattr(routes, "connection", connection)
    monkeypatch.setattr(repository, "collection_command", lambda *a, **kw: {"bad": "response"})
    response = CLIENT.put(PREFIX + f"/favorites/{RID}",
                          json={"favorite": True, "expected_revision": 0},
                          headers=authenticated | {"Idempotency-Key": "request-1"})
    assert response.status_code == 503
    assert events == ["rollback"]
