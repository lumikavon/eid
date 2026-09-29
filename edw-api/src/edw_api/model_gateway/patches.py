"""Apply only server-derived, stable-ID AI edits to a copied document AST."""
from copy import deepcopy
from hashlib import sha256
from uuid import UUID, uuid5

from ..errors import ApiError
from ..task_contract import canonical


def apply_selected(ast, entries):
    updated = deepcopy(ast)
    touched = set()
    appended = set()
    created = set()
    baseline = {s['id']: s for s in ast['document']['sections']}
    if len(baseline) != len(ast['document']['sections']):
        raise ApiError(409, 'AI_PATCH_CONFLICT', '章节 ID 不唯一')
    for entry in entries:
        patch = entry['patch']
        if set(patch) != {'target_id', 'expected_hash', 'kind', 'after', 'evidence', 'state'}:
            raise ApiError(422, 'AI_PATCH_INVALID', '提案包含未批准的补丁字段')
        target_id = patch['target_id']
        if not isinstance(target_id, str) or not isinstance(patch.get('after'), dict):
            raise ApiError(422, 'AI_PATCH_INVALID', '补丁目标或内容无效')
        kind = patch['kind']
        if (target_id in touched or (kind != 'append_section_block' and target_id in appended)
                or patch.get('state') != 'REVIEW_REQUIRED'
                or not isinstance(patch.get('evidence'), dict)):
            raise ApiError(409, 'AI_PATCH_CONFLICT', '目标重复或提案不可接受')
        if kind == 'append_section_block':
            appended.add(target_id)
        else:
            touched.add(target_id)
        if target_id in created:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '目标依赖另一提案的新内容')
        section = next((s for s in updated['document']['sections'] if s['id'] == entry['section_id']), None)
        original_section = baseline.get(entry['section_id'])
        if not section or not original_section:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '章节已变化')
        blocks = section['blocks']
        if kind == 'append_section_block':
            target, index = original_section, len(blocks)
        else:
            index = next((i for i, block in enumerate(blocks) if block['id'] == target_id), None)
            if index is None:
                raise ApiError(409, 'AI_PATCH_CONFLICT', '目标块已变化')
            if any(block['id'] == target_id and section_id != entry['section_id']
                   for section_id, baseline_section in baseline.items() for block in baseline_section['blocks']):
                raise ApiError(409, 'AI_PATCH_CONFLICT', '目标块 ID 不唯一')
            target = next((b for b in original_section['blocks'] if b['id'] == target_id), None)
            if target is None:
                raise ApiError(409, 'AI_PATCH_CONFLICT', '目标块未在基础版本中')
        if target['id'] != target_id or sha256(canonical(target)).hexdigest() != patch['expected_hash']:
            raise ApiError(409, 'AI_PATCH_CONFLICT', '目标内容已变化')
        after = patch['after']
        if kind == 'replace_block':
            if (after.get('id') != target_id or after.get('type') != target['type']
                    or set(after) != set(target) or
                    any(after[key] != target[key] for key in target if key != 'content')):
                raise ApiError(422, 'AI_PATCH_INVALID', '不可替换目标结构')
            blocks[index] = deepcopy(after)
        elif kind in ('append_section_block', 'insert_block_after'):
            allowed = {'paragraph'} if kind == 'insert_block_after' else {'paragraph','table','diagram'}
            if after.get('type') in ('table','diagram') and set(after) != {'id','type','content'}:
                raise ApiError(422, 'AI_PATCH_INVALID', '结构化节点字段无效')
            if after.get('type') == 'paragraph' and (set(after) != {'id','type','content'}
                    or not isinstance(after.get('content'), dict)
                    or set(after['content']) != {'text'}
                    or not isinstance(after['content']['text'], str)):
                raise ApiError(422, 'AI_PATCH_INVALID', '段落提案字段无效')
            if after.get('type') == 'diagram':
                from .graphics import safe_mermaid
                content = after.get('content')
                if not isinstance(content, dict) or set(content) != {'text', 'svg'} or not isinstance(content['text'], str):
                    raise ApiError(422, 'GRAPH_INVALID', '图形内容无效')
                expected_id = uuid5(UUID(target_id), 'diagram:'+sha256(content['text'].encode()).hexdigest())
                if (safe_mermaid(content['text']) != content['svg']
                        or after['id'] != str(expected_id)):
                    raise ApiError(422, 'GRAPH_INVALID', '图形预览不匹配受限语法')
            if after.get('type') == 'table':
                from .graphics import table_block
                content = after.get('content')
                if not isinstance(content, dict) or set(content) != {'rows'}:
                    raise ApiError(422, 'TABLE_INVALID', '表格结构无效')
                rows = content['rows']
                try:
                    plain = [[cell['text'] for cell in row] for row in rows]
                except (KeyError, TypeError) as exc:
                    raise ApiError(422, 'TABLE_INVALID', '表格单元格无效') from exc
                if after != table_block(target_id, plain):
                    raise ApiError(422, 'TABLE_INVALID', '表格提案内容不匹配')
            if after.get('type') not in allowed or not isinstance(after.get('id'), str) or after['id'] in created or any(
                    after['id'] == s['id'] or any(b['id'] == after['id'] for b in s['blocks'])
                    for s in updated['document']['sections']):
                raise ApiError(422, 'AI_PATCH_INVALID', '新增块 ID 冲突')
            blocks.insert(index if kind == 'append_section_block' else index + 1, deepcopy(after))
            created.add(after['id'])
        else:
            raise ApiError(422, 'AI_PATCH_INVALID', '未知补丁种类')
    return updated
