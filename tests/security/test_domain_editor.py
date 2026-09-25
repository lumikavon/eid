"""Story 2.2 domain/permission examples. Execution deferred by project policy."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from edw_api.access.policy import AccessDenied
from edw_api.documents.domain import content_hash, initial_ast
from edw_api.documents.editor_domain import InvalidAst, validate_ast
from edw_api.documents import editor_repository
from edw_api.documents.editor_routes import SaveDocument
from edw_api.errors import ApiError


WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT = uuid4()
TEMPLATE = uuid4()
VERSION = uuid4()
ACTOR = uuid4()


def ast():
    return initial_ast("文档", "technical_solution", "project_only", TEMPLATE,
                       {"sections": [{"title": "概述"}]})


def validate(value, old=None):
    return validate_ast(value, expected_template_id=TEMPLATE, document_type="technical_solution",
                        knowledge_scope="project_only", old_ast=old)


def test_initial_ast_remains_valid_and_preserves_requirements_and_bindings():
    value = ast()
    value["document"]["sections"][0]["blocks"].append({
        "id": str(uuid4()), "type": "requirement",
        "content": {"requirement_id": "REQ-1", "statement": "明确目标",
                    "verification_method": "人工核对", "source_refs": [str(uuid4())]},
    })
    value["document"]["claims"] = [{"id": str(uuid4()), "text": "目标已确认"}]
    value["document"]["citations"] = [{"id": str(uuid4()), "source_id": str(uuid4())}]
    assert validate(value) == set()
    assert value["document"]["sections"][0]["blocks"][1]["content"]["requirement_id"] == "REQ-1"


@pytest.mark.parametrize("mark", [
    {"type": "link", "href": "javascript:alert(1)"},
    {"type": "link", "href": "data:text/html,evil"},
    {"type": "color", "value": "url(javascript:evil)"},
    {"type": ["bold"]},
])
def test_unsafe_or_malformed_marks_reject_without_mutating_prior_ast(mark):
    previous = ast()
    draft = deepcopy(previous)
    draft["document"]["sections"][0]["blocks"][0]["content"] = {
        "text": "x", "runs": [{"text": "x", "marks": [mark]}],
    }
    with pytest.raises(InvalidAst):
        validate(draft, previous)
    assert previous["document"]["sections"][0]["blocks"][0]["content"] == {"text": ""}


def test_review_state_and_other_metadata_cannot_be_forged_by_editor():
    previous = ast()
    draft = deepcopy(previous)
    draft["document"]["review_state"]["status"] = "approved"
    with pytest.raises(InvalidAst, match="Immutable document state"):
        validate(draft, previous)
    draft = deepcopy(previous)
    draft["document"]["metadata"]["publication_state"] = "published"
    with pytest.raises(InvalidAst, match="Immutable document metadata"):
        validate(draft, previous)


def test_future_node_is_read_only_and_remains_byte_equivalent():
    previous = ast()
    opaque = {"id": str(uuid4()), "type": "future_widget", "content": {"nested": [1, 2]}}
    previous["document"]["sections"][0]["blocks"].append(opaque)
    unchanged = deepcopy(previous)
    unchanged["document"]["sections"][0]["blocks"][0]["content"]["text"] = "edited"
    assert validate(unchanged, previous) == set()
    changed = deepcopy(unchanged)
    changed["document"]["sections"][0]["blocks"][1]["content"]["nested"] = [1]
    with pytest.raises(InvalidAst, match="read-only"):
        validate(changed, previous)
    deleted = deepcopy(unchanged)
    deleted["document"]["sections"][0]["blocks"].pop()
    with pytest.raises(InvalidAst, match="read-only"):
        validate(deleted, previous)


def test_figure_requires_private_id_alt_and_dimensions_without_remote_src():
    value = ast()
    image_id = uuid4()
    figure = {"id": str(uuid4()), "type": "figure", "content": {
        "resource_id": str(image_id), "alt": "架构图", "width": 800, "height": 600,
    }}
    value["document"]["sections"][0]["blocks"].append(figure)
    assert validate(value) == {str(image_id)}
    figure["content"]["src"] = "https://external.invalid/image.png"
    with pytest.raises(InvalidAst):
        validate(value)


def test_conflict_never_inserts_version(monkeypatch):
    previous = ast()
    current = {"actor_id": ACTOR, "evaluated_at": datetime.now(timezone.utc)}
    resource = {"kind": "document", "head_ref": VERSION, "publication_state": "unpublished",
                "approval_state": "draft"}
    monkeypatch.setattr(editor_repository, "checked", lambda *_args, **_kw: (current, resource, None))
    monkeypatch.setattr(editor_repository, "_local_write_target", lambda _conn: None)
    class Connection:
        def __init__(self):
            self.commands = []
        def execute(self, sql, _params):
            self.commands.append(sql)
            class Result:
                def fetchone(self):
                    return {"head_version_id": VERSION, "revision": 2,
                            "template_version_id": TEMPLATE, "document_type": "technical_solution",
                            "knowledge_scope": "project_only"}
            return Result()
    conn = Connection()
    command = SaveDocument(base_version_id=VERSION, revision=1, ast=previous)
    with pytest.raises(ApiError) as error:
        editor_repository.save_document(conn, "subject", WORKSPACE, DOCUMENT, command, "req", "0" * 32)
    assert error.value.status_code == 409
    assert all(not sql.startswith("INSERT") for sql in conn.commands)


def test_authorized_save_appends_version_and_advances_head_without_mutating_old_version(monkeypatch):
    previous = ast()
    draft = deepcopy(previous)
    draft["document"]["sections"][0]["blocks"][0]["content"]["text"] = "新正文"
    current = {"actor_id": ACTOR, "evaluated_at": datetime.now(timezone.utc)}
    resource = {"kind": "document", "head_ref": VERSION, "publication_state": "unpublished",
                "approval_state": "draft"}
    monkeypatch.setattr(editor_repository, "checked", lambda *_args, **_kw: (current, resource, None))
    monkeypatch.setattr(editor_repository, "_local_write_target", lambda _conn: None)
    monkeypatch.setattr(editor_repository, "_document_row", lambda *_args: {"ast": previous})
    monkeypatch.setattr(editor_repository, "_scope_allowed", lambda *_args: None)

    class Result:
        def __init__(self, value):
            self.value = value
        def fetchone(self):
            return self.value
        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.commands = []
        def execute(self, sql, params):
            self.commands.append((sql, params))
            if sql.startswith("SELECT head_version_id"):
                return Result({"head_version_id": VERSION, "revision": 1,
                               "template_version_id": TEMPLATE, "document_type": "technical_solution",
                               "knowledge_scope": "project_only"})
            if sql.startswith("UPDATE document ") or sql.startswith("UPDATE access_resource "):
                return Result({"id": DOCUMENT})
            return Result(None)

    conn = Connection()
    saved = editor_repository.save_document(conn, "subject", WORKSPACE, DOCUMENT,
                                             SaveDocument(base_version_id=VERSION, revision=1, ast=draft),
                                             "req", "0" * 32)
    assert saved["revision"] == 2 and saved["base_version_id"] == VERSION
    assert previous["document"]["sections"][0]["blocks"][0]["content"]["text"] == ""
    assert len([sql for sql, _ in conn.commands if sql.startswith("INSERT INTO document_version")]) == 1
    assert not any(sql.startswith("UPDATE document_version") or sql.startswith("DELETE FROM document_version")
                   for sql, _ in conn.commands)


def test_revoked_or_published_document_rejects_before_write(monkeypatch):
    def revoked(*_args, **_kwargs):
        raise AccessDenied()
    monkeypatch.setattr(editor_repository, "checked", revoked)
    with pytest.raises(ApiError) as error:
        editor_repository.editable_document(object(), "subject", WORKSPACE, DOCUMENT)
    assert error.value.status_code == 404
    monkeypatch.setattr(editor_repository, "checked", lambda *_args, **_kw: (
        {}, {"kind": "document", "publication_state": "published", "approval_state": "draft"}, None))
    with pytest.raises(ApiError) as error:
        editor_repository.editable_document(object(), "subject", WORKSPACE, DOCUMENT)
    assert error.value.status_code == 409

def test_history_is_scoped_to_current_read_grant_and_document_owner(monkeypatch):
    monkeypatch.setattr(editor_repository, "_read_history_target",
                        lambda *_args: {"owner_id": ACTOR})
    class Connection:
        def execute(self, sql, params):
            assert "d.workspace_id=%s AND d.owner_id=%s" in sql
            assert params[:3] == (DOCUMENT, WORKSPACE, ACTOR)
            class Result:
                def fetchall(self):
                    prior = ast()
                    return [{"id": uuid4(), "revision": revision, "base_version_id": VERSION,
                             "content_hash": content_hash(prior), "ast": prior, "created_by": ACTOR,
                             "created_at": datetime.now(timezone.utc)} for revision in range(51, 0, -1)]
            return Result()
    page = editor_repository.list_versions(Connection(), "subject", WORKSPACE, DOCUMENT)
    assert len(page["items"]) == 50
    assert page["next_revision"] == page["items"][-1]["revision"] == 2
    assert page["items"][0]["source"] == "manual_edit"


def test_historic_version_reauthorizes_and_rejects_cross_document_or_corrupt_ast(monkeypatch):
    monkeypatch.setattr(editor_repository, "_read_history_target",
                        lambda *_args: {"owner_id": ACTOR})
    class Connection:
        def __init__(self, row):
            self.row = row
        def execute(self, sql, params):
            assert "v.document_id=d.id" in sql and "d.owner_id=%s" in sql
            assert params == (DOCUMENT, WORKSPACE, ACTOR, VERSION)
            class Result:
                def __init__(self, value):
                    self.value = value
                def fetchone(self):
                    return self.value
            return Result(self.row)
    with pytest.raises(ApiError) as missing:
        editor_repository.read_version(Connection(None), "subject", WORKSPACE, DOCUMENT, VERSION)
    assert missing.value.status_code == 404
    prior = ast()
    row = {"id": DOCUMENT, "workspace_id": WORKSPACE, "document_type": "technical_solution",
           "knowledge_scope": "project_only", "template_version_id": TEMPLATE,
           "version_id": VERSION, "revision": 1, "base_version_id": None,
           "ast": prior, "content_hash": "0" * 64}
    with pytest.raises(ApiError) as corrupt:
        editor_repository.read_version(Connection(row), "subject", WORKSPACE, DOCUMENT, VERSION)
    assert corrupt.value.status_code == 503
    monkeypatch.setattr(editor_repository, "_read_history_target",
                        lambda *_args: (_ for _ in ()).throw(ApiError(404, "DOCUMENT_NOT_FOUND", "hidden")))
    with pytest.raises(ApiError) as revoked:
        editor_repository.read_version(Connection(row), "subject", WORKSPACE, DOCUMENT, VERSION)
    assert revoked.value.status_code == 404
