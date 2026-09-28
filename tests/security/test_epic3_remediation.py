"""Delayed delegation and current-use source checks (never connect to a database)."""
from pathlib import Path

from hashlib import sha256
from types import SimpleNamespace

import pytest
from edw_api.access.policy import AccessDenied
from edw_api.documents.claims import classify
from edw_api.knowledge import governance

ROOT = Path(__file__).resolve().parents[2]


def test_multiple_claim_relations_are_conservative():
    claim = {'statement': '容量 20 GB', 'value': '20', 'conditions': '', 'critical': True}
    support = {'relation': 'supports', 'quoted_text': '容量 20 GB'}
    background = {'relation': 'contextual', 'quoted_text': '无关背景'}
    conflict = {'relation': 'conflicts', 'quoted_text': '容量 10 GB'}
    assert classify(claim, [support, background]) == 'supported'
    assert classify(claim, [support, conflict]) == 'conflicting'
    assert classify(claim, [background]) == 'unsupported'


def test_local_excerpt_rechecks_live_grant_and_pinned_version(monkeypatch):
    from uuid import uuid4
    doc = uuid4()
    content = '容量 20 GB'
    digest = sha256(content.encode()).hexdigest()
    version = 'a' * 64
    row = {'document_id': doc, 'sha256': version, 'source_sha256': version,
           'parse_sha256': version, 'parser_version': 'attachment-v1',
           'indexed_parser': 'attachment-v1', 'classification': 1,
           'content': content, 'content_hash': digest, 'locator': 'page:1:char:0', 'state': 'SUCCEEDED'}

    class Conn:
        def execute(self, _sql, _params):
            return self
        def fetchone(self):
            return row

    monkeypatch.setattr(governance, 'checked', lambda *_: (None,
                        {'kind': 'document', 'project_id': 'p'}, SimpleNamespace(classification=1)))
    args = (Conn(), uuid4(), {'project_id': 'p'}, str(uuid4()), version, digest,
            row['locator'], 1, 1, 1, 'actor')
    assert governance.local_source(*args) == content
    with pytest.raises(AccessDenied):
        governance.local_source(*args[:4], 'new-version', *args[5:])
    monkeypatch.setattr(governance, 'checked', lambda *_: (_ for _ in ()).throw(AccessDenied()))
    with pytest.raises(AccessDenied):
        governance.local_source(*args)


def test_forward_migration_does_not_trust_expired_delegation():
    sql = (ROOT / 'migrations/versions/0021_epic3_remediation.py').read_text()
    assert 'g.expires_at>clock_timestamp()' not in sql
    assert 'g.issued_epoch=f.workspace_epoch' not in sql
    assert 'f.identity_active AND f.membership_active' in sql
    assert "g.service_id='eid-worker' AND g.active" in sql
    assert 'r.classification<=f.clearance' in sql
    assert "p.state='BLOCKED'" in sql
    assert 'eid_attachment_allowed_v1(p.attachment_id)' in sql
    assert "'bucket',a.storage_bucket" in sql
    assert "DEFAULT 'eid-local-artifacts'" in sql


def test_quarantine_is_bucket_isolated():
    import json
    identities = json.loads((ROOT / 'deployment/seaweedfs/s3.json').read_text())['identities']
    cleaner = next(item for item in identities if item['name'] == 'eid-s3-cleaner')
    assert cleaner['actions'] == ['Read:eid-local-attachment-quarantine',
                                  'Write:eid-local-attachment-quarantine']
    assert 'eid-local-artifacts' not in str(cleaner['actions'])
