"""Governance contract shape only; no running tests in this story."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_contract_forbidden_side_has_no_protected_fields():
    contract = json.loads((ROOT / 'contracts/source-governance-v1.schema.json').read_text())
    forbidden = contract['$defs']['side']['oneOf'][0]
    assert forbidden['additionalProperties'] is False
    assert forbidden['properties'] == {'state': {'const': 'forbidden'}}


def test_migration_version_keys_and_immutable_history():
    migration = (ROOT / 'migrations/versions/0018_source_governance.py').read_text()
    assert 'down_revision = \'0017_authorized_retrieval\'' in migration
    assert 'UNIQUE(workspace_id,conflict_id,revision)' in migration
    assert 'GRANT SELECT,INSERT ON knowledge_disposition TO eid_api' in migration
    assert 'FOREIGN KEY(workspace_id,left_id)' in migration
    assert 'FOREIGN KEY(workspace_id,right_id)' in migration
