"""A citation advanced the head: the old Pack remains provenance, not authorization."""
from contextlib import contextmanager
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

from edw_api.documents import claim_routes
from edw_api.task_contract import canonical


def test_historical_link_traces_against_current_scope(monkeypatch):
    import edw_api.db as db

    document, workspace, pack_id = uuid4(), uuid4(), uuid4()
    item = {'chain': 'attachment', 'source_id': str(uuid4()), 'version': 'a' * 64,
            'chunk_hash': sha256(b'proof').hexdigest(), 'locator': 'page:1:char:0',
            'classification': 1, 'page': 1, 'ordinal': 1, 'excerpt': 'proof'}
    row = {'document_version_id': uuid4(), 'document_revision': 1, 'section_id': uuid4(),
           'outline_version_id': uuid4(), 'context_version_id': uuid4(),
           'actor_id': uuid4(), 'subject': 'user'}
    state = {'head_version_id': uuid4(), 'revision': 2, 'context_version': uuid4()}
    context = SimpleNamespace(actor_id=str(row['actor_id']), policy_epoch=(1, 2, 3), classification=2)

    class Conn:
        def execute(self, sql, _params):
            self.sql = sql
            return self
        def fetchone(self):
            if 'p.document_version_id' in self.sql:
                return row
            if 'SELECT * FROM section_evidence_item' in self.sql:
                return item
            if 'content,content_hash' in self.sql:
                content = {'items': [item]}
                return {'content': content, 'content_hash': sha256(canonical(content)).hexdigest()}
            raise AssertionError(self.sql)

    @contextmanager
    def connection(_settings):
        yield Conn()

    monkeypatch.setattr(claim_routes, 'connection', connection)
    monkeypatch.setattr(claim_routes, 'checked', lambda *_: (None, {'kind': 'document'}, context))
    monkeypatch.setattr(claim_routes, 'scope', lambda *_: ({'project_id': 'p'}, context, state))
    monkeypatch.setattr(claim_routes, 'pinned', lambda *_: (_ for _ in ()).throw(AssertionError('old head')))
    proof_row, proof_item, proof = claim_routes.source_proof(None, 'user', workspace, document,
                                                                pack_id, 1, historical=True)
    assert proof is None
    monkeypatch.setattr(claim_routes, 'local_source', lambda *_: 'proof')
    monkeypatch.setattr(claim_routes, 'decorate', lambda _conn, _anchor, hits, _workspace: hits)
    assert claim_routes.live(Conn(), 'user', workspace, document, proof_row, proof_item,
                             proof, historical=True) == 'proof'
    context.policy_epoch = (2, 2, 3)
    from edw_api.errors import ApiError
    import pytest
    with pytest.raises(ApiError):
        claim_routes.live(Conn(), 'user', workspace, document, proof_row, proof_item,
                          proof, historical=True)

def test_historical_citation_rejects_changed_statement_or_support():
    claim = {'statement': '容量 20 GB', 'value': '20', 'conditions': 'A'}
    link = {'citation_selected_text': '容量 20 GB', 'quoted_text': 'A 容量 20 GB'}
    assert claim_routes.citation_matches_claim(claim, link)
    assert not claim_routes.citation_matches_claim({**claim, 'statement': '容量 30 GB'}, link)
    assert not claim_routes.citation_matches_claim(claim, {**link, 'quoted_text': 'A 容量 30 GB'})
