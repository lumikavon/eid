"""短事务内的当前授权投影、私人收藏与可见性恢复。"""
import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied, authorize
from ..access.repository import checked
from ..errors import ApiError
from .policy import authorize_restore
from .schemas import Item

MAX_PAGE_BYTES = 60000
STORAGE_DEFINITION = "pg_column_size(discovery_record)+pg_column_size(access_resource.title)"

# 工作区事实由 checked 在同一事务持锁获取。资源条件与 authorize(resource:read) 对齐。
# 聚合与分页共同消费一个 MATERIALIZED CTE，不先分页后统计，也不因关系 join 重复记录。
# 待办谓词只在 scoped 定义一次；集合和摘要复用它，并与已有筛选取交集。
AUTHORIZED_SQL = """
WITH scoped AS (
 SELECT d.*, r.workspace_id, r.title, r.owner_id, r.policy_epoch AS resource_epoch,
        (d.kind='document' AND d.lifecycle='DRAFT' AND d.visibility='visible'
         AND r.owner_id=%(actor)s AND %(can_edit)s) AS is_todo,
        coalesce(f.active,false) AS favorite, coalesce(f.revision,0) AS favorite_revision,
        EXISTS (SELECT 1 FROM discovery_participant p
                WHERE p.resource_id=d.resource_id AND p.identity_id=%(actor)s) AS participating,
        (pg_column_size(d)+pg_column_size(r.title))::bigint AS metadata_bytes
 FROM discovery_record d JOIN access_resource r ON r.id=d.resource_id
 LEFT JOIN discovery_favorite f ON f.resource_id=d.resource_id AND f.actor_id=%(actor)s
 WHERE r.workspace_id=%(workspace)s AND d.kind=r.kind AND length(r.title) BETWEEN 1 AND 512
 AND r.valid_from<=%(now)s AND (r.valid_until IS NULL OR r.valid_until>%(now)s)
 AND r.classification BETWEEN 0 AND %(clearance)s AND r.policy_epoch>0
 AND (r.project_id=ANY(%(project_scope)s) OR '*'=ANY(%(project_scope)s))
 AND (r.customer_id=ANY(%(customer_scope)s) OR '*'=ANY(%(customer_scope)s))
 AND (r.product_id=ANY(%(product_scope)s) OR '*'=ANY(%(product_scope)s))
 AND (r.department=ANY(%(department_scope)s) OR '*'=ANY(%(department_scope)s))
 AND (%(owner_scope)s='any' OR r.owner_id=%(actor)s)
 AND r.approval_state=ANY(%(approval_states)s)
 AND d.visibility=%(visibility)s
 AND (%(kind)s::text IS NULL OR d.kind=%(kind)s)
 AND (%(document_type)s::text IS NULL OR d.document_type=%(document_type)s)
 AND (%(lifecycle)s::text IS NULL OR d.lifecycle=%(lifecycle)s)
 AND (%(tab)s='recent'
      OR (%(tab)s='created' AND d.created_by=%(actor)s)
      OR (%(tab)s='favorites' AND coalesce(f.active,false))
      OR (%(tab)s='participating' AND EXISTS (
          SELECT 1 FROM discovery_participant p
          WHERE p.resource_id=d.resource_id AND p.identity_id=%(actor)s)))
 AND (%(query)s::text IS NULL OR strpos(lower(r.title),lower(%(query)s))>0)
), authorized AS MATERIALIZED (
 SELECT * FROM scoped
 WHERE (%(collection)s='all'
        OR (%(collection)s='todo' AND is_todo)
        OR (%(collection)s='references' AND kind IN ('knowledge','reference')))
), page AS (
 SELECT * FROM authorized
 WHERE (%(after_time)s::timestamptz IS NULL
        OR (updated_at,resource_id)<(%(after_time)s::timestamptz,%(after_id)s::uuid))
 ORDER BY updated_at DESC,resource_id DESC LIMIT %(fetch_limit)s
)
SELECT (SELECT count(*) FROM authorized) AS total_count,
       (SELECT coalesce(sum(metadata_bytes),0)::bigint FROM authorized) AS metadata_bytes,
       (SELECT count(*) FROM authorized WHERE kind='document'
        AND created_at>=%(week_start)s AND created_at<=%(now)s) AS week_count,
       (SELECT count(*) FROM authorized WHERE is_todo) AS todo_count,
       (SELECT max(updated_at) FROM authorized) AS last_activity_at,
       coalesce((SELECT jsonb_agg(to_jsonb(page) ORDER BY updated_at DESC,resource_id DESC)
                 FROM page),'[]'::jsonb) AS items
"""

