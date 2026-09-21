"""D01/D02/D04/D07-D09/D11 real PostgreSQL and in-process HTTP acceptance.

Run only with EID_RUN_LIVE_TESTS=1 and the explicit guarded remote selector.
Authentication is injected with a synthetic subject for private-schema HTTP
tests; real OIDC/deployed-browser evidence is deliberately not claimed here.
Ordinary schemas roll back; committed concurrency schemas have retained owner
receipts and are never dropped, reset, or reused by a subsequent run.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from threading import Barrier, Event
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from edw_api import main
from edw_api.access import repository as access
from edw_api.access.policy import AccessDenied, authorize
from edw_api.discovery import repository, routes
from edw_api.discovery.schemas import FavoriteCommand, Filters, RestoreCommand, SearchRequest
from edw_api.errors import ApiError
from tests.ops.discovery_live_support import as_role, fresh_connection, isolated_store

pytestmark = pytest.mark.skipif(os.getenv("EID_RUN_LIVE_TESTS") != "1",
    reason="Explicit guarded remote PostgreSQL acceptance required; not local/mock evidence")


@pytest.fixture
def store():
    with isolated_store() as value:
        yield value


@pytest.fixture
def durable_store():
    with isolated_store(durable=True) as value:
        yield value


def command(conn, store, *, label="document", role="author", favorite=True,
            revision=0, key="test-command", restore=False, environment="isolated_development"):
    body = RestoreCommand(expected_revision=revision, policy_version=store.declared["policy_version"]) if restore else \
           FavoriteCommand(favorite=favorite, expected_revision=revision)
    return repository.collection_command(conn, store.subject(role), store.workspace,
        store.resource(label), body, action="restore_visibility" if restore else "favorite.set",
        idempotency_key=key, request_id="live-discovery", trace_id="d" * 32, environment=environment)


def make_http(monkeypatch, store, role="author"):
    monkeypatch.setattr(main.verifier, "verify", lambda _token: SimpleNamespace(subject=store.subject(role)))
    monkeypatch.setattr(main.settings, "discovery_policy_environment", "isolated_development")
    @contextmanager
    def connection(_settings):
        with store.conn.transaction():
            as_role(store.conn, "eid_api")
            yield store.conn
    monkeypatch.setattr(routes, "connection", connection)
    return TestClient(main.app), {"Authorization": "Bearer injected-private-schema-subject",
                                "X-Request-ID": "live-discovery", "traceparent": "00-" + "d" * 32 + "-" + "a" * 16 + "-01"}


def prefix(store, project="a"):
    return "/api/v1/workspaces/" + store.declared["workspaces"][project]


def reference_ids(store, role="author", filters=None):
    """Independent Python selection calls existing authorize for every resource."""
    conn = store.conn
    filters = filters or Filters(limit=50)
    facts, _, _ = access.checked(conn, store.subject(role), store.workspace)
    resources = conn.execute("SELECT r.*,d.created_by,d.lifecycle,d.visibility,d.document_type,"
        "d.updated_at,d.kind AS discovery_kind FROM access_resource r "
        "JOIN discovery_record d ON d.resource_id=r.id WHERE r.workspace_id=%s", (store.workspace,)).fetchall()
    participants = {str(row["resource_id"]) for row in conn.execute(
        "SELECT resource_id FROM discovery_participant WHERE identity_id=%s", (store.actor(role),)).fetchall()}
    favorites = {str(row["resource_id"]) for row in conn.execute(
        "SELECT resource_id FROM discovery_favorite WHERE actor_id=%s AND active", (store.actor(role),)).fetchall()}
    allowed = []
    for row in resources:
        try:
            authorize(facts, "resource:read", row)
        except AccessDenied:
            continue
        if row["visibility"] != filters.visibility or row["discovery_kind"] != row["kind"]:
            continue
        if any(getattr(filters, field) is not None and row[field] != getattr(filters, field)
               for field in ("kind", "document_type", "lifecycle")):
            continue
        if filters.collection == "references" and row["kind"] not in {"knowledge", "reference"}:
            continue
        if filters.collection == "todo" and not (
            row["kind"] == "document" and row["lifecycle"] == "DRAFT" and row["visibility"] == "visible"
            and str(row["owner_id"]) == store.actor(role) and "author" in facts["roles"]
        ):
            continue
        rid = str(row["id"])
        if filters.tab == "created" and str(row["created_by"]) != store.actor(role):
            continue
        if filters.tab == "participating" and rid not in participants:
            continue
        if filters.tab == "favorites" and rid not in favorites:
            continue
        allowed.append(row)
    return [str(row["id"]) for row in sorted(allowed, key=lambda row: (row["updated_at"], row["id"]), reverse=True)]


@pytest.mark.parametrize("role", ["author", "expert", "quality", "template_admin", "knowledge_admin", "approver", "system_admin"])
def test_D01_authorized_projection_matrix_matches_authorize_and_api(store, monkeypatch, role):
    conn = store.conn
    as_role(conn, "eid_api")
    expected = reference_ids(store, role)
    client, headers = make_http(monkeypatch, store, role)
    response = client.get(prefix(store) + "/discovery", params={"limit": 50}, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [item["id"] for item in data["items"]] == expected
    assert data["total_count"] == len(expected) > 20
    assert data["context"]["actor_id"] == store.actor(role)
    for label in ("classified", "expired", "future", "foreign-project", "foreign-customer",
                  "foreign-product", "foreign-department", "invalid-approval"):
        assert store.resource(label) not in response.text
        assert f" · {label}" not in response.text
    forbidden = client.get(prefix(store) + "/discovery/" + store.resource("classified"), headers=headers)
    unknown = client.get(prefix(store) + "/discovery/" + str(uuid4()), headers=headers)
    assert forbidden.status_code == unknown.status_code == 403
    assert forbidden.json() == unknown.json()
    other_project = client.get(prefix(store, "b") + "/discovery", headers=headers).json()["data"]
    assert [item["id"] for item in other_project["items"]] == [store.resource(project="b")]


@pytest.mark.parametrize("change", ["identity", "membership", "expired", "future", "invalid-role", "clearance", "workspace-scope"])
def test_D01_inactive_expired_and_invalid_current_facts_deny_all_reads(store, monkeypatch, change):
    conn = store.conn
    if change == "identity":
        conn.execute("UPDATE identity_account SET active=false WHERE id=%s", (store.actor(),))
    elif change == "membership":
        conn.execute("UPDATE workspace_membership SET active=false WHERE identity_id=%s AND workspace_id=%s",
                     (store.actor(), store.workspace))
    else:
        updates = {
            "expired": "valid_until=CURRENT_TIMESTAMP-interval '1 day'",
            "future": "valid_from=CURRENT_TIMESTAMP+interval '1 hour'",
            "invalid-role": "roles=ARRAY['invented-admin']",
            "clearance": "clearance=0", "workspace-scope": "project_scope=ARRAY['foreign']",
        }
        conn.execute("UPDATE access_member SET " + updates[change] + " WHERE identity_id=%s AND workspace_id=%s",
                     (store.actor(), store.workspace))
    client, headers = make_http(monkeypatch, store)
    for path in ("/discovery", "/discovery/summary", "/discovery/" + store.resource()):
        response = client.get(prefix(store) + path, headers=headers)
        assert response.status_code == 403
        assert store.resource() not in response.text


def test_D01_owner_scope_is_current_and_system_admin_has_no_attribute_bypass(store):
    conn = store.conn
    conn.execute("UPDATE access_member SET owner_scope='self' WHERE identity_id=%s AND workspace_id=%s",
                 (store.actor(), store.workspace))
    as_role(conn, "eid_api")
    data = repository.list_records(conn, store.subject(), store.workspace, Filters(limit=50))
    assert [item["id"] for item in data["items"]] == reference_ids(store)
    assert store.resource("other-owner") not in [item["id"] for item in data["items"]]
    admin = repository.list_records(conn, store.subject("system_admin"), store.workspace, Filters(limit=50))
    assert store.resource("classified") not in [item["id"] for item in admin["items"]]


def test_D01_unregistered_or_kind_mismatched_access_resources_are_not_discoverable(store):
    conn = store.conn
    bare = uuid4()
    conn.execute("INSERT INTO access_resource SELECT %s,workspace_id,'仅权限资源','local-policy-fixture',"
        "project_id,customer_id,product_id,department,owner_id,classification,approval_state,"
        "publication_state,head_ref,policy_epoch,valid_from,valid_until FROM access_resource WHERE id=%s",
        (bare, store.resource()))
    conn.execute("UPDATE access_resource SET kind='local-policy-fixture' WHERE id=%s", (store.resource("reference"),))
    as_role(conn, "eid_api")
    result = repository.list_records(conn, store.subject(), store.workspace, Filters(limit=50))
    ids = [item["id"] for item in result["items"]]
    assert str(bare) not in ids and store.resource("reference") not in ids
    for rid in (bare, store.resource("reference")):
        with pytest.raises(AccessDenied):
            repository.detail(conn, store.subject(), store.workspace, rid, environment="isolated_development")


def test_D02_tabs_filters_counts_and_search_intersections(store):
    conn = store.conn
    as_role(conn, "eid_api")
    command(conn, store, label="other-owner", key="favorite-other")
    command(conn, store, label="reference", key="favorite-reference")
    for tab in ("recent", "created", "participating", "favorites"):
        for extra in ({}, {"kind": "document"}, {"kind": "document", "document_type": "technical", "lifecycle": "DRAFT"},
                      {"kind": "reference"}, {"document_type": "proposal"}, {"collection": "todo"},
                      {"collection": "references"}, {"collection": "references", "kind": "knowledge"},
                      {"collection": "references", "kind": "document"},
                      {"collection": "todo", "visibility": "recycled"}):
            filters = Filters(tab=tab, limit=50, **extra)
            expected = reference_ids(store, filters=filters)
            data = repository.list_records(conn, store.subject(), store.workspace, filters)
            assert [item["id"] for item in data["items"]] == expected
            assert data["total_count"] == len(expected)
    result = repository.search_records(conn, store.subject(), store.workspace,
        SearchRequest(query="other-owner", tab="favorites", kind="document"))
    assert [item["id"] for item in result["items"]] == [store.resource("other-owner")]
    assert result["total_count"] == 1
    empty = repository.search_records(conn, store.subject(), store.workspace,
        SearchRequest(query="not-a-real-title"))
    assert empty["items"] == [] and empty["total_count"] == 0 and empty["functions"] == []


def test_D02_todo_is_current_owned_editable_and_references_include_both_kinds(store, monkeypatch):
    conn = store.conn
    # Both counterexamples exist only in this test's new, rolled-back schema.
    conn.execute("UPDATE discovery_record SET created_by=%s WHERE resource_id=%s", (store.actor("expert"), store.resource()))
    conn.execute("UPDATE discovery_record SET created_by=%s WHERE resource_id=%s", (store.actor(), store.resource("other-owner")))
    client, headers = make_http(monkeypatch, store)
    todo = client.get(prefix(store) + "/discovery", params={"collection": "todo", "limit": 50}, headers=headers)
    assert todo.status_code == 200, todo.text
    todo = todo.json()["data"]
    ids = [row["id"] for row in todo["items"]]
    assert store.resource() in ids and store.resource("other-owner") not in ids
    assert ids == reference_ids(store, filters=Filters(collection="todo", limit=50))
    created = client.get(prefix(store) + "/discovery", params={"tab": "created", "collection": "todo", "limit": 50}, headers=headers).json()["data"]
    assert store.resource() not in [row["id"] for row in created["items"]]
    summary = client.get(prefix(store) + "/discovery/summary", headers=headers).json()["data"]
    assert summary["todo_count"] == todo["total_count"]
    references = client.get(prefix(store) + "/discovery", params={"collection": "references", "limit": 50}, headers=headers).json()["data"]
    assert {row["kind"] for row in references["items"]} == {"knowledge", "reference"}
    assert {row["id"] for row in references["items"]} == {store.resource("knowledge"), store.resource("reference")}
    denied_intersection = client.get(prefix(store) + "/discovery", params={"collection": "references", "kind": "document"}, headers=headers).json()["data"]
    assert denied_intersection["items"] == [] and denied_intersection["total_count"] == 0
    as_role(conn, "eid_api")
    expert_todo = repository.list_records(conn, store.subject("expert"), store.workspace, Filters(collection="todo"))
    assert expert_todo["items"] == [] and expert_todo["total_count"] == 0


def test_D04_cursor_stable_ties_last_page_and_foreign_context_rejection(store):
    conn = store.conn
    as_role(conn, "eid_api")
    expected = reference_ids(store)
    seen, cursor, first_cursor = [], None, None
    for _ in range(20):
        data = repository.list_records(conn, store.subject(), store.workspace, Filters(limit=3, cursor=cursor))
        assert data["total_count"] == len(expected) and 0 < len(data["items"]) <= 3
        seen.extend(item["id"] for item in data["items"])
        cursor = data["next_cursor"]
        first_cursor = first_cursor or cursor
        if cursor is None:
            break
    assert cursor is None and seen == expected and len(seen) == len(set(seen))
    assert first_cursor
    for subject, workspace, filters in (
        (store.subject(), store.workspace, Filters(limit=3, tab="created", cursor=first_cursor)),
        (store.subject(), store.workspace, Filters(limit=3, collection="references", cursor=first_cursor)),
        (store.subject("expert"), store.workspace, Filters(limit=3, cursor=first_cursor)),
        (store.subject(), store.declared["workspaces"]["b"], Filters(limit=3, cursor=first_cursor)),
        (store.subject(), store.workspace, Filters(limit=3, cursor="malformed")),
    ):
        with pytest.raises(ApiError) as error:
            repository.list_records(conn, subject, workspace, filters)
        assert error.value.code == "INVALID_CURSOR" and error.value.status_code == 422
    as_role(conn, "eid_migrator")
    conn.execute("UPDATE access_workspace SET policy_epoch=policy_epoch+1 WHERE workspace_id=%s", (store.workspace,))
    as_role(conn, "eid_api")
    with pytest.raises(ApiError, match="INVALID_CURSOR"):
        repository.list_records(conn, store.subject(), store.workspace, Filters(limit=3, cursor=first_cursor))


def test_D07_favorites_are_private_revisioned_and_replay_returns_current_state(store, monkeypatch):
    conn = store.conn
    client, headers = make_http(monkeypatch, store)
    path = prefix(store) + "/favorites/" + store.resource()
    body = {"favorite": True, "expected_revision": 0}
    first = client.put(path, json=body, headers=headers | {"Idempotency-Key": "favorite-1"})
    assert first.status_code == 200, first.text
    first = first.json()["data"]
    assert first["current"]["favorite"] is True and first["current"]["favorite_revision"] == 1
    again = client.put(path, json=body, headers=headers | {"Idempotency-Key": "favorite-1"}).json()["data"]
    assert again["replayed"] is True and again["operation_id"] == first["operation_id"]
    removed = client.put(path, json={"favorite": False, "expected_revision": 1},
                         headers=headers | {"Idempotency-Key": "favorite-2"})
    assert removed.status_code == 200
    replay = client.put(path, json=body, headers=headers | {"Idempotency-Key": "favorite-1"}).json()["data"]
    assert replay["current"]["favorite"] is False and replay["current"]["favorite_revision"] == 2
    assert replay["operation_id"] == first["operation_id"]
    conflict = client.put(path, json={"favorite": False, "expected_revision": 0},
                          headers=headers | {"Idempotency-Key": "favorite-1"})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # Same key with a different target is also a conflict within this actor/workspace.
    target_conflict = client.put(prefix(store) + "/favorites/" + store.resource("reference"),
                                 json=body, headers=headers | {"Idempotency-Key": "favorite-1"})
    assert target_conflict.status_code == 409
    as_role(conn, "eid_api")
    other = repository.detail(conn, store.subject("expert"), store.workspace, store.resource(),
                              environment="isolated_development")
    assert other["item"]["favorite"] is False and other["item"]["favorite_revision"] == 0
    as_role(conn, "eid_migrator")
    assert conn.execute("SELECT count(*) AS n FROM discovery_receipt").fetchone()["n"] == 2
    assert conn.execute("SELECT count(*) AS n FROM access_audit WHERE action='favorite.set'").fetchone()["n"] == 2
    audit = conn.execute("SELECT * FROM access_audit WHERE id=%s", (first["operation_id"],)).fetchone()
    assert audit["before_policy"] == {"favorite": False, "revision": 0}
    assert audit["after_policy"]["favorite"] is True and audit["after_policy"]["revision"] == 1
    assert audit["request_id"] == "live-discovery" and audit["trace_id"] == "d" * 32


@pytest.mark.parametrize("restore", [False, True])
def test_D09_current_authorization_rechecked_before_successful_receipt_replay(store, restore):
    conn = store.conn
    as_role(conn, "eid_api")
    args = {"label": "recycled", "restore": True, "revision": 1} if restore else {}
    first = command(conn, store, **args)
    as_role(conn, "eid_migrator")
    conn.execute("UPDATE workspace_membership SET active=false WHERE workspace_id=%s AND identity_id=%s",
                 (store.workspace, store.actor()))
    as_role(conn, "eid_api")
    with pytest.raises(AccessDenied):
        command(conn, store, **args)
    as_role(conn, "eid_migrator")
    assert conn.execute("SELECT operation_id FROM discovery_receipt").fetchone()["operation_id"] == \
           uuid_from(first["operation_id"])
    assert conn.execute("SELECT count(*) AS n FROM access_audit").fetchone()["n"] == 1


def uuid_from(value):
    from uuid import UUID
    return UUID(value)


def test_D08_restore_changes_visibility_only_and_uses_current_policy(store, monkeypatch):
    conn = store.conn
    resource_before = conn.execute("SELECT * FROM access_resource WHERE id=%s", (store.resource("recycled"),)).fetchone()
    before = conn.execute("SELECT * FROM discovery_record WHERE resource_id=%s", (store.resource("recycled"),)).fetchone()
    client, headers = make_http(monkeypatch, store)
    path = prefix(store) + "/recycle/" + store.resource("recycled") + ":restore"
    body = {"expected_revision": 1, "policy_version": store.declared["policy_version"]}
    response = client.post(path, json=body, headers=headers | {"Idempotency-Key": "restore-1"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["current"]["visibility"] == "visible"
    assert response.json()["data"]["current"]["lifecycle"] == "ARCHIVED"
    as_role(conn, "eid_migrator")
    after = conn.execute("SELECT * FROM discovery_record WHERE resource_id=%s", (store.resource("recycled"),)).fetchone()
    assert {key: value for key, value in after.items() if key not in {"visibility", "revision", "updated_at"}} == \
           {key: value for key, value in before.items() if key not in {"visibility", "revision", "updated_at"}}
    assert after["revision"] == 2
    assert conn.execute("SELECT * FROM access_resource WHERE id=%s", (store.resource("recycled"),)).fetchone() == resource_before
    replay = client.post(path, json=body, headers=headers | {"Idempotency-Key": "restore-1"})
    assert replay.status_code == 200 and replay.json()["data"]["replayed"] is True


@pytest.mark.parametrize("failure", ["missing-policy", "inactive", "expired", "future", "owner", "type", "role",
    "production", "owner-marker", "version-marker", "stale-policy", "stale-revision", "wrong-workspace"])
def test_D08_restore_policy_denials_leave_state_receipt_and_audit_unchanged(store, failure):
    conn = store.conn
    label, role, environment, revision = "recycled", "author", "isolated_development", 1
    if failure == "missing-policy":
        # Private uncommitted schema only: move this new policy to an extra owned workspace.
        wid = str(uuid4())
        conn.execute("INSERT INTO workspace(id,slug,name) VALUES (%s,%s,'无策略反例')", (wid, "no-policy-" + uuid4().hex))
        conn.execute("INSERT INTO access_workspace SELECT %s,tenant_id,project_id,customer_id,product_id,department,classification,1 "
                     "FROM access_workspace WHERE workspace_id=%s", (wid, store.workspace))
        conn.execute("UPDATE discovery_restore_policy SET workspace_id=%s WHERE workspace_id=%s", (wid, store.workspace))
    elif failure in {"inactive", "expired", "future", "owner-marker", "version-marker", "stale-policy"}:
        updates = {"inactive": "active=false", "expired": "valid_until=CURRENT_TIMESTAMP-interval '1 day'",
            "future": "valid_from=CURRENT_TIMESTAMP+interval '1 day'", "owner-marker": "fixture_owner='foreign'",
            "version-marker": "fixture_version='different'", "stale-policy": "version='policy-replaced'"}
        conn.execute("UPDATE discovery_restore_policy SET " + updates[failure] + " WHERE workspace_id=%s", (store.workspace,))
    elif failure == "owner":
        label = "recycled-other-owner"
    elif failure == "type":
        label = "recycled-knowledge"
    elif failure == "role":
        # Expert owns this record but has no document:edit operation.
        label, role = "recycled-other-owner", "expert"
    elif failure == "production":
        environment = "production"
    elif failure == "stale-revision":
        revision = 2
    elif failure == "wrong-workspace":
        conn.execute("UPDATE access_resource SET workspace_id=%s WHERE id=%s",
                     (store.declared["workspaces"]["b"], store.resource(label)))
    before = conn.execute("SELECT * FROM discovery_record WHERE resource_id=%s", (store.resource(label),)).fetchone()
    as_role(conn, "eid_api")
    with pytest.raises(ApiError if failure in {"stale-policy", "stale-revision"} else AccessDenied):
        command(conn, store, label=label, role=role, restore=True, revision=revision, environment=environment)
    as_role(conn, "eid_migrator")
    assert conn.execute("SELECT * FROM discovery_record WHERE resource_id=%s", (store.resource(label),)).fetchone() == before
    assert conn.execute("SELECT count(*) AS n FROM discovery_receipt").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM access_audit").fetchone()["n"] == 0


@pytest.mark.parametrize("restore", [False, True])
def test_D09_audit_failure_is_http503_and_rolls_back_entire_command(store, monkeypatch, restore):
    conn = store.conn
    conn.execute("ALTER TABLE access_audit ADD CONSTRAINT reject_discovery_audit CHECK (false)")
    label = "recycled" if restore else "document"
    before = conn.execute("SELECT * FROM discovery_record WHERE resource_id=%s", (store.resource(label),)).fetchone()
    client, headers = make_http(monkeypatch, store)
    if restore:
        response = client.post(prefix(store) + "/recycle/" + store.resource(label) + ":restore",
            json={"expected_revision": 1, "policy_version": store.declared["policy_version"]},
            headers=headers | {"Idempotency-Key": "audit-failure"})
    else:
        response = client.put(prefix(store) + "/favorites/" + store.resource(label),
            json={"favorite": True, "expected_revision": 0}, headers=headers | {"Idempotency-Key": "audit-failure"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "POLICY_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True
    as_role(conn, "eid_migrator")
    assert conn.execute("SELECT * FROM discovery_record WHERE resource_id=%s", (store.resource(label),)).fetchone() == before
    for table in ("discovery_receipt", "discovery_favorite", "access_audit"):
        assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0


def test_D11_filtered_count_and_storage_use_actual_postgresql_bytes_once(store):
    conn = store.conn
    # A second participant must not multiply storage/count through joins.
    conn.execute("INSERT INTO discovery_participant(resource_id,identity_id) VALUES (%s,%s)",
                 (store.resource(), store.actor("expert")))
    as_role(conn, "eid_api")
    command(conn, store, key="storage-favorite")
    for filters in (Filters(limit=2), Filters(tab="participating", limit=2),
                    Filters(tab="favorites"), Filters(visibility="recycled"), Filters(kind="reference"),
                    Filters(collection="todo", limit=2), Filters(collection="references", limit=1)):
        ids = reference_ids(store, filters=filters)
        expected = conn.execute("SELECT coalesce(sum(pg_column_size(d)+pg_column_size(r.title)),0)::bigint AS bytes "
            "FROM discovery_record d JOIN access_resource r ON r.id=d.resource_id WHERE d.resource_id=ANY(%s::uuid[])",
            (ids,)).fetchone()["bytes"]
        data = repository.list_records(conn, store.subject(), store.workspace, filters)
        summary = repository.summary(conn, store.subject(), store.workspace, filters)
        assert data["total_count"] == summary["total_count"] == len(ids)
        assert data["storage"]["metadata_bytes"] == summary["storage"]["metadata_bytes"] == expected
        assert data["storage"]["definition"] == "pg_column_size(discovery_record)+pg_column_size(access_resource.title)"
        assert data["storage"]["visibility"] == filters.visibility
        assert data["storage"]["quota_bytes"] is None and data["storage"]["attachment_bytes"] is None
        assert data["storage"]["measured_at"].tzinfo is not None
        assert all(panel["value"] is None and panel["reason"] and panel["owner"] for panel in summary["future_panels"])


def test_database_roles_reject_worker_new_tables_and_api_business_mutations(store):
    conn = store.conn
    tables = ("discovery_record", "discovery_participant", "discovery_favorite", "discovery_restore_policy", "discovery_receipt")
    as_role(conn, "eid_worker")
    for table in tables:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert conn.execute("SELECT has_table_privilege(current_user,%s,%s) AS allowed", (table, privilege)).fetchone()["allowed"] is False
        for statement in (f"SELECT * FROM {table}", f"INSERT INTO {table} DEFAULT VALUES", f"UPDATE {table} SET " +
                          ("actor_id=actor_id" if table in {"discovery_favorite", "discovery_receipt"} else
                           "workspace_id=workspace_id" if table == "discovery_restore_policy" else "resource_id=resource_id") + " WHERE false"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute(statement)
    as_role(conn, "eid_api")
    for statement in ("UPDATE discovery_record SET lifecycle='ARCHIVED' WHERE false",
                      "UPDATE discovery_record SET fixture_owner='foreign' WHERE false",
                      "UPDATE discovery_record SET created_by=created_by WHERE false",
                      "UPDATE discovery_restore_policy SET active=true WHERE false",
                      "INSERT INTO discovery_record DEFAULT VALUES",
                      "INSERT INTO discovery_participant DEFAULT VALUES",
                      "SELECT * FROM access_audit", "UPDATE access_resource SET head_ref=NULL WHERE false"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
            conn.execute(statement)


@pytest.mark.parametrize("mode", ["same-key", "different-keys", "different-payload", "restore"])
def test_D09_real_two_connection_commands_serialize_and_keep_receipts_consistent(durable_store, mode):
    store = durable_store
    barrier = Barrier(2, timeout=5)
    def invoke(index):
        try:
            with fresh_connection(store) as conn:
                barrier.wait()
                result = command(conn, store,
                    key=f"race-{index}" if mode in {"different-keys", "restore"} else "race-same",
                    favorite=index == 0 if mode == "different-payload" else True,
                    label="recycled" if mode == "restore" else "document",
                    revision=1 if mode == "restore" else 0, restore=mode == "restore")
            return (200, result)
        except ApiError as error:
            return (error.status_code, error.code)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke, index) for index in (0, 1)]
        results = [future.result(timeout=20) for future in futures]
    if mode == "same-key":
        assert [status for status, _ in results] == [200, 200]
        assert results[0][1]["operation_id"] == results[1][1]["operation_id"]
        assert sorted(result["replayed"] for _, result in results) == [False, True]
    else:
        assert sorted(status for status, _ in results) == [200, 409]
        assert [result for status, result in results if status == 409] == [
            "IDEMPOTENCY_CONFLICT" if mode == "different-payload" else "REVISION_CONFLICT"]
    with fresh_connection(store, "eid_migrator") as conn:
        assert conn.execute("SELECT count(*) AS n FROM discovery_receipt").fetchone()["n"] == 1
        assert conn.execute("SELECT count(*) AS n FROM access_audit").fetchone()["n"] == 1
        missing = conn.execute("SELECT count(*) AS n FROM discovery_receipt r LEFT JOIN access_audit a "
                              "ON a.id=r.operation_id WHERE a.id IS NULL").fetchone()["n"]
        assert missing == 0
        if mode == "restore":
            row = conn.execute("SELECT visibility,revision,lifecycle FROM discovery_record WHERE resource_id=%s",
                               (store.resource("recycled"),)).fetchone()
            assert row == {"visibility": "visible", "revision": 2, "lifecycle": "ARCHIVED"}
        else:
            assert conn.execute("SELECT revision FROM discovery_favorite").fetchone()["revision"] == 1


def test_D09_revocation_wins_before_waiting_command_and_replay(durable_store):
    store = durable_store
    with fresh_connection(store) as conn:
        command(conn, store, key="before-revoke")
    ready = Event()
    state = {}
    def blocked_command():
        try:
            with fresh_connection(store) as conn:
                state["pid"] = conn.info.backend_pid
                ready.set()
                return command(conn, store, key="before-revoke")
        except AccessDenied:
            return "denied"
    with ThreadPoolExecutor(max_workers=1) as pool:
        with fresh_connection(store, "eid_migrator") as writer:
            writer.execute("SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR UPDATE", (store.workspace,))
            writer.execute("UPDATE workspace_membership SET active=false WHERE identity_id=%s AND workspace_id=%s",
                           (store.actor(), store.workspace))
            writer.execute("UPDATE access_workspace SET policy_epoch=policy_epoch+1 WHERE workspace_id=%s", (store.workspace,))
            future = pool.submit(blocked_command)
            assert ready.wait(5)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                blockers = writer.execute("SELECT pg_blocking_pids(%s) AS pids", (state["pid"],)).fetchone()["pids"]
                if writer.info.backend_pid in blockers:
                    break
                time.sleep(0.02)
            else:
                pytest.fail("Did not observe the command waiting on the actual PostgreSQL workspace lock")
        assert future.result(timeout=10) == "denied"
    with fresh_connection(store, "eid_migrator") as conn:
        assert conn.execute("SELECT count(*) AS n FROM discovery_receipt").fetchone()["n"] == 1
        assert conn.execute("SELECT count(*) AS n FROM access_audit").fetchone()["n"] == 1


def test_D07_committed_state_is_visible_on_new_api_connection_and_worker_credentials_deny(durable_store):
    store = durable_store
    with fresh_connection(store) as conn:
        result = command(conn, store, key="persisted")
    with fresh_connection(store) as conn:
        detail = repository.detail(conn, store.subject(), store.workspace, store.resource(), environment="isolated_development")
        assert detail["item"]["favorite"] is True and detail["item"]["favorite_revision"] == 1
        replay = command(conn, store, key="persisted")
        assert replay["operation_id"] == result["operation_id"] and replay["replayed"] is True
    with fresh_connection(store, "eid_worker") as conn:
        assert conn.execute("SELECT session_user AS name").fetchone()["name"] == "eid_worker"
        for table in ("discovery_record", "discovery_participant", "discovery_favorite", "discovery_restore_policy", "discovery_receipt"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute(f"SELECT * FROM {table}")


def test_D04_large_page_encoding_stays_bounded(store):
    conn = store.conn
    conn.execute("UPDATE access_resource SET title=repeat('测',512) WHERE workspace_id=%s", (store.workspace,))
    as_role(conn, "eid_api")
    result = repository.list_records(conn, store.subject(), store.workspace, Filters(limit=50))
    assert len(result["items"]) <= 50
    size = sum(len(json.dumps(item, ensure_ascii=False).encode()) for item in result["items"])
    assert size <= repository.MAX_PAGE_BYTES and result["next_cursor"]
    next_page = repository.list_records(conn, store.subject(), store.workspace, Filters(limit=50, cursor=result["next_cursor"]))
    assert {item["id"] for item in result["items"]}.isdisjoint(item["id"] for item in next_page["items"])
    assert len(result["items"]) + len(next_page["items"]) == result["total_count"]


def test_D10_home_week_window_uses_current_actual_records(store):
    conn = store.conn
    as_role(conn, "eid_api")
    database_before = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    result = repository.summary(conn, store.subject(), store.workspace, Filters())
    database_after = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    window = result["week_new_documents"]
    # evaluated_at is a database clock_timestamp, not the client workstation clock.
    assert database_before <= window["window_end"] <= database_after
    utc_end = window["window_end"].astimezone(timezone.utc)
    assert window["window_start"] == (utc_end - timedelta(days=utc_end.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    expected = reference_ids(store, filters=Filters(kind="document"))
    created = {row["resource_id"]: datetime.fromisoformat(row["created_at"])
               for row in store.declared["rows"]["discovery_record"]}
    assert result["week_new_documents"]["value"] == sum(
        result["week_new_documents"]["window_start"] <= created[rid] <= result["week_new_documents"]["window_end"]
        for rid in expected)
    assert result["workspace"]["id"] == store.workspace
    assert all(panel["value"] is None for panel in result["future_panels"])
