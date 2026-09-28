"""Current-ACL claim binding and selection-pinned citation commands."""
from contextlib import contextmanager
from uuid import UUID, uuid4
from types import SimpleNamespace

import psycopg
from fastapi import APIRouter, Depends, Response, Request
from pydantic import BaseModel, ConfigDict, Field

from ..access.policy import AccessDenied
from ..access.repository import checked
from ..auth import bearer_token
from ..db import connection
from ..errors import ApiError
from ..knowledge.gateway import verify_source
from ..knowledge.governance import decorate, local_source
from ..knowledge.evidence import pinned
from .claims import classify
from .editor_repository import editable_document, save_document
from .repository import _document_row
from .schemas import DomainAst


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Declare(Strict):
    base_version_id: UUID
    revision: int = Field(ge=1)
    section_id: UUID
    block_id: UUID
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    claim_type: str = Field(min_length=1, max_length=80)
    conditions: str = Field(default='', max_length=512)
    value: str = Field(min_length=1, max_length=256)
    unit: str = Field(default='', max_length=64)
    critical: bool = True


class Bind(Strict):
    base_version_id: UUID
    revision: int = Field(ge=1)
    pack_id: UUID
    item_ordinal: int = Field(ge=1, le=30)
    relation: str = Field(pattern='^(supports|conflicts|contextual)$')
    quoted_text: str = Field(min_length=1, max_length=4000)


class Cite(Strict):
    base_version_id: UUID
    revision: int = Field(ge=1)
    claim_id: UUID
    link_id: UUID
    section_id: UUID
    block_id: UUID
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    selected_text: str = Field(min_length=1, max_length=4000)
    quoted_text: str = Field(min_length=1, max_length=4000)


def changed():
    raise ApiError(409, 'CITATION_RESELECT', '选区、版本或来源已变化；请重新选择正文')


def head(conn, subject, workspace_id, document_id, version, revision, *, edit=False):
    if edit:
        editable_document(conn, subject, workspace_id, document_id, exclusive=True)
    else:
        _, resource, _ = checked(conn, subject, workspace_id, 'resource:read', document_id)
        if resource['kind'] != 'document':
            raise AccessDenied()
    doc = conn.execute('SELECT head_version_id,revision FROM document WHERE id=%s AND workspace_id=%s FOR UPDATE' if edit else
                       'SELECT head_version_id,revision FROM document WHERE id=%s AND workspace_id=%s FOR SHARE',
                       (document_id, workspace_id)).fetchone()
    if not doc or doc['head_version_id'] != version or doc['revision'] != revision:
        changed()
    return doc


def block_at(ast, section_id, block_id):
    section = next((s for s in ast['document']['sections'] if s['id'] == str(section_id)), None)
    block = next((b for b in section['blocks'] if b['id'] == str(block_id)), None) if section else None
    if not block or block['type'] not in ('paragraph', 'heading', 'warning', 'code'):
        changed()
    return block


