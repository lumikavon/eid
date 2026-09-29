"""技术方案本地审校矩阵；只覆盖确定性规则，不替代企业核验。"""
from edw_api.review.rules import inspect


def ast(*sections):
    return {'document': {'metadata': {'document_type': 'technical_solution'},
                         'sections': [{'id': f's{index}', 'title': title,
                                       'blocks': [{'id': f'b{index}', 'type': 'paragraph',
                                                   'content': {'text': text}}]}
                                      for index, (title, text) in enumerate(sections)]}}


def policy():
    return {'sections': [{'title': '架构'}, {'title': '性能'}],
            'policy_sections': [{'id': 'template-architecture', 'title': '架构', 'mandatory': True},
                                {'id': 'template-performance', 'title': '性能', 'mandatory': True}],
            'context_confirmed': True}


def citation(section, block, quote):
    return {'section_id': section, 'block_id': block, 'selected_text': quote, 'quoted_text': quote,
            'excerpt': quote, 'chain': 'attachment', 'source_id': 'source-1', 'needs_review': False}


def test_complete_solution_uses_pinned_chapters_and_exact_block_sources():
    document = ast(('架构', '架构: 服务节点采用双机，依据架构: 服务节点采用双机'),
                   ('性能', '吞吐: 100 TPS'))
    claims = [{'section_id': 's0', 'block_id': 'b0', 'statement': '架构: 服务节点采用双机',
               'status': 'supported', 'critical': True, 'needs_review': False}]
    _, issues = inspect(document, policy(), claims, citations=[citation('s0', 'b0', '架构: 服务节点采用双机'),
                                                               citation('s1', 'b1', '吞吐: 100 TPS')])
    assert not {'required_chapter', 'architecture_basis_pending', 'unverified_solution_parameter',
                'solution_body_source_pending'} & {item['rule_id'] for item in issues}


def test_missing_chapter_conflicting_values_and_unverified_standard_remain_located():
    document = ast(('架构', '吞吐: 100 TPS；符合 ISO 12345'), ('实施', '吞吐: 200 TPS'))
    _, issues = inspect(document, policy())
    assert any(item['rule_id'] == 'required_chapter' and item['details']['template_section_id'] == 'template-performance'
               for item in issues)
    conflicts = [item for item in issues if item['rule_id'] == 'cross_chapter_parameter_conflict']
    assert len(conflicts) == 2 and all(item['block_id'] and item['details']['counterparts'] for item in conflicts)
    assert any(item['rule_id'] == 'unverified_solution_parameter' and item['severity'] == 'high' for item in issues)
    assert any(item['rule_id'] == 'standard_applicability_pending' and item['block_id'] == 'b0' for item in issues)


def test_stale_source_and_unconfirmed_context_cannot_support_claim():
    document = ast(('架构', '架构: 双机'), ('性能', '吞吐: 100 TPS'))
    current = citation('s1', 'b1', '吞吐: 100 TPS')
    stale = {**current, 'needs_review': True, 'selected_text': '吞吐: 100 TPS'}
    _, issues = inspect(document, {**policy(), 'context_confirmed': False}, citations=[stale], stale_sources=[stale])
    rules = {item['rule_id'] for item in issues}
    assert {'unconfirmed_project_context', 'unverified_solution_parameter', 'obsolete_citation'} <= rules
    _, other_block = inspect(document, policy(), citations=[citation('s0', 'b0', '吞吐: 100 TPS')])
    assert any(item['rule_id'] == 'unverified_solution_parameter' and item['block_id'] == 'b1' for item in other_block)


def test_free_text_performance_number_is_not_inferred_from_a_historical_example():
    document = ast(('架构', '架构: 双机'), ('性能', '预计达到 100 TPS'))
    _, issues = inspect(document, policy())
    assert any(item['rule_id'] == 'unverified_solution_parameter' and item['block_id'] == 'b1' for item in issues)
