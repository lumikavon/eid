"""模板候选、当前资源授权、不可变开发版本发布及废弃。"""
from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..access.policy import AccessDenied, authorize
from ..access.repository import checked
from ..errors import ApiError
from .domain import content_hash
from .governance_schemas import ValidationReport
from .repository import _local_write_target, _lock_template_family


def _hidden():
    return ApiError(404, "TEMPLATE_NOT_FOUND", "模板管理对象不存在或当前不可访问")


def _family(conn, facts, workspace_id, template_id):
    row = conn.execute(
        "SELECT r.*,g.template_id FROM template_governed_family g "
        "JOIN access_resource r ON r.id=g.resource_id AND r.workspace_id=g.workspace_id "
        "WHERE g.template_id=%s AND g.workspace_id=%s AND r.kind='template'",
        (template_id, workspace_id)).fetchone()
    if row is None:
        raise _hidden()
    try:
        authorize(facts, "template:publish", row)
    except AccessDenied as exc:
        raise _hidden() from exc
    return row


def _admin(conn, subject, workspace_id, *, exclusive=False):
    facts, _, _ = checked(conn, subject, workspace_id, exclusive=exclusive)
    if "template_admin" not in facts["roles"]:
        raise AccessDenied()
    return facts


def _audit(conn, facts, target, action, summary, request_id, trace_id, *, before=None):
    conn.execute(
        "INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,"
        "after_policy,request_id,trace_id,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uuid4(), facts["workspace_id"], facts["actor_id"], target, action, Jsonb(before or {}),
         Jsonb(summary), request_id, trace_id, facts["evaluated_at"]))


