"""Framework-independent Story 2.1 catalog and initial domain AST rules."""

import hashlib
import json
from uuid import uuid4


DOCUMENT_TYPES = (
    ("technical_solution", "技术方案"),
    ("bid", "标书"),
    ("prd", "PRD"),
    ("test_plan", "测试方案"),
    ("project_summary", "项目总结"),
    ("technical_requirements", "技术要求"),
    ("quality_outline", "质量大纲"),
    ("project_plan", "项目计划"),
    ("functional_test_outline", "功能测试大纲"),
    ("performance_test_outline", "性能测试大纲"),
    ("production_form", "生产过程记录表单"),
)
DOCUMENT_TYPE_IDS = frozenset(item[0] for item in DOCUMENT_TYPES)
KNOWLEDGE_SCOPES = (
    ("project_only", "仅当前项目"),
    ("project_enterprise_quality", "当前项目 + 企业技术库 + 质量库"),
    ("all_authorized", "全部有权限知识"),
)
KNOWLEDGE_SCOPE_IDS = frozenset(item[0] for item in KNOWLEDGE_SCOPES)
TEMPLATE_SCOPES = frozenset(("enterprise", "department", "product_line", "project", "personal"))

DISCOVERY_TYPES = {
    "technical_solution": "technical",
    "bid": "proposal",
    "prd": "technical",
    "test_plan": "technical",
    "project_summary": "report",
    "technical_requirements": "technical",
    "quality_outline": "report",
    "project_plan": "report",
    "functional_test_outline": "technical",
    "performance_test_outline": "technical",
    "production_form": "other",
}


def canonical_request_hash(workspace_id, command):
    """Bind an idempotency key to the normalized, complete creation intent."""
    payload = {"workspace_id": str(workspace_id), **command.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def content_hash(ast):
    """Hash the exact JSON value persisted as a document version."""
    return hashlib.sha256(json.dumps(ast, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def outline(structure):
    """Reject malformed repository catalog data instead of silently losing chapters."""
    if not isinstance(structure, dict) or set(structure) != {"sections"}:
        raise ValueError("Invalid template structure")
    sections = structure["sections"]
    if not isinstance(sections, list) or not 1 <= len(sections) <= 64:
        raise ValueError("Invalid template sections")
    titles = []
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"title"}:
            raise ValueError("Invalid template section")
        title = section["title"]
        if (not isinstance(title, str) or not title or title != title.strip()
                or len(title) > 256 or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF
                                          for char in title)):
            raise ValueError("Invalid template heading")
        titles.append(title)
    return titles


def initial_ast(name, document_type, knowledge_scope, template_version_id, structure):
    titles = outline(structure)
    return {
        "schema_version": "1.0",
        "document": {
            "metadata": {"title": name, "document_type": document_type,
                         "knowledge_scope": knowledge_scope,
                         "template_version_id": str(template_version_id),
                         "content_state": "initial_draft", "development_template": True},
            "sections": [
                {"id": str(uuid4()), "title": title,
                 "blocks": [{"id": str(uuid4()), "type": "paragraph",
                             "content": {"text": ""}}]}
                for title in titles
            ],
            "claims": [],
            "citations": [],
            "review_state": {"status": "not_reviewed"},
        },
    }
