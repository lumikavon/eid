"""Section-scoped immutable candidate evidence. Retrieval is outside write transactions.

A Pack is a reviewable set of passages, never a factual or publication approval.
"""
import hashlib
import math
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..access.policy import AccessDenied
from ..documents.outline_repository import read_outline
from ..errors import ApiError
from ..task_contract import KnowledgeSearchInput, canonical
from .gateway import retrieve, verify_source
from .governance import decorate, local_source
from .routes import candidates, local_hits, model_call, query_vector, safe_hit, scope

MAX_ITEMS = 30


def pinned(conn, subject, workspace_id, document_id, section_id, outline_id, context_id, document_version):
    outline = read_outline(conn, subject, workspace_id, document_id)
    anchor, access, metadata = scope(conn, subject, workspace_id, document_id, context_id)
    if (outline['state'] != 'OUTLINE_READY' or outline['version_id'] != outline_id
            or outline['context_version_id'] != context_id
            or outline['document_version_id'] != document_version
            or metadata['head_version_id'] != document_version):
        raise ApiError(409, 'EVIDENCE_PREREQUISITE_CHANGED', '大纲、上下文或正文已变化；请重新选择章节')
    section = next((s for s in outline['snapshot']['sections'] if s['id'] == str(section_id)), None)
    if section is None:
        raise ApiError(409, 'EVIDENCE_SECTION_CHANGED', '章节不属于当前确认大纲')
    return section, outline, anchor, access, metadata


def plan(section, context):
    title = re.sub(r'[\x00-\x1f]+', ' ', section['title']).strip()[:90]
    if not title:
        raise ApiError(422, 'EVIDENCE_SECTION_EMPTY', '章节标题为空')
    # Deterministic bounded query planner; context facts are search terms, not assertions of support.
    terms = [title if len(title) >= 2 else f'{title} 资料', f'{title} 标准', f'{title} 项目']
    for fact in context.get('facts', []):
        key = str(fact.get('key', '')).strip()[:50]
        if key:
            terms.append(f'{title[:65]} {key}')
    return list(dict.fromkeys(q[:128] for q in terms))[:10]


def _identity(item):
    return (item['chain'], item['source_id'], item['version'], item['chunk_hash'], item['locator'])


