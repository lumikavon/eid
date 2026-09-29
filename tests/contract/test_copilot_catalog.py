"""All Copilot operation families preserve AST and reject invalid targets."""
from hashlib import sha256
from uuid import uuid4

import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.copilot import CATALOG, interpret, resolve, result
from edw_api.model_gateway.copilot_routes import usable_view
from edw_api.task_contract import canonical


@pytest.fixture
def document():
    section, block = str(uuid4()), str(uuid4())
    ast = {'document': {'sections': [{'id': section, 'title': '章节', 'blocks': [
        {'id': block, 'type': 'paragraph', 'content': {'text': '已核实文本'}}]}]}}
    return ast, section, block


@pytest.mark.parametrize('name', list(CATALOG))
def test_catalog_never_mutates_target(document, name):
    ast, section, block = document
    before = sha256(canonical(ast)).hexdigest()
    target = ast['document']['sections'][0]
    if CATALOG[name].target == 'selection':
        target = target['blocks'][0]
    digest = sha256(canonical(target)).hexdigest()
    operation, current, _ = resolve(ast, section, block, digest, name)
    response = result(name, current, digest, prompt='定位原因')
    assert response['family'] == operation.family
    assert response['state'] == 'BLOCKED_BY_MISSING_INFO'
    assert sha256(canonical(ast)).hexdigest() == before
    if operation.family == 'patch':
        assert response['patch'] is None


def test_missing_and_stale_targets_are_explicit(document):
    ast, section, block = document
    with pytest.raises(ApiError) as missing:
        resolve(ast, uuid4(), block, 'a'*64, 'rewrite')
    assert missing.value.code == 'COPILOT_TARGET_MISSING'
    with pytest.raises(ApiError) as stale:
        resolve(ast, section, block, 'a'*64, 'rewrite')
    assert stale.value.code == 'COPILOT_TARGET_STALE'
    with pytest.raises(ApiError) as unsupported:
        resolve(ast, section, block, 'a'*64, 'shell')
    assert unsupported.value.code == 'COPILOT_OPERATION_UNKNOWN'


@pytest.mark.parametrize('name', ['summarize', 'knowledge_query', 'check_facts', 'rewrite'])
def test_grounded_response_is_read_only_proposal(document, name):
    ast, section, block = document
    before = sha256(canonical(ast)).hexdigest()
    target = ast['document']['sections'][0]
    if CATALOG[name].target == 'selection':
        target = target['blocks'][0]
    digest = sha256(canonical(target)).hexdigest()
    excerpt = '经核验的摘录'
    source = {'source_ref': 3, 'excerpt': excerpt, 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    response = interpret(name, target, digest,
                         {'operation': name, 'target_hash': digest, 'text': '待审核的提案',
                          'source_ref': 3, 'quote': excerpt}, source)
    assert response['family'] == CATALOG[name].family
    assert sha256(canonical(ast)).hexdigest() == before
    if response['family'] == 'patch':
        assert response['patch']['state'] == 'REVIEW_REQUIRED'
        assert response['patch']['expected_hash'] == digest
    elif response['family'] == 'finding':
        assert response['items'][0]['state'] == 'REVIEW_REQUIRED'
    else:
        assert response['state'] == 'REVIEW_REQUIRED'
        assert response['evidence']['source_id'] == source['source_id']


def test_section_proposal_preserves_existing_blocks(document):
    ast, section, _ = document
    target = ast['document']['sections'][0]
    digest = sha256(canonical(target)).hexdigest()
    source = {'source_ref': 1, 'excerpt': '经核验的摘录', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    response = interpret('generate_section', target, digest,
                         {'operation': 'generate_section', 'target_hash': digest,
                          'text': '待审核内容', 'quote': source['excerpt'], 'source_ref': 1}, source)
    assert response['patch']['kind'] == 'append_section_block'
    assert response['patch']['target_id'] == section
    assert response['patch']['expected_hash'] == digest
    assert response['patch']['after']['type'] == 'paragraph'
    assert ast['document']['sections'][0]['blocks'][0]['content']['text'] == '已核实文本'


def test_continue_inserts_after_selection_without_overwrite(document):
    ast, section, block = document
    target = ast['document']['sections'][0]['blocks'][0]
    digest = sha256(canonical(target)).hexdigest()
    source = {'source_ref': 1, 'excerpt': '经核验的摘录', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    response = interpret('continue', target, digest,
                         {'operation': 'continue', 'target_hash': digest,
                          'text': '新增段落', 'quote': source['excerpt'], 'source_ref': 1}, source)
    assert response['patch']['kind'] == 'insert_block_after'
    assert response['patch']['target_id'] == block
    assert response['patch']['after']['id'] != block
    assert target['content']['text'] == '已核实文本'


def test_requirement_proposal_preserves_structured_fields(document):
    ast, section, block = document
    target = ast['document']['sections'][0]['blocks'][0]
    target['type'] = 'requirement'
    target['content'] = {'requirement_id': 'R-1', 'statement': '原需求',
                         'verification_method': '检查', 'source_refs': []}
    digest = sha256(canonical(target)).hexdigest()
    source = {'source_ref': 1, 'excerpt': '经核验的摘录', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    response = interpret('rewrite', target, digest,
                         {'operation': 'rewrite', 'target_hash': digest, 'text': '候审需求',
                          'quote': source['excerpt'], 'source_ref': 1}, source)
    after = response['patch']['after']
    assert after['content'] == {**target['content'], 'statement': '候审需求'}
    assert target['content']['statement'] == '原需求'


def test_pending_finding_remains_unresolved(document):
    ast, section, block = document
    target = ast['document']['sections'][0]['blocks'][0]
    digest = sha256(canonical(target)).hexdigest()
    source = {'source_ref': 1, 'excerpt': '经核验的摘录', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    response = interpret('create_pending', target, digest,
                         {'operation': 'create_pending', 'target_hash': digest, 'text': '待确认',
                          'quote': source['excerpt'], 'source_ref': 1}, source)
    assert response['items'][0]['kind'] == 'pending'
    assert response['items'][0]['state'] == 'REVIEW_REQUIRED'
    assert target['content']['text'] == '已核实文本'


def test_partial_search_does_not_downgrade_revocation():
    view = {'items': [{'excerpt': '可见'}], 'conflict_ids': [], 'version_conflicts': [],
            'gaps': ['SOURCE_SCAN_LIMIT', 'ENTERPRISE_UNAVAILABLE', 'KEY_FACT_SUPPORT_NOT_VERIFIED']}
    assert usable_view(view)
    assert not usable_view({**view, 'gaps': view['gaps'] + ['SOURCE_REVOKED_OR_CHANGED']})
    assert not usable_view({**view, 'items': []})


@pytest.mark.parametrize('change', [{'target_hash': 'a'*64}, {'quote': '伪造摘录'}, {'source_ref': 2}])
def test_unverified_provider_output_cannot_be_presented(document, change):
    ast, section, block = document
    target = ast['document']['sections'][0]['blocks'][0]
    digest = sha256(canonical(target)).hexdigest()
    output = {'operation': 'rewrite', 'target_hash': digest, 'text': '待审核的提案',
              'quote': '经核验的摘录', 'source_ref': 1} | change
    source = {'source_ref': 1, 'excerpt': '经核验的摘录', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    with pytest.raises(ApiError) as failure:
        interpret('rewrite', target, digest, output, source)
    assert failure.value.code in {'COPILOT_OUTPUT_INVALID', 'COPILOT_OUTPUT_UNSUPPORTED'}
