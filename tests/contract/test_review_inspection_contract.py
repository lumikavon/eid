"""审校检查的纯源码契约；当前阶段仅编译，不执行测试套件。"""
from edw_api.review.routes import issue_filters, issue_view
from edw_api.review.routes import version_comparison


def test_filter_validation_and_combination_contract():
    assert issue_filters('high', None, 'OPEN', '  模糊  ') == ('high', None, 'OPEN', '模糊')
    from edw_api.review.routes import filtered_issues
    import inspect
    sql_source = inspect.getsource(filtered_issues)
    assert 'severity=%s' in sql_source and 'section_id=%s::uuid' in sql_source
    assert 'quote ILIKE' in sql_source and 'ORDER BY i.created_at,i.id LIMIT %s OFFSET %s' in sql_source


def test_issue_locator_and_revoked_excerpt_contract():
    ast = {'document': {'sections': [{'id': 'section', 'title': '章节',
            'blocks': [{'id': 'block', 'type': 'paragraph'}]}]}}
    issue = {'id': 'issue', 'category': 'fact', 'rule_id': 'obsolete_citation', 'severity': 'high',
             'section_id': 'section', 'block_id': 'block', 'claim_id': None, 'source_id': 'source',
             'quote': '受保护引文', 'impact': '影响', 'suggestion': '建议', 'details': {'private': 'old'}}
    denied = issue_view(issue, ast, sources_current=False)
    assert denied['quote'] == '[来源需复核]' and denied['source_id'] is None
    assert denied['details'] == {} and denied['trace'] == []
    assert denied['section_title'] == '章节' and denied['status'] == 'OPEN'


def test_unmatched_source_never_becomes_a_trace():
    ast = {'document': {'sections': []}}
    issue = {'id': 'issue', 'category': 'fact', 'rule_id': 'obsolete_citation', 'severity': 'high',
             'section_id': None, 'block_id': None, 'claim_id': None, 'source_id': 'old',
             'quote': '旧引文', 'impact': '影响', 'suggestion': '建议', 'details': {}}
    visible = issue_view(issue, ast, sources_current=True, citations=[])
    assert visible['quote'] == '[来源需复核]' and visible['source_state'] == 'denied'


def test_pinned_version_comparison_uses_block_ids_and_content():
    def ast(blocks):
        return {'document': {'sections': [{'id': 's', 'title': '章节', 'blocks': blocks}]}}
    assert version_comparison(ast([{'id': 'one', 'content': '旧'}, {'id': 'gone'}]),
                              ast([{'id': 'one', 'content': '新'}, {'id': 'added'}])) == {
                                  'added_blocks': 1, 'removed_blocks': 1, 'changed_blocks': 1}
