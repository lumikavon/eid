"""Pure bounded Mermaid subset: no renderer process, file access or network."""
import html
import re
from hashlib import sha256
from uuid import UUID, uuid5

from ..task_contract import canonical

from ..errors import ApiError

MAX_GRAPH = 2048
NODE = re.compile(r'^([A-Za-z][A-Za-z0-9_]{0,31})\[([^\[\]<>"`{}();]{1,80})\]$')
EDGE = re.compile(r'^([A-Za-z][A-Za-z0-9_]{0,31}) --> ([A-Za-z][A-Za-z0-9_]{0,31})$')


def safe_mermaid(value):
    if (not isinstance(value, str) or len(value) > MAX_GRAPH or '\r' in value
            or any(ord(char) < 32 and char != '\n' or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
        raise ApiError(422, 'GRAPH_INVALID', '图形内容过大或无效')
    lines = value.split('\n')
    if not lines or lines[0] != 'flowchart TD' or len(lines) > 32:
        raise ApiError(422, 'GRAPH_UNSUPPORTED', '仅支持有限的 flowchart TD')
    nodes, edges = {}, []
    for line in lines[1:]:
        if not line.startswith('  ') or line.startswith('   '):
            raise ApiError(422, 'GRAPH_UNSUPPORTED', '图语法不在允许范围')
        clause = line[2:]
        node = NODE.fullmatch(clause)
        edge = EDGE.fullmatch(clause)
        if node:
            if node[1] in nodes or len(nodes) >= 16:
                raise ApiError(422, 'GRAPH_INVALID', '节点重复或数量超限')
            label = node[2]
            if re.search(r'(?i)(?:https?://|www\.|data:|javascript:|file:|@import|<|>|\\)', label):
                raise ApiError(422, 'GRAPH_INVALID', '远程资源或指令不可用')
            nodes[node[1]] = label
        elif edge:
            edges.append((edge[1], edge[2]))
            if len(edges) > 24:
                raise ApiError(422, 'GRAPH_INVALID', '连线超限')
        else:
            raise ApiError(422, 'GRAPH_UNSUPPORTED', '图语法不在允许范围')
    if not nodes or any(left not in nodes or right not in nodes for left, right in edges):
        raise ApiError(422, 'GRAPH_INVALID', '连线引用不存在的节点')
    # SVG is constructed only from numeric coordinates and escaped plain labels.
    order = list(nodes)
    height = 60 + len(order) * 92
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="{height}" viewBox="0 0 480 {height}">']
    for left, right in edges:
        a, b = order.index(left), order.index(right)
        parts.append(f'<path d="M240 {88+a*92} L240 {128+b*92}" stroke="#445" fill="none"/>')
    for i, (key, label) in enumerate(nodes.items()):
        y = 36 + i*92
        parts.append(f'<rect x="40" y="{y}" width="400" height="52" fill="#fff" stroke="#445"/>')
        parts.append(f'<text x="240" y="{y+32}" text-anchor="middle" font-size="14">{html.escape(label, quote=True)}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def table_block(target_id, rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32 or any(
            not isinstance(row, list) or not 1 <= len(row) <= 16 or any(
                not isinstance(cell, str) or len(cell) > 512 or any(
                    ord(char) < 32 and char not in '\n\t' or 0xD800 <= ord(char) <= 0xDFFF
                    for char in cell) for cell in row) for row in rows):
        raise ApiError(422, 'TABLE_INVALID', '表格大小或单元格无效')
    if len({len(row) for row in rows}) != 1:
        raise ApiError(422, 'TABLE_INVALID', '表格列数不一致')
    return {'id': str(uuid5(UUID(str(target_id)), 'table:'+sha256(canonical(rows)).hexdigest())), 'type': 'table',
            'content': {'rows': [[{'text': cell} for cell in row] for row in rows]}}
