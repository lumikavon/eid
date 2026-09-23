"""Task commands own a single short caller transaction; never contact the Broker."""
import re
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied, authorize
from ..access.repository import checked, create_delegation
from ..errors import ApiError
from ..task_contract import InventoryResult, TaskEnvelope, TaskSnapshot, payload_hash, wire_time


def snapshot(row):
    prefix = f"/api/v1/workspaces/{row['workspace_id']}/tasks/{row['id']}"
    return TaskSnapshot(task_id=row["id"], state=row["state"], stage=row["stage"],
                        category=row["category"], operation=row["operation"],
                        attempt=row["attempt"], current_seq=row["current_seq"],
                        result_ref=row["result_id"], error=row["error_code"],
                        created_at=row["created_at"], updated_at=row["updated_at"],
                        status_url=prefix, result_url=prefix + "/result")


def submit(conn, subject, workspace_id, command, key, request_id, trace_id):
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
        INSERT INTO durable_task(id,workspace_id,actor_id,delegation_id,input,input_hash,
                                 request_id,trace_id,created_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """, (task_id, workspace_id, context.actor_id, delegation["delegation_id"],
               Jsonb(body), digest, request_id, trace_id, now, now)).fetchone()
    for dependency in command.depends_on:
        conn.execute("INSERT INTO task_dependency(task_id,depends_on) VALUES (%s,%s)",
                     (task_id, dependency))
    conn.execute("""INSERT INTO task_event(event_id,task_id,seq,event_type,state,occurred_at)
                 VALUES (%s,%s,1,'task.queued','QUEUED',%s)""", (event_id, task_id, now))
    conn.execute("INSERT INTO task_outbox(event_id,task_id,envelope,envelope_hash) VALUES (%s,%s,%s,%s)",
                 (event_id, task_id, Jsonb(envelope), payload_hash(envelope)))
    conn.execute("""INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,
                 before_policy,after_policy,request_id,trace_id) VALUES
                 (%s,%s,%s,%s,'task.inventory.submit','{}',%s,%s,%s)""",
                 (audit_id, workspace_id, context.actor_id, task_id,
                  Jsonb({"task_id": str(task_id), "input_hash": digest,
                         "policy_epoch": list(context.policy_epoch), "accepted_at": wire_time(now)}),
                  request_id, trace_id))
    conn.execute("""INSERT INTO task_receipt(actor_id,workspace_id,idempotency_key,
                 payload_hash,task_id,audit_id) VALUES (%s,%s,%s,%s,%s,%s)""",
                 (context.actor_id, workspace_id, key, digest, task_id, audit_id))
    return snapshot(row)


def _owned(conn, subject, workspace_id, task_id):
    facts, _, context = checked(conn, subject, workspace_id, "inventory:read")
    row = conn.execute("SELECT * FROM durable_task WHERE id=%s AND workspace_id=%s AND actor_id=%s",
                       (task_id, workspace_id, context.actor_id)).fetchone()
    if not row:
        raise ApiError(404, "TASK_NOT_FOUND", "任务不存在或不可访问")
    return facts, context, row


def read(conn, subject, workspace_id, task_id):
    return snapshot(_owned(conn, subject, workspace_id, task_id)[2])


def result(conn, subject, workspace_id, task_id):
    facts, context, task = _owned(conn, subject, workspace_id, task_id)
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
    # Every retained identifier is rechecked. A changed/recycled/expired source
    # makes the old summary unavailable instead of disclosing stale membership.
    for item in value.items:
        resource = conn.execute("SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s",
                                (item.resource_id, workspace_id)).fetchone()
        if not resource:
            raise AccessDenied()
        authorize(facts, "resource:read", resource)
        current = conn.execute("SELECT kind,revision,visibility FROM discovery_record "
                               "WHERE resource_id=%s FOR SHARE", (item.resource_id,)).fetchone()
        if (not current or current["visibility"] != "visible" or current["kind"] != item.kind
                or resource["kind"] != item.kind or current["revision"] != item.revision
                or resource["policy_epoch"] != item.resource_epoch):
            raise AccessDenied()
    return value
