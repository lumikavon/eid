"""Current-grant template reads and atomic initial document creation."""

import re
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied, authorize
from ..access.repository import checked
from ..errors import ApiError
from .domain import DISCOVERY_TYPES, canonical_request_hash, content_hash, initial_ast, outline
from .schemas import catalog_items


GOVERNED_PROJECTION = (
    ",to_jsonb(gr) AS governed_resource,p.rule_refs AS governed_manifest,p.manifest_sha256 ")
GOVERNED_JOINS = (
    " LEFT JOIN template_version_policy p ON p.version_id=v.id "
    " LEFT JOIN template_governed_family g ON g.template_id=v.template_id "
    "AND g.workspace_id=w.workspace_id "
    " LEFT JOIN access_resource gr ON gr.id=g.resource_id AND gr.workspace_id=w.workspace_id ")
TEMPLATE_BASE_SQL = (
    "SELECT v.*,t.owner_id,s.status,w.active AS workspace_active" + GOVERNED_PROJECTION +
    "FROM template_version v JOIN template t ON t.id=v.template_id "
    "JOIN template_version_state s ON s.version_id=v.id "
    "JOIN template_workspace w ON w.version_id=v.id AND w.workspace_id=%s" + GOVERNED_JOINS +
    "WHERE v.id=%s")


def _visible(facts, row):
    if (row is None or row["workspace_active"] is not True
            or row["development_only"] is not True
            or row["classification"] > facts["clearance"]):
        return False
    if row["fixture_owner"] != "story-2.1":
        resource = row.get("governed_resource")
        manifest = row.get("governed_manifest")
        if (row["fixture_owner"] is not None or not isinstance(resource, dict)
                or resource.get("kind") != "template" or not isinstance(manifest, dict)
                or content_hash(manifest) != row.get("manifest_sha256")):
            return False
        try:
            authorize(facts, "resource:read", resource)
        except AccessDenied:
            return False
    scope = row["scope"]
    if scope == "personal":
        return str(row["owner_id"]) == str(facts["actor_id"])
    if row["owner_id"] is not None:
        return False
    expected = {"enterprise": None, "department": facts["department"],
                "product_line": facts["product_id"], "project": facts["project_id"]}
    return scope in expected and row["target_scope_value"] == expected[scope]


def _card(row):
    return {"template_id": row["template_id"], "version_id": row["id"],
            "name": row["name"], "description": row["description"],
            "scope": row["scope"], "category": row["category"],
            "document_type": row["document_type"], "version_label": row["version_label"],
            "development_only": True, "outline": outline(row["structure"])}


def type_catalog(conn, subject, workspace_id):
    checked(conn, subject, workspace_id)
    grants = conn.execute(
        "SELECT scope FROM document_knowledge_scope_grant WHERE workspace_id=%s AND active",
        (workspace_id,),
    ).fetchall()
    return catalog_items({row["scope"] for row in grants})


def list_templates(conn, subject, workspace_id, filters):
    facts, _, _ = checked(conn, subject, workspace_id)
    rows = conn.execute(
        "SELECT v.*,t.owner_id,s.status,w.active AS workspace_active" + GOVERNED_PROJECTION +
        "FROM template_workspace w JOIN template_version v ON v.id=w.version_id "
        "JOIN template t ON t.id=v.template_id "
        "JOIN template_version_state s ON s.version_id=v.id" + GOVERNED_JOINS +
        "WHERE w.workspace_id=%s AND w.active AND s.status='active' "
        "ORDER BY v.name,v.id", (workspace_id,),
    ).fetchall()
    items = []
    for row in rows:
        if not _visible(facts, row):
            continue
        if filters.scope is not None and row["scope"] != filters.scope:
            continue
        if filters.category is not None and row["category"] != filters.category:
            continue
        if filters.document_type is not None and row["document_type"] != filters.document_type:
            continue
        if filters.query is not None and filters.query.casefold() not in (
                row["name"] + " " + row["description"] + " " + row["category"]).casefold():
            continue
        items.append(_card(row))
    return {"items": items}


def template_detail(conn, subject, workspace_id, version_id):
    facts, _, _ = checked(conn, subject, workspace_id)
    row = conn.execute(TEMPLATE_BASE_SQL, (workspace_id, version_id)).fetchone()
    if not _visible(facts, row) or row["status"] != "active":
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "模板版本不存在或当前不可见")
    return _card(row) | {"structure": row["structure"]}


