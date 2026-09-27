"""Current-grant context snapshots, CAS, manual confirmation and fail-closed eligibility."""
import json
from uuid import uuid4

from pydantic import ValidationError
from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..errors import ApiError
from .context_schemas import ContextSnapshot
from .domain import content_hash
from .editor_repository import editable_document
from .repository import _local_write_target

MAX_SNAPSHOT_BYTES = 131072  # 0014_project_context.snapshot JSONB CHECK


def _target(conn, subject, workspace_id, document_id, *, write=False):
    if write:
        facts, resource = editable_document(conn, subject, workspace_id, document_id, exclusive=True)
        _local_write_target(conn)
    else:
        try:
            facts, resource, _ = checked(conn, subject, workspace_id, "resource:read", document_id)
        except AccessDenied as exc:
            raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可见") from exc
        if resource["kind"] != "document":
            raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可见")
    # Document head is also the revision fence for context readiness.
    document = conn.execute(
        "SELECT d.head_version_id,d.revision,d.template_version_id,d.knowledge_scope "
        "FROM document d WHERE d.id=%s AND d.workspace_id=%s AND d.owner_id=%s "
        + ("FOR UPDATE" if write else "FOR SHARE"),
        (document_id, workspace_id, resource["owner_id"]),
    ).fetchone()
    if document is None or document["head_version_id"] != resource["head_ref"]:
        raise ApiError(503, "DOCUMENT_INTEGRITY_UNAVAILABLE", "文档当前不可用", retryable=True)
    return facts, resource, document


def _head(conn, document_id, *, lock=False):
    return conn.execute(
        "SELECT h.version_id,h.revision,v.snapshot,v.content_hash,v.document_version_id,"
        "v.document_revision,v.created_by,v.created_at,c.actor_id AS confirmed_by,"
        "c.confirmed_at,c.ready_at_confirmation "
        "FROM project_context_head h JOIN project_context_version v "
        "ON v.id=h.version_id AND v.document_id=h.document_id "
        "LEFT JOIN project_context_confirmation c ON c.version_id=v.id "
        "WHERE h.document_id=%s " + ("FOR UPDATE OF h" if lock else ""), (document_id,),
    ).fetchone()


def _snapshot(row):
    if row is None:
        return None
    if content_hash(row["snapshot"]) != row["content_hash"]:
        raise ApiError(503, "CONTEXT_INTEGRITY_UNAVAILABLE", "上下文版本校验失败", retryable=True)
    try:
        return ContextSnapshot.model_validate(row["snapshot"])
    except ValidationError as exc:
        raise ApiError(503, "CONTEXT_INTEGRITY_UNAVAILABLE", "上下文结构不可用", retryable=True) from exc


def _sources(conn, subject, workspace_id, snapshot):
    # Reauthorize every referenced object at every use; manual locators are not
    # claims of enterprise integration. Missing/foreign references disclose nothing.
    ids = {item.source.resource_id for item in (*snapshot.facts, *snapshot.constraints)
           if item.source.resource_id is not None}
    for resource_id in sorted(ids):
        try:
            checked(conn, subject, workspace_id, "resource:read", resource_id)
        except AccessDenied as exc:
            raise ApiError(404, "CONTEXT_SOURCE_NOT_FOUND", "来源不存在或当前不可访问") from exc


def _invalid_owners(conn, workspace_id, snapshot):
    invalid = []
    for index, fact in enumerate(snapshot.facts):
        member = conn.execute(
            "SELECT 1 FROM workspace_membership WHERE identity_id=%s AND workspace_id=%s AND active",
            (fact.owner_id, workspace_id),
        ).fetchone()
        if member is None:
            invalid.append({"code": "CONTEXT_OWNER_INVALID", "path": f"facts[{index}].owner_id"})
    return invalid


def _owners(conn, workspace_id, snapshot):
    invalid = _invalid_owners(conn, workspace_id, snapshot)
    if invalid:
        raise ApiError(422, "CONTEXT_OWNER_INVALID", "负责人不是当前工作区成员",
                       details={"reasons": invalid})


