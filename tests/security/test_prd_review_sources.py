"""来源匹配只认当前固定输入中的附件引用；不运行外部验证。"""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from edw_api.documents.domain import initial_ast
from edw_api.documents.editor_domain import InvalidAst, validate_ast
from edw_api.review.rules import inspect

ROOT = Path(__file__).resolve().parents[2]


def test_foreign_or_expired_source_does_not_satisfy_requirement():
    block = {'id': 'b1', 'type': 'requirement', 'content': {
        'requirement_id': 'FR-1', 'statement': '查询', 'verification_method': '人工',
        'source_refs': ['c1']}}
    ast = {'document': {'metadata': {'document_type': 'prd'},
                        'sections': [{'id': 's1', 'title': '需求', 'blocks': [block]}]}}
    citation = {'id': 'c1', 'section_id': 's2', 'block_id': 'b2', 'chain': 'attachment',
                'needs_review': False}
    _, issues = inspect(ast, citations=[citation])
    assert any(issue['rule_id'] == 'prd_source_unverified' for issue in issues)
    citation.update(section_id='s1', needs_review=True)
    _, issues = inspect(ast, citations=[citation])
    assert any(issue['rule_id'] == 'prd_source_unverified' for issue in issues)


def test_prd_source_refs_only_change_via_controlled_command():
    template = uuid4()
    previous = initial_ast('PRD', 'prd', 'project_only', template,
                           {'sections': [{'title': '需求'}]})
    block = {'id': str(uuid4()), 'type': 'requirement', 'content': {
        'requirement_id': 'FR-1', 'statement': '查询', 'verification_method': '人工',
        'source_refs': []}}
    previous['document']['sections'][0]['blocks'].append(block)
    forged = deepcopy(previous)
    forged['document']['sections'][0]['blocks'][-1]['content']['source_refs'] = [str(uuid4())]
    with pytest.raises(InvalidAst, match='controlled command'):
        validate_ast(forged, expected_template_id=template, document_type='prd',
                     knowledge_scope='project_only', old_ast=previous)
    forged = deepcopy(previous)
    forged['document']['sections'][0]['blocks'][-1]['content']['statement'] = '变更后的查询'
    assert validate_ast(forged, expected_template_id=template, document_type='prd',
                        knowledge_scope='project_only', old_ast=previous) == set()
    sourced = deepcopy(previous)
    sourced['document']['sections'][0]['blocks'][-1]['content']['source_refs'] = [str(uuid4())]
    changed = deepcopy(sourced)
    changed['document']['sections'][0]['blocks'][-1]['content']['statement'] = '替换后的需求'
    assert validate_ast(changed, expected_template_id=template, document_type='prd',
                        knowledge_scope='project_only', old_ast=sourced) == set()
    changed = deepcopy(sourced)
    changed['document']['sections'][0]['blocks'][-1]['content']['requirement_id'] = 'FR-2'
    assert validate_ast(changed, expected_template_id=template, document_type='prd',
                        knowledge_scope='project_only', old_ast=sourced) == set()


def test_legacy_prd_id_and_long_statement_survive_unrelated_edit():
    template = uuid4()
    previous = initial_ast('PRD', 'prd', 'project_only', template,
                           {'sections': [{'title': '需求'}]})
    previous['document']['sections'][0]['blocks'].append({'id': str(uuid4()),
        'type': 'requirement', 'content': {'requirement_id': 'REQ-1',
            'statement': '既有需求' * 200, 'verification_method': '人工', 'source_refs': []}})
    draft = deepcopy(previous)
    draft['document']['metadata']['title'] = '更新标题'
    assert validate_ast(draft, expected_template_id=template, document_type='prd',
                        knowledge_scope='project_only', old_ast=previous) == set()


def test_duplicate_prd_id_rejected_without_dropping_previous_block():
    template = uuid4()
    previous = initial_ast('PRD', 'prd', 'project_only', template,
                           {'sections': [{'title': '需求'}]})
    draft = deepcopy(previous)
    for identifier in ('FR-1', 'fr-1'):
        draft['document']['sections'][0]['blocks'].append({'id': str(uuid4()),
            'type': 'requirement', 'content': {'requirement_id': identifier,
                'statement': '查询', 'source_refs': []}})
    with pytest.raises(InvalidAst, match='Duplicate PRD requirement ID'):
        validate_ast(draft, expected_template_id=template, document_type='prd',
                     knowledge_scope='project_only', old_ast=previous)
    assert len(previous['document']['sections'][0]['blocks']) == 1


def test_prd_citation_command_has_live_and_version_guards():
    routes = (ROOT / 'edw-api/src/edw_api/documents/claim_routes.py').read_text(encoding='utf-8')
    method = routes.split("@router.post('/requirements/citations')", 1)[1].split("@router.post('/citations')", 1)[0]
    for guard in ('source_proof(', 'live(', 'head(', 'editable_document(', 'save_document(',
                  "claim_type'] != 'prd_requirement'", "item['chain'] != 'attachment'"):
        assert guard in method