def _document_row(conn, facts, workspace_id, document_id):
    resource = conn.execute(
        "SELECT * FROM access_resource WHERE id=%s AND workspace_id=%s AND kind='document'",
        (document_id, workspace_id),
    ).fetchone()
    if resource is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可见")
    try:
        authorize(facts, "resource:read", resource)
    except AccessDenied as exc:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可见") from exc
    row = conn.execute(
        "SELECT d.*,v.ast,v.base_version_id,v.content_hash "
        "FROM document d JOIN document_version v "
        "ON v.id=d.head_version_id AND v.document_id=d.id "
        "WHERE d.id=%s AND d.workspace_id=%s AND d.owner_id=%s "
        "AND d.head_version_id=%s",
        (document_id, workspace_id, resource["owner_id"], resource["head_ref"]),
    ).fetchone()
    if row is None:
        raise ApiError(503, "DOCUMENT_INTEGRITY_UNAVAILABLE", "文档版本当前不可用", retryable=True)
    if content_hash(row["ast"]) != row["content_hash"]:
        raise ApiError(503, "DOCUMENT_INTEGRITY_UNAVAILABLE", "文档版本当前不可用", retryable=True)
    return {"id": row["id"], "workspace_id": row["workspace_id"],
            "name": resource["title"], "document_type": row["document_type"],
            "knowledge_scope": row["knowledge_scope"],
            "template_version_id": row["template_version_id"],
            "version_id": row["head_version_id"], "revision": row["revision"],
            "base_version_id": row["base_version_id"], "content_hash": row["content_hash"],
            "ast": row["ast"]}


def read_document(conn, subject, workspace_id, document_id):
    facts, _, _ = checked(conn, subject, workspace_id)
    return _document_row(conn, facts, workspace_id, document_id) | {"replayed": False}


def _scope_allowed(conn, workspace_id, knowledge_scope):
    conn.execute("SELECT eid_lock_document_knowledge_scope_v1(%s,%s)",
                 (workspace_id, knowledge_scope))
    row = conn.execute(
        "SELECT active FROM document_knowledge_scope_grant "
        "WHERE workspace_id=%s AND scope=%s",
        (workspace_id, knowledge_scope),
    ).fetchone()
    if row is None or row["active"] is not True:
        raise ApiError(403, "KNOWLEDGE_SCOPE_DENIED", "当前工作区未授予此知识范围")


def _local_write_target(conn):
    row = conn.execute(
        "SELECT current_database() AS database_name, "
        "shobj_description(oid,'pg_database') AS marker "
        "FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if row != {"database_name": "eid_local_dev", "marker": "eid-local-dev-v1"}:
        raise ApiError(503, "WRITE_TARGET_UNAVAILABLE", "本地专用文档库未核实", retryable=True)


def _lock_template_family(conn, workspace_id, template_id):
    conn.execute("SELECT eid_lock_template_creation_v1(%s,%s)",
                 (workspace_id, template_id))


def _version_template_id(conn, version_id):
    row = conn.execute("SELECT template_id FROM template_version WHERE id=%s",
                       (version_id,)).fetchone()
    return row["template_id"] if row is not None else None


def _template_for_creation(conn, facts, workspace_id, command):
    if hasattr(command, "template_version_id"):
        template_id = _version_template_id(conn, command.template_version_id)
        if template_id is None:
            raise ApiError(404, "TEMPLATE_NOT_FOUND", "模板版本不存在或当前不可见")
        _lock_template_family(conn, workspace_id, template_id)
        row = conn.execute(
            TEMPLATE_BASE_SQL, (workspace_id, command.template_version_id),
        ).fetchone()
        if not _visible(facts, row):
            raise ApiError(404, "TEMPLATE_NOT_FOUND", "模板版本不存在或当前不可见")
        if row["status"] != "active":
            raise ApiError(409, "TEMPLATE_DEPRECATED", "所选模板版本已废弃")
        return row

    # The template-id form chooses and pins the newest currently active visible
    # version while the root, workspace and version-state rows remain locked.
    _lock_template_family(conn, workspace_id, command.template_id)
    rows = conn.execute(
        "SELECT v.*,t.owner_id,s.status,w.active AS workspace_active" + GOVERNED_PROJECTION +
        "FROM template t JOIN template_version v ON v.template_id=t.id "
        "JOIN template_version_state s ON s.version_id=v.id "
        "JOIN template_workspace w ON w.version_id=v.id AND w.workspace_id=%s" + GOVERNED_JOINS +
        "WHERE t.id=%s ORDER BY v.created_at DESC,v.id DESC",
        (workspace_id, command.template_id),
    ).fetchall()
    visible = [row for row in rows if _visible(facts, row)]
    if not visible:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "模板不存在或当前不可见")
    for row in visible:
        if row["status"] == "active":
            return row
    raise ApiError(409, "TEMPLATE_DEPRECATED", "所选模板版本已废弃")


def _recheck_replay_template(conn, facts, workspace_id, version_id):
    template_id = _version_template_id(conn, version_id)
    if template_id is None:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "模板版本不存在或当前不可见")
    _lock_template_family(conn, workspace_id, template_id)
    row = conn.execute(TEMPLATE_BASE_SQL,
                       (workspace_id, version_id)).fetchone()
    if not _visible(facts, row):
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "模板版本不存在或当前不可见")
    # A successfully created document remains readable after later deprecation.
    # Replay only rechecks current template visibility; it does not create again.


