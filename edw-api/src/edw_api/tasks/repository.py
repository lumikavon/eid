"""Task commands own a single short caller transaction; never contact the Broker."""
import hashlib
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied, authorize
from ..access.repository import checked, create_delegation
from ..errors import ApiError
from ..task_contract import (InventoryResult, SubmitTask, TaskEnvelope, TaskSnapshot, payload_hash,
                             wire_time)

TERMINAL = frozenset({"SUCCEEDED", "BLOCKED", "FAILED", "CANCELLED", "DEAD_LETTER"})
MAX_PAGE_SCAN_ROWS = 512


def _database_now(conn):
    # clock_timestamp advances within a transaction, unlike transaction/statement time.
    return conn.execute("SELECT clock_timestamp() AS evaluated_at").fetchone()["evaluated_at"]


def _capabilities(row):
    if row["operation"] != "inventory" or row["category"] != "integration":
        return False, False, "OPERATION_UNAVAILABLE"
    if row["external_effect_state"] != "none":
        return False, False, "EXTERNAL_EFFECT_UNKNOWN"
    if row["state"] in TERMINAL:
        return False, True, "TASK_TERMINAL"
    return True, False, "TASK_NOT_TERMINAL"


def snapshot(row):
    prefix = f"/api/v1/workspaces/{row['workspace_id']}/tasks/{row['id']}"
    can_cancel, can_retry, reason = _capabilities(row)
    return TaskSnapshot(task_id=row["id"], state=row["state"], stage=row["stage"],
                        category=row["category"], operation=row["operation"],
                        parent_task_id=row.get("parent_task_id"),
                        attempt=row["attempt"], fence_token=row["fence_token"],
                        current_seq=row["current_seq"],
                        retention_floor=row.get("event_floor_seq", 1),
                        result_ref=row["result_id"], error=row["error_code"],
                        error_class=row["error_class"], next_retry_at=row["next_retry_at"],
                        cancel_requested=row["cancel_requested"],
                        external_effect_state=row["external_effect_state"],
                        created_at=row["created_at"], updated_at=row["updated_at"],
                        status_url=prefix,
                        result_url=prefix + "/result" if row["operation"] == "inventory"
                        and row["category"] == "integration" else None,
                        can_cancel=can_cancel, can_retry=can_retry,
                        action_reason=reason)


