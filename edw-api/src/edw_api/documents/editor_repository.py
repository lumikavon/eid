"""Authorized, compare-and-swap creation of immutable document versions."""

from uuid import uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..errors import ApiError
from .domain import content_hash
from .editor_domain import InvalidAst, _id, validate_ast
from .repository import _document_row, _local_write_target, _scope_allowed


def editable_document(conn, subject, workspace_id, document_id, *, exclusive=False):
    try:
        facts, resource, _ = checked(conn, subject, workspace_id, "document:edit", document_id,
                                     exclusive=exclusive)
    except AccessDenied as exc:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可编辑") from exc
    if resource["kind"] != "document":
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可编辑")
    if resource["publication_state"] != "unpublished" or resource["approval_state"] != "draft":
        raise ApiError(409, "DOCUMENT_READ_ONLY", "已发布或非草稿文档不可直接编辑")
    return facts, resource


def save_document(conn, subject, workspace_id, document_id, command, request_id, trace_id):
    facts, resource = editable_document(conn, subject, workspace_id, document_id, exclusive=True)
    _local_write_target(conn)
    # Serialize against concurrent writers, then compare both the immutable base and revision.
    locked = conn.execute(
        "SELECT head_version_id,revision,template_version_id,document_type,knowledge_scope "
        "FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE",
        (document_id, workspace_id),
    ).fetchone()
    if locked is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可编辑")
    if (locked["head_version_id"] != command.base_version_id
            or locked["revision"] != command.revision
            or resource["head_ref"] != command.base_version_id):
        raise ApiError(409, "DOC_VERSION_CONFLICT", "文档已产生新版本；本地编辑尚未保存")
    previous = _document_row(conn, facts, workspace_id, document_id)
    _scope_allowed(conn, workspace_id, locked["knowledge_scope"])
    ast = command.ast.model_dump(mode="json")
    try:
        media_ids = validate_ast(ast, expected_template_id=locked["template_version_id"],
                                 document_type=locked["document_type"],
                                 knowledge_scope=locked["knowledge_scope"], old_ast=previous["ast"])
    except InvalidAst as exc:
        raise ApiError(422, "INVALID_DOCUMENT_AST", str(exc)) from exc
    media = conn.execute(
        "SELECT id,width,height FROM document_media WHERE document_id=%s AND workspace_id=%s "
        "AND id=ANY(%s::uuid[])",
        (document_id, workspace_id, list(media_ids)),
    ).fetchall() if media_ids else []
    if len(media) != len(media_ids):
        raise ApiError(422, "INVALID_DOCUMENT_MEDIA", "图片资源不可引用")
    dimensions = {str(item["id"]): (item["width"], item["height"]) for item in media}
    for section in ast["document"]["sections"]:
        for block in section["blocks"]:
            if block["type"] == "figure":
                image = block["content"]
                if dimensions[_id(image["resource_id"])] != (image["width"], image["height"]):
                    raise ApiError(422, "INVALID_DOCUMENT_MEDIA", "图片尺寸与资源不匹配")
    next_revision = locked["revision"] + 1
    if next_revision > 9007199254740991:
        raise ApiError(409, "DOC_VERSION_CONFLICT", "修订号已达上限")
    version_id, operation_id = uuid4(), uuid4()
    now = facts["evaluated_at"]
    digest = content_hash(ast)
    conn.execute(
        "INSERT INTO document_version(id,document_id,revision,base_version_id,content_hash,"
        "ast,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (version_id, document_id, next_revision, command.base_version_id, digest,
         Jsonb(ast), facts["actor_id"], now),
    )
    updated = conn.execute(
        "UPDATE document SET head_version_id=%s,revision=%s WHERE id=%s AND workspace_id=%s "
        "AND head_version_id=%s AND revision=%s RETURNING id",
        (version_id, next_revision, document_id, workspace_id,
         command.base_version_id, command.revision),
    ).fetchone()
    if updated is None:
        raise ApiError(409, "DOC_VERSION_CONFLICT", "文档已产生新版本；本地编辑尚未保存")
    title = ast["document"]["metadata"]["title"]
    updated_resource = conn.execute(
        "UPDATE access_resource SET title=%s,head_ref=%s WHERE id=%s AND workspace_id=%s "
        "AND head_ref=%s RETURNING id",
        (title, version_id, document_id, workspace_id, command.base_version_id),
    ).fetchone()
    if updated_resource is None:
        raise ApiError(409, "DOC_VERSION_CONFLICT", "文档元数据已变化；本地编辑尚未保存")
    conn.execute(
        "UPDATE discovery_record SET updated_at=%s,revision=%s WHERE resource_id=%s",
        (now, next_revision, document_id),
    )
    conn.execute(
        "INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,"
        "after_policy,request_id,trace_id,occurred_at) VALUES "
        "(%s,%s,%s,%s,'document.edit',%s,%s,%s,%s,%s)",
        (operation_id, workspace_id, facts["actor_id"], document_id,
         Jsonb({"base_version_id": str(command.base_version_id), "revision": command.revision}),
         Jsonb({"version_id": str(version_id), "revision": next_revision}), request_id, trace_id, now),
    )
    return {"id": document_id, "workspace_id": workspace_id, "name": title,
            "document_type": locked["document_type"],
            "knowledge_scope": locked["knowledge_scope"],
            "template_version_id": locked["template_version_id"], "version_id": version_id,
            "base_version_id": command.base_version_id, "content_hash": digest,
            "revision": next_revision, "ast": ast, "replayed": False}