def _reasons(snapshot, document, row, resource):
    reasons = []
    if row is None:
        return [{"code": "CONTEXT_MISSING", "path": "snapshot"}]
    if row["document_version_id"] != document["head_version_id"] or row["document_revision"] != document["revision"]:
        reasons.append({"code": "DOCUMENT_CHANGED", "path": "document_version_id"})
    if resource["publication_state"] != "unpublished" or resource["approval_state"] != "draft":
        reasons.append({"code": "DOCUMENT_NOT_DRAFT", "path": "document"})
    if not snapshot.intent:
        reasons.append({"code": "INTENT_REQUIRED", "path": "intent"})
    if not snapshot.facts and not snapshot.zero_facts:
        reasons.append({"code": "FACTS_REQUIRED", "path": "facts"})
    for index, fact in enumerate(snapshot.facts):
        if not fact.confirmed:
            reasons.append({"code": "FACT_UNCONFIRMED", "path": f"facts[{index}].confirmed"})
    for index, missing in enumerate(snapshot.missing):
        if missing.required and not missing.resolved:
            reasons.append({"code": "REQUIRED_MISSING", "path": f"missing[{index}]"})
    if row["confirmed_at"] is None:
        reasons.append({"code": "HUMAN_CONFIRMATION_REQUIRED", "path": "confirmation"})
    elif not row["ready_at_confirmation"]:
        reasons.append({"code": "CONFIRMATION_NOT_READY", "path": "confirmation"})
    return reasons


def _collisions(snapshot):
    conflicts = []
    for field, items, attr in (("facts", snapshot.facts, "key"),
                               ("glossary", snapshot.glossary, "term"),
                               ("missing", snapshot.missing, "key")):
        seen = {}
        for index, item in enumerate(items):
            key = getattr(item, attr).casefold()
            if key in seen:
                conflicts.append({"code": "DUPLICATE_OR_CONTRADICTORY_ENTRY",
                                  "path": f"{field}[{index}].{attr}", "other_path": f"{field}[{seen[key]}].{attr}"})
            else:
                seen[key] = index
    return conflicts


def _missing_regressions(previous, current):
    if previous is None:
        return []
    current_by_key = {item.key.casefold(): item for item in current.missing}
    return [{"code": "REQUIRED_MISSING_NOT_RESOLVED", "path": f"missing[{index}]"}
            for index, item in enumerate(previous.missing)
            if item.required and not item.resolved and
            (item.key.casefold() not in current_by_key or
             not current_by_key[item.key.casefold()].required)]


def _result(conn, subject, workspace_id, row, document, resource, *, current=True):
    snapshot = _snapshot(row)
    if snapshot is not None:
        _sources(conn, subject, workspace_id, snapshot)
    reasons = _reasons(snapshot, document, row, resource)
    if snapshot is not None:
        reasons.extend(_invalid_owners(conn, workspace_id, snapshot))
    if not current:
        reasons.append({"code": "CONTEXT_SUPERSEDED", "path": "version_id"})
    try:
        checked(conn, subject, workspace_id, "document:edit", resource["id"])
    except AccessDenied:
        reasons.append({"code": "CURRENT_EDIT_DENIED", "path": "document"})
    return {"version_id": row["version_id"] if row else None,
            "revision": row["revision"] if row else 0,
            "document_version_id": row["document_version_id"] if row else document["head_version_id"],
            "document_revision": row["document_revision"] if row else document["revision"],
            "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
            "content_hash": row["content_hash"] if row else None,
            "created_by": row["created_by"] if row else None,
            "created_at": row["created_at"] if row else None,
            "confirmed_by": row["confirmed_by"] if row else None,
            "confirmed_at": row["confirmed_at"] if row else None,
            "state": "CONTEXT_PENDING" if reasons else "CONTEXT_READY", "reasons": reasons}


def read_context(conn, subject, workspace_id, document_id):
    _, resource, document = _target(conn, subject, workspace_id, document_id)
    return _result(conn, subject, workspace_id, _head(conn, document_id), document, resource)


