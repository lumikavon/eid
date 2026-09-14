from datetime import datetime, timedelta
from uuid import uuid4
import re
import json

from psycopg.types.json import Jsonb
from psycopg import OperationalError

from .policy import AccessDenied, APPROVAL_STATES, COMMON_OPERATIONS, ROLE_OPERATIONS, authorize

CURRENT_WORKSPACE_SQL = """
    SELECT workspace_id FROM access_current_facts
    WHERE subject=%s AND (%s::uuid IS NULL OR workspace_id>%s::uuid)
      AND identity_active AND membership_active
      AND cardinality(roles)>0 AND roles <@ %s::text[]
      AND approval_states <@ %s::text[]
      AND valid_from<=statement_timestamp()
      AND (valid_until IS NULL OR valid_until>statement_timestamp())
      AND classification BETWEEN 0 AND clearance AND clearance BETWEEN 0 AND 3
      AND policy_epoch>0 AND workspace_epoch>0
      AND (project_id=ANY(project_scope) OR '*'=ANY(project_scope))
      AND (customer_id=ANY(customer_scope) OR '*'=ANY(customer_scope))
      AND (product_id=ANY(product_scope) OR '*'=ANY(product_scope))
      AND (department=ANY(department_scope) OR '*'=ANY(department_scope))
    ORDER BY workspace_id LIMIT 1
"""


def workspace_discovery_params(subject, after=None):
    return (subject, after, after, list(ROLE_OPERATIONS), sorted(APPROVAL_STATES))


def load_current(conn, subject, workspace_id, resource_id=None, *, exclusive=False):
    # Policy writes take the same workspace lock exclusively. No slow calls in this transaction.
    mode = "UPDATE" if exclusive else "SHARE"
    row = conn.execute(
        f"SELECT workspace_id FROM access_workspace WHERE workspace_id=%s FOR {mode}",
        (workspace_id,),
    ).fetchone()
    if not row:
        raise AccessDenied()
    facts = conn.execute(
        "SELECT *,clock_timestamp() AS evaluated_at FROM access_current_facts "
        "WHERE subject=%s AND workspace_id=%s",
        (subject, workspace_id),
    ).fetchone()
    resource = None
    if resource_id is not None:
        resource = conn.execute(
            "SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s",
            (resource_id, workspace_id),
        ).fetchone()
        if not resource:
            raise AccessDenied()
    return facts, resource


def checked(conn, subject, workspace_id, operation="workspace:read", resource_id=None,
            *, exclusive=False):
    facts, resource = load_current(conn, subject, workspace_id, resource_id, exclusive=exclusive)
    return facts, resource, authorize(facts, operation, resource)


def workspace_payload(facts, context):
    # Navigation capabilities are advisory; every resource use still calls authorize.
    authorize(facts, "workspace:read")
    operations = sorted(COMMON_OPERATIONS | set().union(
        *(ROLE_OPERATIONS[role] for role in facts["roles"])))
    return {"workspace_id": str(facts["workspace_id"]), "name": facts["workspace_name"],
            "slug": facts["workspace_slug"], "actor_id": str(facts["actor_id"]),
            "display_name": facts["display_name"], "department": facts["actor_department"],
            "roles": facts["roles"], "clearance": facts["clearance"],
            "policy_epoch": list(context.policy_epoch), "operations": operations}


def first_workspace(conn, subject):
    # SQL narrows discovery; only the locked, fresh pure decision below grants access.
    # A bounded retry handles a candidate revoked between discovery and its lock.
    after = None
    for _ in range(3):
        row = conn.execute(CURRENT_WORKSPACE_SQL, workspace_discovery_params(subject, after)).fetchone()
        if row is None:
            return None
        try:
            facts, _, context = checked(conn, subject, row["workspace_id"])
            return workspace_payload(facts, context)
        except AccessDenied:
            after = row["workspace_id"]
    raise OperationalError("Current workspace changed repeatedly during resolution")


def members(conn, subject, workspace_id, after=None):
    _, _, context = checked(conn, subject, workspace_id, "membership:manage")
    rows = conn.execute("""
        SELECT p.*, i.display_name, m.active FROM access_member p
        JOIN identity_account i ON i.id=p.identity_id
        JOIN workspace_membership m ON m.identity_id=p.identity_id AND m.workspace_id=p.workspace_id
        WHERE p.workspace_id=%s AND (%s::uuid IS NULL OR p.identity_id>%s::uuid)
        ORDER BY p.identity_id LIMIT 51
        """, (workspace_id, after, after)).fetchall()
    page = []
    size = 0
    for row in rows[:50]:
        encoded_size = len(json.dumps(row, default=str, ensure_ascii=False).encode("utf8"))
        if page and size + encoded_size > 60000:
            break
        page.append(row)
        size += encoded_size
    return {"members": page, "policy_epoch": list(context.policy_epoch),
            "next_cursor": str(page[-1]["identity_id"]) if len(rows)>len(page) else None}


