"""Current-access source governance. Stored history is never an access token."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..errors import ApiError
from .gateway import verify_source

AUTHORITY = ('law', 'company', 'project', 'product', 'approved_history',
             'department', 'internal', 'allowed_external', 'llm_general')


def applicable(row, anchor, now=None):
    now = now or datetime.now(timezone.utc)
    return (row['effective_from'] <= now and (row['effective_until'] is None or now < row['effective_until'])
            and row['project_id'] == anchor['project_id']
            and (row['product_id'] is None or row['product_id'] == anchor['product_id'])
            and (row['customer_id'] is None or row['customer_id'] == anchor['customer_id']))


def local_source(conn, workspace_id, anchor, source_id, version, chunk_hash, locator, classification,
                 page, ordinal, subject):
    try:
        identifier = UUID(source_id)
    except (ValueError, TypeError):
        raise AccessDenied() from None
    row = conn.execute('''SELECT a.document_id,a.sha256,a.classification,c.content,c.locator,c.content_hash,
        p.state,p.source_sha256 AS parse_sha256,p.parser_version,i.source_sha256,i.parser_version AS indexed_parser FROM attachment a JOIN attachment_parse p ON p.attachment_id=a.id
        JOIN attachment_chunk c ON c.attachment_id=a.id AND c.page_number=%s AND c.ordinal=%s
        JOIN attachment_search_index i ON i.attachment_id=a.id AND i.page_number=c.page_number AND i.ordinal=c.ordinal
        WHERE a.id=%s AND a.workspace_id=%s AND i.content_hash=c.content_hash''',
        (page, ordinal, identifier, workspace_id)).fetchone()
    if not row:
        raise AccessDenied()
    _, resource, auth = checked(conn, subject, workspace_id, 'resource:read', row['document_id'])
    if (resource['kind'] != 'document' or resource['project_id'] != anchor['project_id']
            or row['classification'] != classification or classification > auth.classification
            or row['sha256'] != row['source_sha256'] or row['sha256'] != row['parse_sha256']
            or row['parser_version'] != row['indexed_parser'] or row['sha256'] != version
            or row['content_hash'] != chunk_hash or row['locator'] != locator
            or row['state'] not in ('PARTIAL', 'SUCCEEDED')
            or sha256(row['content'].encode()).hexdigest() != chunk_hash):
        raise AccessDenied()
    return row['content']


def current_source(conn, settings, subject, workspace_id, anchor, context, row):
    if not applicable(row, anchor) or row['authority'] == 9:
        return None
    if row['chain'] == 'attachment':
        try:
            return local_source(conn, workspace_id, anchor, row['source_id'], row['version'], row['chunk_hash'],
                                row['locator'], row['classification'], row['page'], row['ordinal'], subject)
        except AccessDenied:
            return None
    # No network call while holding a DB transaction: enterprise proof must be obtained
    # by the caller in a separate phase. Never use this branch to reauthorize a snapshot.
    return None


def source_identity(hit):
    return (hit['chain'], hit['source_id'], hit['version'], hit['chunk_hash'], hit['locator'])


def decorate(conn, anchor, hits, workspace_id):
    """Only decorate already current-authorized hits; metadata cannot authorize a hit."""
    keys = [source_identity(h) for h in hits]
    if not keys:
        return hits
    rows = conn.execute('''SELECT * FROM knowledge_assertion WHERE workspace_id=%s
        AND source_id=ANY(%s::text[])''', (workspace_id, [k[1] for k in keys])).fetchall()
    by_key = {}
    expired = set()
    for row in rows:
        key = (row['chain'], row['source_id'], row['version'], row['chunk_hash'], row['locator'])
        if applicable(row, anchor):
            by_key.setdefault(key, []).append(row)
        else:
            expired.add(key)
    hits = [hit for hit in hits if source_identity(hit) not in expired or source_identity(hit) in by_key]
    visible_ids = [r['id'] for records in by_key.values() for r in records]
    links = {}
    if visible_ids:
        for link in conn.execute('''SELECT id,left_id,right_id FROM knowledge_conflict WHERE workspace_id=%s
            AND (left_id=ANY(%s::uuid[]) OR right_id=ANY(%s::uuid[]))''',
            (workspace_id, visible_ids, visible_ids)).fetchall():
            for key in ('left_id', 'right_id'):
                links.setdefault(link[key], str(link['id']))
    for hit in hits:
        records = by_key.get(source_identity(hit), [])
        hit['governance'] = [{'assertion_id': str(r['id']), 'authority': r['authority'],
                              'authority_label': AUTHORITY[r['authority']-1],
                              'conflict_id': links.get(r['id']),
                              'effective_from': r['effective_from'].isoformat(),
                              'effective_until': r['effective_until'].isoformat() if r['effective_until'] else None}
                             for r in records]
    return sorted(hits, key=lambda h: (min((r['authority'] for r in by_key.get(source_identity(h), [])), default=10),
                                    -(h.get('rerank_score') or h.get('semantic_score') or 0)))


def register(conn, workspace_id, actor_id, command, text):
    """Admin-reviewed metadata; text is taken only from freshly proven source, not the request."""
    if (sha256(text.encode()).hexdigest() != command.chunk_hash or command.statement not in text
            or command.value not in command.statement):
        raise AccessDenied()
    existing = conn.execute('''SELECT * FROM knowledge_assertion WHERE workspace_id=%s AND chain=%s AND
      source_id=%s AND version=%s AND chunk_hash=%s AND locator=%s AND topic=%s AND conditions=%s''',
      (workspace_id, command.chain, command.source_id, command.version, command.chunk_hash,
       command.locator, command.topic, command.conditions)).fetchone()
    if existing:
        if any(existing[field] != getattr(command, field) for field in
               ('statement', 'value', 'unit', 'authority', 'classification', 'effective_from',
                'effective_until', 'project_id', 'product_id', 'customer_id')):
            raise ApiError(409, 'KNOWLEDGE_ASSERTION_EXISTS', '来源版本已有不同登记')
        return str(existing['id'])
    identifier = uuid4()
    conn.execute('''INSERT INTO knowledge_assertion(id,workspace_id,chain,source_id,document_id,version,chunk_hash,
      locator,page,ordinal,authority,classification,project_id,product_id,customer_id,effective_from,effective_until,
      topic,statement,value,unit,conditions,recorded_by)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
      (identifier, workspace_id, command.chain, command.source_id, command.document_id,
       command.version, command.chunk_hash, command.locator, command.page, command.ordinal,
       command.authority, command.classification, command.project_id, command.product_id,
       command.customer_id, command.effective_from, command.effective_until, command.topic,
       command.statement, command.value, command.unit, command.conditions, actor_id))
    # Record conflicting exact versions and values; do not suppress the lower-ranked side.
    counterparts = conn.execute('''SELECT id FROM knowledge_assertion WHERE workspace_id=%s AND id<>%s
      AND project_id=%s AND topic=%s AND unit=%s AND conditions=%s
      AND (product_id IS NULL OR %s::text IS NULL OR product_id=%s)
      AND (customer_id IS NULL OR %s::text IS NULL OR customer_id=%s)
      AND (value<>%s OR version<>%s) LIMIT 101''',
      (workspace_id, identifier, command.project_id, command.topic, command.unit, command.conditions,
       command.product_id, command.product_id, command.customer_id, command.customer_id,
       command.value, command.version)).fetchall()
    if len(counterparts) > 100:
        raise ApiError(409, 'KNOWLEDGE_CONFLICT_LIMIT', '主题冲突过多，请缩小登记范围')
    for other in counterparts:
        left, right = sorted((identifier, other['id']))
        conn.execute('''INSERT INTO knowledge_conflict(id,workspace_id,left_id,right_id)
          VALUES (%s,%s,%s,%s) ON CONFLICT (workspace_id,left_id,right_id) DO NOTHING''',
          (uuid4(), workspace_id, left, right))
    return str(identifier)


def side(conn, settings, subject, workspace_id, anchor, context, row, proof):
    """Proof is a freshly gateway-verified set from outside the DB transaction."""
    text = current_source(conn, settings, subject, workspace_id, anchor, context, row)
    if row['chain'] == 'enterprise' and applicable(row, anchor) and row['classification'] <= context.classification:
        text = proof.get(str(row['id']))
    if text is None or row['statement'] not in text:
        return {'state': 'forbidden'}  # indistinguishable from stale, including no title or locator
    return {'state': 'current', 'id': str(row['id']), 'chain': row['chain'],
            'source_id': row['source_id'], 'version': row['version'], 'chunk_hash': row['chunk_hash'],
            'locator': row['locator'], 'statement': row['statement'], 'value': row['value'],
            'unit': row['unit'], 'conditions': row['conditions'], 'authority': row['authority'],
            'authority_label': AUTHORITY[row['authority']-1],
            'effective_until': row['effective_until'].isoformat() if row['effective_until'] else None}


def enterprise_proofs(settings, subject, workspace_id, anchor, context, rows, context_version):
    result = {}
    for row in rows:
        if row['chain'] == 'enterprise' and applicable(row, anchor) and row['classification'] <= context.classification:
            text = verify_source(settings, subject, workspace_id, anchor, context, row, context_version)
            if text is not None:
                result[str(row['id'])] = text
    return result