def read_context_version(conn, subject, workspace_id, document_id, version_id):
    _, resource, document = _target(conn, subject, workspace_id, document_id)
    row = conn.execute(
        "SELECT v.id AS version_id,v.revision,v.snapshot,v.content_hash,v.document_version_id,"
        "v.document_revision,v.created_by,v.created_at,c.actor_id AS confirmed_by,"
        "c.confirmed_at,c.ready_at_confirmation FROM project_context_version v "
        "LEFT JOIN project_context_confirmation c ON c.version_id=v.id "
        "WHERE v.document_id=%s AND v.id=%s", (document_id, version_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "CONTEXT_VERSION_NOT_FOUND", "上下文版本不存在或不可见")
    head = _head(conn, document_id)
    return _result(conn, subject, workspace_id, row, document, resource,
                   current=head is not None and head["version_id"] == version_id)


def list_context_versions(conn, subject, workspace_id, document_id):
    _target(conn, subject, workspace_id, document_id)
    rows = conn.execute(
        "SELECT v.id AS version_id,v.revision,v.created_by,v.created_at,"
        "c.actor_id AS confirmed_by,c.confirmed_at FROM project_context_version v "
        "LEFT JOIN project_context_confirmation c ON c.version_id=v.id "
        "WHERE v.document_id=%s ORDER BY v.revision DESC LIMIT 101", (document_id,),
    ).fetchall()
    return {"items": [{"version_id": str(row["version_id"]), "revision": row["revision"],
                       "created_by": str(row["created_by"]), "created_at": row["created_at"].isoformat(),
                       "confirmed_by": str(row["confirmed_by"]) if row["confirmed_by"] else None,
                       "confirmed_at": row["confirmed_at"].isoformat() if row["confirmed_at"] else None}
                      for row in rows[:100]], "more": len(rows) > 100}


def _document_cas(document, command):
    if (document["head_version_id"] != command.document_version_id
            or document["revision"] != command.document_revision):
        raise ApiError(409, "DOC_VERSION_CONFLICT", "文档已更新；上下文输入尚未保存",
                       details={"path": "document_version_id"})


def save_context(conn, subject, workspace_id, document_id, command, request_id, trace_id):
    facts, resource, document = _target(conn, subject, workspace_id, document_id, write=True)
    _document_cas(document, command)
    previous = _head(conn, document_id, lock=True)
    if ((previous["version_id"] if previous else None) != command.base_context_version_id
            or (previous["revision"] if previous else 0) != command.context_revision):
        raise ApiError(409, "CONTEXT_VERSION_CONFLICT", "上下文版本已更新；本地输入未保存",
                       details={"path": "base_context_version_id"})
    snapshot = command.snapshot
    conflicts = _collisions(snapshot)
    if conflicts:
        raise ApiError(422, "CONTEXT_CONFLICT", "上下文条目存在冲突", details={"conflicts": conflicts})
    regressions = _missing_regressions(_snapshot(previous), snapshot)
    if regressions:
        raise ApiError(422, "CONTEXT_MISSING_UNRESOLVED", "必须先明确解决已记录的必需缺项",
                       details={"reasons": regressions})
    _sources(conn, subject, workspace_id, snapshot)
    _owners(conn, workspace_id, snapshot)
    version_id = uuid4()
    now = facts["evaluated_at"]
    body = snapshot.model_dump(mode="json")
    # ASCII escaping and default separators conservatively bound PostgreSQL's
    # JSONB text representation, including multibyte input and punctuation.
    if len(json.dumps(body, ensure_ascii=True, sort_keys=True).encode("ascii")) > MAX_SNAPSHOT_BYTES:
        raise ApiError(422, "CONTEXT_SNAPSHOT_TOO_LARGE", "上下文内容超过 128 KiB 限额",
                       details={"path": "snapshot", "max_bytes": MAX_SNAPSHOT_BYTES})
    digest = content_hash(body)
    revision = command.context_revision + 1
    conn.execute(
        "INSERT INTO project_context_version(id,document_id,revision,base_version_id,"
        "document_version_id,document_revision,snapshot,content_hash,created_by,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (version_id, document_id, revision, command.base_context_version_id,
         command.document_version_id, command.document_revision, Jsonb(body), digest, facts["actor_id"], now),
    )
    if previous is None:
        conn.execute("INSERT INTO project_context_head(document_id,version_id,revision) VALUES (%s,%s,%s)",
                     (document_id, version_id, revision))
    else:
        updated = conn.execute(
            "UPDATE project_context_head SET version_id=%s,revision=%s WHERE document_id=%s "
            "AND version_id=%s AND revision=%s RETURNING document_id",
            (version_id, revision, document_id, command.base_context_version_id, command.context_revision),
        ).fetchone()
        if updated is None:
            raise ApiError(409, "CONTEXT_VERSION_CONFLICT", "上下文已更新；本地输入未保存")
    conn.execute(
        "INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,"
        "after_policy,request_id,trace_id,occurred_at) VALUES "
        "(%s,%s,%s,%s,'context.save',%s,%s,%s,%s,%s)",
        (uuid4(), workspace_id, facts["actor_id"], document_id,
         Jsonb({"version_id": str(command.base_context_version_id) if previous else None}),
         Jsonb({"version_id": str(version_id), "revision": revision, "content_hash": digest}),
         request_id, trace_id, now),
    )
    return _result(conn, subject, workspace_id, _head(conn, document_id), document, resource)


