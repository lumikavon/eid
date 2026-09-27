"""Current-grant manual outlines with immutable snapshots and exact readiness fences."""

import json
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..errors import ApiError
from .context_repository import _target, read_context
from .domain import content_hash, outline
from .governance_schemas import Manifest
from .outline_schemas import OutlineSnapshot

MAX_SNAPSHOT_BYTES = 131072


def _template_sections(conn, template_version_id):
    row = conn.execute(
        "SELECT v.id,v.structure,v.fixture_owner,v.development_only,"
        "p.rule_refs,p.manifest_sha256 FROM template_version v "
        "LEFT JOIN template_version_policy p ON p.version_id=v.id "
        "WHERE v.id=%s", (template_version_id,),
    ).fetchone()
    if row is None or row["development_only"] is not True:
        raise ApiError(503, "TEMPLATE_POLICY_UNAVAILABLE", "固定模板策略当前不可用", retryable=True)
    try:
        titles = outline(row["structure"])
        if row["rule_refs"] is None:
            if row["fixture_owner"] != "story-2.1":
                raise ValueError("Unproven fixture policy")
            return [{"id": str(uuid5(UUID(str(template_version_id)), f"outline-section:{index}")),
                     "title": title, "mandatory": True} for index, title in enumerate(titles)]
        if row["fixture_owner"] is not None or content_hash(row["rule_refs"]) != row["manifest_sha256"]:
            raise ValueError("Governed policy digest mismatch")
        manifest = Manifest.model_validate(row["rule_refs"])
        if len({section.id for section in manifest.sections}) != len(manifest.sections):
            raise ValueError("Duplicate pinned template section ID")
        if [section.title for section in manifest.sections] != titles:
            raise ValueError("Governed manifest and structure disagree")
        return [{"id": str(section.id), "title": section.title,
                 "mandatory": section.mandatory} for section in manifest.sections]
    except (ValidationError, TypeError, ValueError, KeyError) as exc:
        raise ApiError(503, "TEMPLATE_POLICY_UNAVAILABLE", "固定模板策略当前不可用",
                       retryable=True) from exc


def _head(conn, document_id, *, lock=False):
    return conn.execute(
        "SELECT h.version_id,h.revision,v.base_version_id,v.snapshot,v.content_hash,"
        "v.document_version_id,v.document_revision,v.context_version_id,v.template_version_id,"
        "v.created_by,v.created_at,c.actor_id AS confirmed_by,c.confirmed_at,"
        "c.ready_at_confirmation FROM document_outline_head h "
        "JOIN document_outline_version v ON v.id=h.version_id AND v.document_id=h.document_id "
        "LEFT JOIN document_outline_confirmation c ON c.version_id=v.id "
        "WHERE h.document_id=%s " + ("FOR UPDATE OF h" if lock else ""), (document_id,),
    ).fetchone()


def _snapshot(row):
    if row is None:
        return None
    if content_hash(row["snapshot"]) != row["content_hash"]:
        raise ApiError(503, "OUTLINE_INTEGRITY_UNAVAILABLE", "大纲版本校验失败", retryable=True)
    try:
        return OutlineSnapshot.model_validate(row["snapshot"])
    except ValidationError as exc:
        raise ApiError(503, "OUTLINE_INTEGRITY_UNAVAILABLE", "大纲结构不可用", retryable=True) from exc


def _section_reasons(snapshot, template_sections):
    if snapshot is None:
        return []
    reasons = []
    expected = {section["id"]: section for section in template_sections}
    seen_ids = {}
    seen_template = {}
    for index, section in enumerate(snapshot.sections):
        section_id = str(section.id)
        if section_id in seen_ids:
            reasons.append({"code": "DUPLICATE_SECTION_ID", "path": f"sections[{index}].id",
                            "other_path": f"sections[{seen_ids[section_id]}].id"})
        else:
            seen_ids[section_id] = index
        if section.template_section_id is None:
            continue
        template_id = str(section.template_section_id)
        if template_id in seen_template:
            reasons.append({"code": "DUPLICATE_TEMPLATE_SECTION", "path": f"sections[{index}].template_section_id",
                            "other_path": f"sections[{seen_template[template_id]}].template_section_id"})
        else:
            seen_template[template_id] = index
        rule = expected.get(template_id)
        if rule is None:
            reasons.append({"code": "UNKNOWN_TEMPLATE_SECTION", "path": f"sections[{index}].template_section_id"})
        elif section.title != rule["title"]:
            reasons.append({"code": "REQUIRED_SECTION_TITLE_CHANGED" if rule["mandatory"] else
                            "TEMPLATE_SECTION_TITLE_CHANGED", "path": f"sections[{index}].title",
                            "template_section_id": template_id, "expected_title": rule["title"]})
    for rule in template_sections:
        if rule["mandatory"] and rule["id"] not in seen_template:
            reasons.append({"code": "REQUIRED_SECTION_MISSING", "path": "sections",
                            "template_section_id": rule["id"], "expected_title": rule["title"]})
    return reasons