def workspace_page(conn, subject, after=None):
    # Advance by scanned identity even when current authorization rejects an item.
    rows = conn.execute("""
        SELECT workspace_id FROM access_current_facts
        WHERE subject=%s AND (%s::uuid IS NULL OR workspace_id>%s::uuid)
        ORDER BY workspace_id LIMIT 51
        """, (subject, after, after)).fetchall()
    page = []
    size = 0
    scanned = 0
    for row in rows[:50]:
        try:
            facts, _, context = checked(conn, subject, row["workspace_id"])
            item = workspace_payload(facts, context)
        except AccessDenied:
            scanned += 1
            continue
        encoded_size = len(json.dumps(item, ensure_ascii=False).encode("utf8"))
        if scanned and size + encoded_size > 60000:
            break
        page.append(item)
        size += encoded_size
        scanned += 1
    return {"workspaces": page,
            "next_cursor": str(rows[scanned-1]["workspace_id"]) if len(rows)>scanned else None}


def change_member(conn, subject, workspace_id, target_id, policy, expected_epoch, request_id, trace_id):
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or not request_id:
        raise AccessDenied()
    facts, _, context = checked(conn, subject, workspace_id, "membership:manage", exclusive=True)
    if list(context.policy_epoch) != expected_epoch:
        return None
    before = conn.execute(
        "SELECT * FROM access_member WHERE identity_id=%s AND workspace_id=%s",
        (target_id, workspace_id),
    ).fetchone()
    if not before:
        raise AccessDenied()
    # A manager cannot delegate authority beyond its current attribute/clearance ceiling.
    if policy["clearance"] > facts["clearance"]:
        raise AccessDenied()
    for name in ("project_scope", "customer_scope", "product_scope", "department_scope"):
        if "*" not in facts[name] and not set(policy[name]).issubset(facts[name]):
            raise AccessDenied()
    if facts["owner_scope"] != "any" and policy["owner_scope"] == "any":
        raise AccessDenied()
    if not set(policy["approval_states"]).issubset(facts["approval_states"]):
        raise AccessDenied()
    if policy["valid_from"] < facts["valid_from"] or (facts["valid_until"] is not None and
            (policy["valid_until"] is None or policy["valid_until"] > facts["valid_until"])):
        raise AccessDenied()
    before_active = conn.execute(
        "SELECT active FROM workspace_membership WHERE identity_id=%s AND workspace_id=%s",
        (target_id, workspace_id),
    ).fetchone()["active"]
    columns = ("roles", "project_scope", "customer_scope", "product_scope", "department_scope",
               "owner_scope", "approval_states", "clearance", "valid_from", "valid_until")
    after = conn.execute(
        "UPDATE access_member SET " + ",".join(f"{key}=%s" for key in columns)
        + ",policy_epoch=policy_epoch+1 WHERE identity_id=%s AND workspace_id=%s RETURNING *",
        tuple(policy[key] for key in columns) + (target_id, workspace_id),
    ).fetchone()
    conn.execute("UPDATE workspace_membership SET active=%s WHERE identity_id=%s AND workspace_id=%s",
                 (policy["active"], target_id, workspace_id))
    epoch = conn.execute(
        "UPDATE access_workspace SET policy_epoch=policy_epoch+1 WHERE workspace_id=%s "
        "RETURNING policy_epoch", (workspace_id,),
    ).fetchone()["policy_epoch"]
    audit_id = uuid4()
    def serial(row):
        return {key: value.isoformat() if isinstance(value, datetime) else
                str(value) if key in {"identity_id", "workspace_id"} else value
                for key, value in row.items()}
    conn.execute("""
        INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,
        after_policy,request_id,trace_id) VALUES (%s,%s,%s,%s,'membership.change',%s,%s,%s,%s)
        """, (audit_id, workspace_id, facts["actor_id"], target_id,
               Jsonb(serial({**before, "active": before_active})),
               Jsonb(serial({**after, "active": policy["active"]})), request_id, trace_id))
    conn.execute("""
        INSERT INTO access_invalidation(id,workspace_id,actor_id,policy_epoch)
        VALUES (%s,%s,%s,%s)
        """, (audit_id, workspace_id, target_id, epoch))
    return {"audit_id": str(audit_id), "workspace_epoch": epoch}


def create_delegation(conn, subject, workspace_id, resource_id, operation, purpose, request_id, trace_id):
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or not request_id:
        raise AccessDenied()
    facts, _, context = checked(conn, subject, workspace_id, operation, resource_id)
    if operation == "membership:manage":
        raise AccessDenied()
    delegation_id = uuid4()
    expires_at = facts["evaluated_at"] + timedelta(minutes=5)
    conn.execute("""
        INSERT INTO access_delegation(id,actor_id,workspace_id,resource_id,operation,purpose,
        service_id,expires_at,issued_epoch,request_id,trace_id)
        VALUES (%s,%s,%s,%s,%s,%s,'eid-worker',%s,%s,%s,%s)
        """, (delegation_id, facts["actor_id"], workspace_id, resource_id, operation, purpose,
               expires_at, context.policy_epoch[0], request_id, trace_id))
    return {"delegation_id": str(delegation_id), "expires_at": expires_at,
            "context": context.payload() | {"request_id": request_id, "trace_id": trace_id}}
