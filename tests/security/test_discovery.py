"""D04/D07–D09 的纯授权、游标与事务编排回归；不替代现场 PG 证据。"""
from contextlib import contextmanager
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import psycopg
import pytest

from edw_api.access.policy import AccessDenied, authorize
from edw_api.discovery import repository
from edw_api.discovery.policy import authorize_restore
from edw_api.discovery.schemas import FavoriteCommand, Filters, RestoreCommand, SearchRequest
from edw_api.errors import ApiError

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)
AID = UUID("11111111-1111-4111-8111-111111111111")
WID = UUID("22222222-2222-4222-8222-222222222222")
RID = UUID("33333333-3333-4333-8333-333333333333")
OTHER = UUID("44444444-4444-4444-8444-444444444444")
DATABASE = {"database_name": "eid_local_dev", "marker": "eid-local-dev-v1"}


@pytest.fixture
def facts():
    return {"actor_id": AID, "identity_active": True, "membership_active": True,
            "roles": ["author"], "workspace_id": WID, "tenant_id": WID,
            "project_id": "p", "customer_id": "c", "product_id": "x", "department": "d",
            "project_scope": ["p"], "customer_scope": ["c"], "product_scope": ["x"],
            "department_scope": ["d"], "owner_scope": "any", "approval_states": ["draft"],
            "classification": 1, "clearance": 2, "valid_from": NOW-timedelta(days=1),
            "valid_until": NOW+timedelta(days=1), "evaluated_at": NOW,
            "policy_epoch": 3, "workspace_epoch": 5}


@pytest.fixture
def resource(facts):
    return {key: facts[key] for key in ("workspace_id", "project_id", "customer_id", "product_id",
                                      "department", "classification", "valid_from", "valid_until")} | {
        "id": RID, "owner_id": AID, "kind": "document", "title": "可见记录",
        "approval_state": "draft", "policy_epoch": 7, "head_ref": OTHER,
        "publication_state": "unpublished"}


@pytest.fixture
def record(resource):
    return {"resource_id": RID, "workspace_id": WID, "title": resource["title"],
            "resource_epoch": 7, "kind": "document", "created_by": AID,
            "created_at": NOW-timedelta(days=1), "updated_at": NOW,
            "document_type": "technical", "lifecycle": "ARCHIVED", "version_label": "来源v1",
            "visibility": "recycled", "revision": 1, "fixture_owner": "story-1.3",
            "fixture_version": "1", "favorite": False, "favorite_revision": 0,
            "participating": False}


@pytest.fixture
def policy():
    return {"workspace_id": WID, "kind": "document", "version": "restore-1",
            "action": "restore_visibility", "required_operation": "document:edit",
            "owner_only": True, "environment_class": "isolated_development",
            "fixture_owner": "story-1.3", "fixture_version": "1", "active": True,
            "valid_from": NOW-timedelta(days=1), "valid_until": NOW+timedelta(days=1)}


def restore(facts, resource, record, policy, environment="isolated_development", database=DATABASE):
    return authorize_restore(facts, resource, record, policy, environment=environment,
                             database_identity=database)


def test_explicit_owned_development_policy_uses_current_production_authorize(facts, resource, record, policy):
    assert restore(facts, resource, record, policy) == authorize(facts, "resource:read", resource)


@pytest.mark.parametrize("field,value", [
    ("workspace_id", OTHER), ("kind", "knowledge"), ("action", "delete"),
    ("required_operation", "workspace:read"), ("owner_only", False), ("active", False),
    ("environment_class", "production"), ("fixture_owner", "other"), ("fixture_version", "2"),
    ("valid_from", NOW+timedelta(seconds=1)), ("valid_until", NOW), ("version", ""),
])
def test_policy_missing_or_invalid_never_grants_restore(facts, resource, record, policy, field, value):
    policy[field] = value
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, policy)
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, None)


@pytest.mark.parametrize("field,value", [
    ("membership_active", False), ("identity_active", False), ("roles", ["system_admin"]),
    ("roles", []), ("project_scope", []), ("approval_states", []), ("clearance", 0),
    ("valid_until", NOW),
])
def test_restore_has_no_admin_or_historical_authorization_bypass(facts, resource, record, policy, field, value):
    restore(facts, resource, record, policy)
    facts[field] = value
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, policy)