def submit(conn, subject, workspace_id, command, key, request_id, trace_id,
           parent_task_id=None):
    if (not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id)
            or not re.fullmatch(r"[0-9a-f]{32}", trace_id) or trace_id == "0" * 32):
        raise AccessDenied()
    facts, _, context = checked(conn, subject, workspace_id, "inventory:read")
    body = command.model_dump(mode="json")
    digest = payload_hash(body)
    # Serializes only this actor/workspace/key; collision only adds contention.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                 (f"task:{context.actor_id}:{workspace_id}:{key}",))
    receipt = conn.execute("SELECT * FROM task_receipt WHERE actor_id=%s AND workspace_id=%s "
                           "AND idempotency_key=%s", (context.actor_id, workspace_id, key)).fetchone()
    if receipt:
        if receipt["payload_hash"] != digest:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "幂等键已用于其他请求")
        bound = conn.execute("SELECT parent_task_id FROM durable_task WHERE id=%s",
                             (receipt["task_id"],)).fetchone()
        if not bound or bound["parent_task_id"] != parent_task_id:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "幂等键已用于其他请求")
        return read(conn, subject, workspace_id, receipt["task_id"])
    # Dependencies always refer to existing same-owner tasks. A new random task ID
    # cannot be an ancestor of any existing task, so this insertion cannot form a cycle.
    for dependency in command.depends_on:
        row = conn.execute("SELECT id FROM durable_task WHERE id=%s AND actor_id=%s "
                           "AND workspace_id=%s AND state IN ('QUEUED','RUNNING','SUCCEEDED')",
                           (dependency, context.actor_id, workspace_id)).fetchone()
        if not row:
            raise ApiError(409, "TASK_DEPENDENCY_UNAVAILABLE", "任务依赖不可用")
    task_id, event_id, audit_id = uuid4(), uuid4(), uuid4()
    purpose = f"task:{task_id}"
    delegation = create_delegation(conn, subject, workspace_id, None, "inventory:read",
                                   purpose, request_id, trace_id)
    now = facts["evaluated_at"]
    envelope = TaskEnvelope(message_schema_version="1.0", source="eid-api", event_id=event_id,
                            event_type="task.inventory.requested", occurred_at=now,
                            aggregate_id=task_id, aggregate_version=1, task_id=task_id,
                            category="integration", input_ref=task_id, input_hash=digest,
                            actor_id=context.actor_id, workspace_id=workspace_id,
                            delegation_id=delegation["delegation_id"],
                            request_id=request_id, trace_id=trace_id).model_dump(mode="json")
    row = conn.execute("""
        INSERT INTO durable_task(id,workspace_id,actor_id,delegation_id,parent_task_id,input,input_hash,
                                 request_id,trace_id,created_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """, (task_id, workspace_id, context.actor_id, delegation["delegation_id"],
               parent_task_id, Jsonb(body), digest, request_id, trace_id, now, now)).fetchone()
    for dependency in command.depends_on:
        conn.execute("INSERT INTO task_dependency(task_id,depends_on) VALUES (%s,%s)",
                     (task_id, dependency))
    conn.execute("""INSERT INTO task_event(event_id,task_id,seq,event_type,state,occurred_at)
                 VALUES (%s,%s,1,'task.queued','QUEUED',%s)""", (event_id, task_id, now))
    conn.execute("INSERT INTO task_outbox(event_id,task_id,envelope,envelope_hash) VALUES (%s,%s,%s,%s)",
                 (event_id, task_id, Jsonb(envelope), payload_hash(envelope)))
    conn.execute("""INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,
                 before_policy,after_policy,request_id,trace_id) VALUES
                 (%s,%s,%s,%s,%s,'{}',%s,%s,%s)""",
                 (audit_id, workspace_id, context.actor_id, task_id,
                  "task.inventory.retry" if parent_task_id else "task.inventory.submit",
                  Jsonb({"task_id": str(task_id), "input_hash": digest,
                         "parent_task_id": str(parent_task_id) if parent_task_id else None,
                         "policy_epoch": list(context.policy_epoch), "accepted_at": wire_time(now)}),
                  request_id, trace_id))
    conn.execute("""INSERT INTO task_receipt(actor_id,workspace_id,idempotency_key,
                 payload_hash,task_id,audit_id) VALUES (%s,%s,%s,%s,%s,%s)""",
                 (context.actor_id, workspace_id, key, digest, task_id, audit_id))
    return snapshot(row)


def _visible_task(conn, facts, context, row):
    if (str(row["workspace_id"]) != context.workspace_id
            or str(row["actor_id"]) != context.actor_id):
        return False
    if row["operation"] == "inventory" and row["category"] == "integration":
        authorize(facts, "inventory:read", now=_database_now(conn))
        return True
    bindings = conn.execute("""SELECT * FROM task_observation_binding
        WHERE task_id=%s ORDER BY resource_id""",
        (row["id"],)).fetchall()
    if not bindings:
        return False
    resources = []
    for binding in bindings:
        resource = conn.execute("""SELECT r.*,d.kind AS discovery_kind,
            d.visibility AS discovery_visibility FROM access_resource r
            JOIN discovery_record d ON d.resource_id=r.id
            WHERE r.id=%s AND r.workspace_id=%s FOR SHARE OF r,d""",
            (binding["resource_id"], row["workspace_id"])).fetchone()
        if (binding["workspace_id"] != row["workspace_id"]
                or binding["actor_id"] != row["actor_id"]
                or binding["authority"] != "local_access_resource"
                or binding["workspace_epoch"] != context.policy_epoch[0]
                or binding["policy_epoch"] != context.policy_epoch[1]
                or resource is None or binding["resource_epoch"] != resource["policy_epoch"]
                or resource["discovery_kind"] != resource["kind"]
                or resource["discovery_visibility"] != "visible"):
            return False
        resources.append(resource)
    # The resource/discovery rows remain share-locked. Recheck every validity
    # window against one fresh database time after the last row was fetched.
    now = _database_now(conn)
    for resource in resources:
        try:
            authorize(facts, "resource:read", resource, now=now)
        except AccessDenied:
            return False
    return True


def _owned(conn, subject, workspace_id, task_id):
    facts, _, context = checked(conn, subject, workspace_id, "workspace:read")
    row = conn.execute("SELECT * FROM durable_task WHERE id=%s AND workspace_id=%s AND actor_id=%s",
                       (task_id, workspace_id, context.actor_id)).fetchone()
    if not row or not _visible_task(conn, facts, context, row):
        raise ApiError(404, "TASK_NOT_FOUND", "任务不存在或不可访问")
    return facts, context, row


