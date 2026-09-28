"""Deferred security checks for the controlled claim/citation surface."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / 'edw-api/src/edw_api/documents/claim_routes.py'
DOMAIN = ROOT / 'edw-api/src/edw_api/documents/editor_domain.py'
EDITOR = ROOT / 'edw-web/src/features/templates/DomainEditor.tsx'


def test_citation_bookmark_and_current_proof_guards_present():
    text = ROUTES.read_text(encoding='utf-8')
    assert 'command.base_version_id, command.revision, edit=True' in text
    assert 'command.selected_text' in text and 'original[command.start_offset:command.end_offset]' in text
    assert 'local_source(conn' in text and 'verify_source(settings' in text
    assert "command.quoted_text not in text" in text
    assert 'save_document(conn' in text and 'controlled_citation=True' in text
    assert 'row[\'actor_id\']' in text and 'row[\'subject\']' in text
    assert 'source_proof(settings' in text and "setTrace(null)" in (ROOT / 'edw-web/src/features/knowledge/ClaimPanel.tsx').read_text(encoding='utf-8')


def test_client_binding_and_stale_selection_guards_present():
    assert 'controlled_citation=False' in DOMAIN.read_text(encoding='utf-8')
    text = EDITOR.read_text(encoding='utf-8')
    assert 'from.parent!==to.parent' in text and 'from.parentOffset' in text
    assert 'setBookmark(null)' in text and 'setCanvasGeneration(n=>n+1)' in text
    assert 'insertCite' in text and 'base_version_id:baseRef.current.version_id' in text