def source_proof(settings, subject, workspace_id, document_id, pack_id, ordinal):
    # No gateway request under a write transaction. This first phase grants nothing by itself.
    with connection(settings) as conn:
        _, resource, _ = checked(conn, subject, workspace_id, 'resource:read', document_id)
        row = conn.execute('''SELECT p.document_version_id,p.context_version_id,p.outline_version_id,p.section_id,j.document_revision,
            i.*,p.id AS evidence_pack_id,j.actor_id,j.subject FROM section_evidence_pack p
            JOIN section_evidence_job j ON j.id=p.job_id
            JOIN section_evidence_item i ON i.pack_id=p.id
            WHERE p.id=%s AND p.workspace_id=%s AND p.document_id=%s AND i.ordinal=%s''',
            (pack_id, workspace_id, document_id, ordinal)).fetchone()
        if not row:
            raise ApiError(404, 'EVIDENCE_NOT_FOUND', '来源不可访问')
        _, _, anchor, context, state = pinned(conn, subject, workspace_id, document_id,
            row['section_id'], row['outline_version_id'], row['context_version_id'], row['document_version_id'])
        if str(row['actor_id']) != context.actor_id or row['subject'] != subject:
            raise AccessDenied()
        if state['head_version_id'] != row['document_version_id'] or state['revision'] != row['document_revision']:
            changed()
        source_row = conn.execute('SELECT * FROM section_evidence_item WHERE pack_id=%s AND ordinal=%s',
                                  (pack_id, ordinal)).fetchone()
        if not source_row:
            changed()
        source = dict(source_row)
        # Pack content has the verified classification and locator metadata required by the gateway.
        from ..task_contract import canonical
        from hashlib import sha256
        pack = conn.execute('SELECT content,content_hash FROM section_evidence_pack WHERE id=%s', (pack_id,)).fetchone()
        if not pack or sha256(canonical(pack['content'])).hexdigest() != pack['content_hash']:
            raise ApiError(503, 'EVIDENCE_INTEGRITY', '来源完整性不可用')
        items = pack['content'].get('items', [])
        if ordinal > len(items) or not isinstance(items[ordinal-1], dict):
            changed()
        item = items[ordinal-1]
        if any(item.get(k) != source[k] for k in ('chain','source_id','version','chunk_hash','locator')) or item.get('excerpt') != source['excerpt']:
            changed()
        anchor = dict(anchor)
    proof = verify_source(settings, subject, workspace_id, anchor, context, item, row['context_version_id']) if item['chain'] == 'enterprise' else None
    return row, item, proof


def live(conn, subject, workspace_id, document_id, row, item, proof):
    _, _, anchor, context, state = pinned(conn, subject, workspace_id, document_id,
        row['section_id'], row['outline_version_id'], row['context_version_id'], row['document_version_id'])
    if state['head_version_id'] != row['document_version_id'] or state['revision'] != row['document_revision']:
        changed()
    if item['chain'] == 'attachment':
        try:
            text = local_source(conn, workspace_id, anchor, item['source_id'], item['version'], item['chunk_hash'],
                                item['locator'], item['classification'], item['page'], item['ordinal'], subject)
        except AccessDenied:
            changed()
    else:
        if context.classification < item['classification'] or proof is None:
            changed()
        text = proof
    if text != item['excerpt'] or not decorate(conn, anchor, [dict(item)], workspace_id):
        changed()
    return text


