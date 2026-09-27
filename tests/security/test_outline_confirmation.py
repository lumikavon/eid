"""Offline source contract cases for Story 2.6; runtime execution is deferred."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError

from edw_api.access.policy import AccessDenied
from edw_api.documents.domain import content_hash
from edw_api.documents.outline_repository import (
    _identity_reasons,
    _reasons,
    _result,
    _section_reasons,
    _template_sections,
    confirm_outline,
    list_outline_versions,
    read_outline,
    read_outline_version,
    save_outline,
)
from edw_api.documents.outline_schemas import OutlineSnapshot, SaveOutline
from edw_api.errors import ApiError

WORKSPACE = UUID("00000000-0000-4000-8000-000000000001")
DOCUMENT = UUID("00000000-0000-4000-8000-000000000002")
ACTOR = UUID("00000000-0000-4000-8000-000000000003")
DOC_VERSION = UUID("00000000-0000-4000-8000-000000000004")
CONTEXT_VERSION = UUID("00000000-0000-4000-8000-000000000005")
TEMPLATE_VERSION = UUID("00000000-0000-4000-8000-000000000006")
OUTLINE_VERSION = UUID("00000000-0000-4000-8000-000000000007")
SECTION = UUID("00000000-0000-4000-8000-000000000008")
TEMPLATE_SECTION = UUID("00000000-0000-4000-8000-000000000009")
OPTIONAL_SECTION = UUID("00000000-0000-4000-8000-00000000000a")
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def rules():
    return [{"id": str(TEMPLATE_SECTION), "title": "概述", "mandatory": True},
            {"id": str(OPTIONAL_SECTION), "title": "附录", "mandatory": False}]


def snapshot(*, section_id=SECTION, title="概述", template_id=TEMPLATE_SECTION):
    return OutlineSnapshot.model_validate({"sections": [{"id": str(section_id), "title": title,
        "template_section_id": str(template_id) if template_id else None}]})


def resource():
    return {"id": DOCUMENT, "publication_state": "unpublished", "approval_state": "draft"}


def document():
    return {"head_version_id": DOC_VERSION, "revision": 1,
            "template_version_id": TEMPLATE_VERSION}


def context():
    return {"version_id": CONTEXT_VERSION, "state": "CONTEXT_READY", "reasons": []}


def row(*, confirmed=False, version_id=OUTLINE_VERSION, revision=1):
    body = snapshot().model_dump(mode="json")
    return {"version_id": version_id, "revision": revision, "base_version_id": None,
            "snapshot": body, "content_hash": content_hash(body),
            "document_version_id": DOC_VERSION, "document_revision": 1,
            "context_version_id": CONTEXT_VERSION, "template_version_id": TEMPLATE_VERSION,
            "created_by": ACTOR, "created_at": NOW,
            "confirmed_by": ACTOR if confirmed else None,
            "confirmed_at": NOW if confirmed else None,
            "ready_at_confirmation": confirmed}


def save_command(**patch):
    value = {"base_outline_version_id": None, "outline_revision": 0,
             "document_version_id": DOC_VERSION, "document_revision": 1,
             "context_version_id": CONTEXT_VERSION,
             "template_version_id": TEMPLATE_VERSION, "snapshot": snapshot()}
    return SimpleNamespace(**(value | patch))


def confirm_command(**patch):
    value = {"version_id": OUTLINE_VERSION, "document_version_id": DOC_VERSION,
             "document_revision": 1, "context_version_id": CONTEXT_VERSION,
             "template_version_id": TEMPLATE_VERSION}
    return SimpleNamespace(**(value | patch))


def arrange_current(monkeypatch):
    monkeypatch.setattr("edw_api.documents.outline_repository._target",
                        lambda *args, **kwargs: ({"actor_id": ACTOR, "evaluated_at": NOW},
                                                 resource(), document()))
    monkeypatch.setattr("edw_api.documents.outline_repository.read_context",
                        lambda *args: context())
    monkeypatch.setattr("edw_api.documents.outline_repository._template_sections",
                        lambda *args: rules())
    monkeypatch.setattr("edw_api.documents.outline_repository.checked",
                        lambda *args: None)


def test_client_cannot_supply_mandatory_flag_or_unbounded_title():
    valid = save_command().snapshot.model_dump(mode="json")
    valid["sections"][0]["mandatory"] = False
    with pytest.raises(ValidationError):
        OutlineSnapshot.model_validate(valid)
    with pytest.raises(ValidationError):
        OutlineSnapshot.model_validate({"sections": [{"id": str(SECTION),
            "title": "x" * 257, "template_section_id": str(TEMPLATE_SECTION)}]})
    with pytest.raises(ValidationError):
        SaveOutline.model_validate({**save_command().__dict__, "snapshot": valid})


def test_required_template_identity_and_title_cannot_be_replaced_by_same_name():
    for changed, expected in [
        (snapshot(template_id=None), "REQUIRED_SECTION_MISSING"),
        (snapshot(template_id=OPTIONAL_SECTION), "REQUIRED_SECTION_MISSING"),
        (snapshot(title="改写概述"), "REQUIRED_SECTION_TITLE_CHANGED"),
    ]:
        found = _section_reasons(changed, rules())
        assert expected in {reason["code"] for reason in found}
        assert all("path" in reason for reason in found)
    assert _section_reasons(snapshot(), rules()) == []
    assert _identity_reasons(snapshot(), snapshot(section_id=ACTOR)) == [{
        "code": "TEMPLATE_SECTION_ID_CHANGED", "path": "sections[0].id",
        "template_section_id": str(TEMPLATE_SECTION)}]


def test_duplicate_and_foreign_template_section_ids_are_located():
    data = OutlineSnapshot.model_validate({"sections": [
        {"id": str(SECTION), "title": "概述", "template_section_id": str(TEMPLATE_SECTION)},
        {"id": str(SECTION), "title": "概述", "template_section_id": str(TEMPLATE_SECTION)},
        {"id": str(ACTOR), "title": "未授权模板章", "template_section_id": str(DOCUMENT)},
    ]})
    assert {reason["code"] for reason in _section_reasons(data, rules())} == {
        "DUPLICATE_SECTION_ID", "DUPLICATE_TEMPLATE_SECTION", "UNKNOWN_TEMPLATE_SECTION"}


def test_fixture_manifest_is_deterministic_and_unproven_policy_fails_closed():
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {
        "id": TEMPLATE_VERSION, "structure": {"sections": [{"title": "概述"}]},
        "fixture_owner": "story-2.1", "development_only": True,
        "rule_refs": None, "manifest_sha256": None}
    assert _template_sections(conn, TEMPLATE_VERSION) == [{
        "id": str(uuid5(TEMPLATE_VERSION, "outline-section:0")),
        "title": "概述", "mandatory": True}]
    conn.execute.return_value.fetchone.return_value["fixture_owner"] = "other-project"
    with pytest.raises(ApiError) as error:
        _template_sections(conn, TEMPLATE_VERSION)
    assert (error.value.status_code, error.value.code) == (503, "TEMPLATE_POLICY_UNAVAILABLE")


@pytest.mark.parametrize("changed,code", [
    ({"head_version_id": ACTOR}, "DOCUMENT_CHANGED"),
    ({"revision": 2}, "DOCUMENT_CHANGED"),
    ({"template_version_id": ACTOR}, "TEMPLATE_CHANGED"),
])
def test_current_readiness_rechecks_document_and_template_heads(changed, code):
    current = document() | changed
    assert code in {r["code"] for r in _reasons(snapshot(), row(confirmed=True),
                                                  current, resource(), context(), rules())}


def test_context_change_and_revoked_edit_grant_remove_ready(monkeypatch):
    def denied(*args):
        raise AccessDenied()
    monkeypatch.setattr("edw_api.documents.outline_repository.checked", denied)
    changed_context = context() | {"version_id": ACTOR, "state": "CONTEXT_PENDING",
                                   "reasons": [{"code": "DOCUMENT_CHANGED", "path": "document"}]}
    result = _result(Mock(), "subject", WORKSPACE, resource(), document(), row(confirmed=True),
                     rules(), changed_context)
    assert result["state"] == "OUTLINE_PENDING"
    assert {r["code"] for r in result["reasons"]} == {
        "CONTEXT_CHANGED", "CONTEXT_NOT_READY", "CURRENT_EDIT_DENIED"}


def test_hidden_document_returns_404_before_outline_or_history_query(monkeypatch):
    def hidden(*args, **kwargs):
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在或当前不可见")
    monkeypatch.setattr("edw_api.documents.outline_repository._target", hidden)
    conn = Mock()
    for action in (read_outline, list_outline_versions):
        with pytest.raises(ApiError) as error:
            action(conn, "subject", WORKSPACE, DOCUMENT)
        assert (error.value.status_code, error.value.code) == (404, "DOCUMENT_NOT_FOUND")
    conn.execute.assert_not_called()


def test_revoked_write_grant_prevents_save_and_confirm_before_sql(monkeypatch):
    def denied(*args, **kwargs):
        assert kwargs["write"] is True
        raise AccessDenied()
    monkeypatch.setattr("edw_api.documents.outline_repository._target", denied)
    conn = Mock()
    for action, command in ((save_outline, save_command()),
                            (confirm_outline, confirm_command())):
        with pytest.raises(AccessDenied):
            action(conn, "subject", WORKSPACE, DOCUMENT, command, "req", "trace")
    conn.execute.assert_not_called()


@pytest.mark.parametrize("patch,code", [
    ({"document_version_id": ACTOR}, "DOC_VERSION_CONFLICT"),
    ({"template_version_id": ACTOR}, "TEMPLATE_VERSION_CONFLICT"),
    ({"context_version_id": ACTOR}, "CONTEXT_VERSION_CONFLICT"),
])
def test_save_rejects_stale_prerequisites_before_insert(monkeypatch, patch, code):
    arrange_current(monkeypatch)
    conn = Mock()
    with pytest.raises(ApiError) as error:
        save_outline(conn, "subject", WORKSPACE, DOCUMENT, save_command(**patch), "req", "trace")
    assert (error.value.status_code, error.value.code) == (409, code)
    conn.execute.assert_not_called()


def test_save_rejects_stale_outline_cas_and_invalid_required_section(monkeypatch):
    arrange_current(monkeypatch)
    monkeypatch.setattr("edw_api.documents.outline_repository._head", lambda *args, **kwargs: row())
    conn = Mock()
    with pytest.raises(ApiError) as stale:
        save_outline(conn, "subject", WORKSPACE, DOCUMENT, save_command(), "req", "trace")
    assert stale.value.code == "OUTLINE_VERSION_CONFLICT"
    monkeypatch.setattr("edw_api.documents.outline_repository._head", lambda *args, **kwargs: None)
    with pytest.raises(ApiError) as invalid:
        save_outline(conn, "subject", WORKSPACE, DOCUMENT,
                     save_command(snapshot=snapshot(template_id=None)), "req", "trace")
    assert invalid.value.code == "OUTLINE_INVALID"
    assert invalid.value.details["reasons"][0]["code"] == "REQUIRED_SECTION_MISSING"
    conn.execute.assert_not_called()


def test_head_update_cas_rejects_racing_writer_before_audit(monkeypatch):
    arrange_current(monkeypatch)
    monkeypatch.setattr("edw_api.documents.outline_repository._head",
                        lambda *args, **kwargs: row())
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = None
    with pytest.raises(ApiError) as error:
        save_outline(conn, "subject", WORKSPACE, DOCUMENT,
                     save_command(base_outline_version_id=OUTLINE_VERSION, outline_revision=1),
                     "req", "trace")
    assert error.value.code == "OUTLINE_VERSION_CONFLICT"
    assert any("UPDATE document_outline_head" in call.args[0]
               for call in conn.execute.call_args_list)
    assert not any("INSERT INTO access_audit" in call.args[0]
                   for call in conn.execute.call_args_list)


def test_context_not_ready_blocks_save_even_with_matching_context_version(monkeypatch):
    arrange_current(monkeypatch)
    monkeypatch.setattr("edw_api.documents.outline_repository.read_context",
                        lambda *args: context() | {"state": "CONTEXT_PENDING",
                                                  "reasons": [{"code": "FACTS_REQUIRED", "path": "facts"}]})
    conn = Mock()
    with pytest.raises(ApiError) as error:
        save_outline(conn, "subject", WORKSPACE, DOCUMENT, save_command(), "req", "trace")
    assert (error.value.status_code, error.value.code) == (422, "CONTEXT_NOT_READY")
    assert error.value.details["reasons"][0]["path"] == "facts"
    conn.execute.assert_not_called()


def test_save_and_explicit_confirm_create_separate_receipts_and_audit(monkeypatch):
    arrange_current(monkeypatch)
    before = row()
    monkeypatch.setattr("edw_api.documents.outline_repository._head",
                        Mock(side_effect=[None, before, before, row(confirmed=True)]))
    conn = Mock()
    saved = save_outline(conn, "subject", WORKSPACE, DOCUMENT, save_command(), "req", "trace")
    assert saved["state"] == "OUTLINE_PENDING"
    assert "HUMAN_CONFIRMATION_REQUIRED" in {r["code"] for r in saved["reasons"]}
    assert saved["version_id"] == OUTLINE_VERSION
    assert saved["revision"] == 1
    version_insert = next(call for call in conn.execute.call_args_list
                          if "INSERT INTO document_outline_version" in call.args[0])
    head_insert = next(call for call in conn.execute.call_args_list
                       if "INSERT INTO document_outline_head" in call.args[0])
    assert version_insert.args[1][0] == head_insert.args[1][1]
    assert version_insert.args[1][2:5] == (1, None, DOC_VERSION)
    save_audit = next(call for call in conn.execute.call_args_list
                      if "INSERT INTO access_audit" in call.args[0])
    assert save_audit.args[1][1:5] == (WORKSPACE, ACTOR, DOCUMENT, "outline.save")
    assert save_audit.args[1][7:9] == ("req", "trace")
    conn.reset_mock()
    confirmed = confirm_outline(conn, "subject", WORKSPACE, DOCUMENT,
                                confirm_command(), "req", "trace")
    assert confirmed["state"] == "OUTLINE_READY"
    assert confirmed["version_id"] == OUTLINE_VERSION
    assert confirmed["confirmed_by"] == ACTOR
    assert confirmed["confirmed_at"] == NOW
    assert any("INSERT INTO document_outline_confirmation" in call.args[0]
               for call in conn.execute.call_args_list)
    confirm_audit = next(call for call in conn.execute.call_args_list
                         if "INSERT INTO access_audit" in call.args[0])
    assert confirm_audit.args[1][1:5] == (WORKSPACE, ACTOR, DOCUMENT, "outline.confirm")
    assert confirm_audit.args[1][7:9] == ("req", "trace")


def test_confirmation_rejects_superseded_version_without_new_receipt(monkeypatch):
    arrange_current(monkeypatch)
    monkeypatch.setattr("edw_api.documents.outline_repository._head", lambda *args, **kwargs: row())
    conn = Mock()
    with pytest.raises(ApiError) as error:
        confirm_outline(conn, "subject", WORKSPACE, DOCUMENT,
                        confirm_command(version_id=ACTOR), "req", "trace")
    assert error.value.code == "OUTLINE_VERSION_CONFLICT"
    conn.execute.assert_not_called()


def test_confirmation_rejects_changed_saved_prerequisite_and_incomplete_snapshot(monkeypatch):
    arrange_current(monkeypatch)
    conn = Mock()
    monkeypatch.setattr("edw_api.documents.outline_repository._head",
                        lambda *args, **kwargs: row() | {"context_version_id": ACTOR})
    with pytest.raises(ApiError) as changed:
        confirm_outline(conn, "subject", WORKSPACE, DOCUMENT,
                        confirm_command(), "req", "trace")
    assert changed.value.code == "OUTLINE_PREREQUISITE_CHANGED"
    invalid_body = snapshot(template_id=None).model_dump(mode="json")
    incomplete = row() | {"snapshot": invalid_body, "content_hash": content_hash(invalid_body)}
    monkeypatch.setattr("edw_api.documents.outline_repository._head",
                        lambda *args, **kwargs: incomplete)
    with pytest.raises(ApiError) as missing:
        confirm_outline(conn, "subject", WORKSPACE, DOCUMENT,
                        confirm_command(), "req", "trace")
    assert missing.value.code == "OUTLINE_INCOMPLETE"
    assert missing.value.details["reasons"][0]["code"] == "REQUIRED_SECTION_MISSING"
    conn.execute.assert_not_called()


def test_repeated_confirmation_rechecks_grant_but_never_inserts_second_receipt(monkeypatch):
    arrange_current(monkeypatch)
    target = Mock(return_value=({"actor_id": ACTOR, "evaluated_at": NOW},
                                resource(), document()))
    monkeypatch.setattr("edw_api.documents.outline_repository._target", target)
    monkeypatch.setattr("edw_api.documents.outline_repository._head",
                        lambda *args, **kwargs: row(confirmed=True))
    conn = Mock()
    result = confirm_outline(conn, "subject", WORKSPACE, DOCUMENT,
                             confirm_command(), "req", "trace")
    assert result["state"] == "OUTLINE_READY"
    target.assert_called_once_with(conn, "subject", WORKSPACE, DOCUMENT, write=True)
    conn.execute.assert_not_called()


@pytest.mark.parametrize("patch,code", [
    ({"document_version_id": ACTOR}, "DOC_VERSION_CONFLICT"),
    ({"context_version_id": ACTOR}, "CONTEXT_VERSION_CONFLICT"),
    ({"template_version_id": ACTOR}, "TEMPLATE_VERSION_CONFLICT"),
])
def test_confirmation_rechecks_prerequisite_versions_before_receipt(monkeypatch, patch, code):
    arrange_current(monkeypatch)
    conn = Mock()
    with pytest.raises(ApiError) as error:
        confirm_outline(conn, "subject", WORKSPACE, DOCUMENT,
                        confirm_command(**patch), "req", "trace")
    assert (error.value.status_code, error.value.code) == (409, code)
    conn.execute.assert_not_called()


def test_history_is_scoped_and_old_confirmed_version_is_not_ready(monkeypatch):
    arrange_current(monkeypatch)
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [
        {"version_id": OUTLINE_VERSION, "revision": 2, "document_version_id": DOC_VERSION,
         "context_version_id": CONTEXT_VERSION, "template_version_id": TEMPLATE_VERSION,
         "created_by": ACTOR, "created_at": NOW, "confirmed_by": None, "confirmed_at": None}]
    page = list_outline_versions(conn, "subject", WORKSPACE, DOCUMENT)
    assert page["items"][0]["version_id"] == OUTLINE_VERSION
    assert page["more"] is False
    assert conn.execute.call_args.args[1] == (DOCUMENT,)
    old = _reasons(snapshot(), row(confirmed=True), document(), resource(), context(), rules(),
                   current=False)
    assert "OUTLINE_SUPERSEDED" in {reason["code"] for reason in old}


def test_historical_read_hides_missing_version_and_never_promotes_old_confirmation(monkeypatch):
    arrange_current(monkeypatch)
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = None
    with pytest.raises(ApiError) as missing:
        read_outline_version(conn, "subject", WORKSPACE, DOCUMENT, OUTLINE_VERSION)
    assert (missing.value.status_code, missing.value.code) == (404, "OUTLINE_VERSION_NOT_FOUND")
    conn.execute.return_value.fetchone.return_value = row(confirmed=True)
    monkeypatch.setattr("edw_api.documents.outline_repository._head",
                        lambda *args, **kwargs: row(version_id=ACTOR, revision=2))
    old = read_outline_version(conn, "subject", WORKSPACE, DOCUMENT, OUTLINE_VERSION)
    assert old["state"] == "OUTLINE_PENDING"
    assert "OUTLINE_SUPERSEDED" in {reason["code"] for reason in old["reasons"]}