def read(conn, subject, workspace_id, task_id):
    return snapshot(_owned(conn, subject, workspace_id, task_id)[2])


def page(conn, subject, workspace_id, after=None):
    facts, _, context = checked(conn, subject, workspace_id, "workspace:read")
    if after is not None:
        cursor = conn.execute("SELECT * FROM durable_task WHERE id=%s AND workspace_id=%s "
                              "AND actor_id=%s", (after, workspace_id, context.actor_id)).fetchone()
        if not cursor or not _visible_task(conn, facts, context, cursor):
            raise ApiError(400, "INVALID_TASK_CURSOR", "任务游标无效")
        bound = (cursor["created_at"], cursor["id"])
    else:
        bound = None
    visible = []
    scanned = 0
    while len(visible) < 26:
        rows = conn.execute("""SELECT * FROM durable_task WHERE workspace_id=%s AND actor_id=%s
            AND (%s::timestamptz IS NULL OR (created_at,id)<(%s::timestamptz,%s::uuid))
            ORDER BY created_at DESC,id DESC LIMIT 128""",
            (workspace_id, context.actor_id, bound[0] if bound else None,
             bound[0] if bound else None, bound[1] if bound else None)).fetchall()
        scanned += len(rows)
        for row in rows:
            if _visible_task(conn, facts, context, row):
                visible.append(row)
                if len(visible) == 26:
                    break
        if len(rows) < 128 or len(visible) == 26:
            break
        if scanned >= MAX_PAGE_SCAN_ROWS:
            raise ApiError(503, "TASK_PAGE_SCAN_LIMIT", "任务列表暂时无法完整核对", retryable=True)
        bound = (rows[-1]["created_at"], rows[-1]["id"])
    return {"data": [snapshot(row) for row in visible[:25]],
            "next_cursor": visible[24]["id"] if len(visible) > 25 else None}


def event_page(conn, subject, workspace_id, task_id, cursor, limit=64):
    _, _, task = _owned(conn, subject, workspace_id, task_id)
    if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 64:
        raise ApiError(400, "INVALID_EVENT_CURSOR", "事件游标无效")
    current, floor = task["current_seq"], task["event_floor_seq"]
    if cursor > current:
        raise ApiError(400, "INVALID_EVENT_CURSOR", "事件游标无效")
    if cursor < floor - 1:
        return {"data": [], "current_seq": current, "retention_floor": floor,
                "reset_required": True}
    rows = conn.execute("""SELECT task_id,seq,event_type,state,occurred_at FROM task_event
        WHERE task_id=%s AND seq>%s AND seq<=%s ORDER BY seq LIMIT %s""",
        (task_id, cursor, current, limit)).fetchall()
    if cursor < current and (not rows or any(
            event["seq"] != cursor + position for position, event in enumerate(rows, 1))):
        return {"data": [], "current_seq": current, "retention_floor": floor,
                "reset_required": True}
    return {"data": rows, "current_seq": current, "retention_floor": floor,
            "reset_required": False}


def notification_page(conn, subject, workspace_id, after=None):
    facts, _, context = checked(conn, subject, workspace_id, "workspace:read")
    if after is not None:
        cursor = conn.execute("""SELECT n.created_at,n.id FROM task_notification n
            WHERE n.id=%s AND n.workspace_id=%s AND n.actor_id=%s""",
            (after, workspace_id, context.actor_id)).fetchone()
        cursor_task = conn.execute("""SELECT t.* FROM durable_task t JOIN task_notification n
            ON n.task_id=t.id WHERE n.id=%s""", (after,)).fetchone() if cursor else None
        if not cursor or not cursor_task or not _visible_task(conn, facts, context, cursor_task):
            raise ApiError(400, "INVALID_NOTIFICATION_CURSOR", "通知游标无效")
        bound = (cursor["created_at"], cursor["id"])
    else:
        bound = None
    visible = []
    scanned = 0
    while len(visible) < 26:
        rows = conn.execute("""SELECT n.id AS notification_id,n.task_id,n.event_seq,
            n.event_type,n.state,n.created_at,n.read_at FROM task_notification n
            WHERE n.workspace_id=%s AND n.actor_id=%s
            AND (%s::timestamptz IS NULL OR (n.created_at,n.id)<(%s::timestamptz,%s::uuid))
            ORDER BY n.created_at DESC,n.id DESC LIMIT 128""",
            (workspace_id, context.actor_id, bound[0] if bound else None,
             bound[0] if bound else None, bound[1] if bound else None)).fetchall()
        scanned += len(rows)
        for row in rows:
            task = conn.execute("SELECT * FROM durable_task WHERE id=%s", (row["task_id"],)).fetchone()
            if task and _visible_task(conn, facts, context, task):
                visible.append(row)
                if len(visible) == 26:
                    break
        if len(rows) < 128 or len(visible) == 26:
            break
        if scanned >= MAX_PAGE_SCAN_ROWS:
            raise ApiError(503, "NOTIFICATION_PAGE_SCAN_LIMIT", "通知列表暂时无法完整核对", retryable=True)
        bound = (rows[-1]["created_at"], rows[-1]["notification_id"])
    return {"data": visible[:25],
            "next_cursor": visible[24]["notification_id"] if len(visible) > 25 else None}


