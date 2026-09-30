"""当前授权、版本隔离和未评估指标的静态边界。"""
from pathlib import Path


def test_history_and_issue_detail_recheck_current_access_and_pinned_run():
    source = Path('edw-api/src/edw_api/review/routes.py').read_text(encoding='utf-8')
    assert 'current(conn, current_actor.subject, workspace_id, document_id)' in source
    assert 'read_version(conn, subject, workspace_id, document_id, row[\'document_version_id\'])' in source
    assert "WHERE run_id=%s AND id=%s" in source
    assert 'source_safe(conn, workspace_id, anchor, subject, citations)' in source
    assert "'score': {'numerator': None, 'denominator': None" in source
    assert "'coverage': coverage_metric" in source


def test_ui_discards_cross_run_and_cross_filter_selection():
    source = Path('edw-web/src/features/templates/ReviewStatus.tsx').read_text(encoding='utf-8')
    assert "setSelected('');setRun(null)" in source
    assert "setSelected('');setFilters" in source
    assert "setOffset(0);setRunId" in source
    assert 'issues.find(item=>item.id===selected)' in source
    assert "setTab(value);setSelected('')" in source