@pytest.mark.parametrize("field,value", [("owner_id", OTHER), ("kind", "reference"),
                                        ("classification", 3), ("valid_until", NOW)])
def test_record_current_attributes_limit_restore(facts, resource, record, policy, field, value):
    resource[field] = value
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, policy)


@pytest.mark.parametrize("database", [None, {}, DATABASE | {"database_name": "enterprise"},
                                    DATABASE | {"marker": None}])
def test_environment_flag_never_substitutes_for_actual_database(facts, resource, record, policy, database):
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, policy, database=database)


def test_real_mode_requires_real_policy_and_rejects_fixture_policy(facts, resource, record, policy):
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, policy, environment="production")
    policy.update(environment_class="production", fixture_owner=None, fixture_version=None)
    with pytest.raises(AccessDenied):
        restore(facts, resource, record, policy, environment="production")
    record.update(fixture_owner=None, fixture_version=None)
    assert restore(facts, resource, record, policy, environment="production")


def test_cursor_binds_filters_identity_scope_epoch_and_page_size(facts, record):
    filters = Filters()
    context = authorize(facts, "workspace:read")
    binding = repository._binding(facts, context, filters, None)
    item = repository.item_payload(record)
    cursor = repository.encode_cursor(item, binding)
    assert repository.decode_cursor(cursor, binding) == (NOW, RID)
    for changed in (Filters(tab="created"), Filters(visibility="recycled"), Filters(limit=1),
                    Filters(kind="reference"), Filters(lifecycle="ARCHIVED"),
                    Filters(collection="todo"), Filters(collection="references")):
        other = repository._binding(facts, context, changed, None)
        with pytest.raises(ApiError) as error:
            repository.decode_cursor(cursor, other)
        assert error.value.code == "INVALID_CURSOR"
    for key, value in (("actor_id", OTHER), ("workspace_id", OTHER), ("workspace_epoch", 6),
                       ("policy_epoch", 4), ("clearance", 1)):
        changed = facts | {key: value}
        other = repository._binding(changed, authorize(changed, "workspace:read"), filters, None)
        with pytest.raises(ApiError):
            repository.decode_cursor(cursor, other)


@pytest.mark.parametrize("cursor", ["", "*", "x"*2049, "e30", "bnVsbA", "W10", "YWJj"])
def test_cursor_malformed_inputs_fail_with_safe_422(cursor):
    with pytest.raises(ApiError) as error:
        repository.decode_cursor(cursor, "binding")
    assert error.value.status_code == 422


@pytest.mark.parametrize("field,value", [("id", 4), ("id", {}), ("id", "bad"),
                                        ("at", "2026-09-18"), ("at", None), ("v", True)])
def test_cursor_inner_types_are_strictly_validated(field, value):
    payload = {"v": 1, "binding": "binding", "id": str(RID), "at": NOW.isoformat(), field: value}
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(ApiError) as error:
        repository.decode_cursor(cursor, "binding")
    assert error.value.status_code == 422


def test_query_uses_literal_search_and_one_utc_week_window(facts):
    params = repository.projection_params(facts, Filters(tab="favorites", visibility="recycled"),
                                          query="%_' OR true --")
    assert params["query"] == "%_' OR true --"
    assert params["week_start"] == datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert params["now"] == NOW
    assert params["fetch_limit"] == 21
    assert params["tab"] == "favorites" and params["visibility"] == "recycled"


def test_todo_predicate_is_defined_once_and_distinguishes_owner_from_creator():
    # 查询结构断言：作者创建但他人持有不属于待办，他人创建但当前作者持有属于待办。
    # 此处不执行 SQL；两个方向的真实行集合由 PostgreSQL 验收覆盖。
    sql = " ".join(repository.AUTHORIZED_SQL.split())
    predicate = ("(d.kind='document' AND d.lifecycle='DRAFT' AND d.visibility='visible' "
                 "AND r.owner_id=%(actor)s AND %(can_edit)s) AS is_todo")
    assert sql.count(predicate) == 1
    assert "(%(tab)s='created' AND d.created_by=%(actor)s)" in sql
    assert "(%(collection)s='todo' AND is_todo)" in sql
    assert "(SELECT count(*) FROM authorized WHERE is_todo) AS todo_count" in sql