def has_unread_notification(conn, subject, workspace_id):
    facts, _, context = checked(conn, subject, workspace_id, "workspace:read")
    # Read one extra candidate to distinguish a complete scan from a capped one.
    # The current observation policy must authorize a task before its unread
    # notification can affect this actor's badge.
    tasks = conn.execute("""SELECT t.* FROM task_notification n
        JOIN durable_task t ON t.id=n.task_id AND t.workspace_id=n.workspace_id
            AND t.actor_id=n.actor_id
        WHERE n.workspace_id=%s AND n.actor_id=%s AND n.read_at IS NULL
        ORDER BY n.created_at DESC,n.id DESC LIMIT %s""",
        (workspace_id, context.actor_id, MAX_PAGE_SCAN_ROWS + 1)).fetchall()
    for task in tasks[:MAX_PAGE_SCAN_ROWS]:
        try:
            if _visible_task(conn, facts, context, task):
                return True
        except AccessDenied:
            # A revoked inventory task is hidden; later unread tasks may remain visible.
            continue
    if len(tasks) > MAX_PAGE_SCAN_ROWS:
        raise ApiError(503, "NOTIFICATION_UNREAD_SCAN_LIMIT",
                       "未读通知暂时无法完整核对", retryable=True)
    return False


def notification(conn, subject, workspace_id, notification_id, mark_read=False,
                 open_target=False):
    _, _, context = checked(conn, subject, workspace_id, "workspace:read")
    row = conn.execute("""SELECT n.id AS notification_id,n.task_id,n.event_seq,
        n.event_type,n.state,n.created_at,n.read_at FROM task_notification n
        WHERE n.id=%s AND n.workspace_id=%s AND n.actor_id=%s""",
        (notification_id, workspace_id, context.actor_id)).fetchone()
    if not row:
        raise ApiError(404, "NOTIFICATION_NOT_FOUND", "通知不存在或不可访问")
    task = read(conn, subject, workspace_id, row["task_id"])
    if open_target and task.state == "SUCCEEDED" and task.operation == "inventory" \
            and task.category == "integration":
        # A notification cannot open a retained result after its source records
        # or policy epoch have stopped authorizing the current actor.
        result(conn, subject, workspace_id, row["task_id"])
    if mark_read:
        accepted = conn.execute("SELECT eid_notification_mark_read_v1(%s,%s) AS accepted",
                                (notification_id, UUID(context.actor_id))).fetchone()["accepted"]
        if not accepted:
            raise ApiError(404, "NOTIFICATION_NOT_FOUND", "通知不存在或不可访问")
        row = {**row, "read_at": conn.execute("SELECT read_at FROM task_notification WHERE id=%s",
                                               (notification_id,)).fetchone()["read_at"]}
    return row, task


