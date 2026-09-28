"""Static source checks; runtime ACL/enterprise tests remain not-run by policy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_nine_levels_are_not_clearance():
    source = (ROOT / 'edw-api/src/edw_api/knowledge/governance.py').read_text()
    migration = (ROOT / 'migrations/versions/0018_source_governance.py').read_text()
    assert "'llm_general'" in source
    assert "authority BETWEEN 1 AND 8" in migration
    assert 'classification BETWEEN 0 AND 3' in migration
    assert "checked(conn, subject, workspace_id, 'resource:read'" in source


def test_recheck_and_forbidden_side():
    source = (ROOT / 'edw-api/src/edw_api/knowledge/governance_routes.py').read_text()
    assert 'unchanged(initial, fresh)' in source
    assert "'knowledge:manage'" in source
    assert "any(x['state'] != 'current' for x in visible)" in source
    assert 'expected_revision != conflict' in source
    assert 'needs_review=true' in source
    assert "{'state': 'forbidden'}" in (ROOT / 'edw-api/src/edw_api/knowledge/governance.py').read_text()


def test_enterprise_proof_cannot_reauthorize_history():
    source = (ROOT / 'edw-api/src/edw_api/knowledge/gateway.py').read_text()
    assert "exchange(client, url, key, 'inspect'" in source
    assert "reply.get('authorized') is not True" in source
    assert "reply.get('current_version') != source['version']" in source
    assert "hashlib.sha256(text.encode()).hexdigest() != source['chunk_hash']" in source