@pytest.mark.parametrize("roles,can_edit", [
    (["author"], True), (["author", "expert"], True), (["expert"], False),
    (["system_admin"], False), (["knowledge_admin"], False),
])
def test_todo_edit_capability_comes_from_current_author_role(facts, roles, can_edit):
    facts["roles"] = roles
    authorize(facts, "workspace:read")
    params = repository.projection_params(facts, Filters(collection="todo"))
    assert params["actor"] == AID
    assert params["can_edit"] is can_edit
    assert params["collection"] == "todo"


def test_collection_and_tab_filters_precede_one_shared_aggregate_and_page():
    # 静态查询结构证明，不将替身结果当作 PostgreSQL 筛选/计量证明。
    sql = " ".join(repository.AUTHORIZED_SQL.split())
    scoped, remaining = sql.split("), authorized AS MATERIALIZED (")
    authorized, remainder = remaining.split("), page AS (")
    assert scoped.startswith("WITH scoped AS ( SELECT d.*")
    for condition in (
        "AND d.visibility=%(visibility)s",
        "AND (%(kind)s::text IS NULL OR d.kind=%(kind)s)",
        "AND (%(document_type)s::text IS NULL OR d.document_type=%(document_type)s)",
        "AND (%(lifecycle)s::text IS NULL OR d.lifecycle=%(lifecycle)s)",
        "AND (%(tab)s='recent' OR (%(tab)s='created' AND d.created_by=%(actor)s) "
        "OR (%(tab)s='favorites' AND coalesce(f.active,false)) "
        "OR (%(tab)s='participating' AND EXISTS ( SELECT 1 FROM discovery_participant p "
        "WHERE p.resource_id=d.resource_id AND p.identity_id=%(actor)s)))",
        "AND (%(query)s::text IS NULL OR strpos(lower(r.title),lower(%(query)s))>0)",
    ):
        assert condition in scoped
    assert authorized.strip() == (
        "SELECT * FROM scoped WHERE (%(collection)s='all' "
        "OR (%(collection)s='todo' AND is_todo) "
        "OR (%(collection)s='references' AND kind IN ('knowledge','reference')))")
    assert remainder.startswith(" SELECT * FROM authorized WHERE ")
    assert "(SELECT count(*) FROM authorized) AS total_count" in remainder
    assert "(SELECT coalesce(sum(metadata_bytes),0)::bigint FROM authorized) AS metadata_bytes" in remainder
    assert "(SELECT count(*) FROM authorized WHERE is_todo) AS todo_count" in remainder


@pytest.mark.parametrize("collection", ["all", "todo", "references"])
@pytest.mark.parametrize("tab", ["recent", "created", "participating", "favorites"])
def test_projection_preserves_collection_and_tab_intersection(facts, collection, tab):
    filters = Filters(collection=collection, tab=tab, kind="document", visibility="recycled",
                      lifecycle="APPROVED", document_type="technical")
    params = repository.projection_params(facts, filters, query="knowledge")
    assert {key: params[key] for key in Filters.model_fields if key not in {"limit", "cursor"}} == (
        filters.model_dump(exclude={"limit", "cursor"}))
    assert params["query"] == "knowledge"


@pytest.mark.parametrize("operation", ["list_records", "summary", "search_records"])
@pytest.mark.parametrize("collection", ["all", "todo", "references"])
def test_reads_submit_current_collection_to_same_sql_before_any_result(
        monkeypatch, facts, operation, collection):
    # 只核验入口编排；在执行边界停止，不返回伪造聚合结果冒充 SQL 证明。
    events = []
    class QueryObserved(Exception):
        pass
    class Connection:
        def execute(self, sql, params):
            events.append("query")
            assert sql is repository.AUTHORIZED_SQL
            assert params["actor"] == AID and params["workspace"] == WID
            assert params["collection"] == collection and params["tab"] == "favorites"
            assert params["kind"] == "knowledge" and params["lifecycle"] == "DRAFT"
            assert params["fetch_limit"] == (0 if operation == "summary" else 4)
            assert params["query"] == ("实际" if operation == "search_records" else None)
            raise QueryObserved()
    conn = Connection()
    def checked(connection, subject, workspace):
        assert connection is conn and subject == "verified" and workspace == WID
        events.append("current_authorization")
        return facts, None, authorize(facts, "workspace:read")
    monkeypatch.setattr(repository, "checked", checked)
    values = {"collection": collection, "tab": "favorites", "kind": "knowledge",
              "lifecycle": "DRAFT", "limit": 3}
    filters = (SearchRequest(query="实际", **values) if operation == "search_records"
               else Filters(**values))
    with pytest.raises(QueryObserved):
        getattr(repository, operation)(conn, "verified", WID, filters)
    assert events == ["current_authorization", "query"]


