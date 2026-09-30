"""Story 2.1 current-grant and immutable-intent checks (runtime deferred)."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from edw_api.access.policy import AccessDenied, authorize
from edw_api.documents import domain, repository, routes
from edw_api.documents.schemas import CreateDocument, CreateDocumentFromTemplate
from edw_api.errors import ApiError


NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)
ACTOR = UUID("11111111-1111-4111-8111-111111111111")
WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
VERSION = UUID("33333333-3333-4333-8333-333333333333")


def facts():
    return {"actor_id": ACTOR, "workspace_id": WORKSPACE, "tenant_id": WORKSPACE,
            "identity_active": True, "membership_active": True, "roles": ["author"],
            "approval_states": ["draft"], "valid_from": NOW-timedelta(days=1),
            "valid_until": NOW+timedelta(days=1), "evaluated_at": NOW,
            "project_id": "p", "customer_id": "c", "product_id": "x", "department": "d",
            "project_scope": ["p"], "customer_scope": ["c"], "product_scope": ["x"],
            "department_scope": ["d"], "owner_scope": "self", "classification": 1,
            "clearance": 2, "workspace_epoch": 2, "policy_epoch": 3}


def template(scope="project", target="p", owner=None):
    return {"id": VERSION, "template_id": VERSION, "name": "开发样例",
            "description": "仅供开发", "scope": scope, "target_scope_value": target,
            "owner_id": owner, "category": "技术方案", "document_type": "technical_solution",
            "version_label": "1.0", "classification": 1, "development_only": True,
            "fixture_owner": "story-2.1", "workspace_active": True, "status": "active",
            "structure": {"sections": [{"title": "项目概述"}]}}


def command(name="  文档  "):
    return CreateDocument(name=name, document_type="technical_solution",
                          knowledge_scope="project_only", template_version_id=VERSION)


def source_command(title="  文档  "):
    return CreateDocumentFromTemplate(workspace_id=WORKSPACE, title=title,
                                      document_type="technical_solution", template_id=VERSION)


def test_name_is_canonical_and_initial_ast_has_own_stable_node_ids():
    first = command()
    assert first.name == "文档"
    ast = domain.initial_ast(first.name, first.document_type, first.knowledge_scope,
                             VERSION, template()["structure"])
    assert ast["schema_version"] == "1.0"
    assert ast["document"]["metadata"]["template_version_id"] == str(VERSION)
    sections = ast["document"]["sections"]
    assert len({sections[0]["id"], sections[0]["blocks"][0]["id"]}) == 2
    assert ast["document"]["claims"] == ast["document"]["citations"] == []
    assert domain.canonical_request_hash(WORKSPACE, first) == domain.canonical_request_hash(
        WORKSPACE, command("文档"))
    assert domain.content_hash(ast) == domain.content_hash(ast.copy())


def test_source_create_contract_normalizes_title_and_keeps_explicit_intent():
    chosen = source_command()
    assert chosen.title == "文档"
    assert chosen.knowledge_scope == "project_only"
    assert domain.canonical_request_hash(WORKSPACE, chosen) == domain.canonical_request_hash(
        WORKSPACE, source_command("文档"))
    assert domain.canonical_request_hash(WORKSPACE, chosen) != domain.canonical_request_hash(
        WORKSPACE, command("文档"))


def test_canonical_create_route_requires_idempotency_key():
    router = routes.create_canonical_router(object(), lambda token: token)
    route = next(item for item in router.routes if item.path == "/api/v1/documents")
    assert route.methods == {"POST"}
    assert any(parameter.alias.casefold() == "idempotency-key" and parameter.field_info.is_required()
               for parameter in route.dependant.header_params)


@pytest.mark.parametrize("name", [" ", "a\x00b", "a\ud800b", "x" * 257])
def test_invalid_name_rejected_before_repository(name):
    with pytest.raises(ValueError):
        command(name)


def test_template_scope_is_explicit_and_subject_bound():
    current = facts()
    assert repository._visible(current, template())
    assert not repository._visible(current, template(target="foreign"))
    assert not repository._visible(current, template(scope="personal", target=None, owner=None))
    assert repository._visible(current, template(scope="personal", target=None, owner=ACTOR))
    assert not repository._visible(current, template() | {"workspace_active": False})
    assert not repository._visible(current, template() | {"classification": 3})


def test_catalog_does_not_truncate_before_current_grant_filters(monkeypatch):
    current = facts()
    rows = [template() | {"id": UUID(int=index + 1), "target_scope_value": "foreign"}
            for index in range(256)] + [template()]

    class Result:
        def fetchall(self):
            return rows

    class Connection:
        def execute(self, sql, _params):
            assert "LIMIT 256" not in sql
            return Result()

    monkeypatch.setattr(repository, "checked", lambda *_args: (current, None, None))
    from edw_api.documents.schemas import TemplateFilters
    result = repository.list_templates(Connection(), "verified", WORKSPACE, TemplateFilters())
    assert len(result["items"]) == 1
    assert result["items"][0]["version_id"] == VERSION


def test_template_id_resolves_newest_active_visible_version_under_lock():
    older = template() | {"id": UUID(int=2), "status": "active"}
    newest = template() | {"id": UUID(int=3), "status": "deprecated"}

    class Result:
        def fetchall(self):
            return [newest, older]

    class Connection:
        def execute(self, sql, params):
            if sql.startswith("SELECT eid_lock_template_creation_v1"):
                assert params == (WORKSPACE, VERSION)
                return Result()
            assert "ORDER BY v.created_at DESC" in sql
            assert params == (WORKSPACE, VERSION)
            return Result()

    assert repository._template_for_creation(Connection(), facts(), WORKSPACE,
                                             source_command())["id"] == UUID(int=2)


def test_template_id_create_pins_version_and_content_digest(monkeypatch):
    current = facts()
    statements = []
    monkeypatch.setattr(repository, "checked", lambda *_args, **_kwargs:
                        (current, None, authorize(current, "document:create")))
    monkeypatch.setattr(repository, "_local_write_target", lambda _conn: None)
    monkeypatch.setattr(repository, "_scope_allowed", lambda *_args: None)
    monkeypatch.setattr(repository, "_template_for_creation", lambda *_args:
                        template() | {"id": UUID(int=2)})

    class Result:
        def fetchone(self):
            return None

    class Connection:
        def execute(self, sql, params=None):
            statements.append((sql, params))
            return Result()

    result = repository.create_document(Connection(), "verified", WORKSPACE, source_command(),
                                        idempotency_key="intent-1", request_id="request-1",
                                        trace_id="1" * 32)
    assert result["template_version_id"] == UUID(int=2)
    assert result["ast"]["document"]["metadata"]["template_version_id"] == str(UUID(int=2))
    assert result["base_version_id"] is None
    assert result["content_hash"] == domain.content_hash(result["ast"])
    version_insert = next(params for sql, params in statements
                          if sql.startswith("INSERT INTO document_version"))
    assert version_insert[2] == result["content_hash"]


def test_create_reauthorizes_before_receipt_or_template_lookup(monkeypatch):
    current = facts() | {"membership_active": False}
    calls = []

    def checked(_conn, _subject, _workspace, operation, *, exclusive):
        calls.append((operation, exclusive))
        authorize(current, operation)

    class Connection:
        def execute(self, *_args):
            pytest.fail("revoked actor reached persistence")

    monkeypatch.setattr(repository, "checked", checked)
    with pytest.raises(AccessDenied):
        repository.create_document(Connection(), "verified", WORKSPACE, command(),
                                   idempotency_key="intent-1", request_id="request-1",
                                   trace_id="1" * 32)
    assert calls == [("document:create", True)]


def test_deprecated_template_rejects_without_any_insert(monkeypatch):
    current = facts()
    events = []

    def checked(_conn, _subject, _workspace, operation, *, exclusive):
        events.append("authorize")
        return current, None, authorize(current, operation)

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def execute(self, sql, _params=None):
            if sql.startswith("SELECT payload_hash"):
                events.append("receipt")
                return Result(None)
            if sql.startswith("SELECT template_id FROM template_version"):
                return Result({"template_id": VERSION})
            if sql.startswith("SELECT eid_lock_template_creation_v1"):
                events.append("template_lock")
                return Result(None)
            if sql.startswith(repository.TEMPLATE_BASE_SQL):
                events.append("template_read")
                return Result(template() | {"status": "deprecated"})
            pytest.fail("rejected template reached a write")

    monkeypatch.setattr(repository, "checked", checked)
    monkeypatch.setattr(repository, "_local_write_target", lambda _conn: events.append("target"))
    monkeypatch.setattr(repository, "_scope_allowed", lambda *_: events.append("scope"))
    with pytest.raises(ApiError) as error:
        repository.create_document(Connection(), "verified", WORKSPACE, command(),
                                   idempotency_key="intent-1", request_id="request-1",
                                   trace_id="1" * 32)
    assert error.value.code == "TEMPLATE_DEPRECATED"
    assert events == ["authorize", "target", "scope", "receipt", "template_lock",
                      "template_read"]


def test_replay_rechecks_create_and_resource_rights_before_return(monkeypatch):
    current = facts()
    chosen = command()
    events = []

    def checked(_conn, _subject, _workspace, operation, *, exclusive):
        events.append("create_grant")
        return current, None, authorize(current, operation)

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def execute(self, sql, _params=None):
            if sql.startswith("SELECT payload_hash"):
                events.append("receipt")
                return Result({"payload_hash": domain.canonical_request_hash(WORKSPACE, chosen),
                               "document_id": VERSION})
            if sql.startswith("SELECT template_id FROM template_version"):
                return Result({"template_id": VERSION})
            if sql.startswith("SELECT eid_lock_template_creation_v1"):
                events.append("template_lock")
                return Result(None)
            assert sql.startswith(repository.TEMPLATE_BASE_SQL)
            events.append("template_grant")
            return Result(template() | {"status": "deprecated"})

    monkeypatch.setattr(repository, "checked", checked)
    monkeypatch.setattr(repository, "_local_write_target", lambda _conn: events.append("target"))
    monkeypatch.setattr(repository, "_scope_allowed", lambda *_: events.append("scope"))
    monkeypatch.setattr(repository, "_document_row", lambda *_: events.append("read_grant") or
                        {"id": VERSION, "template_version_id": VERSION})
    result = repository.create_document(Connection(), "verified", WORKSPACE, chosen,
                                        idempotency_key="intent-1", request_id="request-1",
                                        trace_id="1" * 32)
    assert result == {"id": VERSION, "template_version_id": VERSION, "replayed": True}
    assert events == ["create_grant", "target", "scope", "receipt", "read_grant",
                      "template_lock", "template_grant"]


def test_replay_rejects_template_grant_revoked():
    class Result:
        def fetchone(self):
            return template() | {"workspace_active": False, "status": "deprecated"}

    class Connection:
        def execute(self, sql, params):
            if sql.startswith("SELECT template_id FROM template_version"):
                assert params == (VERSION,)
                return ResultTemplate()
            if sql.startswith("SELECT eid_lock_template_creation_v1"):
                assert params == (WORKSPACE, VERSION)
                return ResultVoid()
            assert sql.startswith(repository.TEMPLATE_BASE_SQL)
            assert params == (WORKSPACE, VERSION)
            return Result()

    class ResultTemplate:
        def fetchone(self):
            return {"template_id": VERSION}

    class ResultVoid:
        pass

    with pytest.raises(ApiError) as error:
        repository._recheck_replay_template(Connection(), facts(), WORKSPACE, VERSION)
    assert error.value.code == "TEMPLATE_NOT_FOUND"


def test_historical_document_read_needs_document_grant_and_valid_content(monkeypatch):
    current = facts()
    resource = {"id": VERSION, "workspace_id": WORKSPACE, "owner_id": ACTOR,
                "title": "旧文档", "head_ref": VERSION, "project_id": "p",
                "customer_id": "c", "product_id": "x", "department": "d",
                "valid_from": NOW-timedelta(days=1), "valid_until": None,
                "approval_state": "draft", "classification": 1, "policy_epoch": 1}
    ast = domain.initial_ast("旧文档", "technical_solution", "project_only", VERSION,
                             template()["structure"])
    document = {"id": VERSION, "workspace_id": WORKSPACE,
                "document_type": "technical_solution", "knowledge_scope": "project_only",
                "template_version_id": VERSION, "head_version_id": VERSION,
                "revision": 1, "base_version_id": None,
                "content_hash": domain.content_hash(ast), "ast": ast}
    monkeypatch.setattr(repository, "checked", lambda *_args: (current, None, None))

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        calls = 0

        def execute(self, sql, _params):
            self.calls += 1
            if self.calls == 1:
                assert sql.startswith("SELECT * FROM access_resource")
                return Result(resource)
            assert self.calls == 2 and sql.startswith("SELECT d.*,v.ast")
            return Result(document)

    conn = Connection()
    assert repository.read_document(conn, "verified", WORKSPACE, VERSION)["content_hash"] == (
        domain.content_hash(ast))
    assert conn.calls == 2

    document["content_hash"] = "0" * 64
    with pytest.raises(ApiError) as error:
        repository.read_document(Connection(), "verified", WORKSPACE, VERSION)
    assert error.value.code == "DOCUMENT_INTEGRITY_UNAVAILABLE"


def test_same_key_different_canonical_intent_rejects_before_template_lookup(monkeypatch):
    current = facts()
    first = command()
    monkeypatch.setattr(repository, "checked", lambda *_args, **_kwargs:
                        (current, None, authorize(current, "document:create")))
    monkeypatch.setattr(repository, "_local_write_target", lambda _conn: None)
    monkeypatch.setattr(repository, "_scope_allowed", lambda *_: None)

    class Result:
        def fetchone(self):
            return {"payload_hash": domain.canonical_request_hash(WORKSPACE, first),
                    "document_id": VERSION}

    class Connection:
        def execute(self, sql, _params=None):
            assert sql.startswith("SELECT payload_hash")
            return Result()

    with pytest.raises(ApiError) as error:
        repository.create_document(Connection(), "verified", WORKSPACE, command("另一文档"),
                                   idempotency_key="intent-1", request_id="request-1",
                                   trace_id="1" * 32)
    assert error.value.code == "IDEMPOTENCY_KEY_REUSED"
