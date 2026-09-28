"""Deferred contract cases; never treat these deterministic checks as model precision."""
from edw_api.documents.claims import candidates, classify
from edw_api.documents.editor_domain import InvalidAst, validate_ast


def test_candidate_types_and_unknown_declaration_contract():
    cases = {'percentage': '99.5%', 'date': '2026-09-28', 'capacity': '512 GB',
             'performance': '100 QPS', 'acceptance_threshold': '至少 99%',
             'standard': 'ISO 9001', 'regulation': '《数据安全法》',
             'version': 'v2.3', 'model': '型号 X-900',
             'customer_project_name': '客户：星辰公司', 'capability': '支持容灾切换。',
             'number': '42。'}
    for kind, value in cases.items():
        assert kind in {type_ for type_, *_ in candidates(value)}
    assert classify({'statement': '512 GB', 'value': '512', 'conditions': '', 'critical': True}, []) == 'unsupported'
    assert classify({'statement': '512 GB', 'value': '512', 'conditions': '', 'critical': True},
                    [{'relation': 'supports', 'quoted_text': '512 GB'}]) == 'supported'
    assert classify({'statement': '512 GB', 'value': '512', 'conditions': '', 'critical': True},
                    [{'relation': 'supports', 'quoted_text': '容量为 512'}]) == 'partially_supported'
    assert classify({'statement': '512 GB', 'value': '512', 'conditions': '', 'critical': True},
                    [{'relation': 'conflicts', 'quoted_text': '256 GB'}]) == 'conflicting'


def test_arbitrary_client_bindings_rejected():
    template_id = '00000000-0000-0000-0000-000000000001'
    base_ast = {'schema_version': '1.0', 'document': {
        'metadata': {'title': 'Test', 'document_type': 'prd', 'knowledge_scope': 'project_only',
                     'template_version_id': template_id},
        'sections': [{'id': '00000000-0000-0000-0000-000000000002', 'title': 'Section',
                      'blocks': [{'id': '00000000-0000-0000-0000-000000000003', 'type': 'paragraph',
                                  'content': {'text': '容量 512 GB'}}]}],
        'review_state': {}, 'claims': [], 'citations': []}}
    ast = dict(base_ast)
    ast['document'] = {**base_ast['document'], 'citations': [{'id': '00000000-0000-0000-0000-000000000001'}]}
    try:
        validate_ast(ast, expected_template_id=template_id,
                     document_type=base_ast['document']['metadata']['document_type'],
                     knowledge_scope=base_ast['document']['metadata']['knowledge_scope'],
                     old_ast=base_ast)
    except InvalidAst:
        pass
    else:
        raise AssertionError('citation array must not grant a write')
