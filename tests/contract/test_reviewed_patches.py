"""离线契约：仅选中的稳定目标被变更；这些测试当前不执行。"""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.copilot import interpret
from edw_api.model_gateway.patches import apply_selected
from edw_api.model_gateway.patch_routes import Decision, request_hash
from edw_api.task_contract import canonical


def fixture():
    section = str(uuid4())
    blocks = [{'id': str(uuid4()), 'type': 'paragraph', 'content': {'text': text}}
              for text in ('原文 A', '原文 B', '保留原文')]
    return {'document': {'sections': [{'id': section, 'title': '章节', 'blocks': blocks}]}}, section


def entry(section, target, text, operation='rewrite'):
    digest = sha256(canonical(target)).hexdigest()
    source = {'source_ref': 1, 'excerpt': '当前证据', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    result = interpret(operation, target, digest, {'operation': operation, 'target_hash': digest,
        'text': text, 'source_ref': 1, 'quote': source['excerpt']}, source)
    return {'section_id': section, 'patch': result['patch']}


def test_selected_subset_changes_only_selected_block_once():
    ast, section = fixture()
    blocks = ast['document']['sections'][0]['blocks']
    first, second = entry(section, blocks[0], '候审 A'), entry(section, blocks[1], '候审 B')
    original = deepcopy(ast)
    result = apply_selected(ast, [first])
    assert result['document']['sections'][0]['blocks'][0]['content']['text'] == '候审 A'
    assert result['document']['sections'][0]['blocks'][1:] == original['document']['sections'][0]['blocks'][1:]
    assert ast == original
    assert apply_selected(ast, [first, second])['document']['sections'][0]['blocks'][1]['content']['text'] == '候审 B'


def test_append_and_insert_preserve_existing_prose():
    ast, section = fixture()
    original = deepcopy(ast)
    section_node = ast['document']['sections'][0]
    result = apply_selected(ast, [entry(section, section_node, '本章附加', 'generate_section'),
                                   entry(section, section_node['blocks'][0], '续写', 'continue')])
    blocks = result['document']['sections'][0]['blocks']
    assert [item['content']['text'] for item in blocks] == ['原文 A', '续写', '原文 B', '保留原文', '本章附加']
    assert ast == original


def test_two_distinct_section_appends_form_one_selected_version():
    ast, section = fixture()
    source = ast['document']['sections'][0]
    first = entry(section, source, '新增段落 A', 'generate_section')
    second = entry(section, source, '新增段落 B', 'generate_section')
    result = apply_selected(ast, [first, second])
    assert [block['content']['text'] for block in result['document']['sections'][0]['blocks']][-2:] == [
        '新增段落 A', '新增段落 B']


def test_stale_deleted_duplicate_and_dependency_fail_closed():
    ast, section = fixture()
    patch = entry(section, ast['document']['sections'][0]['blocks'][0], '候审 A')
    for candidate in (patch,):
        with pytest.raises(ApiError):
            apply_selected(ast, [candidate, candidate])
    stale = deepcopy(patch)
    stale['patch']['expected_hash'] = '0' * 64
    with pytest.raises(ApiError):
        apply_selected(ast, [stale])
    deleted = deepcopy(patch)
    deleted['patch']['target_id'] = str(uuid4())
    with pytest.raises(ApiError):
        apply_selected(ast, [deleted])
    assert ast['document']['sections'][0]['blocks'][0]['content']['text'] == '原文 A'


def test_pointer_and_metadata_are_not_patch_targets():
    ast, section = fixture()
    patch = entry(section, ast['document']['sections'][0]['blocks'][0], '候审 A')
    patch['patch']['target_id'] = '/document/metadata/acl'
    with pytest.raises(ApiError):
        apply_selected(ast, [patch])


def test_replace_cannot_change_non_content_block_fields():
    ast, section = fixture()
    target = ast['document']['sections'][0]['blocks'][0]
    target['review_tag'] = 'unchanged'
    patch = entry(section, target, '候审 A')
    patch['patch']['after']['review_tag'] = 'changed'
    with pytest.raises(ApiError):
        apply_selected(ast, [patch])


def test_append_cannot_add_unreviewed_block_fields():
    ast, section = fixture()
    patch = entry(section, ast['document']['sections'][0], '候审段落', 'generate_section')
    patch['patch']['after']['arbitrary'] = 'unreviewed'
    with pytest.raises(ApiError):
        apply_selected(ast, [patch])


def test_decision_key_replay_binds_exact_order_and_action():
    first, second = uuid4(), uuid4()
    base = {'request_key': uuid4(), 'base_version_id': uuid4(), 'base_revision': 1,
            'action': 'accept', 'run_ids': [first, second]}
    original = request_hash(Decision(**base))
    assert original == request_hash(Decision(**base))
    assert original != request_hash(Decision(**(base | {'action': 'reject'})))
    assert original != request_hash(Decision(**(base | {'run_ids': [second, first]})))
