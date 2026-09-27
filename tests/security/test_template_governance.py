"""治理回归测试源码；当前策略禁止执行，包括不依赖服务的测试。"""
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from edw_api.access.policy import AccessDenied
from edw_api.documents import governance_repository as repository
from edw_api.documents import repository as documents
from edw_api.documents.domain import content_hash
from edw_api.documents.governance_schemas import CandidateMetadata, PublishCandidate, ValidationReport
from edw_api.errors import ApiError


def report_fixture():
    manifest = {"schema_version": "1.0", "name": "开发样例", "description": "非正式",
                "category": "研发", "document_type": "technical_solution",
                "sections": [{"id": str(uuid4()), "title": "背景", "mandatory": True}],
                "rules": {key: None for key in ("retrieval_profile_id", "prompt_version_id",
                    "reviewer_rule_version_id", "render_theme_version_id", "approval_policy_version_id")},
                "assets": []}
    return {"source_sha256": "1" * 64, "manifest_sha256": content_hash(manifest),
            "validator_version": "template-archive-v1", "development_only": True,
            "manifest": manifest, "assets": []}


def test_report_binds_exact_manifest_and_explicit_development_status():
    value = report_fixture()
    assert ValidationReport.model_validate(value).development_only is True
    changed = deepcopy(value)
    changed["manifest"]["sections"][0]["title"] = "被替换的章节"
    with pytest.raises(ValidationError):
        ValidationReport.model_validate(changed)
    value["development_only"] = False
    with pytest.raises(ValidationError):
        ValidationReport.model_validate(value)


@pytest.mark.parametrize("confirmation", [1, "true", False, None])
def test_publish_requires_literal_boolean_confirmation(confirmation):
    with pytest.raises(ValidationError):
        PublishCandidate.model_validate({"manifest_sha256": "0" * 64,
                                         "mode": "development", "confirmed": confirmation})


def test_new_family_cannot_borrow_existing_base_version():
    with pytest.raises(ValidationError):
        CandidateMetadata.model_validate({"version_label": "1.0", "scope": "project",
                                           "classification": 0, "base_version_id": str(uuid4())})


def test_malformed_asset_base64_is_report_integrity_error():
    value = report_fixture()
    value["manifest"]["assets"] = ["assets/cover.png"]
    value["assets"] = [{"name": "assets/cover.png", "source_sha256": "1" * 64,
                        "sha256": "2" * 64, "width": 1, "height": 1,
                        "png_base64": "not-base64!"}]
    value["manifest_sha256"] = content_hash(value["manifest"])
    row = {"state": "VALIDATED", "report": value, "package_sha256": "1" * 64}
    with pytest.raises(ApiError) as error:
        repository._report(row)
    assert error.value.status_code == 503


def test_report_rejects_cross_package_receipt_and_unvalidated_state():
    value = report_fixture()
    row = {"state": "VALIDATED", "report": value, "package_sha256": "2" * 64}
    with pytest.raises(ApiError) as error:
        repository._report(row)
    assert error.value.status_code == 503
    row["state"] = "RUNNING"
    with pytest.raises(ApiError) as error:
        repository._report(row)
    assert error.value.status_code == 409


def test_family_authorization_is_resource_bound_and_hides_revocation(monkeypatch):
    conn = Mock()
    resource = {"kind": "template", "id": uuid4()}
    conn.execute.return_value.fetchone.return_value = resource
    authorization = Mock(side_effect=AccessDenied())
    monkeypatch.setattr(repository, "authorize", authorization)
    facts = {"actor_id": uuid4()}
    with pytest.raises(ApiError) as error:
        repository._family(conn, facts, uuid4(), uuid4())
    assert error.value.status_code == 404
    authorization.assert_called_once_with(facts, "template:publish", resource)


def test_receipt_lookup_rechecks_current_candidate_access(monkeypatch):
    conn = Mock()
    actor, workspace, candidate = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(repository, "_admin", lambda *a, **k: {"actor_id": actor})
    conn.execute.return_value.fetchone.return_value = {"candidate_id": candidate}
    denied = Mock(side_effect=ApiError(404, "TEMPLATE_NOT_FOUND", "不可访问"))
    monkeypatch.setattr(repository, "_candidate", denied)
    with pytest.raises(ApiError) as error:
        repository.lookup_operation(conn, "subject", workspace, "original")
    assert error.value.status_code == 404
    denied.assert_called_once()


def test_upload_quota_rejects_before_new_family_or_blob_insert(monkeypatch):
    conn = Mock()
    receipt = Mock()
    receipt.fetchone.side_effect = [None, None, {"total": 128}]
    conn.execute.return_value = receipt
    monkeypatch.setattr(repository, "_admin", lambda *a, **k: {
        "actor_id": uuid4(), "classification": 0, "clearance": 1})
    monkeypatch.setattr(repository, "_local_write_target", lambda *a: None)
    metadata = CandidateMetadata(version_label="v2", scope="personal", classification=0)
    with pytest.raises(ApiError) as error:
        repository.upload_candidate(conn, "subject", uuid4(), metadata, b"zip", "key", "req", "trace")
    assert error.value.status_code == 409
    assert error.value.code == "TEMPLATE_CANDIDATE_QUOTA"
    assert not any("INSERT INTO template" in call.args[0] for call in conn.execute.call_args_list)


