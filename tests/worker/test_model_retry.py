"""Not run: static contract for fenced API-owned model recovery."""
from pathlib import Path


def test_api_only_commit_and_persisted_retry():
    source = Path('edw-api/src/edw_api/model_gateway/routes.py').read_text(encoding='utf-8')
    migration = Path('migrations/versions/0022_model_governance.py').read_text(encoding='utf-8')
    assert "else 'RETRY_WAIT'" in source and "r.state='RETRY_WAIT'" in migration
    assert 'attempt<3' in source and 'AND fence=%s' in source
    assert 'model_generation_run' in migration
    assert 'GRANT SELECT,INSERT ON model_generation_run TO eid_api' in migration
    assert 'GRANT SELECT,INSERT ON model_generation_run TO eid_worker' not in migration
    assert 'eid_model_pending_v1' in migration and 'dispatch_models()' in Path(
        'edw-worker/src/edw_worker/relay.py').read_text(encoding='utf-8')
    assert "state='RUNNING' AND attempt>=3 AND lease_until<clock_timestamp()" in source
    assert 'reserved_tokens integer NOT NULL' in migration
    assert 'policy_revision bigint NOT NULL' in migration
    assert "pointer['revision'] != row['policy_revision']" in source
    assert "or isinstance(exc, ApiError) and not exc.retryable else 'RETRY_WAIT'" in source


def test_final_commit_requires_current_document_and_audit():
    source = Path('edw-api/src/edw_api/model_gateway/routes.py').read_text(encoding='utf-8')
    assert source.index('current_document(conn, row') < source.index("'model:run:completed'")
    assert source.index("'model:run:completed'") < source.index("state='SUCCEEDED'")