def _identity_reasons(previous, current):
    if previous is None:
        return []
    previous_ids = {str(section.template_section_id): section.id for section in previous.sections
                    if section.template_section_id is not None}
    return [{"code": "TEMPLATE_SECTION_ID_CHANGED", "path": f"sections[{index}].id",
             "template_section_id": str(section.template_section_id)}
            for index, section in enumerate(current.sections)
            if section.template_section_id is not None
            and str(section.template_section_id) in previous_ids
            and previous_ids[str(section.template_section_id)] != section.id]


def _reasons(snapshot, row, document, resource, context, template_sections, *, current=True):
    if row is None:
        reasons = [{"code": "OUTLINE_MISSING", "path": "snapshot"}]
        if context["state"] != "CONTEXT_READY":
            reasons.append({"code": "CONTEXT_NOT_READY", "path": "context",
                            "context_reasons": context["reasons"]})
        if resource["publication_state"] != "unpublished" or resource["approval_state"] != "draft":
            reasons.append({"code": "DOCUMENT_NOT_DRAFT", "path": "document"})
        return reasons
    reasons = _section_reasons(snapshot, template_sections)
    if row["document_version_id"] != document["head_version_id"] or row["document_revision"] != document["revision"]:
        reasons.append({"code": "DOCUMENT_CHANGED", "path": "document_version_id"})
    if row["template_version_id"] != document["template_version_id"]:
        reasons.append({"code": "TEMPLATE_CHANGED", "path": "template_version_id"})
    if row["context_version_id"] != context["version_id"]:
        reasons.append({"code": "CONTEXT_CHANGED", "path": "context_version_id"})
    if context["state"] != "CONTEXT_READY":
        reasons.append({"code": "CONTEXT_NOT_READY", "path": "context",
                        "context_reasons": context["reasons"]})
    if resource["publication_state"] != "unpublished" or resource["approval_state"] != "draft":
        reasons.append({"code": "DOCUMENT_NOT_DRAFT", "path": "document"})
    if not current:
        reasons.append({"code": "OUTLINE_SUPERSEDED", "path": "version_id"})
    if row["confirmed_at"] is None:
        reasons.append({"code": "HUMAN_CONFIRMATION_REQUIRED", "path": "confirmation"})
    elif row["ready_at_confirmation"] is not True:
        reasons.append({"code": "CONFIRMATION_NOT_READY", "path": "confirmation"})
    return reasons


def _result(conn, subject, workspace_id, resource, document, row, template_sections, context, *, current=True):
    snapshot = _snapshot(row)
    reasons = _reasons(snapshot, row, document, resource, context, template_sections, current=current)
    try:
        checked(conn, subject, workspace_id, "document:edit", resource["id"])
    except AccessDenied:
        reasons.append({"code": "CURRENT_EDIT_DENIED", "path": "document"})
    return {
        "version_id": row["version_id"] if row else None,
        "revision": row["revision"] if row else 0,
        "base_version_id": row["base_version_id"] if row else None,
        "document_version_id": row["document_version_id"] if row else document["head_version_id"],
        "document_revision": row["document_revision"] if row else document["revision"],
        "context_version_id": row["context_version_id"] if row else context["version_id"],
        "template_version_id": row["template_version_id"] if row else document["template_version_id"],
        "development_only": True,
        "template_sections": template_sections,
        "required_sections": [section for section in template_sections if section["mandatory"]],
        "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
        "content_hash": row["content_hash"] if row else None,
        "created_by": row["created_by"] if row else None,
        "created_at": row["created_at"] if row else None,
        "confirmed_by": row["confirmed_by"] if row else None,
        "confirmed_at": row["confirmed_at"] if row else None,
        "state": "OUTLINE_PENDING" if reasons else "OUTLINE_READY",
        "reasons": reasons,
    }


