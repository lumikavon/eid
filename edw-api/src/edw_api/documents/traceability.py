"""版本固定的测试链与真实需求分母；当前授权始终重新核验。"""
from ..errors import ApiError
from ..access.policy import AccessDenied
from .editor_repository import read_version

KINDS = {'requirement': 'test_item', 'test_item': 'test_case', 'test_case': 'acceptance'}
MEASUREMENT = ('condition', 'metric', 'unit', 'threshold', 'verification_method')


def blocks(ast):
    return {(s['id'], b['id']): b for s in ast['document']['sections'] for b in s['blocks']}


def resolve(conn, subject, workspace_id, ref):
    value = read_version(conn, subject, workspace_id, ref['document_id'], ref['version_id'])
    head = conn.execute('SELECT head_version_id FROM document WHERE id=%s AND workspace_id=%s',
                        (ref['document_id'], workspace_id)).fetchone()
    block = blocks(value['ast']).get((ref['section_id'], ref['block_id']))
    return value, block, bool(head and str(head['head_version_id']) == ref['version_id'])


def validate_links(conn, subject, workspace_id, document_id, ast, old_ast):
    previous = blocks(old_ast)
    for ref in ast['document'].get('test_baselines', []):
        value = read_version(conn, subject, workspace_id, ref['document_id'], ref['version_id'])
        if value['document_type'] not in ('prd', 'technical_requirements'):
            raise ApiError(422, 'TEST_TRACE_INVALID', '测试基线须为需求文档')
    for locator, block in blocks(ast).items():
        if block['type'] not in ('test_item', 'test_case', 'acceptance'):
            continue
        old = previous.get(locator)
        for ref in block['content'].get('links', []):
            # Local links use the base version as an immutable pin. A new version makes
            # them stale, so link chains normally use separately versioned documents.
            value, target, current = resolve(conn, subject, workspace_id, ref)
            if not target or KINDS.get(target['type']) != block['type']:
                raise ApiError(422, 'TEST_TRACE_INVALID', '测试链的目标类型或区块不匹配')
            unchanged = old == block
            if not current and not unchanged:
                raise ApiError(409, 'TEST_TRACE_STALE', '测试链目标已产生新版本')
            if target['type'] == 'requirement' and value['document_type'] not in ('prd', 'technical_requirements'):
                raise ApiError(422, 'TEST_TRACE_INVALID', '测试基线须为结构化需求文档')
            for field in MEASUREMENT:
                expected = target['content'].get(field)
                if block['content'].get(field, '') != (expected or ''):
                    raise ApiError(422, 'TEST_THRESHOLD_MISMATCH', f'测试不得替换来源字段：{field}')