def test_derived_todo_and_owner_fields_are_not_returned_as_item_attributes(record):
    item = repository.item_payload(record | {"is_todo": True, "owner_id": AID})
    assert "is_todo" not in item and "owner_id" not in item


@pytest.mark.parametrize("source,target", [
    ("all", "todo"), ("todo", "references"), ("references", "all"),
])
def test_search_cursor_rejects_a_changed_collection(facts, record, source, target):
    context = authorize(facts, "workspace:read")
    filters = SearchRequest(query="知识", collection=source)
    binding = repository._binding(facts, context, filters, filters.query)
    cursor = repository.encode_cursor(repository.item_payload(record), binding)
    assert repository.decode_cursor(cursor, binding) == (NOW, RID)
    changed = filters.model_copy(update={"collection": target})
    with pytest.raises(ApiError) as error:
        repository.decode_cursor(cursor, repository._binding(facts, context, changed, changed.query))
    assert error.value.status_code == 422 and error.value.code == "INVALID_CURSOR"


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Store:
    """事务编排测试替身，不声称验证 PostgreSQL SQL 或并发锁行为。"""
    def __init__(self, record, policy):
        self.record = deepcopy(record)
        self.policy = deepcopy(policy)
        self.receipts = {}
        self.audit = []
        self.fail_audit = False

    @contextmanager
    def transaction(self):
        before = deepcopy((self.record, self.receipts, self.audit))
        try:
            yield self
        except Exception:
            self.record, self.receipts, self.audit = before
            raise

    def execute(self, sql, params=None):
        if sql == repository.RECORD_SQL:
            return Result(deepcopy(self.record))
        if sql.startswith("SELECT * FROM discovery_restore_policy"):
            return Result(self.policy)
        if sql.startswith("SELECT current_database()"):
            return Result(DATABASE)
        if sql.startswith("SELECT * FROM discovery_receipt"):
            return Result(self.receipts.get(tuple(params)))
        if "INSERT INTO discovery_favorite" in sql:
            self.record.update(favorite=params[2], favorite_revision=params[3])
        elif sql.startswith("UPDATE discovery_record"):
            self.record.update(visibility="visible", revision=self.record["revision"]+1,
                               updated_at=params[0])
        elif "INSERT INTO access_audit" in sql:
            if self.fail_audit:
                raise psycopg.OperationalError("审计故障")
            self.audit.append(params)
        elif "INSERT INTO discovery_receipt" in sql:
            self.receipts[tuple(params[:3])] = {"operation_id": params[3], "action": params[5],
                                                "payload_hash": params[6], "occurred_at": params[7]}
        else:
            pytest.fail("意外 SQL: " + sql)
        return Result(None)


@pytest.fixture
def store(monkeypatch, facts, resource, record, policy):
    def checked(conn, subject, workspace, operation, target, *, exclusive):
        assert exclusive is True
        assert subject == "verified" and workspace == WID and target == RID
        return facts, resource, authorize(facts, operation, resource)
    monkeypatch.setattr(repository, "checked", checked)
    return Store(record, policy)


def command(store, body, key="request-1", action="favorite.set"):
    with store.transaction():
        return repository.collection_command(
            store, "verified", WID, RID, body, action=action, idempotency_key=key,
            request_id="request-1", trace_id="1"*32, environment="isolated_development")


def test_favorite_replay_preserves_operation_identity_but_returns_current_state(store):
    first_body = FavoriteCommand(favorite=True, expected_revision=0)
    first = command(store, first_body)
    second = command(store, FavoriteCommand(favorite=False, expected_revision=1), key="request-2")
    replay = command(store, first_body)
    assert replay["operation_id"] == first["operation_id"] != second["operation_id"]
    assert replay["replayed"] is True
    assert replay["current"]["favorite"] is False and replay["current"]["favorite_revision"] == 2
    assert len(store.audit) == len(store.receipts) == 2


