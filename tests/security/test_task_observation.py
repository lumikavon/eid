"""Story 1.6 action and notification security test source; execution is deferred."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from edw_api.access.policy import AccessDenied, authorize
from edw_api.errors import ApiError
from edw_api.tasks import repository


WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("33333333-3333-4333-8333-333333333333")
TASK = UUID("44444444-4444-4444-8444-444444444444")
FACTS_TIME = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def parent(**changes):
    return {"id": TASK, "actor_id": ACTOR, "operation": "inventory",
            "category": "integration", "state": "FAILED", "external_effect_state": "none",
            "input": {"operation": "inventory", "input": {"limit": 2}, "depends_on": []}} | changes


class ParentConnection:
    def __init__(self, task):
        self.task = task
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        assert sql == "SELECT * FROM durable_task WHERE id=%s FOR UPDATE"
        assert params == (TASK,)
        return SimpleNamespace(fetchone=lambda: self.task)


def test_manual_retry_creates_distinct_parent_bound_child(monkeypatch):
    task = parent()
    conn = ParentConnection(task)
    monkeypatch.setattr(repository, "_owned", lambda *_: (
        {}, SimpleNamespace(actor_id=str(ACTOR)), task))
    accepted = uuid4()
    submissions = []

    def submit(_conn, subject, workspace_id, command, key, request_id, trace_id,
               parent_task_id=None):
        submissions.append((subject, workspace_id, command, key, request_id,
                            trace_id, parent_task_id))
        return accepted

    monkeypatch.setattr(repository, "submit", submit)
    first = repository.retry(conn, "verified", WORKSPACE, TASK, "retry-key", "request-1", "1" * 32)
    second = repository.retry(conn, "verified", WORKSPACE, TASK, "retry-key", "request-1", "1" * 32)
    assert first == second == accepted
    assert len(submissions) == 2
    assert submissions[0][3] == submissions[1][3]
    assert submissions[0][3].startswith("retry:" + TASK.hex + ":")
    assert submissions[0][6] == TASK
    assert submissions[0][2].operation == "inventory"


@pytest.mark.parametrize("changes,reason", [
    ({"state": "RUNNING"}, "TASK_NOT_TERMINAL"),
    ({"external_effect_state": "unknown"}, "EXTERNAL_EFFECT_UNKNOWN"),
    ({"operation": "external_export"}, "OPERATION_UNAVAILABLE"),
])
def test_manual_retry_fails_closed_without_enqueue(monkeypatch, changes, reason):
    task = parent(**changes)
    conn = ParentConnection(task)
    monkeypatch.setattr(repository, "_owned", lambda *_: (
        {}, SimpleNamespace(actor_id=str(ACTOR)), task))
    monkeypatch.setattr(repository, "submit", lambda *_args, **_kwargs: pytest.fail("No child"))
    with pytest.raises(ApiError) as error:
        repository.retry(conn, "verified", WORKSPACE, TASK, "retry-key", "request-1", "1" * 32)
    assert error.value.code == "TASK_ACTION_UNAVAILABLE"
    assert error.value.details == {"reason": reason}


def test_unknown_external_effect_cannot_request_cancellation(monkeypatch):
    task = parent(state="RUNNING", external_effect_state="unknown")
    monkeypatch.setattr(repository, "_owned", lambda *_: (
        {}, SimpleNamespace(actor_id=str(ACTOR)), task))
    class NoSql:
        def execute(self, *_args):
            pytest.fail("Cancellation must not reach database function")
    with pytest.raises(ApiError) as error:
        repository.cancel(NoSql(), "verified", WORKSPACE, TASK, "request-1")
    assert error.value.details == {"reason": "EXTERNAL_EFFECT_UNKNOWN"}


def test_cancel_rejects_effect_change_after_initial_read(monkeypatch):
    task = parent(state="RUNNING")
    monkeypatch.setattr(repository, "_owned", lambda *_: (
        {}, SimpleNamespace(actor_id=str(ACTOR)), task))

    class ChangedEffectConnection:
        def execute(self, sql, params):
            assert "eid_task_cancel_observed_v1" in sql
            assert params[:2] == (TASK, ACTOR)
            return SimpleNamespace(fetchone=lambda: {"outcome": {"status": "action_unavailable"}})

    with pytest.raises(ApiError) as error:
        repository.cancel(ChangedEffectConnection(), "verified", WORKSPACE, TASK, "request-1")
    assert error.value.code == "TASK_ACTION_UNAVAILABLE"
    assert error.value.details == {"reason": "EXTERNAL_EFFECT_UNKNOWN"}


def observation_facts():
    return {"actor_id": ACTOR, "workspace_id": WORKSPACE, "tenant_id": uuid4(),
            "identity_active": True, "membership_active": True, "roles": ["author"],
            "approval_states": ["draft"], "owner_scope": "any", "clearance": 2,
            "classification": 0, "workspace_epoch": 2, "policy_epoch": 3,
            "project_id": "project", "customer_id": "customer", "product_id": "product",
            "department": "department", "project_scope": ["project"],
            "customer_scope": ["customer"], "product_scope": ["product"],
            "department_scope": ["department"], "valid_from": FACTS_TIME,
            "valid_until": None, "evaluated_at": FACTS_TIME}


def bound_resource(resource_id, **changes):
    return {"id": resource_id, "workspace_id": WORKSPACE, "kind": "document",
            "discovery_kind": "document", "discovery_visibility": "visible",
            "owner_id": ACTOR, "project_id": "project", "customer_id": "customer",
            "product_id": "product", "department": "department",
            "classification": 1, "approval_state": "draft", "policy_epoch": 7,
            "valid_from": FACTS_TIME, "valid_until": None} | changes


def binding(resource_id, **changes):
    return {"resource_id": resource_id, "workspace_id": WORKSPACE,
            "actor_id": ACTOR, "workspace_epoch": 2, "policy_epoch": 3,
            "resource_epoch": 7, "authority": "local_access_resource"} | changes


class BindingConnection:
    def __init__(self, bindings, resources, db_now=None):
        self.bindings = bindings
        self.resources = resources
        self.db_now = db_now if db_now is not None else datetime.now(timezone.utc)
        self.clock_reads = 0

    def execute(self, sql, params=None):
        if sql == "SELECT clock_timestamp() AS evaluated_at":
            self.clock_reads += 1
            return SimpleNamespace(fetchone=lambda: {"evaluated_at": self.db_now})
        if "FROM task_observation_binding" in sql:
            return SimpleNamespace(fetchall=lambda: self.bindings)
        assert "FOR SHARE OF r,d" in sql
        return SimpleNamespace(fetchone=lambda: self.resources.get(params[0]))


@pytest.mark.parametrize("entry", ["detail", "events", "notification"])
def test_revoked_non_inventory_binding_denies_owned_entry_points(monkeypatch, entry):
    resource_id, notification_id = uuid4(), uuid4()
    task = parent(operation="draft", category="generation", workspace_id=WORKSPACE)
    facts = observation_facts()
    context = authorize(facts, "workspace:read")
    monkeypatch.setattr(repository, "checked", lambda _conn, subject, workspace, permission:
                        (facts, None, context) if (subject, workspace, permission) ==
                        ("verified", WORKSPACE, "workspace:read") else pytest.fail("Wrong scope"))

    class OwnedConnection(BindingConnection):
        def execute(self, sql, params=None):
            if sql.startswith("SELECT * FROM durable_task WHERE id=%s AND workspace_id=%s"):
                assert params == (TASK, WORKSPACE, context.actor_id)
                return SimpleNamespace(fetchone=lambda: task)
            if "FROM task_notification n" in sql:
                assert params == (notification_id, WORKSPACE, context.actor_id)
                return SimpleNamespace(fetchone=lambda: {"task_id": TASK})
            return super().execute(sql, params)

    conn = OwnedConnection([binding(resource_id)], {resource_id: bound_resource(resource_id)})
    assert repository._owned(conn, "verified", WORKSPACE, TASK)[2] is task
    conn.resources[resource_id] = bound_resource(resource_id, project_id="revoked-project")
    with pytest.raises(ApiError) as error:
        if entry == "detail":
            repository.read(conn, "verified", WORKSPACE, TASK)
        elif entry == "events":
            repository.event_page(conn, "verified", WORKSPACE, TASK, cursor=0)
        else:
            repository.notification(conn, "verified", WORKSPACE, notification_id)
    assert error.value.status_code == 404
    assert error.value.code == "TASK_NOT_FOUND"


def test_bound_non_inventory_task_checks_every_current_resource():
    first, second = uuid4(), uuid4()
    task = parent(operation="draft", category="generation", workspace_id=WORKSPACE)
    conn = BindingConnection([binding(first), binding(second)],
                             {first: bound_resource(first), second: bound_resource(second)})
    facts = observation_facts()
    context = authorize(facts, "workspace:read")
    assert repository._visible_task(conn, facts, context, task) is True
    conn.resources[second] = bound_resource(second, project_id="revoked-project")
    assert repository._visible_task(conn, facts, context, task) is False


@pytest.mark.parametrize("expiring", ["membership", "resource"])
def test_bound_task_uses_database_time_for_expiring_authority(expiring):
    resource_id = uuid4()
    expiry = FACTS_TIME + timedelta(minutes=1)
    facts = observation_facts()
    resource = bound_resource(resource_id)
    facts.update(valid_from=FACTS_TIME, evaluated_at=FACTS_TIME)
    resource["valid_from"] = FACTS_TIME
    if expiring == "membership":
        facts["valid_until"] = expiry
    else:
        resource["valid_until"] = expiry
    context = authorize(facts, "workspace:read")
    task = parent(operation="draft", category="generation", workspace_id=WORKSPACE)
    conn = BindingConnection([binding(resource_id)], {resource_id: resource},
                             db_now=expiry - timedelta(seconds=1))

    assert repository._visible_task(conn, facts, context, task) is True
    conn.db_now = expiry
    assert repository._visible_task(conn, facts, context, task) is False
    assert conn.clock_reads == 2


@pytest.mark.parametrize("bindings,resource_change", [
    ([], {}),
    ([binding(uuid4(), workspace_id=uuid4())], {}),
    ([binding(uuid4(), policy_epoch=2)], {}),
    ([binding(uuid4(), resource_epoch=6)], {}),
])
def test_missing_cross_workspace_or_stale_binding_fails_closed(bindings, resource_change):
    task = parent(operation="draft", category="generation", workspace_id=WORKSPACE)
    resources = {item["resource_id"]: bound_resource(item["resource_id"], **resource_change)
                 for item in bindings}
    facts = observation_facts()
    context = authorize(facts, "workspace:read")
    assert repository._visible_task(BindingConnection(bindings, resources), facts, context, task) is False


def test_non_inventory_result_and_actions_do_not_enter_inventory_handler(monkeypatch):
    task = parent(operation="draft", category="generation", state="SUCCEEDED", result_id=uuid4())
    monkeypatch.setattr(repository, "_owned", lambda *_: (
        {}, SimpleNamespace(actor_id=str(ACTOR)), task))

    class NoInventorySql:
        def execute(self, sql, _params):
            if sql == "SELECT * FROM durable_task WHERE id=%s FOR UPDATE":
                return SimpleNamespace(fetchone=lambda: task)
            pytest.fail("Non-inventory operation reached inventory SQL")

    with pytest.raises(ApiError) as result_error:
        repository.result(NoInventorySql(), "verified", WORKSPACE, TASK)
    assert result_error.value.code == "TASK_RESULT_UNAVAILABLE"
    with pytest.raises(ApiError) as cancel_error:
        repository.cancel(NoInventorySql(), "verified", WORKSPACE, TASK, "request-1")
    assert cancel_error.value.details == {"reason": "OPERATION_UNAVAILABLE"}
    with pytest.raises(ApiError) as retry_error:
        repository.retry(NoInventorySql(), "verified", WORKSPACE, TASK,
                         "retry-key", "request-1", "1" * 32)
    assert retry_error.value.details == {"reason": "OPERATION_UNAVAILABLE"}


@pytest.mark.parametrize("expiring,final_offset,allowed", [
    ("resource", -1, True),
    ("resource", 0, False),
    ("membership", -1, True),
    ("membership", 0, False),
])
def test_inventory_result_rechecks_source_and_membership_at_final_database_time(
        monkeypatch, expiring, final_offset, allowed):
    resource_id, result_id = uuid4(), uuid4()
    expiry = FACTS_TIME + timedelta(minutes=1)
    facts = observation_facts()
    source = bound_resource(resource_id, discovery_revision=4)
    facts.update(valid_from=FACTS_TIME, evaluated_at=FACTS_TIME)
    source["valid_from"] = FACTS_TIME
    if expiring == "membership":
        facts["valid_until"] = expiry
    else:
        source["valid_until"] = expiry
    context = authorize(facts, "workspace:read")
    task = parent(workspace_id=WORKSPACE, state="SUCCEEDED", result_id=result_id)
    payload = {"result_id": result_id, "task_id": TASK, "workspace_id": WORKSPACE,
               "measured_at": FACTS_TIME, "scope": "first_authorized_visible_records",
               "limit": 2, "items": [{"resource_id": resource_id, "kind": "document",
                                     "revision": 4, "resource_epoch": 7}],
               "policy_epoch": context.policy_epoch}
    monkeypatch.setattr(repository, "checked", lambda _conn, subject, workspace, permission:
                        (facts, None, context) if (subject, workspace, permission) ==
                        ("verified", WORKSPACE, "workspace:read") else pytest.fail("Wrong scope"))

    class ResultConnection:
        def __init__(self):
            self.clock_reads = 0

        def execute(self, sql, params=None):
            if sql == "SELECT clock_timestamp() AS evaluated_at":
                self.clock_reads += 1
                assert self.clock_reads <= 2
                now = FACTS_TIME if self.clock_reads == 1 else expiry + timedelta(
                    seconds=final_offset)
                return SimpleNamespace(fetchone=lambda: {"evaluated_at": now})
            if sql.startswith("SELECT * FROM durable_task WHERE id=%s AND workspace_id=%s"):
                assert params == (TASK, WORKSPACE, context.actor_id)
                return SimpleNamespace(fetchone=lambda: task)
            if sql == "SELECT payload FROM task_result WHERE id=%s AND task_id=%s":
                assert params == (result_id, TASK)
                return SimpleNamespace(fetchone=lambda: {"payload": payload})
            assert "FOR SHARE OF r,d" in sql
            assert params == (resource_id, WORKSPACE)
            return SimpleNamespace(fetchone=lambda: source)

    conn = ResultConnection()
    if allowed:
        assert repository.result(conn, "verified", WORKSPACE, TASK).result_id == result_id
    else:
        with pytest.raises(AccessDenied):
            repository.result(conn, "verified", WORKSPACE, TASK)
    assert conn.clock_reads == 2


def test_notification_mark_read_has_independent_resource_authorization():
    migration = (Path(__file__).resolve().parents[2] / "migrations" / "versions" /
                 "0010_task_observation.py").read_text(encoding="utf8")
    mark_read = migration.split("CREATE FUNCTION eid_notification_mark_read_v1", 1)[1].split(
        "CREATE FUNCTION eid_task_cancel_observed_v1", 1)[0]
    assert "eid_task_observation_allowed_v1(target.task_id,p_actor)" in mark_read
    assert "t.operation='inventory'" not in mark_read
    assert "REVOKE ALL ON task_observation_binding FROM PUBLIC,eid_worker,eid_api" in migration


class UnreadConnection:
    def __init__(self, tasks):
        self.tasks = tasks

    def execute(self, sql, params):
        assert "n.read_at IS NULL" in sql
        assert "n.workspace_id=%s AND n.actor_id=%s" in sql
        assert "t.workspace_id=n.workspace_id" in sql
        assert "t.actor_id=n.actor_id" in sql
        assert params == (WORKSPACE, str(ACTOR), repository.MAX_PAGE_SCAN_ROWS + 1)
        return SimpleNamespace(fetchall=lambda: self.tasks)


def test_unread_existence_checks_current_visibility_after_read_rows(monkeypatch):
    # The query filters read notifications in SQL, so their page count cannot
    # conceal an older unread notification.
    facts, context = object(), SimpleNamespace(actor_id=str(ACTOR))
    checked_calls = []
    def checked(_conn, subject, workspace_id, permission):
        checked_calls.append((subject, workspace_id, permission))
        return facts, None, context
    monkeypatch.setattr(repository, "checked", checked)
    hidden, visible = {"id": uuid4()}, {"id": uuid4()}
    checked_tasks = []
    def visible_task(_conn, actual_facts, actual_context, task):
        assert (actual_facts, actual_context) == (facts, context)
        checked_tasks.append(task)
        if task is hidden:
            raise AccessDenied()
        return task is visible
    monkeypatch.setattr(repository, "_visible_task", visible_task)
    assert repository.has_unread_notification(
        UnreadConnection([hidden, visible]), "verified", WORKSPACE) is True
    assert checked_calls == [("verified", WORKSPACE, "workspace:read")]
    assert checked_tasks == [hidden, visible]


def test_unread_existence_never_returns_false_from_truncated_scan(monkeypatch):
    monkeypatch.setattr(repository, "checked", lambda *_: (
        {}, None, SimpleNamespace(actor_id=str(ACTOR))))
    checked_tasks = []
    monkeypatch.setattr(repository, "_visible_task", lambda _conn, _facts, _context, task:
                        checked_tasks.append(task) or False)
    hidden = [{"id": uuid4()} for _ in range(repository.MAX_PAGE_SCAN_ROWS + 1)]
    with pytest.raises(ApiError) as error:
        repository.has_unread_notification(UnreadConnection(hidden), "verified", WORKSPACE)
    assert error.value.status_code == 503
    assert error.value.code == "NOTIFICATION_UNREAD_SCAN_LIMIT"
    assert error.value.retryable is True
    assert checked_tasks == hidden[:-1]
    assert repository.has_unread_notification(
        UnreadConnection(hidden[:-1]), "verified", WORKSPACE) is False