def coverage(conn, subject, workspace_id, ast, document_id=None, version_id=None):
    """分母包含被引用需求文档的全部当前需求，而非只计算已有测试。"""
    baseline = {}
    links = []
    baseline_documents = set()
    baseline_states = []
    for ref in ast['document'].get('test_baselines', []):
        try:
            pinned = read_version(conn, subject, workspace_id, ref['document_id'], ref['version_id'])
            head = conn.execute('SELECT head_version_id FROM document WHERE id=%s AND workspace_id=%s',
                                (ref['document_id'], workspace_id)).fetchone()
            if not head or pinned['document_type'] not in ('prd', 'technical_requirements'):
                raise ApiError(404, 'DOCUMENT_VERSION_NOT_FOUND', '需求基线当前不可用')
            live = read_version(conn, subject, workspace_id, ref['document_id'], head['head_version_id'])
            state = 'current' if str(head['head_version_id']) == ref['version_id'] else 'stale'
            baseline_states.append({**ref, 'state': state})
            baseline_documents.add(ref['document_id'])
            for (s, b), requirement in blocks(live['ast']).items():
                if requirement['type'] == 'requirement':
                    key = (ref['document_id'], str(live['version_id']), s, b)
                    baseline[key] = {'document_id': key[0], 'version_id': key[1], 'section_id': s,
                        'block_id': b, 'requirement_id': requirement['content'].get('requirement_id')}
        except (AccessDenied, ApiError) as exc:
            if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
                raise
            baseline_states.append({**ref, 'state': 'unavailable'})
    def collect_baseline(ref, seen):
        key = tuple(ref[f] for f in ('document_id', 'version_id', 'section_id', 'block_id'))
        if key in seen or len(seen) >= 32:
            return
        value, target, _ = resolve(conn, subject, workspace_id, ref)
        if not target:
            return
        if target['type'] == 'requirement' and ref['document_id'] not in baseline_documents:
            baseline_documents.add(ref['document_id'])
            head = conn.execute('SELECT head_version_id FROM document WHERE id=%s AND workspace_id=%s',
                                (ref['document_id'], workspace_id)).fetchone()
            live = read_version(conn, subject, workspace_id, ref['document_id'], head['head_version_id'])
            for (s, b), requirement in blocks(live['ast']).items():
                if requirement['type'] == 'requirement':
                    baseline_key = (ref['document_id'], str(live['version_id']), s, b)
                    baseline[baseline_key] = {'document_id': baseline_key[0], 'version_id': baseline_key[1],
                        'section_id': s, 'block_id': b, 'requirement_id': requirement['content'].get('requirement_id')}
        elif target['type'] in ('test_item', 'test_case'):
            for parent in target['content'].get('links', []):
                collect_baseline(parent, seen | {key})
    def upstream(ref, seen):
        key = tuple(ref[f] for f in ('document_id', 'version_id', 'section_id', 'block_id'))
        if key in seen or len(seen) >= 32:
            return False
        value, target, current = resolve(conn, subject, workspace_id, ref)
        if not target or not current:
            return False
        if target['type'] == 'requirement':
            return value['document_type'] in ('prd', 'technical_requirements')
        parents = target['content'].get('links', [])
        if target['type'] not in ('test_item', 'test_case', 'acceptance') or not parents:
            return False
        for parent in parents:
            _, parent_block, _ = resolve(conn, subject, workspace_id, parent)
            if not parent_block or KINDS.get(parent_block['type']) != target['type']:
                return False
            if any((parent_block['content'].get(field) or '') !=
                   (target['content'].get(field) or '') for field in MEASUREMENT):
                return False
            if not upstream(parent, seen | {key}):
                return False
        return True
    for (section_id, block_id), block in blocks(ast).items():
        if block['type'] not in ('test_item', 'test_case', 'acceptance'):
            continue
        for ref in block['content'].get('links', []):
            try:
                value, target, current = resolve(conn, subject, workspace_id, ref)
            except (AccessDenied, ApiError) as exc:
                if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
                    raise
                links.append({'section_id': section_id, 'block_id': block_id,
                              'target': ref, 'state': 'unavailable'})
                continue
            state = 'current' if current and target and KINDS.get(target['type']) == block['type'] else 'stale'
            try:
                if state == 'current' and not upstream(ref, set()):
                    state = 'stale'
            except (AccessDenied, ApiError) as exc:
                if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
                    raise
                state = 'unavailable'
            if target and any((target['content'].get(f) or '') != block['content'].get(f, '')
                              for f in MEASUREMENT):
                state = 'threshold_mismatch'
            links.append({'section_id': section_id, 'block_id': block_id, 'target': ref, 'state': state})
            try:
                collect_baseline(ref, set())
            except (AccessDenied, ApiError) as exc:
                if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
                    raise
    rows = []
    covered = 0
    # Only a complete, currently authorized requirement→item→case→acceptance
    # chain contributes to the numerator. Gather current reverse projections.
    def children(ref, kind, seen):
        key = tuple(str(ref[f]) for f in ('document_id', 'version_id', 'section_id', 'block_id'))
        if key in seen or len(seen) >= 32:
            return []
        found = []
        for (s, b), candidate in blocks(ast).items():
            if candidate['type'] == kind and any(tuple(str(parent[f]) for f in
                    ('document_id', 'version_id', 'section_id', 'block_id')) == key
                    for parent in candidate['content'].get('links', [])):
                found.append({'section_id': s, 'block_id': b, 'block': candidate, 'local': True,
                              **({'document_id': str(document_id), 'version_id': str(version_id)} if document_id else {})})
        if hasattr(conn, 'execute'):
            cursor = conn.execute('''SELECT t.* FROM requirement_trace t JOIN document d
                ON d.id=t.document_id AND d.head_version_id=t.version_id
                WHERE t.workspace_id=%s AND t.target_document_id=%s AND t.target_version_id=%s
                AND t.target_section_id=%s AND t.target_block_id=%s''', (workspace_id, *key))
            for row in cursor.fetchall() if hasattr(cursor, 'fetchall') else []:
                try:
                    value = read_version(conn, subject, workspace_id, row['document_id'], row['version_id'])
                    candidate = blocks(value['ast']).get((str(row['section_id']), str(row['block_id'])))
                    if candidate and candidate['type'] == kind and any(
                            tuple(str(parent[f]) for f in ('document_id', 'version_id', 'section_id', 'block_id')) == key
                            for parent in candidate['content'].get('links', [])):
                        found.append({'document_id': str(row['document_id']), 'version_id': str(row['version_id']),
                            'section_id': str(row['section_id']), 'block_id': str(row['block_id']), 'block': candidate})
                except (AccessDenied, ApiError) as exc:
                    if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
                        raise
        unique = {tuple(item.get(f, '') for f in ('document_id', 'version_id', 'section_id', 'block_id')): item for item in found}
        return list(unique.values())
    for key, requirement in baseline.items():
        peers = [link for link in links if link['state'] == 'current'
                 and tuple(link['target'][f] for f in ('document_id', 'version_id', 'section_id', 'block_id')) == key]
        items = children(requirement, 'test_item', set())
        complete = []
        for item in items:
            if 'document_id' not in item:
                continue
            for case in children(item, 'test_case', set()):
                if 'document_id' not in case:
                    continue
                for acceptance in children(case, 'acceptance', set()):
                    chain = [item, case, acceptance]
                    try:
                         requirement_block = resolve(conn, subject, workspace_id, requirement)[1]
                         valid = bool(requirement_block) and all(
                                     KINDS.get(resolve(conn, subject, workspace_id, parent)[1]['type']) == entry['block']['type']
                                     and upstream(parent, set()) for entry in chain
                                     for parent in entry['block']['content'].get('links', [])) and all(
                                     bool(entry['block']['content'].get('links'))
                                     and all((entry['block']['content'].get(f) or '') ==
                                             (requirement_block['content'].get(f) or '') for f in MEASUREMENT)
                                     for entry in chain)
                    except (AccessDenied, ApiError):
                        valid = False
                    if valid:
                        complete.append([{f: entry[f] for f in ('document_id', 'version_id', 'section_id', 'block_id')
                                          if f in entry} for entry in chain])
        covered += bool(complete)
        rows.append({**requirement, 'tests': peers, 'chains': complete, 'state': 'uncovered' if not complete else
                     'redundant' if len(complete) > 1 else 'covered'})
    return {'numerator': covered, 'denominator': len(baseline),
            'state': 'unavailable' if any(b['state'] == 'unavailable' for b in baseline_states) else
                     'evaluated' if baseline else 'unevaluated', 'requirements': rows, 'links': links,
            'baselines': baseline_states,
            'unlinked': [{'section_id': s, 'block_id': b} for (s, b), block in blocks(ast).items()
                         if block['type'] in ('test_item', 'test_case', 'acceptance')
                         and not block['content'].get('links')]}


def project(conn, workspace_id, document_id, version_id, ast):
    for (section_id, block_id), block in blocks(ast).items():
        for ref in block['content'].get('links', []) if block['type'] in ('test_item', 'test_case', 'acceptance') else []:
            conn.execute('''INSERT INTO requirement_trace(workspace_id,document_id,version_id,section_id,
                block_id,target_document_id,target_version_id,target_section_id,target_block_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (workspace_id, document_id, version_id, section_id, block_id,
                 ref['document_id'], ref['version_id'], ref['section_id'], ref['block_id']))
