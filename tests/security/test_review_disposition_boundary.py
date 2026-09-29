"""静态确认处置入口不提供豁免、直写正文或无效重审关闭路径。"""
from pathlib import Path


def test_dispositions_are_immutable_and_api_only():
    migration = Path('migrations/versions/0028_review_dispositions.py').read_text(encoding='utf-8')
    assert 'BEFORE UPDATE OR DELETE ON review_disposition' in migration
    assert 'GRANT SELECT,INSERT ON review_disposition TO eid_api' in migration
    assert "action IN ('accept','reject','modify','handled')" in migration
    assert 'waive' not in migration


def test_authorized_patches_and_fresh_recheck_gate_closure():
    source = Path('edw-api/src/edw_api/review/routes.py').read_text(encoding='utf-8')
    assert "'document:review', document_id, exclusive=True" in source
    assert 'selected_patches(preliminary' in source
    assert 'persist_decision(conn, subject' in source
    assert 'editable_document(conn, subject' in source
    assert 'if any(same_defect(issue, peer) for peer in peers)' in source
    assert "'REVIEW_DEFECT_PERSISTS'" in source
    assert "'REVIEW_REASON_REQUIRED'" in source
    assert "'REVIEW_VERSION_CHANGED'" in source
    assert "recheck['document_revision'] <= row['document_revision']" in source
    assert 'waive' not in source


def test_ui_navigates_a_real_block_and_clears_stale_selection():
    review = Path('edw-web/src/features/templates/ReviewStatus.tsx').read_text(encoding='utf-8')
    editor = Path('edw-web/src/features/templates/DomainEditor.tsx').read_text(encoding='utf-8')
    assert 'onNavigateToBlock(body.data.section_id,body.data.block_id)' in review
    assert "setSelected('');setRun(null)" in review
    assert "section?.blocks.some(item=>item.id===blockId)" in editor
    assert 'node.attrs?.blockId===targetBlock' in editor