def _read_dependencies(conn, subject, workspace_id, document_id):
    _, resource, document = _target(conn, subject, workspace_id, document_id)
    template_sections = _template_sections(conn, document["template_version_id"])
    context = read_context(conn, subject, workspace_id, document_id)
    return resource, document, template_sections, context


def read_outline(conn, subject, workspace_id, document_id):
    resource, document, template_sections, context = _read_dependencies(conn, subject, workspace_id, document_id)
    return _result(conn, subject, workspace_id, resource, document, _head(conn, document_id),
                   template_sections, context)


def read_outline_version(conn, subject, workspace_id, document_id, version_id):
    resource, document, template_sections, context = _read_dependencies(conn, subject, workspace_id, document_id)
    row = conn.execute(
        "SELECT v.id AS version_id,v.revision,v.base_version_id,v.snapshot,v.content_hash,"
        "v.document_version_id,v.document_revision,v.context_version_id,v.template_version_id,"
        "v.created_by,v.created_at,c.actor_id AS confirmed_by,c.confirmed_at,"
        "c.ready_at_confirmation FROM document_outline_version v "
        "LEFT JOIN document_outline_confirmation c ON c.version_id=v.id "
        "WHERE v.document_id=%s AND v.id=%s", (document_id, version_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "OUTLINE_VERSION_NOT_FOUND", "大纲版本不存在或不可见")
    head = _head(conn, document_id)
    return _result(conn, subject, workspace_id, resource, document, row, template_sections, context,
                   current=head is not None and head["version_id"] == version_id)


def list_outline_versions(conn, subject, workspace_id, document_id):
    _target(conn, subject, workspace_id, document_id)
    rows = conn.execute(
        "SELECT v.id AS version_id,v.revision,v.document_version_id,v.context_version_id,"
        "v.template_version_id,v.created_by,v.created_at,c.actor_id AS confirmed_by,c.confirmed_at "
        "FROM document_outline_version v LEFT JOIN document_outline_confirmation c ON c.version_id=v.id "
        "WHERE v.document_id=%s ORDER BY v.revision DESC LIMIT 101", (document_id,),
    ).fetchall()
    return {"items": [{key: value for key, value in row.items()} for row in rows[:100]],
            "more": len(rows) > 100}


def _preconditions(conn, subject, workspace_id, document_id, document, command):
    if (document["head_version_id"] != command.document_version_id
            or document["revision"] != command.document_revision):
        raise ApiError(409, "DOC_VERSION_CONFLICT", "正文版本已变化；大纲输入未保存",
                       details={"path": "document_version_id"})
    if document["template_version_id"] != command.template_version_id:
        raise ApiError(409, "TEMPLATE_VERSION_CONFLICT", "固定模板版本不匹配",
                       details={"path": "template_version_id"})
    context = read_context(conn, subject, workspace_id, document_id)
    if context["version_id"] != command.context_version_id:
        raise ApiError(409, "CONTEXT_VERSION_CONFLICT", "项目上下文版本已变化",
                       details={"path": "context_version_id", "reasons": context["reasons"]})
    if context["state"] != "CONTEXT_READY":
        raise ApiError(422, "CONTEXT_NOT_READY", "项目上下文当前不满足生成前置条件",
                       details={"reasons": context["reasons"]})
    return context


def _audit(conn, facts, workspace_id, document_id, action, before, after, request_id, trace_id):
    conn.execute(
        "INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,"
        "after_policy,request_id,trace_id,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uuid4(), workspace_id, facts["actor_id"], document_id, action, Jsonb(before), Jsonb(after),
         request_id, trace_id, facts["evaluated_at"]),
    )


