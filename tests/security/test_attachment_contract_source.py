"""Deferred runtime tests: only source is added in the software-only phase."""
from pathlib import Path

import pytest

from edw_api.attachments.routes import kind_for
from edw_api.errors import ApiError
from edw_api.task_contract import AttachmentJobSnapshot


def test_declared_type_and_signature_must_agree():
    assert kind_for(b"%PDF-1.7\n", "application/pdf") == "pdf"
    with pytest.raises(ApiError):
        kind_for(b"%PDF-1.7\n", "image/png")
    with pytest.raises(ApiError):
        kind_for(b"PK\x03\x04", "application/pdf")


def test_worker_cannot_select_protected_tables_directly():
    migration = Path("migrations/versions/0016_safe_attachments.py").read_text()
    assert "REVOKE ALL ON attachment,attachment_parse,attachment_page,attachment_chunk" in migration
    assert "eid_attachment_allowed_v1(p_id)" in migration
    assert "p.lease_owner IS DISTINCT FROM p_owner" in migration


def test_attachment_job_contract_rejects_invalid_state_and_attempt():
    valid = {
        "id": "11111111-1111-4111-8111-111111111111",
        "document_id": "22222222-2222-4222-8222-222222222222",
        "state": "QUEUED", "error_code": None, "attempt": 0,
        "created_at": "2026-09-27T00:00:00Z", "updated_at": "2026-09-27T00:00:00Z",
    }
    AttachmentJobSnapshot.model_validate(valid)
    for change in ({"state": "UNKNOWN"}, {"attempt": 4}, {"error_code": "sensitive data"}):
        with pytest.raises(ValueError):
            AttachmentJobSnapshot.model_validate({**valid, **change})


def test_orphan_cleanup_guard_stays_worker_only():
    migration = Path("migrations/versions/0016_safe_attachments.py").read_text()
    assert "session_user='eid_worker'" in migration
    assert "NOT EXISTS(SELECT 1 FROM attachment WHERE object_key=p_key)" in migration
    assert "GRANT EXECUTE ON FUNCTION eid_attachment_orphan_v1(text) TO eid_worker" in migration


def test_output_does_not_contain_storage_key():
    source = Path("edw-api/src/edw_api/attachments/routes.py").read_text()
    assert "SELECT a.id,a.sha256,a.kind" in source
    assert '"key": key' not in source
