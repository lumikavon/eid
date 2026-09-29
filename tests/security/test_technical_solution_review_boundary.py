"""审校固定输入及授权边界源码契约。"""
from pathlib import Path

from edw_api.review.routes import input_hash


ROOT = Path(__file__).resolve().parents[2]


def test_pinned_policy_context_and_citation_identity_affect_review_input():
    routes = (ROOT / 'edw-api/src/edw_api/review/routes.py').read_text(encoding='utf-8')
    assert '_template_sections(conn, ast[' in routes
    assert "structure['context_confirmed'] = context_confirmed" in routes
    assert 'source_safe(conn, workspace_id, anchor, job[' in routes
    assert 'citations=fresh_citations' in routes
    assert 'citations=(), stale_sources=fresh_citations' in routes
    assert "content_hash(structure) != job['template_hash']" in routes
    baseline = input_hash([], [{'key': '吞吐', 'value': '100', 'confirmed': True}], [])
    assert baseline != input_hash([], [{'key': '吞吐', 'value': '200', 'confirmed': True}], [])


def test_local_rules_do_not_turn_standard_pattern_into_verified_applicability():
    rules = (ROOT / 'edw-api/src/edw_api/review/rules.py').read_text(encoding='utf-8')
    assert 'standard_applicability_pending' in rules
    assert "claim.get('status') == 'supported'" in rules
    assert "citation.get('chain') == 'attachment'" in rules