def prepare(settings, job):
    """Search in bounded phases. No DB connection survives a model or gateway request."""
    from ..db import connection
    with connection(settings) as conn:
        section, outline, anchor, access, metadata = pinned(conn, job['subject'], job['workspace_id'],
            job['document_id'], job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])
        if (access.actor_id != str(job['actor_id']) or list(access.policy_epoch) != job['policy_epoch']
                or metadata['revision'] != job['document_revision']):
            raise AccessDenied()
        context = conn.execute('SELECT snapshot FROM project_context_version WHERE id=%s AND document_id=%s',
                               (job['context_version_id'], job['document_id'])).fetchone()
        queries = plan(section, context['snapshot'])
        project = dict(anchor)
    items, chain_status, gaps = {}, [], []
    for query in queries:
        vector = query_vector(settings, query)
        command = KnowledgeSearchInput(query=query, context_document_id=job['document_id'],
                                       context_version_id=job['context_version_id'], limit=10)
        # The indexed local path is always bounded, even if the vector/model is unavailable.
        with connection(settings) as conn:
            _, live, state = pinned(conn, job['subject'], job['workspace_id'], job['document_id'],
                job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])[2:]
            if live.policy_epoch != access.policy_epoch or state['revision'] != job['document_revision']:
                raise AccessDenied()
            ids, _capped = candidates(conn, job['subject'], job['workspace_id'], project, live, command)
            rows = local_hits(conn, ids, command, vector)
            local = []
            for row in rows[:10]:
                hit = safe_hit(row)
                try:
                    text = local_source(conn, job['workspace_id'], project, hit['source_id'], hit['version'],
                                        hit['chunk_hash'], hit['locator'], hit['classification'], hit['page'], hit['ordinal'], job['subject'])
                    if text == hit['excerpt']:
                        local.append(hit)
                except AccessDenied:
                    continue
            local = decorate(conn, project, local, job['workspace_id'])
        remote, available = retrieve(settings, job['subject'], job['workspace_id'], project, access,
                                     query, 'all', 10, context_version=job['context_version_id'])
        chain = {'keyword': 'available', 'semantic': 'available' if vector else 'unavailable',
                 'enterprise': 'available' if available else 'unavailable', 'rerank': 'unavailable'}
        chain_status.append(chain)
        # Enumeration always has a fixed scan budget; do not disclose a denied-source count threshold.
        gaps.append('SOURCE_SCAN_LIMIT')
        if not available:
            gaps.append('ENTERPRISE_UNAVAILABLE')
        if not vector:
            gaps.append('SEMANTIC_UNAVAILABLE')
        with connection(settings) as conn:
            section2, _, latest, fresh, state = pinned(conn, job['subject'], job['workspace_id'], job['document_id'],
                job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])
            if section2 != section or fresh.policy_epoch != access.policy_epoch or state['revision'] != job['document_revision']:
                raise AccessDenied()
            # Source metadata can suppress stale records, never create authorization.
            combined = decorate(conn, latest, local + remote, job['workspace_id'])
        # Only verified passages reach the reranker, outside a database transaction.
        if combined:
            scores = model_call(settings.reranker_endpoint,
                {'model': 'bge-reranker-v2-m3', 'query': query,
                 'passages': [hit['excerpt'] for hit in combined[:20]]}, 'scores')
            if isinstance(scores, list) and len(scores) == min(len(combined), 20) and all(
                    type(score) in (int, float) and math.isfinite(score) for score in scores):
                for hit, score in zip(combined[:20], scores):
                    hit['rerank_score'] = float(score)
                    hit['reranker_version'] = 'bge-reranker-v2-m3'
                combined.sort(key=lambda hit: hit.get('rerank_score', float('-inf')), reverse=True)
                chain['rerank'] = 'available'
        for hit in combined[:10]:
            key = _identity(hit)
            if key not in items and len(items) < MAX_ITEMS:
                items[key] = {**hit, 'queries': [query]}
            elif key in items:
                items[key]['queries'].append(query)
            else:
                gaps.append('ITEM_BUDGET_EXHAUSTED')
    return queries, list(items.values()), chain_status, sorted(set(gaps))