def _head(conn, template_id):
    return conn.execute(
        "SELECT id,scope,target_scope_value,classification FROM template_version "
        "WHERE template_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (template_id,)).fetchone()


def _candidate(conn, facts, workspace_id, candidate_id, *, include_report=True):
    report_column = "v.report" if include_report else "NULL::jsonb AS report"
    row = conn.execute(
        "SELECT c.id,c.template_id,c.workspace_id,c.actor_id,c.package_sha256,c.version_label,"
        "c.scope,c.target_scope_value,c.classification,c.base_version_id,c.created_at,"
        "v.state," + report_column + ",v.error_code,v.attempt,v.updated_at "
        "FROM template_candidate c JOIN template_validation v ON v.candidate_id=c.id "
        "WHERE c.id=%s AND c.workspace_id=%s", (candidate_id, workspace_id)).fetchone()
    if row is None:
        raise _hidden()
    _family(conn, facts, workspace_id, row["template_id"])
    if row["classification"] > facts["clearance"]:
        raise _hidden()
    return row


def _report(row):
    if row["state"] != "VALIDATED" or row["report"] is None:
        raise ApiError(409, "TEMPLATE_NOT_VALIDATED", "模板尚未通过隔离校验")
    try:
        report = ValidationReport.model_validate(row["report"])
    except (ValidationError, ValueError, TypeError) as exc:
        raise ApiError(503, "TEMPLATE_REPORT_INTEGRITY", "模板校验收据无效") from exc
    if report.source_sha256 != row["package_sha256"]:
        raise ApiError(503, "TEMPLATE_REPORT_INTEGRITY", "模板校验收据不匹配")
    return report


def _summary(conn, row, *, include_preview=True):
    result = {key: row[key] for key in (
        "id", "template_id", "workspace_id", "version_label", "scope", "classification",
        "base_version_id", "created_at", "state", "error_code", "attempt", "updated_at")}
    result["development_only"] = True
    published = conn.execute("SELECT version_id FROM template_version_policy WHERE candidate_id=%s",
                             (row["id"],)).fetchone()
    result["published_version_id"] = published["version_id"] if published else None
    head = _head(conn, row["template_id"])
    result["head_version_id"] = head["id"] if head else None
    result["preview"] = None
    if row["state"] == "VALIDATED" and include_preview:
        report = _report(row)
        result["preview"] = {"manifest": row["report"]["manifest"],
                             "manifest_sha256": report.manifest_sha256,
                             "assets": [asset.model_dump(exclude={"png_base64"}) for asset in report.assets],
                             "formal_ready": False,
                             "formal_blockers": ["官方字体、渲染主题及审批/规则引用尚未接入批准注册表"]}
    return result


def upload_candidate(conn, subject, workspace_id, metadata, raw, key, request_id, trace_id):
    facts = _admin(conn, subject, workspace_id, exclusive=True)
    _local_write_target(conn)
    if not 0 < len(raw) <= 5 * 1024 * 1024:
        raise ApiError(413, "TEMPLATE_PACKAGE_LIMIT", "模板包超过大小限制")
    digest = sha256(raw).hexdigest()
    request_hash = content_hash({"metadata": metadata.model_dump(mode="json"), "package": digest})
    receipt = conn.execute(
        "SELECT payload_hash,candidate_id FROM template_governance_receipt "
        "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
        (facts["actor_id"], workspace_id, key)).fetchone()
    if receipt:
        if receipt["payload_hash"] != request_hash:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一操作标识不能用于其他模板包")
        return _summary(conn, _candidate(conn, facts, workspace_id, receipt["candidate_id"]))
    if conn.execute("SELECT 1 FROM template_governance_action_receipt "
                    "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
                    (facts["actor_id"], workspace_id, key)).fetchone():
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "此操作标识已用于另一治理动作")
    if not facts["classification"] <= metadata.classification <= facts["clearance"]:
        raise AccessDenied()
    # The workspace lock serializes uploads; immutable candidates have no cleanup path.
    # Fail closed before another 5 MiB blob can grow the isolated development store.
    count = conn.execute("SELECT count(*) AS total FROM template_candidate WHERE workspace_id=%s",
                         (workspace_id,)).fetchone()["total"]
    if count >= 128:
        raise ApiError(409, "TEMPLATE_CANDIDATE_QUOTA", "此工作区已达到候选包上限")
    scope_value = {"enterprise": None, "personal": None, "project": facts["project_id"],
                   "department": facts["department"], "product_line": facts["product_id"]}[metadata.scope]
    family_id = metadata.template_id
    if family_id is None:
        family_id, resource_id = uuid4(), uuid4()
        target = {**{name: facts[name] for name in (
            "workspace_id", "project_id", "customer_id", "product_id", "department")},
            "owner_id": facts["actor_id"], "classification": metadata.classification,
            "approval_state": "draft", "policy_epoch": 1, "valid_from": facts["evaluated_at"],
            "valid_until": None}
        authorize(facts, "template:publish", target)
        conn.execute("INSERT INTO template(id,owner_id) VALUES (%s,%s)",
                     (family_id, facts["actor_id"] if metadata.scope == "personal" else None))
        conn.execute(
            "INSERT INTO access_resource(id,workspace_id,title,kind,project_id,customer_id,product_id,"
            "department,owner_id,classification,approval_state,publication_state,valid_from) "
            "VALUES (%s,%s,'待验证模板','template',%s,%s,%s,%s,%s,%s,'draft','unpublished',%s)",
            (resource_id, workspace_id, facts["project_id"], facts["customer_id"], facts["product_id"],
             facts["department"], facts["actor_id"], metadata.classification, facts["evaluated_at"]))
        conn.execute(
            "INSERT INTO template_governed_family(template_id,workspace_id,resource_id,created_by) "
            "VALUES (%s,%s,%s,%s)", (family_id, workspace_id, resource_id, facts["actor_id"]))
    else:
        resource = _family(conn, facts, workspace_id, family_id)
        if resource["classification"] != metadata.classification:
            raise ApiError(422, "TEMPLATE_SCOPE_CHANGED", "新版本必须保持模板家族密级")
    _lock_template_family(conn, workspace_id, family_id)
    head = _head(conn, family_id)
    if (head["id"] if head else None) != metadata.base_version_id:
        raise ApiError(409, "TEMPLATE_VERSION_CONFLICT", "模板已有新版本，请重新读取")
    origin = head or conn.execute(
        "SELECT scope,target_scope_value FROM template_candidate WHERE template_id=%s "
        "ORDER BY created_at,id LIMIT 1", (family_id,)).fetchone()
    if origin and (origin["scope"] != metadata.scope or origin["target_scope_value"] != scope_value):
        raise ApiError(422, "TEMPLATE_SCOPE_CHANGED", "新版本必须保持模板家族范围")
    candidate_id = uuid4()
    conn.execute(
        "INSERT INTO template_candidate(id,template_id,workspace_id,actor_id,package_bytes,"
        "package_sha256,version_label,scope,target_scope_value,classification,base_version_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (candidate_id, family_id, workspace_id, facts["actor_id"], raw, digest, metadata.version_label,
         metadata.scope, scope_value, metadata.classification, metadata.base_version_id))
    conn.execute(
        "INSERT INTO template_governance_receipt(actor_id,workspace_id,idempotency_key,"
        "payload_hash,candidate_id) VALUES (%s,%s,%s,%s,%s)",
        (facts["actor_id"], workspace_id, key, request_hash, candidate_id))
    _audit(conn, facts, candidate_id, "template.upload", {"package_sha256": digest}, request_id, trace_id)
    return _summary(conn, _candidate(conn, facts, workspace_id, candidate_id))


