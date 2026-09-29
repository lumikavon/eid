"""危险指令不能进入无外部依赖的图形编译器。"""
import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.graphics import safe_mermaid, table_block
from uuid import uuid4


@pytest.mark.parametrize('value', [
    'flowchart TD\n  A[https://example.com]',
    'flowchart TD\n  A[<script>]',
    'flowchart TD\n  A[安全]\n  click A "https://example.com"',
    'sequenceDiagram\n  Alice->>Bob: hello',
    'flowchart TD\n  A[安全]\n  A --> missing',
    'flowchart TD\n  A[安全]\n  A[重复]',
    'flowchart TD\n  A[安全]\n  %%{init: {"theme": "base"}}%%',
    'flowchart TD\n  A[安全]\n  B[恶意](file:///secret)',
    'flowchart TD\n' + '\n'.join(f'  N{i}[节点]' for i in range(33)),
    'flowchart TD\n  A[安全\t隐藏]',
    'flowchart TD\n   A[缩进不规范]',
    'flowchart TD\n  A[安全]\n  A-->A',
])
def test_mermaid_denies_directives_remote_and_excess(value):
    with pytest.raises(ApiError):
        safe_mermaid(value)


@pytest.mark.parametrize('cell', ['非法\x00内容', '悬空\ud800代理项'])
def test_table_rejects_non_json_safe_text(cell):
    with pytest.raises(ApiError):
        table_block(uuid4(), [[cell]])
