"""Bounded binary upload, private quarantine and current-policy source viewing."""
from contextlib import contextmanager
from hashlib import sha256
from uuid import UUID, uuid4

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Header, Request, Response

from ..access.policy import AccessDenied
from ..access.repository import checked, create_delegation
from ..auth import bearer_token
from ..db import connection
from ..documents.editor_repository import editable_document
from ..documents.media import object_client
from ..errors import ApiError
from ..task_contract import AttachmentJobSnapshot

MAX_BYTES = 10 * 1024 * 1024
TYPES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "png": "image/png", "jpeg": "image/jpeg"}


def kind_for(data: bytes, declared: str) -> str:
    for kind, content_type in TYPES.items():
        if declared == content_type:
            if (kind == "pdf" and data.startswith(b"%PDF-") or
                kind in ("docx", "xlsx") and data.startswith(b"PK\x03\x04") or
                kind == "png" and data.startswith(b"\x89PNG\r\n\x1a\n") or
                kind == "jpeg" and data.startswith(b"\xff\xd8\xff")):
                return kind
    raise ApiError(422, "ATTACHMENT_TYPE_INVALID", "附件类型或签名无效")


def create_router(settings, verify):
    router = APIRouter()
    documents = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/documents/{document_id}/attachments")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(404, "ATTACHMENT_NOT_FOUND", "附件不存在或不可访问") from exc
        except psycopg.Error as exc:
            raise ApiError(503, "ATTACHMENT_UNAVAILABLE", "附件服务暂不可用", retryable=True) from exc

    def authorized(conn, subject, workspace_id, document_id):
        _, resource, context = checked(conn, subject, workspace_id, "resource:read", document_id)
        if resource["kind"] != "document":
            raise AccessDenied()
        return context

    def selected(conn, subject, workspace_id, document_id, attachment_id):
        context = authorized(conn, subject, workspace_id, document_id)
        row = conn.execute("""SELECT a.id,a.sha256,a.kind,a.byte_length,a.classification,a.retention,
            a.created_at,p.state,p.error_code,p.updated_at,p.parser_version
            FROM attachment a JOIN attachment_parse p ON p.attachment_id=a.id
            WHERE a.id=%s AND a.document_id=%s AND a.workspace_id=%s""",
            (attachment_id, document_id, workspace_id)).fetchone()
        if row is None or row["classification"] > context.classification:
            raise AccessDenied()
        return row

    @documents.post("", status_code=201)
    async def upload(workspace_id: UUID, document_id: UUID, request: Request,
                     current=Depends(actor), content_type: str = Header(default=""),
                     expected_sha256: str = Header(default="", alias="X-Content-SHA256")):
        if request.headers.get("content-length"):
            try:
                length = int(request.headers["content-length"])
            except ValueError as exc:
                raise ApiError(422, "ATTACHMENT_INVALID", "附件请求长度无效") from exc
            if length > MAX_BYTES:
                raise ApiError(413, "ATTACHMENT_TOO_LARGE", "附件超过大小限制")
        # Preflight before any object write; never accept client object keys or filenames.
        with database() as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ApiError(413, "ATTACHMENT_TOO_LARGE", "附件超过大小限制")
        if not raw or len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
            raise ApiError(422, "ATTACHMENT_INVALID", "附件散列或内容无效")
        digest = sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise ApiError(422, "ATTACHMENT_INTEGRITY", "附件散列不匹配")
        kind = kind_for(raw, content_type)
        with database() as conn:
            context = editable_document(conn, current.subject, workspace_id, document_id)[0]
            actor_id = context["actor_id"]
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         (f"attachment-quota:{workspace_id}",))
            existing = conn.execute("""SELECT id FROM attachment WHERE document_id=%s
                AND uploader_id=%s AND sha256=%s AND kind=%s""",
                (document_id, actor_id, digest, kind)).fetchone()
            if existing:
                row = selected(conn, current.subject, workspace_id, document_id, existing["id"])
                return {"data": dict(row)}
            if conn.execute("""SELECT count(*) AS count,COALESCE(sum(byte_length),0) AS bytes
                FROM attachment WHERE workspace_id=%s""", (workspace_id,)).fetchone()["bytes"] + len(raw) > 256 * 1024 * 1024:
                raise ApiError(413, "ATTACHMENT_QUOTA", "工作区附件配额已满")
            if conn.execute("SELECT count(*) AS count FROM attachment WHERE workspace_id=%s", (workspace_id,)).fetchone()["count"] >= 1000:
                raise ApiError(413, "ATTACHMENT_QUOTA", "工作区附件配额已满")
            attachment_id = uuid4()
            key = f"attachment-quarantine/{workspace_id}/{attachment_id}"
            # Lock is held across this bounded private write to serialize quota and digest.
            s3 = object_client(settings)
            try:
                s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=bytes(raw),
                              ContentType="application/octet-stream", Metadata={"sha256": digest})
            except (BotoCoreError, ClientError) as exc:
                raise ApiError(503, "ATTACHMENT_STORAGE", "附件存储暂不可用", retryable=True) from exc
            finally:
                s3.close()
            try:
                # The workspace policy share lock prevents revocation between check and metadata commit.
                facts, resource, _ = checked(conn, current.subject, workspace_id, "resource:read", document_id)
                editable_document(conn, current.subject, workspace_id, document_id)
                delegation = create_delegation(conn, current.subject, workspace_id, document_id,
                                               "resource:read", f"attachment:{attachment_id}",
                                               request.state.request_id, request.state.trace_id)
                conn.execute("""INSERT INTO attachment(id,workspace_id,document_id,uploader_id,object_key,
                    sha256,kind,byte_length,classification) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (attachment_id, workspace_id, document_id, facts["actor_id"], key, digest,
                     kind, len(raw), resource["classification"]))
                conn.execute("""INSERT INTO attachment_parse(attachment_id,parser_version,source_sha256,delegation_id)
                    VALUES (%s,'attachment-v1',%s,%s)""",
                    (attachment_id, digest, delegation["delegation_id"]))
            except Exception:
                s3 = object_client(settings)
                try:
                    s3.delete_object(Bucket=settings.s3_bucket, Key=key)
                except (BotoCoreError, ClientError):
                    pass  # Unreferenced quarantine is not reachable through any API.
                finally:
                    s3.close()
                raise
            return {"data": {"id": attachment_id, "sha256": digest, "kind": kind,
                              "byte_length": len(raw), "state": "QUEUED"}}

    @documents.get("")
    def list_attachments(workspace_id: UUID, document_id: UUID, response: Response,
                         current=Depends(actor)):
        with database() as conn:
            context = authorized(conn, current.subject, workspace_id, document_id)
            rows = conn.execute("""SELECT a.id,a.sha256,a.kind,a.byte_length,a.classification,a.retention,
                a.created_at,p.state,p.error_code,p.updated_at,p.parser_version
                FROM attachment a JOIN attachment_parse p ON p.attachment_id=a.id
                WHERE a.workspace_id=%s AND a.document_id=%s AND a.classification<=%s
                ORDER BY a.created_at DESC LIMIT 100""",
                (workspace_id, document_id, context.classification)).fetchall()
        response.headers["Cache-Control"] = "no-store"
        return {"data": [dict(row) for row in rows]}

    @documents.get("/{attachment_id}")
    def inspect(workspace_id: UUID, document_id: UUID, attachment_id: UUID, response: Response,
                current=Depends(actor)):
        with database() as conn:
            row = selected(conn, current.subject, workspace_id, document_id, attachment_id)
            pages = conn.execute("""SELECT page_number,section,state,error_code FROM attachment_page
                WHERE attachment_id=%s ORDER BY page_number""", (attachment_id,)).fetchall()
            chunks = conn.execute("""SELECT page_number,ordinal,locator,content,content_hash
                FROM attachment_chunk WHERE attachment_id=%s ORDER BY page_number,ordinal LIMIT 1000""",
                (attachment_id,)).fetchall()
            # Revalidate before exposing page text, not merely on request entry.
            selected(conn, current.subject, workspace_id, document_id, attachment_id)
        response.headers["Cache-Control"] = "no-store"
        return {"data": {**dict(row), "pages": [dict(page) for page in pages],
                         "chunks": [dict(chunk) for chunk in chunks]}}

    jobs = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/attachment-jobs")

    @jobs.get("")
    def list_jobs(workspace_id: UUID, response: Response, current=Depends(actor)):
        with database() as conn:
            _, _, context = checked(conn, current.subject, workspace_id, "workspace:read")
            candidates = conn.execute("""SELECT a.id,a.document_id,p.state,p.error_code,p.attempt,
                p.created_at,p.updated_at FROM attachment a JOIN attachment_parse p ON p.attachment_id=a.id
                WHERE a.workspace_id=%s AND a.uploader_id=%s AND a.classification<=%s
                ORDER BY p.updated_at DESC LIMIT 200""",
                (workspace_id, context.actor_id, context.classification)).fetchall()
            visible = []
            for row in candidates:
                try:
                    selected(conn, current.subject, workspace_id, row["document_id"], row["id"])
                except AccessDenied:
                    continue
                visible.append(AttachmentJobSnapshot.model_validate(dict(row)).model_dump(mode="json"))
                if len(visible) == 25:
                    break
        response.headers["Cache-Control"] = "no-store"
        return {"data": visible, "limited": len(candidates) == 200 or len(visible) == 25}

    router.include_router(documents)
    router.include_router(jobs)
    return router