def confirm_context(conn, subject, workspace_id, document_id, command, request_id, trace_id):
    facts, resource, document = _target(conn, subject, workspace_id, document_id, write=True)
    _document_cas(document, command)
    row = _head(conn, document_id, lock=True)
    if row is None or row["version_id"] != command.version_id:
        raise ApiError(409, "CONTEXT_VERSION_CONFLICT", "上下文版本已变化；请保留输入并重新核对",
                       details={"path": "version_id"})
    snapshot = _snapshot(row)
    _sources(conn, subject, workspace_id, snapshot)
    _owners(conn, workspace_id, snapshot)
    if _collisions(snapshot):
        raise ApiError(409, "CONTEXT_CONFLICT", "上下文版本存在冲突")
    if snapshot.zero_facts and not command.zero_facts_acknowledged:
        raise ApiError(422, "ZERO_FACTS_ACK_REQUIRED", "请明确确认无项目事实",
                       details={"path": "zero_facts_acknowledged"})
    if not snapshot.zero_facts and command.zero_facts_acknowledged:
        raise ApiError(422, "ZERO_FACTS_ACK_INVALID", "当前版本含项目事实")
    if row["confirmed_at"] is not None:
        # No stale success replay; this call has already rechecked the current grant.
        return _result(conn, subject, workspace_id, row, document, resource)
    reasons = _reasons(snapshot, document, row, resource)
    blocking = [reason for reason in reasons if reason["code"] != "HUMAN_CONFIRMATION_REQUIRED"]
    if blocking:
        raise ApiError(422, "CONTEXT_INCOMPLETE", "请处理必需缺项及未确认事实",
                       details={"reasons": blocking})
    now = facts["evaluated_at"]
    conn.execute(
        "INSERT INTO project_context_confirmation(version_id,document_id,actor_id,confirmed_at,ready_at_confirmation) "
        "VALUES (%s,%s,%s,%s,true)", (command.version_id, document_id, facts["actor_id"], now),
    )
    conn.execute(
        "INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,"
        "after_policy,request_id,trace_id,occurred_at) VALUES "
        "(%s,%s,%s,%s,'context.confirm',%s,%s,%s,%s,%s)",
        (uuid4(), workspace_id, facts["actor_id"], document_id,
         Jsonb({"version_id": str(command.version_id), "state": "CONTEXT_PENDING"}),
         Jsonb({"version_id": str(command.version_id), "state": "CONTEXT_READY",
                "zero_facts": snapshot.zero_facts}), request_id, trace_id, now),
    )
    return _result(conn, subject, workspace_id, _head(conn, document_id), document, resource)
