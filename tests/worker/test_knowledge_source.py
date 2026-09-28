"""Index replay/model outage cases; suite not executed here."""
from edw_worker.knowledge import embedding


def test_unconfigured_embedding_is_not_a_fake_vector(monkeypatch):
    monkeypatch.delenv('EID_BGE_M3_ENDPOINT', raising=False)
    assert embedding('GB/T 12345-2024') is None


def test_indexing_only_uses_idempotent_database_function():
    from pathlib import Path
    source = Path('edw-worker/src/edw_worker/knowledge.py').read_text()
    assert 'eid_search_pending_v1(%s,%s)' in source
    assert 'eid_search_index_v1' in source
    assert 'logger.info(text)' not in source
