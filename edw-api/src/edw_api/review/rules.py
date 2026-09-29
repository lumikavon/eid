"""Versioned local Review rules. Results attest bounded checks, never model recall."""
import re
from collections import defaultdict
from uuid import uuid4

CATEGORIES = ('structure', 'fact', 'requirement', 'technical', 'quality',
              'consistency', 'style', 'safety')
RULE_VERSION = 'local-review-3'
VAGUE = re.compile(r'\b(?:fast|robust|scalable|high.performance)\b|快速|高效|稳定|先进|适当', re.I)
STANDARD_HINT = re.compile(r'标准|\bstandard\b', re.I)
STANDARD = re.compile(r'\b(?:GB(?:/T)?|ISO|IEC|IEEE)\s*[- ]?\s*\d{3,6}(?:[.\-]\d+)*(?:[-:]\d{4})?\b', re.I)
METRIC = re.compile(r'(?<!\w)\d+(?:\.\d+)?\s*(?:%|GB|TB|GiB|QPS|TPS|Mbps|Gbps|ms|毫秒|秒|分钟)(?!\w)', re.I)
NAME = re.compile(r'(?:客户|项目|单位|公司)\s*[:：]\s*([^\s，。；]{2,80})')
SECRET = re.compile(r'(?i)(?:password|secret|api[_-]?key|密码|密钥)\s*[:=：]\s*\S{4,}')
TERM = re.compile(r'\b[A-Z][A-Za-z0-9-]{2,24}\b')
ARCHITECTURE = re.compile(r'架构|拓扑|部署|组件|接口|数据流|容灾|architecture', re.I)
PARAMETER = re.compile(r'(?P<key>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_ /-]{0,28})\s*[:：]\s*(?P<value>\d+(?:\.\d+)?\s*(?:%|GB|TB|GiB|QPS|TPS|Mbps|Gbps|ms|毫秒|秒|分钟))(?!\w)', re.I)


def _grounded_citation(section, block, phrase, citations):
    """A pinned, current citation must quote the exact assertion; a pattern alone proves nothing."""
    return next((citation for citation in citations
                 if str(citation.get('section_id')) == section['id']
                 and str(citation.get('block_id')) == block['id']
                 and not citation.get('needs_review') and citation.get('chain') == 'attachment'
                 and phrase in citation.get('selected_text', '')
                 and phrase in citation.get('quoted_text', '')
                 and phrase in citation.get('excerpt', '')), None)


