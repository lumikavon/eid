"""Security boundaries for candidate Packs; integration acceptance remains not-run."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_stale_and_revoked_sources_are_never_served_from_snapshot_only():
    code = (ROOT / 'edw-api/src/edw_api/knowledge/evidence.py').read_text()
    assert "def visible(settings, job):" in code
    assert 'verify_source(settings' in code
    assert 'local_source(conn' in code
    assert "decorated = decorate(conn, fresh_anchor, [dict(hit)]" in code
    assert "output.append({**decorated[0], 'ordinal': ordinal})" in code
    assert "'SOURCE_REVOKED_OR_CHANGED'" in code
    assert "k not in ('items', 'conflict_ids', 'version_conflicts', 'gaps')" in code


def test_attempts_are_fenced_and_never_log_passages():
    code = (ROOT / 'edw-api/src/edw_api/knowledge/evidence_routes.py').read_text()
    assert "attempt<3" in code
    assert "lease_until" in code
    assert "WHERE id=%s AND fence=%s" in code
    assert 'exc.__str__' not in code
    assert 'log.warning(\'evidence_build_retry error_type=%s\'' in code