RECORD_SQL = """
 SELECT d.*,r.workspace_id,r.title,r.policy_epoch AS resource_epoch,
        coalesce(f.active,false) AS favorite,coalesce(f.revision,0) AS favorite_revision,
        EXISTS (SELECT 1 FROM discovery_participant p WHERE p.resource_id=d.resource_id
                AND p.identity_id=%s) AS participating
 FROM discovery_record d JOIN access_resource r ON r.id=d.resource_id
 LEFT JOIN discovery_favorite f ON f.resource_id=d.resource_id AND f.actor_id=%s
 WHERE d.resource_id=%s AND r.workspace_id=%s AND d.kind=r.kind
 AND length(r.title) BETWEEN 1 AND 512
"""


def public_context(context):
    return {"actor_id": context.actor_id, "workspace_id": context.workspace_id,
            "policy_epoch": list(context.policy_epoch)}


def item_payload(record):
    keys = set(Item.model_fields) - {"id"}
    return Item.model_validate({key: record[key] for key in keys} |
                               {"id": record["resource_id"]}).model_dump(mode="json")


def _binding(facts, context, filters, query):
    # 绑定服务端当前权限内容，防止错误维护 epoch 的调用方复用旧筛选游标。
    policy = {key: facts[key] for key in (
        "roles", "project_scope", "customer_scope", "product_scope", "department_scope",
        "owner_scope", "approval_states", "clearance", "valid_from", "valid_until",
        "classification", "project_id", "customer_id", "product_id", "department")}
    payload = {"context": public_context(context), "policy": policy,
               "filters": filters.model_dump(exclude={"cursor"}), "query": query}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str,
                                    separators=(",", ":")).encode()).hexdigest()


def _invalid_cursor():
    return ApiError(422, "INVALID_CURSOR", "分页上下文已失效，请从首页重新读取")


def decode_cursor(cursor, binding):
    if cursor is None:
        return None, None
    try:
        if len(cursor) > 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError()
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        value = json.loads(raw)
        if (not isinstance(value, dict) or set(value) != {"v", "binding", "at", "id"}
                or type(value["v"]) is not int or value["v"] != 1
                or value["binding"] != binding or not isinstance(value["at"], str)
                or not isinstance(value["id"], str)):
            raise ValueError()
        position = datetime.fromisoformat(value["at"].replace("Z", "+00:00"))
        if position.tzinfo is None or position.utcoffset() != timedelta(0):
            raise ValueError()
        resource_id = UUID(value["id"])
        if str(resource_id) != value["id"]:
            raise ValueError()
        return position, resource_id
    except (ValueError, TypeError, KeyError, OverflowError, binascii.Error, UnicodeError) as exc:
        raise _invalid_cursor() from exc


def encode_cursor(item, binding):
    value = {"v": 1, "binding": binding, "at": item["updated_at"], "id": item["id"]}
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def projection_params(facts, filters, *, query=None, after=(None, None), fetch_limit=None):
    now = facts["evaluated_at"].astimezone(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"actor": facts["actor_id"], "workspace": facts["workspace_id"], "now": now,
            "clearance": facts["clearance"], "owner_scope": facts["owner_scope"],
            **{name: facts[name] for name in ("project_scope", "customer_scope", "product_scope",
                                             "department_scope", "approval_states")},
            **filters.model_dump(exclude={"cursor", "limit", "query"}),
            "query": query, "after_time": after[0], "after_id": after[1],
            "fetch_limit": filters.limit + 1 if fetch_limit is None else fetch_limit,
            "week_start": week_start, "can_edit": "author" in facts["roles"]}


def storage_payload(row, params):
    return {"metadata_bytes": row["metadata_bytes"], "measured_at": params["now"],
            "scope": "authorized_filtered_record_metadata", "definition": STORAGE_DEFINITION,
            "visibility": params["visibility"], "attachment_bytes": None, "quota_bytes": None}


