"""Offline security contract cases for manual context (not executed in Story 2.5)."""
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import ValidationError

from edw_api.documents.context_schemas import ContextSnapshot, Missing
from edw_api.documents.context_repository import (_collisions, _missing_regressions, _reasons,
                                                   _sources, confirm_context, save_context)
from edw_api.errors import ApiError
from edw_api.access.policy import AccessDenied

ACTOR = "11111111-1111-4111-8111-111111111111"
SOURCE = "33333333-3333-4333-8333-333333333333"


def snapshot(*, confirmed=True, locator="manual:project brief p.3", resource=None):
    return ContextSnapshot.model_validate({"intent": "Deploy approved project scope", "facts": [{"key": "Capacity", "value": "42", "unit": "kW",
        "source": {"locator": locator, "resource_id": resource}, "owner_id": ACTOR,
        "confirmed": confirmed}], "glossary": [], "constraints": [], "missing": [], "zero_facts": False})


def row(confirmed=True):
    return {"document_version_id": UUID(SOURCE), "document_revision": 1,
            "confirmed_at": "2026-09-26T00:00:00Z" if confirmed else None,
            "ready_at_confirmation": confirmed}


def document():
    return {"head_version_id": UUID(SOURCE), "revision": 1}


def resource():
    return {"publication_state": "unpublished", "approval_state": "draft"}


def test_empty_source_and_zero_facts_with_facts_rejected():
    with pytest.raises(ValidationError):
        snapshot(locator="  ")
    with pytest.raises(ValidationError):
        ContextSnapshot.model_validate({**snapshot().model_dump(mode="json"), "zero_facts": True})


def test_no_implicit_ready_without_human_confirmation_or_on_document_edit():
    assert {r["code"] for r in _reasons(snapshot(), document(), row(False), resource())} == {
        "HUMAN_CONFIRMATION_REQUIRED"}
    assert "DOCUMENT_CHANGED" in {r["code"] for r in _reasons(snapshot(),
        {"head_version_id": UUID(ACTOR), "revision": 2}, row(), resource())}
    assert "FACT_UNCONFIRMED" in {r["code"] for r in _reasons(snapshot(confirmed=False),
        document(), row(), resource())}


def test_required_missing_and_zero_fact_ack_preconditions():
    empty = ContextSnapshot.model_validate({"intent": "Manual purpose", "facts": [], "glossary": [], "constraints": [],
                                             "missing": [], "zero_facts": False})
    assert "FACTS_REQUIRED" in {r["code"] for r in _reasons(empty, document(), row(), resource())}
    pending = empty.model_copy(update={"zero_facts": True, "missing": [
        Missing(key="customer sign-off", required=True, resolved=False)]})
    assert "REQUIRED_MISSING" in {r["code"] for r in _reasons(pending, document(), row(), resource())}


def test_recorded_required_missing_cannot_be_silently_dropped():
    pending = snapshot()
    pending.missing.append(Missing(key="approval", required=True, resolved=False))
    assert _missing_regressions(pending, snapshot()) == [
        {"code": "REQUIRED_MISSING_NOT_RESOLVED", "path": "missing[0]"}]


def test_contradictions_located_without_overwriting_version():
    data = snapshot()
    data.facts.append(data.facts[0].model_copy(update={"value": "43"}))
    assert _collisions(data) == [{"code": "DUPLICATE_OR_CONTRADICTORY_ENTRY",
        "path": "facts[1].key", "other_path": "facts[0].key"}]


def test_stale_document_cas_rejects_before_any_context_write(monkeypatch):
    monkeypatch.setattr("edw_api.documents.context_repository._target",
        lambda *args, **kwargs: ({}, {}, document()))
    conn = Mock()
    command = SimpleNamespace(document_version_id=UUID(ACTOR), document_revision=1)
    with pytest.raises(ApiError) as error:
        save_context(conn, "subject", UUID(ACTOR), UUID(SOURCE), command, "req", "trace")
    assert error.value.code == "DOC_VERSION_CONFLICT"
    conn.execute.assert_not_called()


def test_zero_fact_confirmation_requires_explicit_ack(monkeypatch):
    empty = ContextSnapshot(intent="Manual project purpose", facts=[], glossary=[], constraints=[],
                            missing=[], zero_facts=True)
    saved = {"version_id": UUID(SOURCE), "confirmed_at": None}
    monkeypatch.setattr("edw_api.documents.context_repository._target",
        lambda *args, **kwargs: ({}, {}, document()))
    monkeypatch.setattr("edw_api.documents.context_repository._head",
        lambda *args, **kwargs: saved)
    monkeypatch.setattr("edw_api.documents.context_repository._snapshot", lambda _: empty)
    monkeypatch.setattr("edw_api.documents.context_repository._sources", lambda *args: None)
    monkeypatch.setattr("edw_api.documents.context_repository._owners", lambda *args: None)
    command = SimpleNamespace(document_version_id=UUID(SOURCE), document_revision=1,
                              version_id=UUID(SOURCE), zero_facts_acknowledged=False)
    conn = Mock()
    with pytest.raises(ApiError) as error:
        confirm_context(conn, "subject", UUID(ACTOR), UUID(SOURCE), command, "req", "trace")
    assert error.value.code == "ZERO_FACTS_ACK_REQUIRED"
    conn.execute.assert_not_called()


def test_foreign_source_is_not_treated_as_confirmed(monkeypatch):
    def denied(*args, **kwargs):
        raise AccessDenied()
    monkeypatch.setattr("edw_api.documents.context_repository.checked", denied)
    with pytest.raises(ApiError) as error:
        _sources(None, "subject", UUID(ACTOR), snapshot(resource=SOURCE))
    assert error.value.status_code == 404
