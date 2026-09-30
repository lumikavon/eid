"""PRD 结构字段的源码契约；本阶段不运行测试套件。"""
from edw_api.review.rules import inspect


def document(*blocks):
    return {'document': {'metadata': {'document_type': 'prd'},
                         'sections': [{'id': 's1', 'title': '功能需求', 'blocks': list(blocks)}]}}


def requirement(identifier, **changes):
    content = dict(requirement_id=identifier, name='查询', role='作者', scenario='项目中',
                   prerequisites='登录', normal_flow='提交查询', exception_flow='无结果提示',
                   rules='范围校验', inputs='关键词', outputs='结果', permissions='项目成员',
                   nfr='待确认', acceptance_criteria='结果可定位', statement='查询需求',
                   verification_method='人工核对', source_refs=[])
    content.update(changes)
    return {'id': identifier + '-block', 'type': 'requirement', 'content': content}


def test_duplicate_and_missing_fields_have_exact_block_locations():
    first = requirement('FR-1', exception_flow='')
    second = requirement('FR-1', permissions='', acceptance_criteria='')
    second['id'] = 'another-block'
    _, issues = inspect(document(first, second))
    duplicates = [issue for issue in issues if issue['rule_id'] == 'prd_duplicate_id']
    assert {issue['block_id'] for issue in duplicates} == {'FR-1-block', 'another-block'}
    missing = {(issue['block_id'], issue['details']['field']) for issue in issues if issue['rule_id'] == 'prd_missing_field'}
    assert {('FR-1-block', 'exception_flow'), ('another-block', 'permissions'),
            ('another-block', 'acceptance_criteria')} <= missing


def test_prose_does_not_supply_structured_prd_fields():
    block = requirement('', name='', source_refs=['citation-1'])
    prose = {'id': 'prose', 'type': 'paragraph', 'content': {'text': 'FR-ID: FR-3；名称：查询'}}
    _, issues = inspect(document(prose, block), citations=[])
    rules = {issue['rule_id'] for issue in issues}
    assert {'prd_missing_field', 'prd_source_unverified'} <= rules


def test_current_exact_requirement_citation_passes_bounded_source_check():
    block = requirement('FR-4', source_refs=['citation-4'])
    citation = {'id': 'citation-4', 'section_id': 's1', 'block_id': block['id'],
                'selected_text': block['content']['statement'],
                'quoted_text': '证据支持查询需求', 'chain': 'attachment', 'needs_review': False}
    _, issues = inspect(document(block), citations=[citation])
    assert not any(issue['rule_id'] in ('prd_missing_field', 'prd_duplicate_id',
                                       'prd_source_unverified') for issue in issues)
