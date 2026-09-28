"""Section Pack deterministic invariants; runtime suites intentionally not run here."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_contract_limits_and_immutable_migration():
    schema = json.loads((ROOT / 'contracts/evidence-pack-v1.schema.json').read_text())
    assert schema['properties']['queries']['minItems'] == 3
    assert schema['properties']['queries']['maxItems'] == 10
    assert schema['properties']['items']['maxItems'] == 30
    assert schema['properties']['state']['const'] == 'insufficient'
    sql = (ROOT / 'migrations/versions/0019_section_evidence.py').read_text()
    assert 'UNIQUE(workspace_id,actor_id,request_key)' in sql
    assert 'GRANT SELECT,INSERT ON section_evidence_pack' in sql
    assert 'UPDATE(state,stage,attempt,fence' in sql
    assert 'UPDATE ON section_evidence_pack' not in sql


def test_retrieval_and_commit_are_separate_and_fenced():
    code = (ROOT / 'edw-api/src/edw_api/knowledge/evidence.py').read_text()
    assert "outline['state'] != 'OUTLINE_READY'" in code
    assert 'source_id' in code and "hit['version']" in code
    assert 'verify_source(settings' in code
    assert 'local_source(conn' in code
    assert 'FOR UPDATE' in code
    assert "'KEY_FACT_SUPPORT_NOT_VERIFIED'" in code
    assert 'knowledge_dependency' in code
    assert 'hashlib.sha256(canonical(payload))' in code
    assert 'fresh.policy_epoch != context.policy_epoch' in code


def test_budgeted_planner():
    from edw_api.knowledge.evidence import plan
    assert len(plan({'title': '容量'}, {'facts': [{'key': f'metric-{i}'} for i in range(40)]})) == 10
    assert len(plan({'title': '容量'}, {'facts': []})) == 3
    assert len(set(plan({'title': '容量'}, {'facts': []}))) == 3
