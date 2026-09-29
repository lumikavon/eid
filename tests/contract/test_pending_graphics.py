"""Story 4.5 结构化候审的离线测试源码；当前不运行。"""
from hashlib import sha256
from uuid import uuid4

import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.copilot import structured
from edw_api.model_gateway.graphics import safe_mermaid, table_block
from edw_api.model_gateway.patches import apply_selected
from edw_api.task_contract import canonical


def context():
    section = {'id': str(uuid4()), 'title': '章节', 'blocks': []}
    ast = {'document': {'sections': [section]}}
    source = {'source_ref': 1, 'excerpt': '核验摘录', 'source_id': str(uuid4()),
              'locator': 'p.1', 'version': 'v1'}
    return ast, section, source


def test_table_is_bounded_patch_and_keeps_baseline():
    ast, section, source = context()
    digest = sha256(canonical(section)).hexdigest()
    proposal = structured('table', section, digest, {'operation': 'table', 'target_hash': digest,
        'rows': [['名称','值'],['状态','候审']], 'source_ref': 1, 'quote': source['excerpt']}, source)
    updated = apply_selected(ast, [{'section_id': section['id'], 'patch': proposal['patch']}])
    assert updated['document']['sections'][0]['blocks'][0]['type'] == 'table'
    assert ast['document']['sections'][0]['blocks'] == []


def test_mermaid_preview_is_escaped_static_svg():
    svg = safe_mermaid('flowchart TD\n  A[安全节点]\n  B[输出]\n  A --> B')
    assert '<svg ' in svg and '<script' not in svg
    ast, section, source = context()
    digest = sha256(canonical(section)).hexdigest()
    proposal = structured('mermaid', section, digest, {'operation': 'mermaid', 'target_hash': digest,
        'diagram': 'flowchart TD\n  A[安全节点]', 'source_ref': 1, 'quote': source['excerpt']}, source)
    assert apply_selected(ast, [{'section_id': section['id'], 'patch': proposal['patch']}])['document']['sections'][0]['blocks'][0]['type'] == 'diagram'


def test_plantuml_explicitly_unsupported():
    ast, section, source = context()
    with pytest.raises(ApiError) as rejected:
        structured('plantuml', section, sha256(canonical(section)).hexdigest(), {}, source)
    assert rejected.value.code == 'GRAPH_UNSUPPORTED'


def test_invalid_table_shape_rejected():
    with pytest.raises(ApiError):
        table_block(str(uuid4()), [['one'],['two','three']])
