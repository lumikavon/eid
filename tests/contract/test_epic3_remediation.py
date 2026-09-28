"""Deterministic policy/view regressions; no services are needed to run these later."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

from edw_api.access.policy import AccessDenied
from edw_api.knowledge import evidence, governance
from edw_api.task_contract import canonical


def test_applicability_rejects_expiry_and_wrong_scope():
    now = datetime.now(timezone.utc)
    anchor = {'project_id': 'p', 'product_id': 'q', 'customer_id': 'c'}
    row = {'effective_from': now - timedelta(days=1), 'effective_until': now + timedelta(minutes=1),
           'project_id': 'p', 'product_id': 'q', 'customer_id': None}
    assert governance.applicable(row, anchor, now)
    assert not governance.applicable(row, anchor, now + timedelta(minutes=2))
    assert not governance.applicable(row, {**anchor, 'product_id': 'other'}, now)


def test_visible_pack_keeps_original_ordinals_and_current_governance(monkeypatch):
    import edw_api.db as db
    from contextlib import contextmanager

    job = {key: uuid4() for key in ('workspace_id', 'document_id', 'section_id', 'outline_version_id',
                                    'context_version_id', 'document_version_id', 'id')}
    job['subject'] = 'actor'
    content = {'items': [dict(chain='attachment', source_id=str(uuid4()), version='v',
                              chunk_hash='h', locator='loc', classification=1, page=1,
                              ordinal=i, excerpt=f'protected {i}', governance=[{'authority': 8}], queries=['query'])
                         for i in (1, 2)], 'gaps': [], 'queries': ['a', 'b', 'c'], 'state': 'insufficient'}
    pack = {'id': uuid4(), 'content': content, 'content_hash': sha256(canonical(content)).hexdigest()}

    class Conn:
        def execute(self, query, params):
            assert 'section_evidence_pack' in query
            return self
        def fetchone(self):
            return pack

    @contextmanager
    def connection(_settings):
        yield Conn()

    monkeypatch.setattr(db, 'connection', connection)
    monkeypatch.setattr(evidence, 'pinned', lambda *_: (None, None, {'project_id': 'p'},
                        SimpleNamespace(policy_epoch=(1,), classification=2), None))

    def local(_conn, _workspace, _anchor, _source, _version, _hash, _locator, _class, _page, ordinal, _subject):
        if ordinal == 1:
            raise AccessDenied()
        return 'protected 2'

    monkeypatch.setattr(evidence, 'local_source', local)
    monkeypatch.setattr(evidence, 'decorate', lambda _conn, _anchor, hits, _workspace:
                        [{**hits[0], 'governance': [{'authority': 1}]}])
    view = evidence.visible(None, job)
    assert [hit['ordinal'] for hit in view['items']] == [2]
    assert view['items'][0]['governance'] == [{'authority': 1}]
    assert 'protected 1' not in str(view)
    assert view['snapshot_hash'] == pack['content_hash']
    assert view['view_hash'] != view['snapshot_hash']
    assert 'SOURCE_REVOKED_OR_CHANGED' in view['gaps']