def result(conn, subject, workspace_id, task_id):
    facts, context, task = _owned(conn, subject, workspace_id, task_id)
    if task["operation"] != "inventory" or task["category"] != "integration":
        raise ApiError(409, "TASK_RESULT_UNAVAILABLE", "当前任务未开放结果读取")
    if task["state"] != "SUCCEEDED" or task["result_id"] is None:
        raise ApiError(409, "TASK_RESULT_UNAVAILABLE", "任务尚无可用结果")
    stored = conn.execute("SELECT payload FROM task_result WHERE id=%s AND task_id=%s",
                          (task["result_id"], task_id)).fetchone()
    if not stored:
        raise ApiError(503, "TASK_STORAGE_UNAVAILABLE", "任务存储不可用", retryable=True)
    value = InventoryResult.model_validate(stored["payload"])
    if (value.task_id != task["id"] or value.workspace_id != task["workspace_id"]
            or value.policy_epoch != context.policy_epoch):
        raise AccessDenied()
    # The result is capped at 50 items. Lock both source rows so identity and
    # visibility cannot change before the final authorization decision.
    resources = []
    for item in value.items:
        resource = conn.execute("""SELECT r.*,d.kind AS discovery_kind,
            d.revision AS discovery_revision,d.visibility AS discovery_visibility
            FROM access_resource r JOIN discovery_record d ON d.resource_id=r.id
            WHERE r.id=%s AND r.workspace_id=%s FOR SHARE OF r,d""",
            (item.resource_id, workspace_id)).fetchone()
        if not resource:
            raise AccessDenied()
        resources.append((item, resource))
    # checked() and _owned() ran earlier in this transaction. Their sampled time
    # must not authorize a source or membership that expires while this result
    # is assembled; the workspace policy and source rows stay share-locked.
    now = _database_now(conn)
    authorize(facts, "inventory:read", now=now)
    for item, resource in resources:
        if (resource["discovery_visibility"] != "visible"
                or resource["discovery_kind"] != item.kind
                or resource["kind"] != item.kind
                or resource["discovery_revision"] != item.revision
                or resource["policy_epoch"] != item.resource_epoch):
            raise AccessDenied()
        authorize(facts, "resource:read", resource, now=now)
    return value


def cancel(conn, subject, workspace_id, task_id, request_id):
    # Keep the workspace policy lock and the task ownership decision in the
    # caller's transaction. The SECURITY DEFINER function locks the task and
    # decides the completion/cancellation order with current database facts.
    _, context, task = _owned(conn, subject, workspace_id, task_id)
    can_cancel, _, reason = _capabilities(task)
    if not can_cancel:
        raise ApiError(409, "TASK_ACTION_UNAVAILABLE", "当前任务无法取消",
                       details={"reason": reason})
    decision = conn.execute("SELECT eid_task_cancel_observed_v1(%s,%s,%s) AS outcome",
                            (task_id, UUID(context.actor_id), request_id)).fetchone()["outcome"]
    if decision["status"] in {"not_found", "forbidden"}:
        raise ApiError(404, "TASK_NOT_FOUND", "任务不存在或不可访问")
    if decision["status"] == "too_late":
        raise ApiError(409, "TASK_CANCEL_TOO_LATE", "任务已结束，无法取消",
                       details={"status": "too_late"})
    if decision["status"] == "action_unavailable":
        raise ApiError(409, "TASK_ACTION_UNAVAILABLE", "当前任务无法取消",
                       details={"reason": "EXTERNAL_EFFECT_UNKNOWN"})
    if decision["status"] != "cancel_requested":
        raise ApiError(503, "TASK_STORAGE_UNAVAILABLE", "任务存储不可用", retryable=True)
    return read(conn, subject, workspace_id, task_id)


def retry(conn, subject, workspace_id, task_id, key, request_id, trace_id):
    # The workspace policy lock is held by _owned through this transaction.
    # Lock the parent as well so terminal/cancel races resolve before the child
    # and its independent receipt, delegation, event and Outbox are committed.
    _, context, _ = _owned(conn, subject, workspace_id, task_id)
    parent = conn.execute("SELECT * FROM durable_task WHERE id=%s FOR UPDATE", (task_id,)).fetchone()
    if not parent or parent["actor_id"] != UUID(context.actor_id):
        raise ApiError(404, "TASK_NOT_FOUND", "任务不存在或不可访问")
    _, can_retry, reason = _capabilities(parent)
    if not can_retry:
        raise ApiError(409, "TASK_ACTION_UNAVAILABLE", "当前任务无法重试",
                       details={"reason": reason})
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise AccessDenied()
    command = SubmitTask.model_validate(parent["input"])
    child_key = "retry:" + task_id.hex + ":" + hashlib.sha256(key.encode("ascii")).hexdigest()[:32]
    return submit(conn, subject, workspace_id, command, child_key, request_id, trace_id,
                  parent_task_id=task_id)