def list_records(conn, subject, workspace_id, filters, *, query=None):
    facts, _, context = checked(conn, subject, workspace_id)
    binding = _binding(facts, context, filters, query)
    after = decode_cursor(filters.cursor, binding)
    params = projection_params(facts, filters, query=query, after=after)
    result = conn.execute(AUTHORIZED_SQL, params).fetchone()
    page, size = [], 0
    for row in result["items"][:filters.limit]:
        item = item_payload(row)
        encoded = len(json.dumps(item, ensure_ascii=False).encode())
        if page and size + encoded > MAX_PAGE_BYTES:
            break
        page.append(item)
        size += encoded
    return {"items": page, "total_count": result["total_count"],
            "next_cursor": encode_cursor(page[-1], binding) if len(result["items"]) > len(page) else None,
            "context": public_context(context), "storage": storage_payload(result, params)}


FUNCTIONS = (
    ("documents", "项目文档", "文档 documents"),
    ("favorites", "我的收藏", "收藏 favorites"),
    ("references", "参考资料", "参考 知识 references knowledge"),
    ("recycle", "回收站", "回收 recycle"),
    ("project", "项目详情", "项目 project"),
)


def search_records(conn, subject, workspace_id, filters):
    result = list_records(conn, subject, workspace_id, filters, query=filters.query)
    # 五个入口仅需当前 workspace:read；写能力和创建等功能不进入此目录。
    result["functions"] = [{"id": key, "title": title, "route": key,
                             "workspace_id": str(workspace_id)}
                            for key, title, terms in FUNCTIONS
                            if filters.query.casefold() in (title + " " + terms).casefold()]
    return result


FUTURE_PANELS = (
    {"id": "review", "value": None, "state": "not_collected", "reason": "尚无审校业务数据", "owner": "5-2"},
    {"id": "ai_words", "value": None, "state": "not_collected", "reason": "尚无真实生成字数来源", "owner": "4-2"},
    {"id": "quality", "value": None, "state": "not_evaluated", "reason": "质量指标尚未评估", "owner": "9-1"},
    {"id": "templates", "value": None, "state": "unavailable", "reason": "模板治理尚未开放", "owner": "2-4"},
    {"id": "recommendations", "value": None, "state": "unavailable", "reason": "推荐依赖尚未就绪", "owner": "3-4"},
    {"id": "creation", "value": None, "state": "unavailable", "reason": "正文创建尚未开放", "owner": "2-1"},
)


def summary(conn, subject, workspace_id, filters):
    if filters.cursor:
        raise _invalid_cursor()
    facts, _, context = checked(conn, subject, workspace_id)
    params = projection_params(facts, filters, fetch_limit=0)
    result = conn.execute(AUTHORIZED_SQL, params).fetchone()
    return {"context": public_context(context),
            "workspace": {"id": str(workspace_id), "name": facts["workspace_name"],
                          "slug": facts["workspace_slug"],
                          **{key: facts[key] for key in ("project_id", "customer_id", "product_id",
                                                         "department", "classification")}},
            "total_count": result["total_count"], "storage": storage_payload(result, params),
            "week_new_documents": {"value": result["week_count"], "window_start": params["week_start"],
                                   "window_end": params["now"],
                                   "definition": "authorized_filtered_documents_created_since_utc_monday"},
            "todo_count": result["todo_count"], "last_activity_at": result["last_activity_at"],
            "future_panels": list(FUTURE_PANELS)}


def _record(conn, facts, resource_id):
    row = conn.execute(RECORD_SQL, (facts["actor_id"], facts["actor_id"], resource_id,
                                   facts["workspace_id"])).fetchone()
    if row is None:
        raise AccessDenied()
    return row


def _restore_policy(conn, facts, record):
    return conn.execute("SELECT * FROM discovery_restore_policy WHERE workspace_id=%s AND kind=%s",
                        (facts["workspace_id"], record["kind"])).fetchone()


def _database_identity(conn):
    return conn.execute("SELECT current_database() AS database_name, "
                        "shobj_description(oid,'pg_database') AS marker FROM pg_database "
                        "WHERE datname=current_database()").fetchone()


