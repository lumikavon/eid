"""Versioned local Review rules. Results attest bounded checks, never model recall."""
import re
from collections import defaultdict
from uuid import uuid4

CATEGORIES = ('structure', 'fact', 'requirement', 'technical', 'quality',
              'consistency', 'style', 'safety')
RULE_VERSION = 'local-review-2'
VAGUE = re.compile(r'\b(?:fast|robust|scalable|high.performance)\b|快速|高效|稳定|先进|适当', re.I)
STANDARD_HINT = re.compile(r'标准|\bstandard\b', re.I)
STANDARD = re.compile(r'\b(?:GB(?:/T)?|ISO|IEC|IEEE)\s*[- ]?\s*\d{3,6}(?:[.\-]\d+)*(?:[-:]\d{4})?\b', re.I)
METRIC = re.compile(r'(?<!\w)\d+(?:\.\d+)?\s*(?:%|GB|TB|GiB|QPS|TPS|Mbps|Gbps|ms|毫秒|秒|分钟)(?!\w)', re.I)
NAME = re.compile(r'(?:客户|项目|单位|公司)\s*[:：]\s*([^\s，。；]{2,80})')
SECRET = re.compile(r'(?i)(?:password|secret|api[_-]?key|密码|密钥)\s*[:=：]\s*\S{4,}')
TERM = re.compile(r'\b[A-Z][A-Za-z0-9-]{2,24}\b')


def inspect(ast, template_structure=None, claims=(), *, project_facts=(), stale_sources=()):
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

    def add(category, rule, severity, section, block, quote, impact, suggestion, **details):
        issues.append({'id': str(uuid4()), 'category': category, 'rule_id': rule,
                       'severity': severity, 'section_id': section['id'] if section else None,
                        'block_id': block['id'] if block else None, 'claim_id': details.pop('claim_id', None),
                        'source_id': details.pop('source_id', None), 'quote': SECRET.sub('[REDACTED]', str(quote))[:1500],
                       'impact': impact, 'suggestion': suggestion, 'details': details})

    titles = {section['title'].strip() for section in sections}
    for item in (template_structure or {}).get('sections', []):
        if item.get('title') not in titles:
            add('structure', 'required_chapter', 'high', None, None, item['title'],
                '缺少模板必需章节', '补齐模板章节并重新审校')
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
        if claim.get('status') != 'supported' or claim.get('needs_review'):
            section = next((s for s in sections if s['id'] == str(claim.get('section_id'))), None)
            block = next((b for b in section['blocks'] if b['id'] == str(claim.get('block_id'))), None) if section else None
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
