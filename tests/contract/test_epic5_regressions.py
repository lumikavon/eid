"""跨版本、结构字段及真实基线分母的行为回归。"""
from copy import deepcopy
from uuid import uuid4

import pytest

from edw_api.documents import traceability
from edw_api.documents.domain import initial_ast
from edw_api.documents.editor_domain import InvalidAst, validate_ast
from edw_api.errors import ApiError
from edw_api.review.routes import same_defect
from edw_api.review.rules import inspect


def test_claim_reextraction_does_not_hide_persistent_defect():
    original = dict(category='fact', rule_id='unsupported_critical', section_id='s', block_id='b',
                    claim_id=str(uuid4()), details={})
    assert same_defect(original, dict(original, claim_id=str(uuid4())))
    assert not same_defect(dict(original, details={'field': 'unit'}),
                           dict(original, details={'field': 'threshold'}))
    assert same_defect(dict(original, details=None), dict(original, details=None))


def test_secret_in_nested_prd_field_is_located_and_redacted():
    ast = {'document': {'metadata': {'document_type': 'prd'}, 'sections': [
        {'id': 's', 'title': '需求', 'blocks': [{'id': 'b', 'type': 'requirement',
         'content': {'statement': '查询', 'exception_flow': 'api_key=private123',
                     'nested': {'flows': ['password=hidden123']}}}]}]}}
    _, issues = inspect(ast)
    secrets = [issue for issue in issues if issue['rule_id'] == 'sensitive_literal']
    assert {issue['details']['field'] for issue in secrets} == {'exception_flow', 'nested.flows[0]'}
    assert all(issue['quote'] == '[REDACTED]' for issue in secrets)


def test_measurable_fields_and_source_backed_threshold_cannot_be_silently_replaced():
    template = uuid4()
    ast = initial_ast('要求', 'technical_requirements', 'project_only', template,
                      {'sections': [{'title': '要求'}]})
    content = dict(requirement_id='TR-1', statement='响应', condition='并发10', metric='响应时间',
                   unit='ms', threshold='100', verification_method='负载测试', source_refs=[str(uuid4())])
    ast['document']['sections'][0]['blocks'].append({'id': str(uuid4()), 'type': 'requirement', 'content': content})
    changed = deepcopy(ast)
    changed['document']['sections'][0]['blocks'][-1]['content']['threshold'] = '200'
    with pytest.raises(InvalidAst, match='threshold'):
        validate_ast(changed, expected_template_id=template, document_type='technical_requirements',
                     knowledge_scope='project_only', old_ast=ast)
    _, issues = inspect(ast)
    assert any(i['rule_id'] == 'unsupported_threshold' and i['details']['field'] == 'threshold' for i in issues)


def baseline(monkeypatch):
    requirements = {'document': {'sections': [{'id': 's', 'blocks': [
        {'id': 'r1', 'type': 'requirement', 'content': {'requirement_id': 'FR-1', 'threshold': '100'}},
        {'id': 'r2', 'type': 'requirement', 'content': {'requirement_id': 'FR-2'}}]}]}}
    monkeypatch.setattr(traceability, 'read_version', lambda *_: {
        'ast': requirements, 'version_id': 'v1', 'document_type': 'prd'})
    class Conn:
        def execute(self, *_):
            return self
        def fetchone(self):
            return {'head_version_id': 'v1'}
    return Conn()


def test_coverage_counts_uncovered_and_redundant_baseline_rows(monkeypatch):
    conn = baseline(monkeypatch)
    ref = dict(document_id='d1', version_id='v1', section_id='s', block_id='r1')
    ast = {'document': {'sections': [{'id': 't', 'blocks': [
        {'id': identifier, 'type': 'test_item', 'content': {'threshold': '100', 'links': [ref]}}
        for identifier in ('t1', 't2')]}]}}
    result = traceability.coverage(conn, 'author', 'workspace', ast)
    assert (result['numerator'], result['denominator']) == (0, 2)
    assert {row['state'] for row in result['requirements']} == {'uncovered'}
    ast['document']['sections'][0]['blocks'][0]['content']['threshold'] = '200'
    with pytest.raises(ApiError) as error:
        traceability.validate_links(conn, 'author', 'workspace', 'tests', ast, {'document': {'sections': []}})
    assert error.value.code == 'TEST_THRESHOLD_MISMATCH'
    ref['version_id'] = 'v0'
    result = traceability.coverage(conn, 'author', 'workspace', ast)
    assert result['numerator'] == 0 and result['denominator'] == 2
    assert all(link['state'] != 'current' for link in result['links'])