def test_upload_key_cannot_be_reused_for_an_action(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {"candidate_id": uuid4()}
    facts = {"actor_id": uuid4(), "workspace_id": uuid4()}
    with pytest.raises(ApiError) as error:
        repository._action_receipt(conn, facts, "original", "0" * 64)
    assert error.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_candidate_replay_never_skips_current_resource_authorization(monkeypatch):
    conn = Mock()
    actor, workspace, candidate = uuid4(), uuid4(), uuid4()
    metadata = CandidateMetadata(version_label="1.0", scope="project", classification=0)
    from hashlib import sha256
    digest = content_hash({"metadata": metadata.model_dump(mode="json"),
                           "package": sha256(b"original").hexdigest()})
    conn.execute.return_value.fetchone.return_value = {"payload_hash": digest, "candidate_id": candidate}
    monkeypatch.setattr(repository, "_admin", lambda *a, **k: {"actor_id": actor})
    monkeypatch.setattr(repository, "_local_write_target", lambda *a: None)
    current = Mock(side_effect=ApiError(404, "TEMPLATE_NOT_FOUND", "不可访问"))
    monkeypatch.setattr(repository, "_candidate", current)
    with pytest.raises(ApiError) as error:
        repository.upload_candidate(conn, "subject", workspace, metadata, b"original", "key", "req", "trace")
    assert error.value.status_code == 404
    assert current.call_args.args[-1] == candidate


def test_formal_publish_is_rejected_before_version_insert(monkeypatch):
    conn = Mock()
    monkeypatch.setattr(repository, "_admin", lambda *a, **k: {})
    monkeypatch.setattr(repository, "_local_write_target", lambda *a: None)
    monkeypatch.setattr(repository, "_candidate", lambda *a: {"template_id": uuid4()})
    monkeypatch.setattr(repository, "_lock_template_family", lambda *a: None)
    command = PublishCandidate(manifest_sha256="0" * 64, mode="formal", confirmed=True)
    with pytest.raises(ApiError) as error:
        repository.publish_candidate(conn, "subject", uuid4(), uuid4(), command, "key", "req", "trace")
    assert error.value.status_code == 409
    conn.execute.assert_not_called()


def test_deprecation_audit_records_status_transition(monkeypatch):
    conn = Mock()
    facts = {"actor_id": uuid4(), "workspace_id": uuid4(), "evaluated_at": "2026-09-26"}
    template_id, version_id = uuid4(), uuid4()
    monkeypatch.setattr(repository, "_admin", lambda *a, **k: facts)
    monkeypatch.setattr(repository, "_local_write_target", lambda *a: None)
    monkeypatch.setattr(repository, "version_detail", lambda *a: {
        "template_id": template_id, "status": "active"})
    monkeypatch.setattr(repository, "_lock_template_family", lambda *a: None)
    monkeypatch.setattr(repository, "_action_receipt", lambda *a: None)
    monkeypatch.setattr(repository, "_record_action", lambda *a: None)
    audit = Mock()
    monkeypatch.setattr(repository, "_audit", audit)
    conn.execute.return_value.fetchone.return_value = {"changed": True}
    from edw_api.documents.governance_schemas import DeprecateVersion
    command = DeprecateVersion(reason="替代版本", confirmed=True)
    repository.deprecate_version(conn, "subject", facts["workspace_id"], version_id,
                                 command, "key", "req", "trace")
    assert audit.call_args.kwargs["before"] == {"status": "active"}
    assert audit.call_args.args[4]["status"] == "deprecated"


def test_governed_catalog_visibility_requires_current_resource_read(monkeypatch):
    facts = {"clearance": 2, "actor_id": uuid4(), "department": "engineering",
             "product_id": "product", "project_id": "project"}
    manifest = report_fixture()["manifest"]
    row = {"workspace_active": True, "development_only": True, "classification": 1,
           "fixture_owner": None, "governed_resource": {"kind": "template"},
           "governed_manifest": manifest, "manifest_sha256": content_hash(manifest),
           "scope": "project", "owner_id": None, "target_scope_value": "project"}
    authorized = Mock(return_value=None)
    monkeypatch.setattr(documents, "authorize", authorized)
    assert documents._visible(facts, row) is True
    authorized.assert_called_once_with(facts, "resource:read", row["governed_resource"])
    monkeypatch.setattr(documents, "authorize", Mock(side_effect=AccessDenied()))
    assert documents._visible(facts, row) is False
    assert documents._visible(facts, {**row, "manifest_sha256": "0" * 64}) is False


def test_reference_pagination_filters_authority_before_limit(monkeypatch):
    conn = Mock()
    facts = {"actor_id": uuid4(), "workspace_id": uuid4()}
    monkeypatch.setattr(repository, "_admin", lambda *a: facts)
    monkeypatch.setattr(repository, "version_detail", lambda *a: {})
    conn.execute.return_value.fetchall.return_value = []
    result = repository.pinned_references(conn, "subject", facts["workspace_id"], uuid4())
    sql = conn.execute.call_args.args[0]
    assert sql.index("r.approval_state=ANY") < sql.index("LIMIT 101")
    assert "r.owner_id=%(actor_id)s" in sql
    assert result == {"items": [], "next_cursor": None, "scope": "currently_authorized_documents_only"}