def read_candidate(conn, subject, workspace_id, candidate_id):
    facts = _admin(conn, subject, workspace_id)
    return _summary(conn, _candidate(conn, facts, workspace_id, candidate_id))


def lookup_operation(conn, subject, workspace_id, key):
    """Read only committed receipts; absence is NOT proof a timed-out write cannot commit."""
    facts = _admin(conn, subject, workspace_id)
    receipt = conn.execute(
        "SELECT candidate_id FROM template_governance_receipt "
        "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
        (facts["actor_id"], workspace_id, key)).fetchone()
    if receipt:
        return {"kind": "candidate", "candidate": _summary(conn, _candidate(
            conn, facts, workspace_id, receipt["candidate_id"]))}
    receipt = conn.execute(
        "SELECT version_id FROM template_governance_action_receipt "
        "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
        (facts["actor_id"], workspace_id, key)).fetchone()
    if receipt:
        return {"kind": "version", "version": version_detail(
            conn, subject, workspace_id, receipt["version_id"])}
    return {"kind": "unresolved"}


_RESOURCE_FILTER = """
 r.workspace_id=%(workspace_id)s AND r.valid_from<=%(evaluated_at)s
 AND (r.valid_until IS NULL OR r.valid_until>%(evaluated_at)s)
 AND r.classification BETWEEN 0 AND %(clearance)s AND r.policy_epoch>0
 AND (r.project_id=ANY(%(project_scope)s) OR '*'=ANY(%(project_scope)s))
 AND (r.customer_id=ANY(%(customer_scope)s) OR '*'=ANY(%(customer_scope)s))
 AND (r.product_id=ANY(%(product_scope)s) OR '*'=ANY(%(product_scope)s))
 AND (r.department=ANY(%(department_scope)s) OR '*'=ANY(%(department_scope)s))
 AND (%(owner_scope)s='any' OR r.owner_id=%(actor_id)s)
 AND r.approval_state=ANY(%(approval_states)s)
"""


def list_candidates(conn, subject, workspace_id, after=None):
    facts = _admin(conn, subject, workspace_id)
    rows = conn.execute(
        "SELECT c.id FROM template_candidate c JOIN template_governed_family g "
        "ON g.template_id=c.template_id AND g.workspace_id=c.workspace_id "
        "JOIN access_resource r ON r.id=g.resource_id AND r.workspace_id=c.workspace_id "
        "WHERE r.kind='template' AND " + _RESOURCE_FILTER +
        "AND c.classification<=%(clearance)s AND (%(after)s::uuid IS NULL OR c.id>%(after)s) "
        "ORDER BY c.id LIMIT 101", {**facts, "after": after}).fetchall()
    items = []
    for row in rows[:100]:
        try:
            items.append(_summary(conn, _candidate(conn, facts, workspace_id, row["id"],
                                                   include_report=False), include_preview=False))
        except ApiError as exc:
            if exc.status_code != 404:
                raise
    return {"items": items, "next_cursor": rows[99]["id"] if len(rows) > 100 else None}


