"""Deferred software-only attachment parser checks; do not execute in current phase."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile

import pytest

from edw_worker.attachment_parser_process import safe_zip, page
from edw_worker import attachments


def archive(name, payload=b"x"):
    out = BytesIO()
    with ZipFile(out, "w") as zip_file:
        zip_file.writestr(name, payload)
    return out.getvalue()


@pytest.mark.parametrize("name", ["../word/document.xml", "/word/document.xml", "word/vbaProject.bin"])
def test_unsafe_archive_rejected(name):
    with pytest.raises(ValueError):
        safe_zip(archive(name), "docx")


def test_chunk_locator_and_digest_are_bounded():
    result = page(3, "a" * 8001)
    assert [item["locator"] for item in result["chunks"]] == ["page:3:char:0", "page:3:char:4000", "page:3:char:8000"]
    assert all(len(item["text"]) <= 4000 and len(item["sha256"]) == 64 for item in result["chunks"])


def test_cleanup_never_deletes_recent_or_retained_objects(monkeypatch):
    deleted = []
    now = datetime.now(timezone.utc)

    class Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return self

        def paginate(self, **kwargs):
            assert kwargs["Prefix"] == "attachment-quarantine/"
            yield {"Contents": [
                {"Key": "attachment-quarantine/recent", "LastModified": now},
                {"Key": "attachment-quarantine/retained", "LastModified": now - timedelta(days=2)},
                {"Key": "attachment-quarantine/orphan", "LastModified": now - timedelta(days=2)},
            ]}

        def delete_object(self, **kwargs):
            deleted.append(kwargs["Key"])

        def close(self):
            pass

    monkeypatch.setattr(attachments.boto3, "client", lambda *args, **kwargs: Client())
    monkeypatch.setattr(attachments, "call", lambda sql, args: args[0].endswith("orphan"))
    monkeypatch.setenv("EID_S3_ENDPOINT_URL", "http://invalid.local")
    monkeypatch.setenv("EID_S3_ACCESS_KEY", "unused")
    monkeypatch.setenv("EID_S3_SECRET_KEY", "unused")
    monkeypatch.setenv("EID_S3_BUCKET", "unused")
    attachments.cleanup_orphans()
    assert deleted == ["attachment-quarantine/orphan"]


def test_cleanup_db_uncertainty_fails_closed(monkeypatch):
    deleted = []

    class Client:
        def get_paginator(self, name):
            return self

        def paginate(self, **kwargs):
            yield {"Contents": [{"Key": "attachment-quarantine/orphan",
                                 "LastModified": datetime.now(timezone.utc) - timedelta(days=2)}]}

        def delete_object(self, **kwargs):
            deleted.append(kwargs)

        def close(self):
            pass

    monkeypatch.setattr(attachments.boto3, "client", lambda *args, **kwargs: Client())
    monkeypatch.setattr(attachments, "call", lambda sql, args: (_ for _ in ()).throw(RuntimeError("database unavailable")))
    monkeypatch.setenv("EID_S3_ENDPOINT_URL", "http://invalid.local")
    monkeypatch.setenv("EID_S3_ACCESS_KEY", "unused")
    monkeypatch.setenv("EID_S3_SECRET_KEY", "unused")
    monkeypatch.setenv("EID_S3_BUCKET", "unused")
    with pytest.raises(RuntimeError):
        attachments.cleanup_orphans()
    assert deleted == []
