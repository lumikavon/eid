"""Producing-boundary checks for policy ceilings, pages and short capabilities."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from edw_api.access import repository
from edw_api.access.policy import AccessDenied, AuthContext

WORKSPACE = str(UUID(int=1))
ACTOR = str(UUID(int=2))
CONTEXT = AuthContext(ACTOR, "eid-api", str(UUID(int=3)), WORKSPACE,
                      (4, 2, 4), 1, "workspace:read", "interactive", None)


def test_member_page_splits_fifty_one_small_rows_at_fifty(monkeypatch):
    rows = [{"identity_id": UUID(int=n)} for n in range(1, 52)]
    monkeypatch.setattr(repository, "checked", lambda *_: ({}, None, CONTEXT))
    conn = Mock()
    conn.execute.side_effect = lambda _sql, args: SimpleNamespace(fetchall=lambda: [
        row for row in rows if args[1] is None or row["identity_id"] > UUID(args[1])])
    first = repository.members(conn, "subject", WORKSPACE)
    assert first["members"] == rows[:50]
    assert first["next_cursor"] == str(rows[49]["identity_id"])
    last = repository.members(conn, "subject", WORKSPACE, first["next_cursor"])
    assert last["members"] == rows[50:]
    assert last["next_cursor"] is None


def test_large_valid_members_are_bounded_and_cursor_does_not_skip(monkeypatch):
    # Four maximum-length, maximum-count scopes with multibyte characters.
    scope = [str(n).zfill(3)+"界"*125 for n in range(100)]
    rows = [{"identity_id": UUID(int=n), "roles": ["author"],
             **{key: scope for key in ("project_scope", "customer_scope", "product_scope", "department_scope")}}
            for n in range(1, 5)]
    monkeypatch.setattr(repository, "checked", lambda *_: ({}, None, CONTEXT))
    conn = Mock()
    conn.execute.side_effect = lambda _sql, args: SimpleNamespace(
        fetchall=lambda: [row for row in rows if args[1] is None or row["identity_id"]>UUID(args[1])])
    cursor = None
    seen = []
    for _ in rows:
        page = repository.members(conn, "subject", WORKSPACE, cursor)
        assert len(json.dumps(page, default=str, ensure_ascii=False).encode()) < 256*1024
        assert len(page["members"]) == 1
        seen.extend(page["members"])
        cursor = page["next_cursor"]
        if cursor:
            assert cursor == str(page["members"][-1]["identity_id"])
    assert seen == rows
    assert cursor is None


def test_manager_cannot_raise_clearance_above_current_ceiling_without_writes(monkeypatch):
    monkeypatch.setattr(repository, "checked", lambda *a, **k: ({"clearance": 1}, None, CONTEXT))
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {"clearance": 1}
    with pytest.raises(AccessDenied):
        repository.change_member(conn, "subject", WORKSPACE, ACTOR, {"clearance": 2},
                                 [4, 2, 4], "request", "a"*32)
    assert conn.execute.call_count == 1
    assert conn.execute.call_args.args[0].startswith("SELECT * FROM access_member")


def test_delegation_expiry_is_exactly_five_database_minutes(monkeypatch):
    evaluated = datetime(2026, 9, 11, tzinfo=timezone.utc)
    monkeypatch.setattr(repository, "checked", lambda *a: (
        {"actor_id": ACTOR, "evaluated_at": evaluated}, None, CONTEXT))
    conn = Mock()
    result = repository.create_delegation(conn, "subject", WORKSPACE, None,
                                          "workspace:read", "stage", "request", "a"*32)
    expected = evaluated+timedelta(minutes=5)
    assert result["expires_at"] == expected
    assert conn.execute.call_args.args[1][6] == expected
    assert conn.execute.call_args.args[1][7] == 4


@pytest.mark.parametrize("field,expansion", [
    ("project_scope", ["foreign"]), ("customer_scope", ["foreign"]),
    ("product_scope", ["foreign"]), ("department_scope", ["foreign"]),
    ("owner_scope", "any"), ("approval_states", ["draft", "approved"]),
    ("valid_from", "earlier"), ("valid_until", "later"), ("valid_until", None),
])
def test_manager_attribute_and_validity_ceilings_reject_before_writes(monkeypatch, field, expansion):
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    facts = {"clearance": 1, "owner_scope": "self", "approval_states": ["draft"],
             "valid_from": now, "valid_until": now+timedelta(days=1),
             **{name: ["local"] for name in ("project_scope", "customer_scope", "product_scope", "department_scope")}}
    monkeypatch.setattr(repository, "checked", lambda *a, **k: (facts, None, CONTEXT))
    if expansion == "earlier":
        expansion = now-timedelta(seconds=1)
    elif expansion == "later":
        expansion = facts["valid_until"]+timedelta(seconds=1)
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = facts
    with pytest.raises(AccessDenied):
        repository.change_member(conn, "subject", WORKSPACE, ACTOR, facts | {field: expansion},
                                 [4, 2, 4], "request", "a"*32)
    assert conn.execute.call_count == 1
    assert conn.execute.call_args.args[0].startswith("SELECT * FROM access_member")


def test_first_workspace_rechecks_revoked_candidate_then_stops_at_first_allowed(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchone.side_effect = [{"workspace_id": UUID(int=n)} for n in (1, 2)]
    checked = Mock(side_effect=[AccessDenied(), ({"workspace_id": WORKSPACE}, None, CONTEXT)])
    monkeypatch.setattr(repository, "checked", checked)
    monkeypatch.setattr(repository, "workspace_payload", lambda facts, _: facts)
    assert repository.first_workspace(conn, "subject") == {"workspace_id": WORKSPACE}
    assert checked.call_count == conn.execute.call_count == 2
    assert conn.execute.call_args.args[1][1] == UUID(int=1)


def test_first_workspace_bounds_repeated_concurrent_revocations(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = {"workspace_id": UUID(int=1)}
    monkeypatch.setattr(repository, "checked", Mock(side_effect=AccessDenied()))
    with pytest.raises(repository.OperationalError):
        repository.first_workspace(conn, "subject")
    assert conn.execute.call_count == 3


def test_workspace_pages_reach_more_than_200_and_advance_over_denials(monkeypatch):
    ids = [UUID(int=n) for n in range(1, 207)]
    conn = Mock()
    conn.execute.side_effect = lambda _sql, args: SimpleNamespace(fetchall=lambda: [
        {"workspace_id": wid} for wid in ids if args[1] is None or wid>UUID(args[1])][:51])
    def checked(_conn, _subject, wid):
        if wid.int <= 50:
            raise AccessDenied()
        return {"workspace_id": str(wid)}, None, CONTEXT
    monkeypatch.setattr(repository, "checked", checked)
    monkeypatch.setattr(repository, "workspace_payload", lambda facts, _: facts)
    seen = []
    cursor = None
    for _ in range(5):
        page = repository.workspace_page(conn, "subject", cursor)
        assert len(page["workspaces"]) <= 50
        seen.extend(row["workspace_id"] for row in page["workspaces"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert seen == list(map(str, ids[50:]))


def test_workspace_byte_budget_keeps_large_names_readable_without_skipping(monkeypatch):
    ids = [UUID(int=n) for n in range(1, 26)]
    conn = Mock()
    conn.execute.side_effect = lambda _sql, args: SimpleNamespace(fetchall=lambda: [
        {"workspace_id": wid} for wid in ids if args[1] is None or wid>UUID(args[1])][:51])
    monkeypatch.setattr(repository, "checked", lambda _conn, _subject, wid: (
        {"workspace_id": str(wid), "name": "界"*2000}, None, CONTEXT))
    monkeypatch.setattr(repository, "workspace_payload", lambda facts, _: facts)
    cursor = None
    seen = []
    pages = 0
    while True:
        page = repository.workspace_page(conn, "subject", cursor)
        pages += 1
        assert pages <= len(ids)
        assert len(json.dumps({"data": page}, ensure_ascii=False).encode()) < 64*1024
        seen.extend(row["workspace_id"] for row in page["workspaces"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert cursor == page["workspaces"][-1]["workspace_id"]
    assert pages > 1
    assert seen == list(map(str, ids))
