"""Source/SQL contract checks; not run under current acceptance boundary."""
from pathlib import Path


def test_index_only_from_canonical_chunks_and_fenced_versions():
    sql = Path('migrations/versions/0017_authorized_retrieval.py').read_text()
    assert 'FROM attachment_chunk' in sql
    assert 'p.source_sha256<>a.sha256' in sql
    assert 'session_user<>\'eid_worker\'' in sql
    assert 'REVOKE ALL ON attachment_search_index' in sql
    assert 'CREATE INDEX attachment_search_tokens' in sql
    assert 'vector_cosine_ops' in sql


def test_search_does_not_use_discovery_titles_or_upload_delegation():
    source = Path('edw-api/src/edw_api/knowledge/routes.py').read_text()
    assert 'checked(conn, subject' in source
    assert 'attachment_chunk' in source
    assert 'eid_attachment_allowed_v1' not in source
    assert 'discovery_record' not in source
    assert "'complete': False" in source