def commit(settings, job, fence, prepared):
    """External current ACL attestations precede the short, fenced commit."""
    from ..db import connection
    queries, items, chains, gaps = prepared
    # Gateway cannot be queried inside the committing transaction. Reattest exact pinned excerpts.
    with connection(settings) as conn:
        _, _, anchor, context, _ = pinned(conn, job['subject'], job['workspace_id'], job['document_id'],
            job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])
        project = dict(anchor)
    proofs = {}
    for hit in items:
        if hit['chain'] == 'enterprise':
            proof = verify_source(settings, job['subject'], job['workspace_id'], project, context,
                                  hit, job['context_version_id'])
            if proof == hit['excerpt']:
                proofs[_identity(hit)] = proof
            else:
                gaps.append('SOURCE_REVOKED_OR_CHANGED')
    with connection(settings) as conn:
        # Lock document head to serialize outline/context/document writes; repeat current grants under lock.
        conn.execute('SELECT id FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE',
                     (job['document_id'], job['workspace_id'])).fetchone()
        current = conn.execute('''SELECT * FROM section_evidence_job WHERE id=%s AND workspace_id=%s
            AND lease_until > clock_timestamp() FOR UPDATE''',
                               (job['id'], job['workspace_id'])).fetchone()
        if not current or current['state'] != 'RUNNING' or current['fence'] != fence:
            return False
        _, _, anchor, access, metadata = pinned(conn, job['subject'], job['workspace_id'], job['document_id'],
            job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])
        if (access.actor_id != str(job['actor_id']) or access.policy_epoch != tuple(job['policy_epoch'])
                or metadata['revision'] != job['document_revision']):
            raise AccessDenied()
        accepted = []
        for hit in items:
            if hit['chain'] == 'enterprise':
                if _identity(hit) not in proofs:
                    continue
            else:
                try:
                    text = local_source(conn, job['workspace_id'], anchor, hit['source_id'], hit['version'],
                        hit['chunk_hash'], hit['locator'], hit['classification'], hit['page'], hit['ordinal'], job['subject'])
                    if text != hit['excerpt']:
                        raise AccessDenied()
                except AccessDenied:
                    gaps.append('SOURCE_REVOKED_OR_CHANGED')
                    continue
            current_hit = decorate(conn, anchor, [dict(hit)], job['workspace_id'])
            if not current_hit:
                gaps.append('SOURCE_EXPIRED')
                continue
            accepted.append(current_hit[0])
        # Version conflicts are retained (not coalesced by source id).
        versions = {}
        conflicts = set()
        linked = set()
        for hit in accepted:
            source = (hit['chain'], hit['source_id'])
            if source in versions and versions[source] != hit['version']:
                conflicts.add(hit['source_id'])
            versions[source] = hit['version']
            linked.update(g['conflict_id'] for g in hit.get('governance', []) if g.get('conflict_id'))
        if conflicts or linked:
            gaps.append('SOURCE_CONFLICT_REQUIRES_REVIEW')
        if not accepted:
            gaps.append('NO_CURRENT_SUPPORT')
        # Retrieval and metadata are candidates only. No key-fact support verdict is inferred.
        gaps.append('KEY_FACT_SUPPORT_NOT_VERIFIED')
        payload = {'schema_version': 1, 'state': 'insufficient', 'queries': queries,
                   'items': accepted, 'chains': chains, 'gaps': sorted(set(gaps)),
                   'version_conflicts': sorted(conflicts), 'conflict_ids': sorted(linked),
                   'outline_version_id': str(job['outline_version_id']), 'section_id': str(job['section_id']),
                   'context_version_id': str(job['context_version_id']), 'document_version_id': str(job['document_version_id']),
                   'document_revision': job['document_revision'], 'policy_epoch': job['policy_epoch'],
                   'policy_hash': hashlib.sha256(canonical(job['policy_epoch'])).hexdigest(),
                   'retrieval_version': 'attachment-fts-simple-v1+bge-m3-v1',
                   'dictionary_version': 'indexed-per-item', 'embedding_version': 'bge-m3-v1',
                   'reranker_version': 'bge-reranker-v2-m3' if any(c['rerank'] == 'available' for c in chains) else None,
                   'budget': {'queries': len(queries), 'max_items': MAX_ITEMS}}
        # JSONB hash uses the same canonical representation on read; UUID/date values are converted by wire serializer.
        from fastapi.encoders import jsonable_encoder
        payload = jsonable_encoder(payload)
        digest = hashlib.sha256(canonical(payload)).hexdigest()
        identifier = uuid4()
        conn.execute('INSERT INTO section_evidence_pack(id,workspace_id,job_id,document_id,section_id,outline_version_id,context_version_id,document_version_id,content,content_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                     (identifier, job['workspace_id'], job['id'], job['document_id'], job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'], Jsonb(payload), digest))
        for index, query in enumerate(queries, 1):
            conn.execute('INSERT INTO section_evidence_query(pack_id,ordinal,query) VALUES (%s,%s,%s)', (identifier, index, query))
        for index, hit in enumerate(accepted, 1):
            conn.execute('INSERT INTO section_evidence_item(pack_id,ordinal,chain,source_id,version,chunk_hash,locator,excerpt,scores,provenance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (identifier, index, hit['chain'], hit['source_id'], hit['version'], hit['chunk_hash'], hit['locator'], hit['excerpt'],
                          Jsonb({'semantic': hit.get('semantic_score'), 'rerank': hit.get('rerank_score'), 'keyword': hit.get('keyword_match')}), Jsonb({'queries': hit['queries'], 'policy': hit['policy']})))
        for conflict_id in linked:
            conn.execute("INSERT INTO knowledge_dependency(workspace_id,conflict_id,kind,dependent_id,needs_review) VALUES (%s,%s,'pack',%s,true) ON CONFLICT DO NOTHING",
                         (job['workspace_id'], UUID(conflict_id), identifier))
        finished = conn.execute("""UPDATE section_evidence_job SET state='SUCCEEDED',stage='done',
            fence=NULL,lease_until=NULL,updated_at=clock_timestamp()
            WHERE id=%s AND fence=%s AND state='RUNNING' AND lease_until>clock_timestamp() RETURNING id""",
            (job['id'], fence)).fetchone()
        if not finished:
            raise AccessDenied()  # roll back the Pack, its items and dependencies together
        return True