def inspect(ast, template_structure=None, claims=(), *, project_facts=(), stale_sources=(), citations=()):
    """Return exact-locator findings and eight bounded outcomes on a pinned snapshot.

    Detection of a pattern does not imply that every real-world defect of that kind
    can be found. The project-fact and source checks need independently attested input.
    """
    sections = ast['document']['sections']
    issues = []
    candidates = defaultdict(list)
    names = defaultdict(list)
    terms = defaultdict(list)
    facts = {fact['key'].casefold(): fact for fact in project_facts if fact.get('confirmed')}
    technical = ast['document'].get('metadata', {}).get('document_type') == 'technical_solution'
    citations = tuple(citations)
    claims = tuple(claims)

    def add(category, rule, severity, section, block, quote, impact, suggestion, **details):
        issues.append({'id': str(uuid4()), 'category': category, 'rule_id': rule,
                       'severity': severity, 'section_id': section['id'] if section else None,
                        'block_id': block['id'] if block else None, 'claim_id': details.pop('claim_id', None),
                        'source_id': details.pop('source_id', None), 'quote': SECRET.sub('[REDACTED]', str(quote))[:1500],
                       'impact': impact, 'suggestion': suggestion, 'details': details})

    titles = {section['title'].strip() for section in sections}
    policy = (template_structure or {}).get('policy_sections')
    for item in policy if policy is not None else (template_structure or {}).get('sections', []):
        if item.get('mandatory', True) and item.get('title') not in titles:
            add('structure', 'required_chapter', 'high', None, None, item['title'],
                '缺少固定模板必需章节', '按固定模板版本补齐章节并重新审校',
                template_section_id=item.get('id'))
    if technical and not (template_structure or {}).get('context_confirmed', False) and policy is not None:
        add('fact', 'unconfirmed_project_context', 'high', None, None, '项目上下文',
            '当前文档版本没有已确认的项目事实上下文', '确认当前项目上下文并重新审校')
    if technical:
        for section in sections:
            if not section['blocks'] or all(not str(block.get('content', {}).get('text') or
                                                block.get('content', {}).get('statement') or '').strip()
                                            for block in section['blocks']):
                add('structure', 'empty_solution_chapter', 'high', section, None, section['title'],
                    '技术方案章节无正文', '补充有来源的章节内容')
    if not any(block['type'] == 'requirement' for section in sections for block in section['blocks']) and any(
            word in str(ast['document'].get('metadata', {}).get('document_type', '')) for word in ('prd', 'test_plan', 'requirements')):
        add('requirement', 'missing_requirement', 'high', None, None, 'requirement',
            '文档缺少结构化需求', '新增带稳定编号和来源的需求块')

    for section in sections:
        for block in section['blocks']:
            content = block.get('content', {})
            text = content.get('text') or content.get('statement') or ''
            if not isinstance(text, str):
                continue
            if block['type'] == 'requirement':
                if not content.get('verification_method'):
                    add('requirement', 'missing_verification', 'high', section, block, text,
                        '需求缺少验证方法', '填写验证方法')
                if not content.get('source_refs'):
                    add('requirement', 'missing_source', 'high', section, block, text,
                        '需求缺少来源定位', '补充当前可访问的需求来源')
            match = VAGUE.search(text)
            if match:
                add('quality', 'vague_statement', 'medium', section, block, match.group(),
                    '缺少可衡量的条件或阈值', '补充有来源的指标、阈值和验证方法')
            if STANDARD_HINT.search(text) and not STANDARD.search(text):
                add('technical', 'standard_identifier', 'medium', section, block, text,
                    '标准标识无法精确核对', '提供现行适用的标准编号和来源')
            for match in SECRET.finditer(text):
                add('safety', 'sensitive_literal', 'critical', section, block, '[REDACTED]',
                    '正文疑似包含敏感凭据', '移除凭据并按安全流程核验')
            for match in METRIC.finditer(text):
                prefix = text[max(0, match.start() - 45):match.start()]
                key = re.split(r'[。；;，,\n]', prefix)[-1].strip(' :：\t').casefold()
                if key:
                    candidates[(section['title'].casefold(), key)].append((match.group().replace(' ', ''), section, block))
            if technical and text.strip():
                # Citations on another block or merely similar excerpts cannot certify this assertion.
                if block['type'] in ('paragraph', 'heading', 'warning', 'code', 'diagram') and not any(
                        str(citation.get('section_id')) == section['id']
                        and str(citation.get('block_id')) == block['id']
                        and not citation.get('needs_review') and citation.get('chain') == 'attachment'
                        and citation.get('quoted_text') in text and citation.get('quoted_text')
                        for citation in citations):
                    add('fact', 'solution_body_source_pending', 'medium', section, block, text,
                        '技术方案正文缺少当前授权的区块引用', '为本段关键陈述补充精确来源并重新审校')
                for match in PARAMETER.finditer(text):
                    phrase = match.group().strip()
                    support = _grounded_citation(section, block, phrase, citations)
                    if not support:
                        add('fact', 'unverified_solution_parameter', 'high', section, block, match.group(),
                            '项目参数缺少当前授权的精确引用', '保留待确认并绑定当前来源，不使用历史范例数值')
                for match in METRIC.finditer(text):
                    if not any(candidate.start() <= match.start() and candidate.end() >= match.end()
                               for candidate in PARAMETER.finditer(text)) and not _grounded_citation(
                                   section, block, match.group(), citations):
                        add('fact', 'unverified_solution_parameter', 'high', section, block, match.group(),
                            '正文数值缺少当前授权的精确引用', '保留待确认并绑定当前来源，不使用历史范例数值')
                for match in STANDARD.finditer(text):
                    phrase = match.group()
                    support = _grounded_citation(section, block, phrase, citations)
                    # Source text establishes an identifier, not project applicability or currency.
                    add('technical', 'standard_applicability_pending', 'medium', section, block, phrase,
                        '标准编号模式或引用不能证明现行版本适用于当前项目',
                        '核对现行适用的权威资料并由人工确认',
                        source_id=support.get('source_id') if support else None)
                if ARCHITECTURE.search(section['title']) or ARCHITECTURE.search(text):
                    if not any(str(claim.get('section_id')) == section['id']
                               and str(claim.get('block_id')) == block['id']
                               and claim.get('status') == 'supported'
                               and _grounded_citation(section, block, claim.get('statement', ''), citations)
                               for claim in claims if claim.get('statement')):
                        add('technical', 'architecture_basis_pending', 'medium', section, block, text,
                            '架构论证缺少可复核的当前精确证据 Claim', '声明架构 Claim 并绑定当前证据')
            for match in NAME.finditer(text):
                names[match.group(0).split('：')[0].split(':')[0].strip()].append((match.group(1), section, block))
            for match in TERM.finditer(text):
                terms[match.group().casefold()].append((match.group(), section, block))
            if text and (text != text.strip() or re.search(r'([!?。！？])\1{2,}', text)):
                add('style', 'text_format', 'low', section, block, '[格式片段]',
                    '文字格式不一致', '核对段落空格或重复标点')

    for key, entries in candidates.items():
        if len({value for value, _, _ in entries}) > 1:
            for value, section, block in entries:
                add('consistency', 'numeric_contradiction', 'high', section, block, value,
                     '同一章节指标出现不同数值', '核对相同条件与单位后确认唯一项目参数', metric=key[1])
    if technical:
        parameters = defaultdict(list)
        for section in sections:
            for block in section['blocks']:
                text = block.get('content', {}).get('text', '')
                if isinstance(text, str):
                    for match in PARAMETER.finditer(text):
                        key = re.sub(r'\s+', '', match.group('key')).casefold()
                        parameters[key].append((re.sub(r'\s+', '', match.group('value')).casefold(), section, block))
        for key, entries in parameters.items():
            if len({section['id'] for _, section, _ in entries}) > 1 and len({value for value, _, _ in entries}) > 1:
                for value, section, block in entries:
                    add('consistency', 'cross_chapter_parameter_conflict', 'high', section, block, value,
                        '同名项目参数在不同章节不一致', '核对条件、单位和当前来源后统一参数',
                        parameter=key, counterparts=[{'section_id': other['id'], 'block_id': peer['id'], 'value': other_value}
                                                     for other_value, other, peer in entries if peer['id'] != block['id']])
    for key, entries in names.items():
        approved = facts.get(key.casefold())
        expected = approved['value'].strip() if approved else None
        if expected or len({name for name, _, _ in entries}) > 1:
            for name, section, block in entries:
                if expected is None or name != expected:
                    add('fact', 'project_name_remnant', 'high', section, block, name,
                        '文档名称与已确认项目事实或同文其他名称冲突', '核对当前项目/客户名称',
                        expected=expected)
    for entries in terms.values():
        if len({name for name, _, _ in entries}) > 1:
            for name, section, block in entries:
                add('consistency', 'term_variant', 'medium', section, block, name,
                    '同一术语的大小写/写法不一致', '核对术语表并统一写法')

    for claim in claims:
        if not isinstance(claim, dict) or not claim.get('critical'):
            continue
        section = next((s for s in sections if s['id'] == str(claim.get('section_id'))), None)
        block = next((b for b in section['blocks'] if b['id'] == str(claim.get('block_id'))), None) if section else None
        grounded = section and block and _grounded_citation(
            section, block, claim.get('statement', ''), citations) if claim.get('statement') else False
        if claim.get('status') != 'supported' or claim.get('needs_review') or technical and not grounded:
            add('fact', 'unsupported_critical', 'critical', section, block,
                claim.get('statement', claim.get('value', '')), '关键事实缺少有效支持',
                '补充当前授权证据并复核', claim_id=claim.get('id'))
    for source in stale_sources:
        section = next((s for s in sections if s['id'] == str(source.get('section_id'))), None)
        block = next((b for b in section['blocks'] if b['id'] == str(source.get('block_id'))), None) if section else None
        add('fact', 'obsolete_citation', 'high', section, block, source.get('selected_text', '引用'),
            '引用来源过期或当前不可核验', '重新选择当前授权来源并复核', source_id=source.get('source_id'))

    outcomes = [{'category': category, 'state': 'COMPLETED', 'rule_version': RULE_VERSION,
                 'model_version': 'none', 'execution_kind': 'deterministic', 'error_code': None}
                for category in CATEGORIES]
    return outcomes, issues
