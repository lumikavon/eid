"""Editor-independent, fail-closed validation of document AST version 1.0.

The wire is domain JSON, never ProseMirror JSON or HTML. Future block kinds are
retained by readers but may not be silently rewritten by an older editor.
"""

import json
import re
from urllib.parse import urlsplit
from uuid import UUID


BLOCK_KINDS = frozenset({"paragraph", "heading", "table", "figure", "diagram",
                         "requirement", "citation", "warning", "code", "form"})
MAX_AST_BYTES = 512 * 1024
MAX_TEXT = 100_000


class InvalidAst(ValueError):
    """A malformed or unsupported edit must leave the prior version intact."""


def _object(value):
    if not isinstance(value, dict):
        raise InvalidAst("Expected object")
    return value


def _array(value, maximum=1000):
    if not isinstance(value, list) or len(value) > maximum:
        raise InvalidAst("Invalid array")
    return value


def _id(value):
    if not isinstance(value, str):
        raise InvalidAst("Invalid ID")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise InvalidAst("Invalid ID") from exc


def _text(value, maximum=MAX_TEXT, *, empty=True):
    if (not isinstance(value, str) or len(value) > maximum or (not empty and not value)
            or any(ord(char) < 32 and char not in "\n\t" or 0xD800 <= ord(char) <= 0xDFFF
                   for char in value)):
        raise InvalidAst("Invalid text")
    return value


def _url(value):
    value = _text(value, 2048, empty=False)
    try:
        parts = urlsplit(value)
        safe_authority = bool(parts.hostname) and parts.port != 0
    except ValueError as exc:
        raise InvalidAst("Unsafe link") from exc
    if parts.scheme not in {"https", "http"} or not safe_authority or parts.username or parts.password:
        raise InvalidAst("Unsafe link")
    if re.search(r"[\s\\]", value):
        raise InvalidAst("Unsafe link")
    return value


