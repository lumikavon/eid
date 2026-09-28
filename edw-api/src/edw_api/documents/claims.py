"""Conservative deterministic claim candidates, not a model or factual approval."""
import re
from uuid import uuid4

# Order matters: specific expressions precede generic numbers. Unrecognized declared
# types are accepted by the declare command rather than silently coerced to a known type.
PATTERNS = (
    ('percentage', r'(?<!\w)\d+(?:\.\d+)?\s*%'),
    ('date', r'\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?'),
    ('acceptance_threshold', r'(?:不低于|不超过|至少|最多|≤|≥)\s*\d+(?:\.\d+)?\s*[\w%/]*'),
    ('capacity', r'\d+(?:\.\d+)?\s*(?:GB|TB|MB|GiB|吨|升|kWh)'),
    ('performance', r'\d+(?:\.\d+)?\s*(?:QPS|TPS|Mbps|Gbps|ms|毫秒)'),
    ('time', r'\d+(?:\.\d+)?\s*(?:小时|分钟|秒|天|h|min|s)\b'),
    ('standard', r'(?:GB/T|ISO|IEC|IEEE)\s*[-\w]+'),
    ('regulation', r'《[^》]{2,80}(?:法|条例|规定)》'),
    ('version', r'\b[vV]\d+(?:\.\d+){1,3}\b'),
    ('model', r'(?:型号|Model)\s*[:：]?\s*[\w.-]+'),
    ('customer_project_name', r'(?:客户|项目)\s*[:：]\s*[^\s，。；]{2,80}'),
    ('capability', r'(?:支持|具备|能够)\s*[^，。；]{2,80}'),
    ('number', r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])'),
)


def candidates(text):
    occupied = []
    for kind, pattern in PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            occupied.append(match.span())
            phrase = match.group().strip()
            amount = re.search(r'\d+(?:\.\d+)?', phrase)
            value = amount.group() if amount else phrase
            unit = phrase[amount.end():].strip()[:64] if amount else ''
            yield kind, match.start(), match.end(), phrase, value, unit


def extract_claims(conn, workspace_id, document_id, version_id, ast):
    for section in ast['document']['sections']:
        for block in section['blocks']:
            if block['type'] not in ('paragraph', 'heading', 'warning', 'code'):
                continue
            text = block['content']['text']
            for kind, start, end, phrase, value, unit in candidates(text):
                conn.execute('''INSERT INTO document_claim(id,workspace_id,document_id,document_version_id,
                    section_id,block_id,start_offset,end_offset,statement,claim_type,conditions,value,unit,
                    critical,status,needs_review) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s,%s,true,'unsupported',true)
                    ON CONFLICT (document_version_id,block_id,start_offset,end_offset,claim_type) DO NOTHING''',
                    (uuid4(), workspace_id, document_id, version_id, section['id'], block['id'],
                     start, end, phrase[:4000], kind, value[:256], unit))


def classify(claim, links):
    """Exact textual agreement only; a count, score or search hit is not support."""
    if any(link['relation'] == 'conflicts' for link in links):
        return 'conflicting'
    support = [link for link in links if link['relation'] == 'supports']
    if any(claim['statement'] in link['quoted_text'] and
           (not claim['conditions'] or claim['conditions'] in link['quoted_text']) for link in support):
        return 'supported'
    if any(claim['value'] in link['quoted_text'] and
           (not claim['conditions'] or claim['conditions'] in link['quoted_text']) for link in support):
        return 'partially_supported'
    return 'unsupported' if claim['critical'] else 'unknown'