def create_router(settings, verify):
    router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/documents/{document_id}')

    def actor(token: str = Depends(bearer_token)):
        return verify(token)

    @contextmanager
    def database():
        try:
            with connection(settings) as conn:
                yield conn
        except AccessDenied as exc:
            raise ApiError(404, 'CLAIM_NOT_FOUND', 'Claim 或来源不可访问') from exc
        except psycopg.Error as exc:
            raise ApiError(503, 'CLAIM_UNAVAILABLE', 'Claim 暂不可用', retryable=True) from exc

    @router.get('/claims')
    def claims(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            facts, resource, _ = checked(conn, current.subject, workspace_id, 'resource:read', document_id)
            if resource['kind'] != 'document':
                raise AccessDenied()
            _document_row(conn, facts, workspace_id, document_id)
            version = conn.execute('SELECT head_version_id,revision FROM document WHERE id=%s AND workspace_id=%s',
                                   (document_id, workspace_id)).fetchone()
            if not version:
                raise AccessDenied()
            rows = conn.execute('SELECT * FROM document_claim WHERE workspace_id=%s AND document_id=%s AND document_version_id=%s ORDER BY section_id,block_id,start_offset LIMIT 2048',
                                (workspace_id, document_id, version['head_version_id'])).fetchall()
            # Excerpts are never returned from historical links here; a selected link must be reattested.
            items = [dict(r) for r in rows]
            # A persisted positive verdict is historical until its exact source is reattested.
            # The selected Claim trace performs that live check; list reads cannot certify it.
            for item in items:
                if item['status'] in ('supported', 'partially_supported'):
                    item['recorded_status'] = item['status']
                    item['status'] = 'unknown'
                    item['needs_review'] = True
            return {'data': {'version_id': version['head_version_id'], 'revision': version['revision'], 'items': items}}

    @router.post('/claims/extract')
    def extract(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            facts, _ = editable_document(conn, current.subject, workspace_id, document_id, exclusive=True)
            from .claims import extract_claims
            doc = _document_row(conn, facts, workspace_id, document_id)
            extract_claims(conn, workspace_id, document_id, doc['version_id'], doc['ast'])
            return {'data': {'version_id': doc['version_id']}}

    @router.post('/claims')
    def declare(workspace_id: UUID, document_id: UUID, command: Declare, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            head(conn, current.subject, workspace_id, document_id, command.base_version_id, command.revision, edit=True)
            facts, _ = editable_document(conn, current.subject, workspace_id, document_id)
            ast = _document_row(conn, facts, workspace_id, document_id)['ast']
            text = block_at(ast, command.section_id, command.block_id)['content']['text']
            if command.end_offset > len(text) or command.start_offset >= command.end_offset:
                changed()
            statement = text[command.start_offset:command.end_offset]
            if command.value not in statement:
                raise ApiError(422, 'CLAIM_VALUE_MISMATCH', '声明值须出现在所选陈述中')
            identifier = uuid4()
            row = conn.execute('''INSERT INTO document_claim(id,workspace_id,document_id,document_version_id,section_id,block_id,
                start_offset,end_offset,statement,claim_type,conditions,value,unit,critical,status,needs_review)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'unsupported',true)
                ON CONFLICT (document_version_id,block_id,start_offset,end_offset,claim_type) DO NOTHING RETURNING id''',
                (identifier, workspace_id, document_id, command.base_version_id, command.section_id, command.block_id,
                 command.start_offset, command.end_offset, statement, command.claim_type, command.conditions,
                 command.value, command.unit, command.critical)).fetchone()
            if not row:
                changed()
            return {'data': {'id': identifier, 'status': 'unsupported', 'needs_review': True}}

    @router.post('/claims/{claim_id}/links')
    def bind(workspace_id: UUID, document_id: UUID, claim_id: UUID, command: Bind, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        row, item, proof = source_proof(settings, current.subject, workspace_id, document_id, command.pack_id, command.item_ordinal)
        with database() as conn:
            head(conn, current.subject, workspace_id, document_id, command.base_version_id, command.revision, edit=True)
            claim = conn.execute('SELECT * FROM document_claim WHERE id=%s AND workspace_id=%s AND document_id=%s AND document_version_id=%s',
                                 (claim_id, workspace_id, document_id, command.base_version_id)).fetchone()
            if not claim or claim['section_id'] != row['section_id']:
                changed()
            text = live(conn, current.subject, workspace_id, document_id, row, item, proof)
            if (command.quoted_text not in text
                    or command.relation == 'supports' and claim['value'] not in command.quoted_text
                    or command.relation == 'conflicts' and
                       (len(command.quoted_text) < 3 or claim['value'] in command.quoted_text or
                        claim['conditions'] and claim['conditions'] not in command.quoted_text)):
                changed()
            existing = conn.execute('''SELECT relation,quoted_text FROM claim_evidence_link
                WHERE workspace_id=%s AND claim_id=%s AND pack_id=%s AND item_ordinal=%s''',
                (workspace_id, claim_id, command.pack_id, command.item_ordinal)).fetchone()
            if existing and (existing['relation'] != command.relation or existing['quoted_text'] != command.quoted_text):
                changed()
            identifier = uuid4()
            conn.execute('''INSERT INTO claim_evidence_link(id,workspace_id,claim_id,pack_id,item_ordinal,relation,chain,source_id,
                source_version,chunk_hash,locator,quoted_text) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (workspace_id,claim_id,pack_id,item_ordinal) DO NOTHING''',
                (identifier, workspace_id, claim_id, command.pack_id, command.item_ordinal, command.relation,
                 item['chain'], item['source_id'], item['version'], item['chunk_hash'], item['locator'], command.quoted_text))
            # Do not infer current support from historical, potentially revoked links.
            conflicts = conn.execute("SELECT 1 FROM claim_evidence_link WHERE workspace_id=%s AND claim_id=%s AND relation='conflicts' LIMIT 1",
                                     (workspace_id, claim_id)).fetchone()
            status = classify(claim, [{'relation': command.relation, 'quoted_text': command.quoted_text}]
                              + ([{'relation': 'conflicts', 'quoted_text': ''}] if conflicts else []))
            if status == 'supported' and any(g.get('conflict_id') for g in item.get('governance', [])):
                status = 'conflicting'
            # Exact text agreement is not human factual adjudication; keep review pending.
            conn.execute('UPDATE document_claim SET status=%s,needs_review=true WHERE id=%s',
                         (status, claim_id))
            for governance in item.get('governance', []):
                if governance.get('conflict_id'):
                    conn.execute("INSERT INTO knowledge_dependency(workspace_id,conflict_id,kind,dependent_id,needs_review) VALUES (%s,%s,'claim',%s,true) ON CONFLICT DO NOTHING",
                                 (workspace_id, UUID(governance['conflict_id']), claim_id))
            return {'data': {'status': status, 'needs_review': True}}

    @router.get('/claims/{claim_id}/trace')
    def trace(workspace_id: UUID, document_id: UUID, claim_id: UUID, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as conn:
            facts, resource, _ = checked(conn, current.subject, workspace_id, 'resource:read', document_id)
            if resource['kind'] != 'document':
                raise AccessDenied()
            _document_row(conn, facts, workspace_id, document_id)
            claim = conn.execute('''SELECT c.* FROM document_claim c JOIN document d
                ON d.id=c.document_id AND d.workspace_id=c.workspace_id AND d.head_version_id=c.document_version_id
                WHERE c.id=%s AND c.workspace_id=%s AND c.document_id=%s''',
                (claim_id, workspace_id, document_id)).fetchone()
            if not claim:
                raise AccessDenied()
            links = conn.execute('SELECT * FROM claim_evidence_link WHERE claim_id=%s AND workspace_id=%s ORDER BY created_at,id LIMIT 30',
                                 (claim_id, workspace_id)).fetchall()
        output = []
        for link in links:
            try:
                row, item, proof = source_proof(settings, current.subject, workspace_id, document_id,
                                                link['pack_id'], link['item_ordinal'])
                with database() as conn:
                    head(conn, current.subject, workspace_id, document_id, claim['document_version_id'],
                         conn.execute('SELECT revision FROM document WHERE id=%s AND workspace_id=%s',
                                      (document_id, workspace_id)).fetchone()['revision'])
                    text = live(conn, current.subject, workspace_id, document_id, row, item, proof)
                    if (link['source_version'] != item['version'] or link['chunk_hash'] != item['chunk_hash']
                            or link['locator'] != item['locator'] or link['quoted_text'] not in text):
                        continue
                    output.append({'id': link['id'], 'relation': link['relation'], 'quoted_text': link['quoted_text'],
                                   'source_id': item['source_id'], 'version': item['version'],
                                   'locator': item['locator'], 'chunk_hash': item['chunk_hash']})
            except (AccessDenied, ApiError):
                continue
        return {'data': {'claim_id': claim_id, 'links': output, 'state': 'current' if output else 'unavailable'}}

    @router.post('/citations')
    def cite(workspace_id: UUID, document_id: UUID, command: Cite, request: Request, response: Response, current=Depends(actor)):
        response.headers['Cache-Control'] = 'no-store'
        # Link identity, Pack version and source are rechecked; no client-provided source grants access.
        with database() as conn:
            link = conn.execute('''SELECT l.*,c.document_version_id,c.section_id AS claim_section,c.block_id AS claim_block,
                c.start_offset AS claim_start,c.end_offset AS claim_end FROM claim_evidence_link l
                JOIN document_claim c ON c.id=l.claim_id AND c.workspace_id=l.workspace_id
                WHERE l.id=%s AND l.claim_id=%s AND l.workspace_id=%s AND c.document_id=%s''',
                (command.link_id, command.claim_id, workspace_id, document_id)).fetchone()
            if not link or link['relation'] != 'supports' or link['document_version_id'] != command.base_version_id:
                changed()
        row, item, proof = source_proof(settings, current.subject, workspace_id, document_id, link['pack_id'], link['item_ordinal'])
        with database() as conn:
            head(conn, current.subject, workspace_id, document_id, command.base_version_id, command.revision, edit=True)
            text = live(conn, current.subject, workspace_id, document_id, row, item, proof)
            claim = conn.execute('''SELECT value,conditions,statement FROM document_claim
                WHERE id=%s AND workspace_id=%s AND document_id=%s AND document_version_id=%s''',
                (command.claim_id, workspace_id, document_id, command.base_version_id)).fetchone()
            if (not claim or command.quoted_text != link['quoted_text'] or command.quoted_text not in text
                    or claim['value'] not in command.quoted_text
                    or claim['conditions'] and claim['conditions'] not in command.quoted_text
                    or command.section_id != link['claim_section'] or command.block_id != link['claim_block']
                    or command.start_offset > link['claim_start'] or command.end_offset < link['claim_end']):
                changed()
            previous = conn.execute('SELECT ast FROM document_version WHERE id=%s AND document_id=%s',
                                    (command.base_version_id, document_id)).fetchone()
            if not previous:
                changed()
            ast = previous['ast']
            block = block_at(ast, command.section_id, command.block_id)
            original = block['content']['text']
            if (command.end_offset > len(original) or command.start_offset >= command.end_offset
                    or original[command.start_offset:command.end_offset] != command.selected_text):
                changed()
            citation_id = uuid4()
            marker = f'〔引:{citation_id}〕'
            content = block['content']
            offset = command.end_offset
            if 'runs' in content:
                if ''.join(run['text'] for run in content['runs']) != original:
                    changed()
                runs = []
                for run in content['runs']:
                    part = run['text']
                    if 0 <= offset <= len(part):
                        runs.extend([{**run, 'text': part[:offset]}, {'text': marker, 'marks': []},
                                     {**run, 'text': part[offset:]}])
                        offset = -1
                    else:
                        runs.append(run)
                        offset -= len(part)
                if offset != -1:
                    changed()
                content['runs'] = runs
            content['text'] = original[:command.end_offset] + marker + original[command.end_offset:]
            ast['document']['citations'].append({'id': str(citation_id), 'claim_id': str(command.claim_id),
                'link_id': str(command.link_id), 'section_id': str(command.section_id), 'block_id': str(command.block_id),
                'start_offset': command.start_offset, 'end_offset': command.end_offset,
                'marker': marker, 'needs_review': True})
            saved = save_document(conn, current.subject, workspace_id, document_id,
                                  SimpleNamespace(base_version_id=command.base_version_id,
                                                  revision=command.revision,
                                                  ast=DomainAst.model_validate(ast)),
                                  request.state.request_id, request.state.trace_id, controlled_citation=True)
            conn.execute('''INSERT INTO document_citation(id,workspace_id,document_id,document_version_id,claim_id,link_id,
                section_id,block_id,start_offset,end_offset,selected_text,quoted_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (citation_id, workspace_id, document_id, saved['version_id'], command.claim_id, command.link_id,
                 command.section_id, command.block_id, command.start_offset, command.end_offset,
                 command.selected_text, command.quoted_text))
            return {'data': saved}

    return router