def save_outline(conn, subject, workspace_id, document_id, command, request_id, trace_id):
    facts, resource, document = _target(conn, subject, workspace_id, document_id, write=True)
    context = _preconditions(conn, subject, workspace_id, document_id, document, command)
    template_sections = _template_sections(conn, document["template_version_id"])
    previous = _head(conn, document_id, lock=True)
    if ((previous["version_id"] if previous else None) != command.base_outline_version_id
            or (previous["revision"] if previous else 0) != command.outline_revision):
        raise ApiError(409, "OUTLINE_VERSION_CONFLICT", "大纲版本已更新；本地输入未保存",
                       details={"path": "base_outline_version_id"})
    reasons = _section_reasons(command.snapshot, template_sections)
    reasons.extend(_identity_reasons(_snapshot(previous), command.snapshot))
    if reasons:
        raise ApiError(422, "OUTLINE_INVALID", "必选章节或模板章节身份不完整",
                       details={"reasons": reasons})
    body = command.snapshot.model_dump(mode="json")
    if len(json.dumps(body, ensure_ascii=True, sort_keys=True).encode("ascii")) > MAX_SNAPSHOT_BYTES:
        raise ApiError(422, "OUTLINE_SNAPSHOT_TOO_LARGE", "大纲内容超过 128 KiB 限额",
                       details={"path": "snapshot", "max_bytes": MAX_SNAPSHOT_BYTES})
    version_id = uuid4()
    revision = command.outline_revision + 1
    digest = content_hash(body)
    conn.execute(
        "INSERT INTO document_outline_version(id,document_id,revision,base_version_id,"
        "document_version_id,document_revision,context_version_id,template_version_id,"
        "snapshot,content_hash,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (version_id, document_id, revision, command.base_outline_version_id,
         command.document_version_id, command.document_revision, command.context_version_id,
         command.template_version_id, Jsonb(body), digest, facts["actor_id"], facts["evaluated_at"]),
    )
    if previous is None:
        conn.execute("INSERT INTO document_outline_head(document_id,version_id,revision) VALUES (%s,%s,%s)",
                     (document_id, version_id, revision))
    else:
        updated = conn.execute(
            "UPDATE document_outline_head SET version_id=%s,revision=%s WHERE document_id=%s "
            "AND version_id=%s AND revision=%s RETURNING document_id",
            (version_id, revision, document_id, command.base_outline_version_id, command.outline_revision),
        ).fetchone()
        if updated is None:
            raise ApiError(409, "OUTLINE_VERSION_CONFLICT", "大纲已更新；本地输入未保存")
    _audit(conn, facts, workspace_id, document_id, "outline.save",
           {"version_id": str(command.base_outline_version_id) if previous else None},
           {"version_id": str(version_id), "revision": revision, "content_hash": digest,
            "context_version_id": str(command.context_version_id)}, request_id, trace_id)
    return _result(conn, subject, workspace_id, resource, document, _head(conn, document_id),
                   template_sections, context)


def confirm_outline(conn, subject, workspace_id, document_id, command, request_id, trace_id):
    facts, resource, document = _target(conn, subject, workspace_id, document_id, write=True)
    context = _preconditions(conn, subject, workspace_id, document_id, document, command)
    template_sections = _template_sections(conn, document["template_version_id"])
    row = _head(conn, document_id, lock=True)
    if row is None or row["version_id"] != command.version_id:
        raise ApiError(409, "OUTLINE_VERSION_CONFLICT", "大纲版本已变化；请重新核对",
                       details={"path": "version_id"})
    if (row["document_version_id"] != command.document_version_id
            or row["document_revision"] != command.document_revision
            or row["context_version_id"] != command.context_version_id
            or row["template_version_id"] != command.template_version_id):
        raise ApiError(409, "OUTLINE_PREREQUISITE_CHANGED", "大纲固定的前置版本已变化",
                       details={"path": "version_id"})
    snapshot = _snapshot(row)
    reasons = _reasons(snapshot, row, document, resource, context, template_sections)
    blocking = [reason for reason in reasons if reason["code"] != "HUMAN_CONFIRMATION_REQUIRED"]
    if blocking:
        raise ApiError(422, "OUTLINE_INCOMPLETE", "大纲当前不满足人工确认条件",
                       details={"reasons": blocking})
    if row["confirmed_at"] is not None:
        return _result(conn, subject, workspace_id, resource, document, row, template_sections, context)
    conn.execute(
        "INSERT INTO document_outline_confirmation(version_id,document_id,actor_id,confirmed_at,"
        "ready_at_confirmation) VALUES (%s,%s,%s,%s,true)",
        (command.version_id, document_id, facts["actor_id"], facts["evaluated_at"]),
    )
    _audit(conn, facts, workspace_id, document_id, "outline.confirm",
           {"version_id": str(command.version_id), "state": "OUTLINE_PENDING"},
           {"version_id": str(command.version_id), "state": "OUTLINE_READY",
            "context_version_id": str(command.context_version_id)}, request_id, trace_id)
    return _result(conn, subject, workspace_id, resource, document, _head(conn, document_id),
                   template_sections, context)