def _check_embedded_urls(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "src" and item is not None:
                raise InvalidAst("Inline or remote resources are forbidden")
            if key in {"href", "url"}:
                _url(item)
            else:
                _check_embedded_urls(item)
    elif isinstance(value, list):
        for item in value:
            _check_embedded_urls(item)


def _runs(content):
    content = _object(content)
    text = _text(content.get("text"))
    if "runs" in content:
        runs = _array(content["runs"], 2048)
        if "".join(_text(_object(run).get("text")) for run in runs) != text:
            raise InvalidAst("Text and runs disagree")
        for run in runs:
            for mark in _array(run.get("marks", []), 16):
                mark = _object(mark)
                if not isinstance(mark.get("type"), str) or mark["type"] not in {"bold", "italic", "underline", "color", "link"}:
                    raise InvalidAst("Unsupported mark")
                if mark["type"] == "link":
                    _url(mark.get("href"))
                if mark["type"] == "color" and not re.fullmatch(
                        r"#[0-9a-fA-F]{6}", str(mark.get("value", ""))):
                    raise InvalidAst("Invalid color")
    return text


def validate_ast(ast, *, expected_template_id, document_type, knowledge_scope,
                 old_ast=None, controlled_citation=False):
    """Validate for save; reject opaque edits and arbitrary embedded/remote resources.

    Returns the referenced image IDs for the application layer's current-ACL check.
    Existing unsupported nodes may only pass through unchanged at the same position.
    """
    try:
        raw = json.dumps(ast, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise InvalidAst("AST must be finite JSON") from exc
    if len(raw) > MAX_AST_BYTES:
        raise InvalidAst("AST too large")
    root = _object(ast)
    _check_embedded_urls(root)
    if root.get("schema_version") != "1.0":
        raise InvalidAst("Unsupported AST version")
    document = _object(root.get("document"))
    metadata = _object(document.get("metadata"))
    if (metadata.get("document_type") != document_type
            or metadata.get("knowledge_scope") != knowledge_scope
            or metadata.get("template_version_id") != str(expected_template_id)):
        raise InvalidAst("Immutable document metadata changed")
    title = _text(metadata.get("title"), 256, empty=False)
    if title != title.strip():
        raise InvalidAst("Invalid title")
    _object(document.get("review_state"))
    sections = _array(document.get("sections"), 64)
    if not sections:
        raise InvalidAst("At least one section is required")
    original_sections = []
    if old_ast is not None:
        original_root = _object(old_ast)
        original_document = _object(original_root.get("document"))
        original_metadata = _object(original_document.get("metadata"))
        if ({key: value for key, value in root.items() if key != "document"}
                != {key: value for key, value in original_root.items() if key != "document"}):
            raise InvalidAst("Immutable AST envelope changed")
        if ({key: value for key, value in document.items()
             if key not in {"metadata", "sections", "claims", "citations"}}
                != {key: value for key, value in original_document.items()
                    if key not in {"metadata", "sections", "claims", "citations"}}):
            raise InvalidAst("Immutable document state changed")
        if ({key: value for key, value in metadata.items() if key != "title"}
                != {key: value for key, value in original_metadata.items() if key != "title"}):
            raise InvalidAst("Immutable document metadata changed")
        original_sections = _array(original_document.get("sections"), 64)
    section_ids, block_ids, media_ids = set(), set(), set()
    for index, section in enumerate(sections):
        section = _object(section)
        section_id = _id(section.get("id"))
        if section_id in section_ids or section_id in block_ids:
            raise InvalidAst("Duplicate section ID")
        section_ids.add(section_id)
        heading = _text(section.get("title"), 256, empty=False)
        if heading != heading.strip():
            raise InvalidAst("Invalid section title")
        for block_index, block in enumerate(_array(section.get("blocks"), 1000)):
            block = _object(block)
            block_id = _id(block.get("id"))
            if block_id in block_ids or block_id in section_ids:
                raise InvalidAst("Duplicate block ID")
            block_ids.add(block_id)
            kind = block.get("type")
            if not isinstance(kind, str) or kind not in BLOCK_KINDS:
                # A newer editor's node cannot be invented or changed by an older client.
                if (index >= len(original_sections) or
                        block_index >= len(_array(original_sections[index].get("blocks"))) or
                        block != original_sections[index]["blocks"][block_index]):
                    raise InvalidAst("Unknown block must be preserved read-only")
                continue
            content = _object(block.get("content"))
            if kind in {"paragraph", "heading", "warning", "code", "diagram", "citation"}:
                _runs(content)
                if kind == "diagram" and ("svg" in content or old_ast is not None and
                        not any(existing.get("id") == block_id for old in original_sections
                                for existing in old.get("blocks", []))):
                    from ..model_gateway.graphics import safe_mermaid
                    try:
                        if set(content) != {"text", "svg"} or safe_mermaid(content["text"]) != content["svg"]:
                            raise InvalidAst("Invalid static diagram")
                    except (ValueError, TypeError, KeyError) as exc:
                        raise InvalidAst("Invalid static diagram") from exc
                if kind in {"paragraph", "heading"} and content.get("align", "left") not in {"left", "center", "right", "justify"}:
                    raise InvalidAst("Invalid alignment")
                if kind == "heading" and content.get("level") not in {1, 2, 3, 4, 5, 6}:
                    raise InvalidAst("Invalid heading level")
                if kind == "paragraph" and content.get("list") not in (None, "bullet", "ordered"):
                    raise InvalidAst("Invalid list style")
            elif kind == "requirement":
                for field in ("requirement_id", "statement", "verification_method"):
                    _text(content.get(field), 2048, empty=False)
                for ref in _array(content.get("source_refs"), 128):
                    _id(ref)
            elif kind == "table":
                for row in _array(content.get("rows"), 256):
                    for cell in _array(row, 64):
                        cell = _object(cell)
                        _text(cell.get("text"), 4096)
                        for span in ("rowspan", "colspan"):
                            if type(cell.get(span, 1)) is not int or not 1 <= cell.get(span, 1) <= 64:
                                raise InvalidAst("Invalid table span")
            elif kind == "form":
                _text(content.get("field_id"), 128, empty=False)
                _text(content.get("label"), 256, empty=False)
                _text(content.get("value", ""), 4096)
            elif kind == "figure":
                media_ids.add(_id(content.get("resource_id")))
                _text(content.get("alt"), 512, empty=False)
                width, height = content.get("width"), content.get("height")
                if any(type(size) is not int or not 1 <= size <= 8192 for size in (width, height)):
                    raise InvalidAst("Invalid image dimensions")
                if content.get("src") is not None:
                    raise InvalidAst("Remote or inline image sources are forbidden")
    # Also walk the old AST: validating only new opaque nodes would permit deletion.
    for index, original_section in enumerate(original_sections):
        for block_index, original_block in enumerate(_array(original_section.get("blocks"), 1000)):
            if original_block.get("type") in BLOCK_KINDS:
                continue
            if (index >= len(sections) or
                    sections[index].get("id") != original_section.get("id") or
                    block_index >= len(sections[index]["blocks"]) or
                    sections[index]["blocks"][block_index] != original_block):
                raise InvalidAst("Unknown block must be preserved read-only")
    if old_ast is not None:
        for collection in ("claims", "citations"):
            if collection == "citations" and controlled_citation:
                continue
            if document.get(collection) != original_document.get(collection):
                raise InvalidAst("Claim and citation bindings require a controlled command")
    for collection in ("claims", "citations"):
        ids = set()
        for value in _array(document.get(collection), 2048):
            item = _object(value)
            identifier = _id(item.get("id"))
            if identifier in ids:
                raise InvalidAst("Duplicate binding ID")
            ids.add(identifier)
    return media_ids
