"""Bounded Copilot catalog and target resolution; never a document writer."""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..errors import ApiError
from ..task_contract import canonical


@dataclass(frozen=True)
class Operation:
    label: str
    family: str
    target: str
    input_required: bool = False


CATALOG = {
    'generate_section': Operation('生成本章节', 'patch', 'section'),
    'continue': Operation('续写内容', 'patch', 'selection'),
    'technical_requirements': Operation('改写为技术要求', 'patch', 'selection'),
    'check_facts': Operation('检查事实', 'finding', 'section'),
    'summarize': Operation('总结本章', 'read', 'section'),
    'polish': Operation('润色优化', 'patch', 'selection'),
    'rewrite': Operation('改写', 'patch', 'selection'),
    'expand': Operation('扩写', 'patch', 'selection'),
    'contract': Operation('缩写', 'patch', 'selection'),
    'professional_rewrite': Operation('专业改写', 'patch', 'selection'),
    'requirement_to_test': Operation('需求转测试', 'patch', 'selection'),
    'table': Operation('表格提案', 'structured', 'section'),
    'mermaid': Operation('Mermaid 图提案', 'structured', 'section'),
    'plantuml': Operation('PlantUML 图请求', 'structured', 'section'),
    'knowledge_query': Operation('知识查询', 'read', 'section', True),
    'similar_solution': Operation('相似方案检索', 'read', 'section'),
    'check_omissions': Operation('检查遗漏', 'finding', 'section'),
    'check_conflicts': Operation('检查冲突', 'finding', 'section'),
    'create_pending': Operation('创建待确认项', 'finding', 'selection', True),
}


class CopilotOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: str = Field(max_length=64)
    target_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    text: str = Field(min_length=1, max_length=4000)
    source_ref: int = Field(ge=1, le=12)
    quote: str = Field(min_length=1, max_length=1500)


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: str = Field(pattern='^(table|mermaid)$')
    target_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_ref: int = Field(ge=1, le=12)
    quote: str = Field(min_length=1, max_length=1500)
    rows: list[list[str]] | None = None
    diagram: str | None = None


def structured(operation, target, digest, output, source):
    from .graphics import safe_mermaid, table_block
    if operation == 'plantuml':
        raise ApiError(422, 'GRAPH_UNSUPPORTED', 'PlantUML 未配置受支持的安全转换')
    try:
        data = StructuredOutput.model_validate(output)
    except ValidationError as exc:
        raise ApiError(422, 'GRAPH_INVALID', '结构化提案格式无效') from exc
    if data.operation != operation or data.target_hash != digest or not source or data.source_ref != source['source_ref'] or data.quote.strip() != source['excerpt'][:1500].strip():
        raise ApiError(422, 'GRAPH_SOURCE_INVALID', '结构化提案缺少当前匹配证据')
    if operation == 'table':
        if data.rows is None or data.diagram is not None:
            raise ApiError(422, 'TABLE_INVALID', '表格结构无效')
        block = table_block(target['id'], data.rows)
    elif operation == 'mermaid':
        if data.diagram is None or data.rows is not None:
            raise ApiError(422, 'GRAPH_INVALID', '图形结构无效')
        svg = safe_mermaid(data.diagram)
        block = {'id': str(uuid5(UUID(target['id']), 'diagram:'+sha256(data.diagram.encode()).hexdigest())),
                 'type': 'diagram', 'content': {'text': data.diagram, 'svg': svg}}
    else:
        raise ApiError(422, 'GRAPH_UNSUPPORTED', '图形格式不支持')
    return {'family': 'patch', 'patch': {'target_id': target['id'], 'expected_hash': digest,
        'kind': 'append_section_block', 'after': block, 'evidence': {
            'source_id': source['source_id'], 'locator': source['locator'],
            'version': source['version'], 'quote': data.quote}, 'state': 'REVIEW_REQUIRED'},
        'target_hash': digest}