def _action_receipt(conn, facts, key, digest):
    if conn.execute("SELECT 1 FROM template_governance_receipt "
                    "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
                    (facts["actor_id"], facts["workspace_id"], key)).fetchone():
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "此操作标识已用于候选包上传")
    receipt = conn.execute(
        "SELECT payload_hash,version_id FROM template_governance_action_receipt "
        "WHERE actor_id=%s AND workspace_id=%s AND idempotency_key=%s",
        (facts["actor_id"], facts["workspace_id"], key)).fetchone()
    if receipt and receipt["payload_hash"] != digest:
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一操作标识不能用于其他治理操作")
    return receipt


def _record_action(conn, facts, key, digest, version_id):
    conn.execute(
        "INSERT INTO template_governance_action_receipt(actor_id,workspace_id,idempotency_key,"
        "payload_hash,version_id) VALUES (%s,%s,%s,%s,%s)",
        (facts["actor_id"], facts["workspace_id"], key, digest, version_id))


def publish_candidate(conn, subject, workspace_id, candidate_id, command, key, request_id, trace_id):
    facts = _admin(conn, subject, workspace_id, exclusive=True)
    _local_write_target(conn)
    row = _candidate(conn, facts, workspace_id, candidate_id)
    _lock_template_family(conn, workspace_id, row["template_id"])
    if command.mode != "development":
        raise ApiError(409, "FORMAL_TEMPLATE_NOT_CONFIGURED", "官方字体、主题与批准政策未配置，禁止正式发布")
    report = _report(row)
    if report.manifest_sha256 != command.manifest_sha256:
        raise ApiError(409, "TEMPLATE_VALIDATION_CHANGED", "确认的校验摘要不匹配")
    digest = content_hash({"operation": "publish", "candidate_id": str(candidate_id),
                           "command": command.model_dump(mode="json")})
    receipt = _action_receipt(conn, facts, key, digest)
    if receipt:
        return version_detail(conn, subject, workspace_id, receipt["version_id"])
    existing = conn.execute("SELECT version_id FROM template_version_policy WHERE candidate_id=%s",
                            (candidate_id,)).fetchone()
    if existing:
        raise ApiError(409, "TEMPLATE_ALREADY_PUBLISHED", "此候选包已经发布，请查看原版本")
    head = _head(conn, row["template_id"])
    if (head["id"] if head else None) != row["base_version_id"]:
        raise ApiError(409, "TEMPLATE_VERSION_CONFLICT", "模板家族已有新版本，请提交新候选包")
    if conn.execute("SELECT 1 FROM template_version WHERE template_id=%s AND version_label=%s",
                    (row["template_id"], row["version_label"])).fetchone():
        raise ApiError(409, "TEMPLATE_VERSION_CONFLICT", "版本标签已存在")
    manifest = row["report"]["manifest"]
    if any(value is not None for value in manifest["rules"].values()):
        raise ApiError(409, "RULE_REGISTRY_UNAVAILABLE", "规则所有者注册表未接入，禁止发布未经核实的规则引用")
    version_id = uuid4()
    conn.execute(
        "INSERT INTO template_version(id,template_id,version_label,name,description,scope,"
        "target_scope_value,category,document_type,classification,structure,development_only,"
        "fixture_owner,fixture_version,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,NULL,NULL,clock_timestamp())",
        (version_id, row["template_id"], row["version_label"], manifest["name"],
         manifest["description"] or "开发模板", row["scope"], row["target_scope_value"],
         manifest["category"], manifest["document_type"], row["classification"],
         Jsonb({"sections": [{"title": s["title"]} for s in manifest["sections"]]})))
    conn.execute(
        "INSERT INTO template_version_policy(version_id,template_id,candidate_id,package_sha256,"
        "manifest_sha256,validator_version,rule_refs,sanitized_assets,validated_at,published_by,published_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
        (version_id, row["template_id"], candidate_id, row["package_sha256"], report.manifest_sha256,
         report.validator_version, Jsonb(manifest), Jsonb(row["report"]["assets"]), row["updated_at"],
         facts["actor_id"]))
    conn.execute("INSERT INTO template_version_state(version_id,status) VALUES (%s,'active')", (version_id,))
    conn.execute("INSERT INTO template_workspace(version_id,workspace_id,active) VALUES (%s,%s,true)",
                 (version_id, workspace_id))
    _audit(conn, facts, version_id, "template.publish", {"candidate_id": str(candidate_id),
           "manifest_sha256": report.manifest_sha256, "development_only": True}, request_id, trace_id)
    _record_action(conn, facts, key, digest, version_id)
    return version_detail(conn, subject, workspace_id, version_id)