def detail(conn, subject, workspace_id, resource_id, *, environment):
    facts, resource, resource_context = checked(conn, subject, workspace_id, "resource:read", resource_id)
    workspace_context = authorize(facts, "workspace:read")
    record = _record(conn, facts, resource_id)
    policy = _restore_policy(conn, facts, record)
    can_restore = False
    try:
        authorize_restore(facts, resource, record, policy, environment=environment,
                          database_identity=_database_identity(conn))
        can_restore = record["visibility"] == "recycled"
    except AccessDenied:
        pass
    return {"item": item_payload(record), "context": public_context(workspace_context),
            "resource_context": public_context(resource_context), "content_state": "metadata_only",
            "actions": {"favorite": True, "restore": can_restore,
                        "restore_policy_version": policy["version"] if can_restore else None}}


def _conflict(code="REVISION_CONFLICT"):
    return ApiError(409, code, "状态已变化，请重新读取后确认操作")


def _payload_hash(action, resource_id, command):
    payload = {"action": action, "resource_id": str(resource_id), **command.model_dump()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def collection_command(conn, subject, workspace_id, resource_id, command, *, action,
                       idempotency_key, request_id, trace_id, environment):
    if (action not in {"favorite.set", "restore_visibility"}
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id)
            or not re.fullmatch(r"[0-9a-f]{32}", trace_id)):
        raise AccessDenied()
    # 所有集合写入与成员授权变更使用同一独占锁，重放也先取当前权限。
    facts, resource, context = checked(conn, subject, workspace_id, "resource:read", resource_id,
                                       exclusive=True)
    workspace_context = authorize(facts, "workspace:read")
    record = _record(conn, facts, resource_id)
    policy = None
    if action == "restore_visibility":
        policy = _restore_policy(conn, facts, record)
        authorize_restore(facts, resource, record, policy, environment=environment,
                          database_identity=_database_identity(conn))
        if command.policy_version != policy["version"]:
            raise _conflict("RESTORE_POLICY_CONFLICT")
    digest = _payload_hash(action, resource_id, command)
    receipt = conn.execute("SELECT * FROM discovery_receipt WHERE actor_id=%s AND workspace_id=%s "
                           "AND idempotency_key=%s", (facts["actor_id"], workspace_id,
                                                     idempotency_key)).fetchone()
    if receipt is not None:
        if receipt["payload_hash"] != digest:
            raise _conflict("IDEMPOTENCY_CONFLICT")
        return {"operation_id": str(receipt["operation_id"]), "action": action,
                "resource_id": str(resource_id), "replayed": True,
                "occurred_at": receipt["occurred_at"], "context": public_context(workspace_context),
                "current": item_payload(record)}
    now = facts["evaluated_at"]
    if action == "favorite.set":
        if command.expected_revision != record["favorite_revision"]:
            raise _conflict()
        before = {"favorite": record["favorite"], "revision": record["favorite_revision"]}
        after = {"favorite": command.favorite, "revision": record["favorite_revision"] + 1}
        conn.execute("""
            INSERT INTO discovery_favorite(resource_id,actor_id,active,revision,updated_at)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT(resource_id,actor_id) DO UPDATE
            SET active=EXCLUDED.active,revision=EXCLUDED.revision,updated_at=EXCLUDED.updated_at
            """, (resource_id, facts["actor_id"], after["favorite"], after["revision"], now))
    else:
        if command.expected_revision != record["revision"] or record["visibility"] != "recycled":
            raise _conflict()
        before = {"visibility": record["visibility"], "revision": record["revision"]}
        after = {"visibility": "visible", "revision": record["revision"] + 1}
        conn.execute("UPDATE discovery_record SET visibility='visible',revision=revision+1, "
                     "updated_at=%s WHERE resource_id=%s", (now, resource_id))
    operation_id = uuid4()
    evidence = {"policy_version": policy["version"] if policy else None,
                "policy_epoch": list(context.policy_epoch), "result": "success"}
    conn.execute("""
        INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,
                                 after_policy,request_id,trace_id,occurred_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (operation_id, workspace_id, facts["actor_id"], resource_id, action,
               Jsonb(before), Jsonb(after | evidence), request_id, trace_id, now))
    conn.execute("""
        INSERT INTO discovery_receipt(actor_id,workspace_id,idempotency_key,operation_id,
                                       resource_id,action,payload_hash,occurred_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (facts["actor_id"], workspace_id, idempotency_key, operation_id, resource_id,
               action, digest, now))
    return {"operation_id": str(operation_id), "action": action, "resource_id": str(resource_id),
            "replayed": False, "occurred_at": now, "context": public_context(workspace_context),
            "current": item_payload(_record(conn, facts, resource_id))}
