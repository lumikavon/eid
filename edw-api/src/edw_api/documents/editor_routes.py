"""Current-permission editor, immutable version and private image HTTP boundary."""

import json
from contextlib import contextmanager
from hashlib import sha256
from uuid import UUID, uuid4

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from .editor_repository import editable_document, save_document
from .media import object_client, prepare_image
from .repository import _local_write_target
from .schemas import DocumentResponse, DomainAst


class SaveDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version_id: UUID
    revision: int = Field(ge=1, le=9007199254740990)
    ast: DomainAst


class UploadImage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alt: str = Field(min_length=1, max_length=512)
    base64_data: str = Field(min_length=1, max_length=7_000_000)

    @field_validator("alt")
    @classmethod
    def valid_alt(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Invalid image alternative text")
        return value


def create_router(settings, verify):
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(403, "ACCESS_DENIED", "当前权限不允许此访问") from exc
        except psycopg.Error as exc:
            raise ApiError(503, "POLICY_UNAVAILABLE", "当前权限存储不可用",
                           retryable=True) from exc

    @router.put("/documents/{document_id}", response_model=DocumentResponse)
    def save(workspace_id: UUID, document_id: UUID, command: SaveDocument,
             request: Request, current=Depends(actor)):
        with database() as conn:
            return DocumentResponse(data=save_document(
                conn, current.subject, workspace_id, document_id, command,
                request.state.request_id, request.state.trace_id))

    @router.post("/documents/{document_id}/images", status_code=201)
    async def upload(workspace_id: UUID, document_id: UUID, request: Request,
                     current=Depends(actor)):
        # Do not let FastAPI eagerly materialize an unbounded JSON/base64 body.
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 7_200_000:
                raise ApiError(413, "IMAGE_TOO_LARGE", "图片请求超过大小限制")
        try:
            payload = UploadImage.model_validate(json.loads(raw))
        except (ValidationError, ValueError, UnicodeDecodeError) as exc:
            raise ApiError(422, "INVALID_DOCUMENT_MEDIA", "图片请求格式无效") from exc
        data, digest, width, height = prepare_image(payload.base64_data)
        with database() as conn:
            editable_document(conn, current.subject, workspace_id, document_id)
            _local_write_target(conn)
        media_id = uuid4()
        key = f"document-media/{workspace_id}/{document_id}/{media_id}.png"
        s3 = object_client(settings)
        try:
            s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=data,
                          ContentType="image/png", Metadata={"sha256": digest})
        except (BotoCoreError, ClientError) as exc:
            raise ApiError(503, "MEDIA_STORAGE_UNAVAILABLE", "图片存储暂不可用",
                           retryable=True) from exc
        finally:
            s3.close()
        try:
            with database() as conn:
                facts, _ = editable_document(conn, current.subject, workspace_id,
                                             document_id, exclusive=True)
                _local_write_target(conn)
                conn.execute(
                    "INSERT INTO document_media(id,document_id,workspace_id,uploader_id,"
                    "object_key,content_hash,content_type,byte_length,alt,width,height) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'image/png',%s,%s,%s,%s)",
                    (media_id, document_id, workspace_id, facts["actor_id"], key, digest,
                     len(data), payload.alt, width, height),
                )
        except Exception:
            # Only our newly generated private key can be cleaned up; if cleanup
            # fails, no metadata exists to make the orphan readable via the API.
            s3 = object_client(settings)
            try:
                s3.delete_object(Bucket=settings.s3_bucket, Key=key)
            except (BotoCoreError, ClientError):
                pass
            finally:
                s3.close()
            raise
        return {"data": {"id": media_id, "content_hash": digest, "content_type": "image/png",
                         "byte_length": len(data), "alt": payload.alt, "width": width,
                         "height": height}}

    @router.get("/documents/{document_id}/images/{media_id}")
    def image(workspace_id: UUID, document_id: UUID, media_id: UUID,
              current=Depends(actor)):
        def authorized_media(conn):
            try:
                _, resource, _ = checked(conn, current.subject, workspace_id,
                                         "resource:read", document_id)
            except AccessDenied as exc:
                raise ApiError(404, "DOCUMENT_MEDIA_NOT_FOUND", "图片不存在或不可见") from exc
            if resource["kind"] != "document":
                raise ApiError(404, "DOCUMENT_MEDIA_NOT_FOUND", "图片不存在或不可见")
            row = conn.execute(
                "SELECT object_key,content_hash,byte_length FROM document_media "
                "WHERE id=%s AND document_id=%s AND workspace_id=%s",
                (media_id, document_id, workspace_id),
            ).fetchone()
            if row is None:
                raise ApiError(404, "DOCUMENT_MEDIA_NOT_FOUND", "图片不存在或不可见")
            return row

        with database() as conn:
            media = authorized_media(conn)
        s3 = object_client(settings)
        try:
            object_response = s3.get_object(Bucket=settings.s3_bucket, Key=media["object_key"])
            try:
                data = object_response["Body"].read(5 * 1024 * 1024 + 1)
            finally:
                object_response["Body"].close()
        except (BotoCoreError, ClientError) as exc:
            raise ApiError(503, "MEDIA_STORAGE_UNAVAILABLE", "图片存储暂不可用",
                           retryable=True) from exc
        finally:
            s3.close()
        if (len(data) != media["byte_length"] or sha256(data).hexdigest() != media["content_hash"]):
            raise ApiError(503, "DOCUMENT_MEDIA_INTEGRITY", "图片资源校验失败", retryable=True)
        # A grant can change during the object read; do not return protected bytes
        # without checking current rights once more.
        with database() as conn:
            latest = authorized_media(conn)
            if latest != media:
                raise ApiError(503, "DOCUMENT_MEDIA_INTEGRITY", "图片资源校验失败", retryable=True)
        return Response(content=data, media_type="image/png", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{media_id}.png"',
        })

    return router
