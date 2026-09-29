"""源码安全契约：未知目标与新建块冲突必须关闭。运行验收另行安排。"""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.patches import apply_selected
from edw_api.task_contract import canonical


def test_no_acl_pointer_or_cross_section_write():
    left, right, block = str(uuid4()), str(uuid4()), str(uuid4())
    ast = {'document': {'metadata': {'title': '原文', 'acl': 'private'}, 'sections': [
        {'id': left, 'blocks': []}, {'id': right, 'blocks': [
            {'id': block, 'type': 'paragraph', 'content': {'text': '不可跨章'}}]}]}}
    original = deepcopy(ast)
    target = ast['document']['sections'][1]['blocks'][0]
    patch = {'section_id': left, 'patch': {'target_id': block, 'kind': 'replace_block',
        'expected_hash': sha256(canonical(target)).hexdigest(), 'after': target,
        'state': 'REVIEW_REQUIRED', 'path': '/document/metadata/acl'}}
    with pytest.raises(ApiError):
        apply_selected(ast, [patch])
    patch['patch'].pop('path')
    with pytest.raises(ApiError):
        apply_selected(ast, [patch])
    assert ast == original


def test_unselected_payload_is_not_applied():
    section, block = str(uuid4()), str(uuid4())
    ast = {'document': {'sections': [{'id': section, 'blocks': [
        {'id': block, 'type': 'paragraph', 'content': {'text': '人工内容'}}]}]}}
    assert apply_selected(ast, []) == ast