def create_document(conn, subject, workspace_id, command, *, idempotency_key, request_id, trace_id):
    if (not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id)
            or not re.fullmatch(r"[0-9a-f]{32}", trace_id)):
        raise ApiError(422, "REQUEST_VALIDATION_ERROR", "请求标识格式无效")
    # The same exclusive lock serializes membership changes, workspace grants and
    # all creation attempts. Replays still require the current document:create grant.
    facts, _, context = checked(conn, subject, workspace_id, "document:create", exclusive=True)
    _local_write_target(conn)
    _scope_allowed(conn, workspace_id, command.knowledge_scope)
    digest = canonical_request_hash(workspace_id, command)
    receipt = conn.execute(
        "SELECT payload_hash,document_id FROM document_creation_receipt "
        "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
        (facts["actor_id"], workspace_id, idempotency_key),
    ).fetchone()
    if receipt is not None:
        if receipt["payload_hash"] != digest:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一幂等键不能用于不同创建请求")
        document = _document_row(conn, facts, workspace_id, receipt["document_id"])
        _recheck_replay_template(conn, facts, workspace_id, document["template_version_id"])
        return document | {"replayed": True}

    # The state row is the deprecation authority. A concurrent deprecation must
    # either finish before this lock or wait for this transaction to complete.
    template = _template_for_creation(conn, facts, workspace_id, command)
    template_version_id = template["id"]
    if template["document_type"] != command.document_type:
        raise ApiError(422, "TEMPLATE_TYPE_MISMATCH", "所选模板与文种不匹配",
                       details={"field": "document_type"})
    try:
        name = command.name if hasattr(command, "name") else command.title
        ast = initial_ast(name, command.document_type, command.knowledge_scope,
                          template_version_id, template["structure"])
    except ValueError as exc:
        raise ApiError(503, "TEMPLATE_STRUCTURE_UNAVAILABLE", "模板结构当前不可用",
                       retryable=True) from exc
    now = facts["evaluated_at"]
    ast_digest = content_hash(ast)
    document_id, version_id, operation_id = uuid4(), uuid4(), uuid4()
    conn.execute(
        "INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,"
        "product_id,department,owner_id,classification,approval_state,publication_state,"
        "head_ref,valid_from) VALUES (%s,%s,%s,'document',%s,%s,%s,%s,%s,%s,'draft',"
        "'unpublished',%s,%s)",
        (document_id, workspace_id, name, facts["project_id"], facts["customer_id"],
         facts["product_id"], facts["department"], facts["actor_id"],
         context.classification, version_id, now),
    )
    conn.execute(
        "INSERT INTO document(id,workspace_id,owner_id,document_type,knowledge_scope,"
        "template_version_id,head_version_id,revision,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s)",
        (document_id, workspace_id, facts["actor_id"], command.document_type,
         command.knowledge_scope, template_version_id, version_id, now),
    )
    conn.execute(
        "INSERT INTO document_version(id,document_id,revision,base_version_id,content_hash,"
        "ast,created_by,created_at) VALUES (%s,%s,1,NULL,%s,%s,%s,%s)",
        (version_id, document_id, ast_digest, Jsonb(ast), facts["actor_id"], now),
    )
    conn.execute(
        "INSERT INTO discovery_record(resource_id,kind,created_by,created_at,updated_at,"
        "document_type,lifecycle,version_label,visibility,revision) "
        "VALUES (%s,'document',%s,%s,%s,%s,'DRAFT','1.0','visible',1)",
        (document_id, facts["actor_id"], now, now, DISCOVERY_TYPES[command.document_type]),
    )
    conn.execute(
        "INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,"
        "after_policy,request_id,trace_id,occurred_at) "
        "VALUES (%s,%s,%s,%s,'document.create',%s,%s,%s,%s,%s)",
        (operation_id, workspace_id, facts["actor_id"], document_id, Jsonb({}),
         Jsonb({"template_version_id": str(template_version_id),
                "document_type": command.document_type, "knowledge_scope": command.knowledge_scope,
                "policy_epoch": list(context.policy_epoch), "result": "success"}),
         request_id, trace_id, now),
    )
    conn.execute(
        "INSERT INTO document_creation_receipt(actor_id,workspace_id,idempotency_key,"
        "payload_hash,document_id,operation_id,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (facts["actor_id"], workspace_id, idempotency_key, digest,
         document_id, operation_id, now),
    )
    return {"id": document_id, "workspace_id": workspace_id, "name": name,
            "document_type": command.document_type, "knowledge_scope": command.knowledge_scope,
            "template_version_id": template_version_id, "version_id": version_id,
            "base_version_id": None, "content_hash": ast_digest,
            "revision": 1, "ast": ast, "replayed": False}
