"""Scoped retrieval; never reuse discovery titles or upload-time delegation as Evidence."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import math
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Depends, Response
from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from ..task_contract import KnowledgeSearchInput as Search
from .gateway import retrieve, verify_source
from .governance import decorate, local_source


def model_call(endpoint: str, body: dict, key: str):
    if not endpoint.startswith('https://'):
        return None
    try:
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            result = client.post(endpoint, json=body)
            result.raise_for_status()
            data = result.json()
            if data.get('model') != body['model']:
                return None
            return data[key]
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return None


def query_vector(settings, text):
    values = model_call(settings.bge_m3_endpoint, {'model': 'bge-m3-v1', 'text': text}, 'embedding')
    if not isinstance(values, list) or len(values) != 1024 or any(
            type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 100 for x in values):
        return None
    return '[' + ','.join(str(x) for x in values) + ']'


def scope(conn, subject, workspace_id, document_id, context_version_id):
    _, resource, context = checked(conn, subject, workspace_id, 'resource:read', document_id)
    if resource['kind'] != 'document':
        raise AccessDenied()
    row = conn.execute('''SELECT d.knowledge_scope,d.head_version_id,d.revision,g.active,
        h.version_id AS context_version FROM document d
        JOIN document_knowledge_scope_grant g ON g.workspace_id=d.workspace_id AND g.scope=d.knowledge_scope
        LEFT JOIN project_context_head h ON h.document_id=d.id
        WHERE d.id=%s AND d.workspace_id=%s''', (document_id, workspace_id)).fetchone()
    if not row or not row['active'] or context_version_id is not None and row['context_version'] != context_version_id:
        raise AccessDenied()
    return resource, context, row


def candidates(conn, subject, workspace_id, anchor, context, command):
    # Enumerate IDs only. Never fetch a title or excerpt before checked() for this source.
    rows = conn.execute('''SELECT DISTINCT a.document_id FROM attachment_search_index i
        JOIN attachment a ON a.id=i.attachment_id
        JOIN attachment_parse p ON p.attachment_id=a.id
        JOIN access_resource r ON r.id=a.document_id AND r.workspace_id=a.workspace_id
        WHERE a.workspace_id=%s AND a.classification<=%s AND r.classification<=%s
        AND p.state IN ('SUCCEEDED','PARTIAL') AND p.source_sha256=a.sha256
        AND p.parser_version=i.parser_version AND i.source_sha256=p.source_sha256
        AND (r.project_id=%s) AND (%s::text IS NULL OR a.sha256=%s)
        ORDER BY a.document_id LIMIT 101''',
        (workspace_id, context.classification, context.classification, anchor['project_id'],
         command.source_sha256, command.source_sha256)).fetchall()
    allowed = []
    for row in rows[:100]:
        try:
            _, r, _ = checked(conn, subject, workspace_id, 'resource:read', row['document_id'])
            if r['kind'] == 'document' and r['project_id'] == anchor['project_id']:
                allowed.append(row['document_id'])
        except AccessDenied:
            continue
    return allowed, len(rows) > 100


def local_hits(conn, ids, command, vector):
    if not ids:
        return []
    # Keyword and exact substring both work without embeddings. Query strings are bound values.
    sql = '''SELECT i.attachment_id,i.document_id,i.page_number,i.ordinal,i.source_sha256,
        i.content_hash,i.parser_version,i.keyword_version,i.dictionary_version,i.embedding_version,
        c.content,c.locator,a.classification,a.kind,
        (i.tokens @@ plainto_tsquery('simple',%s) OR strpos(lower(c.content),lower(%s))>0) AS exact,
        CASE WHEN %s::vector IS NULL OR i.embedding IS NULL THEN NULL
             ELSE 1-(i.embedding <=> %s::vector) END AS semantic_score
        FROM attachment_search_index i JOIN attachment_chunk c
        ON c.attachment_id=i.attachment_id AND c.page_number=i.page_number AND c.ordinal=i.ordinal
        JOIN attachment a ON a.id=i.attachment_id AND a.document_id=i.document_id
        JOIN attachment_parse p ON p.attachment_id=a.id
        WHERE i.document_id=ANY(%s::uuid[]) AND p.state IN ('SUCCEEDED','PARTIAL')
        AND p.parser_version=i.parser_version AND p.source_sha256=i.source_sha256
        AND a.sha256=p.source_sha256 AND c.content_hash=i.content_hash
        AND a.classification<=%s AND (%s::text IS NULL OR a.sha256=%s)
        AND (i.tokens @@ plainto_tsquery('simple',%s) OR strpos(lower(c.content),lower(%s))>0
             OR (%s::vector IS NOT NULL AND i.embedding_version='bge-m3-v1'
                 AND i.embedding IS NOT NULL))
        ORDER BY exact DESC, semantic_score DESC NULLS LAST, i.attachment_id,i.page_number,i.ordinal LIMIT 40'''
    return conn.execute(sql, (command.query, command.query, vector, vector, ids,
                              command.classification if command.classification is not None else 3,
                              command.source_sha256, command.source_sha256, command.query,
                              command.query, vector)).fetchall()


def safe_hit(row):
    return {'chain': 'attachment', 'category': 'attachment', 'source_id': str(row['attachment_id']),
            'document_id': str(row['document_id']), 'version': row['source_sha256'],
            'parser_version': row['parser_version'], 'chunk_hash': row['content_hash'],
            'page': row['page_number'], 'ordinal': row['ordinal'], 'locator': row['locator'],
            'excerpt': row['content'], 'classification': row['classification'],
            'keyword_version': row['keyword_version'], 'dictionary_version': row['dictionary_version'],
            'embedding_version': row['embedding_version'],
            'keyword_match': row['exact'], 'semantic_score': row['semantic_score'],
            'policy': 'current-resource-read-v1'}


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/knowledge')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(404, 'KNOWLEDGE_NOT_FOUND', '来源不存在或不可访问') from exc
        except psycopg.Error as exc:
            raise ApiError(503, 'KNOWLEDGE_UNAVAILABLE', '检索暂不可用', retryable=True) from exc

    @router.post('/search')
    def search(workspace_id: UUID, command: Search, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            anchor, context, metadata = scope(conn, current.subject, workspace_id,
                                              command.context_document_id, command.context_version_id)
            allowed, capped = candidates(conn, current.subject, workspace_id, anchor, context, command)
        # Model and enterprise calls are outside any database transaction. Models see query only.
        vector = query_vector(settings, command.query) if command.category in ('all', 'attachment') else None
        status = {'keyword': 'available', 'semantic': 'available' if vector else 'unavailable',
                  'rerank': 'unavailable', 'enterprise': 'unavailable', 'golden': 'unavailable'}
        enterprise = []
        if command.category in ('all', 'enterprise', 'golden'):
            enterprise, available = retrieve(settings, current.subject, workspace_id, anchor, context,
                                             command.query, command.category, command.limit,
                                             command.source_sha256, metadata['context_version'])
            if available:
                status['enterprise'] = 'available'
                status['golden'] = 'available'
        hits = []
        if command.category in ('all', 'attachment'):
            with database() as conn:
                latest, _, state = scope(conn, current.subject, workspace_id,
                                         command.context_document_id, command.context_version_id)
                if (latest['project_id'] != anchor['project_id'] or state['head_version_id'] != metadata['head_version_id']
                        or list(context.policy_epoch) != list(checked(conn, current.subject, workspace_id,
                            'resource:read', command.context_document_id)[2].policy_epoch)
                        or state['context_version'] != metadata['context_version']):
                    raise AccessDenied()
                # Re-enumerate current grants before text is fetched after the network call.
                live, cap2 = candidates(conn, current.subject, workspace_id, latest, context, command)
                capped = capped or cap2
                scope_ids = [x for x in allowed if x in live]
                if vector and (not scope_ids or not conn.execute('''SELECT EXISTS(
                    SELECT 1 FROM attachment_search_index WHERE document_id=ANY(%s::uuid[])
                    AND embedding_version='bge-m3-v1') AS ready''', (scope_ids,)).fetchone()['ready']):
                    status['semantic'] = 'unavailable'
                    vector = None
                hits = local_hits(conn, scope_ids, command, vector)
                valid = []
                for row in hits:
                    try:
                        _, resource, access = checked(conn, current.subject, workspace_id,
                                                      'resource:read', row['document_id'])
                        a = conn.execute('''SELECT a.sha256,a.classification,p.state,p.parser_version,
                            c.content_hash,i.source_sha256 FROM attachment a
                            JOIN attachment_parse p ON p.attachment_id=a.id
                            JOIN attachment_chunk c ON c.attachment_id=a.id AND c.page_number=%s AND c.ordinal=%s
                            JOIN attachment_search_index i ON i.attachment_id=a.id AND i.page_number=%s AND i.ordinal=%s
                            WHERE a.id=%s AND a.workspace_id=%s''',
                            (row['page_number'],row['ordinal'],row['page_number'],row['ordinal'],
                             row['attachment_id'],workspace_id)).fetchone()
                        if (resource['kind'] == 'document' and resource['project_id'] == latest['project_id']
                            and a and a['classification'] <= access.classification
                            and a['sha256'] == a['source_sha256'] == row['source_sha256']
                            and a['content_hash'] == row['content_hash'] and a['parser_version'] == row['parser_version']
                            and a['state'] in ('SUCCEEDED','PARTIAL')):
                            valid.append(safe_hit(row))
                    except AccessDenied:
                        continue
                scope(conn, current.subject, workspace_id, command.context_document_id, command.context_version_id)
                hits = decorate(conn, latest, valid[:40], workspace_id)  # stale text never reaches the reranker
        # The reranker receives only excerpts already checked under current resource policy.
        # Its scores never authorize a source; every source is rechecked after the call.
        if hits:
            scores = model_call(settings.reranker_endpoint,
                {'model': 'bge-reranker-v2-m3', 'query': command.query,
                 'passages': [item['excerpt'] for item in hits]}, 'scores')
            if (isinstance(scores, list) and len(scores) == len(hits) and all(
                    type(s) in (int, float) and math.isfinite(s) for s in scores)):
                for item, score in zip(hits, scores):
                    item['rerank_score'] = float(score)
                    item['reranker_version'] = 'bge-reranker-v2-m3'
                hits.sort(key=lambda item: item['rerank_score'], reverse=True)
                status['rerank'] = 'available'
        # Reattest each exact enterprise excerpt at the final network boundary. A search
        # response alone is never a current-use authorization.
        enterprise = [item for item in enterprise if verify_source(
            settings, current.subject, workspace_id, anchor, context, item,
            metadata['context_version']) == item['excerpt']]
        # Recheck anchor and epoch after the external verification, without an open network transaction.
        with database() as conn:
            latest, fresh, state = scope(conn, current.subject, workspace_id,
                                         command.context_document_id, command.context_version_id)
            if (fresh.policy_epoch != context.policy_epoch or latest['project_id'] != anchor['project_id']
                    or state['head_version_id'] != metadata['head_version_id']
                    or state['context_version'] != metadata['context_version']):
                raise AccessDenied()
            # Gateway results require a fresh signed ACL/version assertion; local rows require
            # another source check at the final output boundary.
            current_hits = []
            for item in hits:
                try:
                    if local_source(conn, workspace_id, latest, item['source_id'], item['version'],
                                    item['chunk_hash'], item['locator'], item['classification'], item['page'],
                                    item['ordinal'], current.subject) == item['excerpt']:
                        current_hits.append(item)
                except AccessDenied:
                    continue
            hits = current_hits
            now = datetime.now(timezone.utc)
            enterprise = [x for x in enterprise if datetime.fromisoformat(
                x['valid_until'].replace('Z', '+00:00')) > now]
            if command.classification is not None:
                enterprise = [x for x in enterprise if x['classification'] <= command.classification]
            items = decorate(conn, latest, hits + enterprise, workspace_id)[:command.limit]
            for item in items:
                item['project_id'] = latest['project_id']
                item['product_id'] = latest['product_id']
                item['customer_id'] = latest['customer_id']
        # A capped source scan and unavailable chains are never called complete.
        return {'data': {'items': items, 'chains': status, 'complete': False,
                         'limited': True,
                         'query_sha256': sha256(command.query.encode()).hexdigest(),
                         'policy_epoch': list(context.policy_epoch),
                         'scope': 'same_project_authorized_documents',
                         'retrieval_version': 'attachment-fts-simple-v1+bge-m3-v1'}}

    @router.get('/attachments/{attachment_id}/chunks/{page}/{ordinal}')
    def inspect(workspace_id: UUID, attachment_id: UUID, page: int, ordinal: int,
                context_document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        if not 1 <= page <= 500 or not 1 <= ordinal <= 200:
            raise ApiError(404, 'KNOWLEDGE_NOT_FOUND', '来源不存在或不可访问')
        with database() as conn:
            anchor, context, _ = scope(conn, current.subject, workspace_id, context_document_id, None)
            source = conn.execute('SELECT document_id FROM attachment WHERE id=%s AND workspace_id=%s',
                                  (attachment_id, workspace_id)).fetchone()
            if not source:
                raise AccessDenied()
            _, resource, auth = checked(conn, current.subject, workspace_id, 'resource:read', source['document_id'])
            row = conn.execute('''SELECT a.document_id,a.sha256,a.classification,c.content,c.locator,c.content_hash,
                p.parser_version,p.state FROM attachment a JOIN attachment_parse p ON p.attachment_id=a.id
                JOIN attachment_chunk c ON c.attachment_id=a.id AND c.page_number=%s AND c.ordinal=%s
                JOIN attachment_search_index i ON i.attachment_id=a.id AND i.page_number=c.page_number AND i.ordinal=c.ordinal
                WHERE a.id=%s AND a.workspace_id=%s AND a.sha256=p.source_sha256
                AND i.source_sha256=p.source_sha256 AND i.parser_version=p.parser_version
                AND i.content_hash=c.content_hash''',
                (page, ordinal, attachment_id, workspace_id)).fetchone()
            if not row:
                raise AccessDenied()
            if (resource['kind'] != 'document' or resource['project_id'] != anchor['project_id']
                    or row['classification'] > auth.classification or row['classification'] > context.classification
                    or row['state'] not in ('SUCCEEDED','PARTIAL')):
                raise AccessDenied()
            latest, _, _ = scope(conn, current.subject, workspace_id, context_document_id, None)
            checked(conn, current.subject, workspace_id, 'resource:read', source['document_id'])
            if latest['project_id'] != anchor['project_id'] or not decorate(conn, latest, [{
                    'chain': 'attachment', 'source_id': str(attachment_id), 'version': row['sha256'],
                    'chunk_hash': row['content_hash'], 'locator': row['locator']}], workspace_id):
                raise AccessDenied()
            return {'data': {'source_id': attachment_id, 'document_id': row['document_id'],
                             'version': row['sha256'], 'parser_version': row['parser_version'],
                             'page': page, 'ordinal': ordinal, 'locator': row['locator'],
                             'chunk_hash': row['content_hash'], 'excerpt': row['content']}}

    return router