def version_detail(conn, subject, workspace_id, version_id):
    facts = _admin(conn, subject, workspace_id)
    row = conn.execute(
        "SELECT v.*,s.status,p.rule_refs,p.manifest_sha256,p.candidate_id,p.published_at,p.published_by "
        "FROM template_version v JOIN template_version_policy p ON p.version_id=v.id "
        "JOIN template_version_state s ON s.version_id=v.id "
        "JOIN template_governed_family g ON g.template_id=v.template_id "
        "WHERE v.id=%s AND g.workspace_id=%s", (version_id, workspace_id)).fetchone()
    if not row:
        raise _hidden()
    _family(conn, facts, workspace_id, row["template_id"])
    if row["classification"] > facts["clearance"]:
        raise _hidden()
    if content_hash(row["rule_refs"]) != row["manifest_sha256"]:
        raise ApiError(503, "TEMPLATE_REPORT_INTEGRITY", "模板策略摘要不匹配")
    return {key: row[key] for key in ("id", "template_id", "version_label", "name", "scope",
            "classification", "structure", "status", "rule_refs", "manifest_sha256",
            "candidate_id", "published_at", "published_by", "development_only")}


def deprecate_version(conn, subject, workspace_id, version_id, command, key, request_id, trace_id):
    facts = _admin(conn, subject, workspace_id, exclusive=True)
    _local_write_target(conn)
    detail = version_detail(conn, subject, workspace_id, version_id)
    _lock_template_family(conn, workspace_id, detail["template_id"])
    digest = content_hash({"operation": "deprecate", "version_id": str(version_id),
                           "command": command.model_dump(mode="json")})
    if _action_receipt(conn, facts, key, digest):
        return version_detail(conn, subject, workspace_id, version_id)
    changed = conn.execute("SELECT eid_deprecate_template_version_v1(%s,%s,%s) AS changed",
                           (workspace_id, version_id, facts["actor_id"])).fetchone()["changed"]
    if not changed:
        raise ApiError(409, "TEMPLATE_DEPRECATED", "此版本已废弃，请重新读取状态")
    _audit(conn, facts, version_id, "template.deprecate",
           {"reason": command.reason, "status": "deprecated"}, request_id, trace_id,
           before={"status": detail["status"]})
    _record_action(conn, facts, key, digest, version_id)
    return version_detail(conn, subject, workspace_id, version_id)


def pinned_references(conn, subject, workspace_id, version_id, after=None):
    facts = _admin(conn, subject, workspace_id)
    version_detail(conn, subject, workspace_id, version_id)
    rows = conn.execute(
        "SELECT r.*,d.template_version_id FROM document d JOIN access_resource r ON r.id=d.id "
        "AND r.workspace_id=d.workspace_id WHERE r.kind='document' "
        "AND d.template_version_id=%(version_id)s AND " + _RESOURCE_FILTER +
        "AND (%(after)s::uuid IS NULL OR d.id>%(after)s) ORDER BY d.id LIMIT 101",
        {**facts, "version_id": version_id, "after": after}).fetchall()
    items = []
    for row in rows[:100]:
        try:
            authorize(facts, "resource:read", row)
        except AccessDenied:
            continue
        items.append({"document_id": row["id"], "name": row["title"], "template_version_id": version_id})
    return {"items": items, "next_cursor": rows[99]["id"] if len(rows) > 100 else None,
            "scope": "currently_authorized_documents_only"}
