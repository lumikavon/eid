"""Pure review-rule contracts; execution is deferred by the development policy."""
from edw_api.review.rules import CATEGORIES, inspect


def test_required_chapter_and_located_requirement_are_not_silent():
    ast = {'document': {'sections': [{'id': '0d2c1d71-9db7-4702-8e80-554882d1c505',
        'title': '概述', 'blocks': [{'id': '69d93f9a-e1cf-48b0-89f9-45de22ac76b0',
        'type': 'requirement', 'content': {'statement': '快速响应'}}]}], 'claims': []}}
    results, issues = inspect(ast, {'sections': [{'title': '概述'}, {'title': '验收'}]})
    assert len(results) == len(CATEGORIES)
    assert {item['category'] for item in results} == set(CATEGORIES)
    assert any(item['rule_id'] == 'required_chapter' and item['quote'] == '验收' for item in issues)
    assert any(item['rule_id'] == 'missing_verification' and item['block_id'] ==
               ast['document']['sections'][0]['blocks'][0]['id'] for item in issues)
    assert all(item['state'] == 'COMPLETED' and item['execution_kind'] == 'deterministic' for item in results)


def test_critical_unknown_is_not_supported():
    claim = {'id': '32db183a-781c-4fdb-81a1-52dba682ca34', 'critical': True,
             'status': 'unsupported', 'statement': '1000 TPS', 'needs_review': True}
    ast = {'document': {'sections': [], 'claims': []}}
    _, issues = inspect(ast, claims=[claim])
    assert any(item['severity'] == 'critical' and item['claim_id'] == claim['id']
               for item in issues)


def test_located_contradiction_names_style_safety_and_stale_source():
    sections = [{'id': '0d2c1d71-9db7-4702-8e80-554882d1c505', 'title': '性能', 'blocks': [
        {'id': '69d93f9a-e1cf-48b0-89f9-45de22ac76b0', 'type': 'paragraph',
         'content': {'text': '吞吐: 100 TPS；客户: 旧客户。Password: abcdef 。。。'}},
        {'id': '4cb038b9-96f4-4938-b0fa-9d14778055c0', 'type': 'paragraph',
         'content': {'text': '吞吐: 200 TPS；客户: 新客户。技术标准待确认'}}]}]
    ast = {'document': {'metadata': {'document_type': 'technical_solution'}, 'sections': sections}}
    _, issues = inspect(ast, {'sections': [{'title': '性能'}, {'title': '结论'}]},
                        project_facts=[{'key': '客户', 'value': '新客户', 'confirmed': True}],
                        stale_sources=[{'section_id': sections[0]['id'], 'block_id': sections[0]['blocks'][0]['id'],
                                        'selected_text': '旧版', 'source_id': 'ref-1'}])
    ids = {issue['rule_id'] for issue in issues}
    assert {'numeric_contradiction', 'project_name_remnant', 'obsolete_citation',
            'required_chapter', 'standard_identifier', 'sensitive_literal', 'text_format'} <= ids
    assert all(issue['section_id'] or issue['rule_id'] == 'required_chapter' for issue in issues)
    assert next(issue for issue in issues if issue['rule_id'] == 'sensitive_literal')['quote'] == '[REDACTED]'


def test_unsupported_claim_quote_redacts_credentials():
    ast = {'document': {'sections': [], 'claims': []}}
    _, issues = inspect(ast, claims=[{'critical': True, 'status': 'unknown',
                                      'statement': 'password: abcdef', 'needs_review': True}])
    assert issues[0]['quote'] == '[REDACTED]'