def test_replay_rechecks_current_permission_before_receipt(store, facts):
    body = FavoriteCommand(favorite=True, expected_revision=0)
    command(store, body)
    facts["membership_active"] = False
    with pytest.raises(AccessDenied):
        command(store, body)
    assert len(store.audit) == len(store.receipts) == 1


def test_same_key_different_payload_and_stale_revision_do_not_write(store):
    command(store, FavoriteCommand(favorite=True, expected_revision=0))
    for key, expected_code in (("request-1", "IDEMPOTENCY_CONFLICT"), ("request-2", "REVISION_CONFLICT")):
        with pytest.raises(ApiError) as error:
            command(store, FavoriteCommand(favorite=False, expected_revision=0), key=key)
        assert error.value.code == expected_code
    assert store.record["favorite"] is True
    assert len(store.audit) == len(store.receipts) == 1


@pytest.mark.parametrize("action", ["favorite.set", "restore_visibility"])
def test_audit_failure_does_not_leave_state_or_receipt(store, action):
    before = deepcopy(store.record)
    store.fail_audit = True
    body = (FavoriteCommand(favorite=True, expected_revision=0) if action == "favorite.set"
            else RestoreCommand(expected_revision=1, policy_version="restore-1"))
    with pytest.raises(psycopg.OperationalError):
        command(store, body, action=action)
    assert store.record == before
    assert not store.receipts and not store.audit


def test_restore_only_changes_visibility_revision_time_and_preserves_archive(store, resource):
    before, access_before = deepcopy(store.record), deepcopy(resource)
    body = RestoreCommand(expected_revision=1, policy_version="restore-1")
    result = command(store, body, action="restore_visibility")
    assert result["current"]["visibility"] == "visible"
    assert result["current"]["revision"] == 2
    assert result["current"]["lifecycle"] == "ARCHIVED"
    for field in before.keys() - {"visibility", "revision", "updated_at"}:
        assert store.record[field] == before[field]
    assert resource == access_before
    assert command(store, body, action="restore_visibility")["operation_id"] == result["operation_id"]
    assert len(store.audit) == 1


def test_restore_replay_rechecks_policy_and_policy_version(store):
    body = RestoreCommand(expected_revision=1, policy_version="restore-1")
    command(store, body, action="restore_visibility")
    store.policy["version"] = "restore-2"
    with pytest.raises(ApiError) as error:
        command(store, body, action="restore_visibility")
    assert error.value.code == "RESTORE_POLICY_CONFLICT"
    store.policy["active"] = False
    with pytest.raises(AccessDenied):
        command(store, body, action="restore_visibility")


def test_audit_contains_actual_before_after_and_correlation(store):
    command(store, FavoriteCommand(favorite=True, expected_revision=0))
    audit = store.audit[0]
    assert audit[1:5] == (WID, AID, RID, "favorite.set")
    assert audit[5].obj == {"favorite": False, "revision": 0}
    assert audit[6].obj == {"favorite": True, "revision": 1, "policy_version": None,
                            "policy_epoch": [5, 3, 7], "result": "success"}
    assert audit[7:] == ("request-1", "1"*32, NOW)


def test_page_byte_budget_keeps_total_and_generates_resume_cursor(monkeypatch, facts, record):
    context = authorize(facts, "workspace:read")
    monkeypatch.setattr(repository, "checked", lambda *_: (facts, None, context))
    rows = [record | {"resource_id": UUID(int=index+1), "title": "实"*512} for index in range(51)]
    aggregate = {"items": rows, "total_count": 101, "metadata_bytes": 98765}
    class Connection:
        def execute(self, sql, params):
            assert sql is repository.AUTHORIZED_SQL
            assert params["fetch_limit"] == 51
            return Result(aggregate)
    result = repository.list_records(Connection(), "verified", WID, Filters(limit=50))
    assert 0 < len(result["items"]) < 50
    assert result["total_count"] == 101
    assert result["storage"]["metadata_bytes"] == 98765
    assert len(json.dumps(result["items"], ensure_ascii=False).encode()) <= repository.MAX_PAGE_BYTES
    binding = repository._binding(facts, context, Filters(limit=50), None)
    assert repository.decode_cursor(result["next_cursor"], binding)[1] == UUID(result["items"][-1]["id"])