def interpret(operation, target, digest, output, source):
    try:
        data = CopilotOutput.model_validate(output)
    except ValidationError as exc:
        raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '模型结构化输出无效') from exc
    config = CATALOG[operation]
    if data.operation != operation or data.target_hash != digest:
        raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '模型目标不匹配')
    if not source or data.source_ref != source['source_ref'] or data.quote.strip() != source['excerpt'][:1500].strip():
        raise ApiError(422, 'COPILOT_OUTPUT_UNSUPPORTED', '模型输出缺少当前证据支持')
    evidence = {'source_id': source['source_id'], 'locator': source['locator'],
                'version': source['version'], 'quote': data.quote}
    if config.family == 'read':
        return {'family': 'read', 'answer': data.text, 'evidence': evidence,
                'state': 'REVIEW_REQUIRED', 'target_hash': digest}
    if config.family == 'finding':
        return {'family': 'finding', 'items': [{'target_id': target['id'], 'reason': data.text,
            'evidence': evidence, 'state': 'REVIEW_REQUIRED',
            'kind': 'pending' if operation == 'create_pending' else 'finding',
            **({'proposed_value': data.text} if operation == 'create_pending' else {})}], 'target_hash': digest}
    if config.family == 'patch':
        new_id = str(uuid5(UUID(target['id']), f'{operation}:{digest}:{sha256(data.text.encode()).hexdigest()}'))
        if config.target == 'section':
            if operation != 'generate_section':
                raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '章节提案操作不匹配')
            return {'family': 'patch', 'patch': {'target_id': target['id'],
                'expected_hash': digest, 'kind': 'append_section_block',
                'after': {'id': new_id, 'type': 'paragraph', 'content': {'text': data.text}},
                'evidence': evidence, 'state': 'REVIEW_REQUIRED'}, 'target_hash': digest}
        if operation == 'continue':
            return {'family': 'patch', 'patch': {'target_id': target['id'],
                'expected_hash': digest, 'kind': 'insert_block_after',
                'after': {'id': new_id, 'type': 'paragraph', 'content': {'text': data.text}},
                'evidence': evidence, 'state': 'REVIEW_REQUIRED'}, 'target_hash': digest}
        if target['type'] == 'heading' and len(data.text) > 256:
            raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '标题文本超出字段上限')
        after = dict(target)
        if target['type'] == 'requirement':
            if len(data.text) > 2048:
                raise ApiError(422, 'COPILOT_OUTPUT_INVALID', '需求陈述超出字段上限')
            after['content'] = {**target['content'], 'statement': data.text}
        else:
            after['content'] = {**target['content'], 'text': data.text}
            after['content'].pop('runs', None)
        return {'family': 'patch', 'patch': {'target_id': target['id'], 'expected_hash': digest,
            'kind': 'replace_block',
            'after': after,
            'evidence': evidence, 'state': 'REVIEW_REQUIRED'}, 'target_hash': digest}
    return result(operation, target, digest, prompt='已提供输入')


def resolve(ast, section_id, block_id, expected_hash, operation):
    config = CATALOG.get(operation)
    if not config:
        raise ApiError(422, 'COPILOT_OPERATION_UNKNOWN', '操作不在批准目录')
    sections = ast['document']['sections']
    section = next((item for item in sections if item['id'] == str(section_id)), None)
    if not section:
        raise ApiError(409, 'COPILOT_TARGET_MISSING', '目标章节不存在')
    if config.target == 'selection':
        block = next((item for item in section['blocks'] if item['id'] == str(block_id)), None)
        if not block or block['type'] not in ('paragraph', 'heading', 'requirement'):
            raise ApiError(409, 'COPILOT_TARGET_MISSING', '需要有效的文本块选区')
        target = block
    else:
        target = section
    digest = sha256(canonical(target)).hexdigest()
    if digest != expected_hash:
        raise ApiError(409, 'COPILOT_TARGET_STALE', '目标内容已变化')
    return config, target, digest


def result(operation, target, digest, *, prompt=''):
    config = CATALOG[operation]
    if config.input_required and not prompt.strip():
        raise ApiError(422, 'COPILOT_INPUT_REQUIRED', '请填写操作输入')
    if len(prompt) > 4000:
        raise ApiError(422, 'COPILOT_INPUT_INVALID', '输入过长')
    # Output is a safe, explicitly unverified proposal until model/source validation
    # is available. Read operations do not invent model answers or source support.
    if config.family == 'read':
        return {'family': 'read', 'state': 'BLOCKED_BY_MISSING_INFO', 'answer': None,
                'reason': 'CURRENT_EVIDENCE_REQUIRED', 'target_hash': digest}
    if config.family == 'finding':
        return {'family': 'finding', 'state': 'BLOCKED_BY_MISSING_INFO', 'items': [],
                'reason': 'CURRENT_EVIDENCE_REQUIRED', 'target_hash': digest}
    if config.family == 'structured':
        return {'family': 'structured', 'state': 'BLOCKED_BY_MISSING_INFO', 'proposal': None,
                'reason': 'VALIDATED_GRAPHIC_REQUIRED', 'target_hash': digest}
    return {'family': 'patch', 'state': 'BLOCKED_BY_MISSING_INFO', 'patch': None,
            'reason': 'GROUNDED_MODEL_OUTPUT_REQUIRED', 'target_hash': digest}