def visible(settings, job):
    """Read never treats an old excerpt as an authorization grant."""
    from ..db import connection
    with connection(settings) as conn:
        _, _, anchor, context, _ = pinned(conn, job['subject'], job['workspace_id'], job['document_id'],
            job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])
        pack = conn.execute('SELECT * FROM section_evidence_pack WHERE workspace_id=%s AND job_id=%s',
                            (job['workspace_id'], job['id'])).fetchone()
        if not pack:
            return None
        if hashlib.sha256(canonical(pack['content'])).hexdigest() != pack['content_hash']:
            raise ApiError(503, 'EVIDENCE_INTEGRITY', '证据完整性暂不可用')
        anchor = dict(anchor)
        content = pack['content']
    proofs = {}
    for hit in content['items']:
        if hit['chain'] == 'enterprise':
            proof = verify_source(settings, job['subject'], job['workspace_id'], anchor, context, hit, job['context_version_id'])
            if proof == hit['excerpt']:
                proofs[_identity(hit)] = True
    with connection(settings) as conn:
        _, _, fresh_anchor, fresh, _ = pinned(conn, job['subject'], job['workspace_id'], job['document_id'],
            job['section_id'], job['outline_version_id'], job['context_version_id'], job['document_version_id'])
        if fresh.policy_epoch != context.policy_epoch:
            raise AccessDenied()
        output = []
        for hit in content['items']:
            if hit['chain'] == 'enterprise':
                if _identity(hit) not in proofs:
                    continue
            else:
                try:
                    if local_source(conn, job['workspace_id'], fresh_anchor, hit['source_id'], hit['version'], hit['chunk_hash'],
                                    hit['locator'], hit['classification'], hit['page'], hit['ordinal'], job['subject']) != hit['excerpt']:
                        continue
                except AccessDenied:
                    continue
            if not decorate(conn, fresh_anchor, [hit], job['workspace_id']):
                continue
            output.append(hit)
        # No counts for denied passages. Missing entries are represented only as a safe state.
        live_conflicts = sorted({g['conflict_id'] for hit in output for g in hit.get('governance', []) if g.get('conflict_id')})
        versions, version_conflicts = {}, set()
        for hit in output:
            key = (hit['chain'], hit['source_id'])
            if key in versions and versions[key] != hit['version']:
                version_conflicts.add(hit['source_id'])
            versions[key] = hit['version']
        return {'id': str(pack['id']), 'content_hash': pack['content_hash'],
                **{k: v for k, v in content.items() if k not in ('items', 'conflict_ids', 'version_conflicts', 'gaps')},
                'items': output, 'conflict_ids': live_conflicts, 'version_conflicts': sorted(version_conflicts),
                'gaps': sorted(set([g for g in content['gaps'] if g != 'SOURCE_CONFLICT_REQUIRES_REVIEW']
                                   + (['SOURCE_CONFLICT_REQUIRES_REVIEW'] if live_conflicts or version_conflicts else [])
                                   + (['SOURCE_REVOKED_OR_CHANGED'] if len(output) != len(content['items']) else []))),
                'state': 'insufficient'}