def test_revoked_trace_is_unavailable_without_reading_protected_baseline(monkeypatch):
    def denied(*_):
        raise ApiError(404, 'DOCUMENT_VERSION_NOT_FOUND', '不可见')
    monkeypatch.setattr(traceability, 'read_version', denied)
    ast = {'document': {'sections': [{'id': 's', 'blocks': [{'id': 't', 'type': 'test_item',
        'content': {'links': [dict(document_id='d', version_id='v', section_id='s', block_id='r')]}}]}]}}
    result = traceability.coverage(None, 'actor', 'workspace', ast)
    assert result['links'][0]['state'] == 'unavailable'
    assert result['requirements'] == [] and result['state'] == 'unevaluated'


def trace_graph(monkeypatch):
    def ref(doc, block):
        return dict(document_id=doc, version_id='v1', section_id='s', block_id=block)
    def document(kind, nodes):
        return {'document_type': kind, 'version_id': 'v1', 'ast': {'document': {
            'sections': [{'id': 's', 'blocks': nodes}]}}}
    def node(identifier, kind, parents=()):
        return {'id': identifier, 'type': kind,
                'content': {'threshold': '100', 'links': list(parents)}}
    docs = {
        'requirements': document('prd', [node('r1', 'requirement'), node('r2', 'requirement')]),
        'items': document('test_plan', [node('item', 'test_item', [ref('requirements', 'r1')])]),
        'cases': document('test_plan', [node('case', 'test_case', [ref('items', 'item')])]),
        'acceptance': document('test_plan', [node('accept', 'acceptance', [ref('cases', 'case')])]),
    }
    revoked = set()
    heads = {name: 'v1' for name in docs}
    def read(_conn, _subject, _workspace, doc, _version):
        if doc in revoked:
            raise ApiError(404, 'DOCUMENT_VERSION_NOT_FOUND', '不可见')
        return docs[doc]
    monkeypatch.setattr(traceability, 'read_version', read)
    class Cursor:
        def __init__(self, rows):
            self.rows = rows
        def fetchone(self):
            return self.rows[0] if self.rows else None
        def fetchall(self):
            return self.rows
    class Conn:
        def execute(self, sql, params):
            if sql.startswith('SELECT head_version_id'):
                return Cursor([{'head_version_id': heads[params[0]]}])
            target = tuple(params[1:])
            return Cursor([dict(document_id=doc, version_id=heads[doc], section_id=s, block_id=b)
                for doc, value in docs.items() for (s, b), block in traceability.blocks(value['ast']).items()
                if any(tuple(parent[f] for f in ('document_id', 'version_id', 'section_id', 'block_id')) == target
                       for parent in block['content'].get('links', []))])
    ast = {'document': {'test_baselines': [{'document_id': 'requirements', 'version_id': 'v1'}],
                        'sections': []}}
    return Conn(), ast, docs, heads, revoked


def test_full_chain_and_explicit_baseline_include_uncovered_requirement(monkeypatch):
    conn, ast, docs, heads, revoked = trace_graph(monkeypatch)
    result = traceability.coverage(conn, 'author', 'workspace', ast)
    assert (result['numerator'], result['denominator']) == (1, 2)
    assert [row['state'] for row in result['requirements']] == ['covered', 'uncovered']
    assert len(result['requirements'][0]['chains'][0]) == 3
    docs['acceptance']['ast']['document']['sections'][0]['blocks'].clear()
    assert traceability.coverage(conn, 'author', 'workspace', ast)['numerator'] == 0


@pytest.mark.parametrize('failure', ['threshold', 'stale', 'revoked', 'wrong_kind'])
def test_chain_never_certifies_mismatched_stale_revoked_or_wrong_kind_ancestor(monkeypatch, failure):
    conn, ast, docs, heads, revoked = trace_graph(monkeypatch)
    item = docs['items']['ast']['document']['sections'][0]['blocks'][0]
    if failure == 'threshold':
        item['content']['threshold'] = '200'
    elif failure == 'stale':
        heads['items'] = 'v2'
    elif failure == 'revoked':
        revoked.add('items')
    else:
        item['type'] = 'test_case'
    result = traceability.coverage(conn, 'author', 'workspace', ast)
    assert (result['numerator'], result['denominator']) == (0, 2)


def test_revoked_explicit_baseline_cannot_return_partial_coverage_as_evaluated(monkeypatch):
    conn, ast, docs, heads, revoked = trace_graph(monkeypatch)
    revoked.add('requirements')
    result = traceability.coverage(conn, 'author', 'workspace', ast)
    assert result['state'] == 'unavailable' and result['denominator'] == 0
    assert result['baselines'][0]['state'] == 'unavailable'
