"""Section proposals are bounded by independently verified evidence."""
from uuid import uuid4

from edw_api.errors import ApiError
from edw_api.model_gateway.sections import _input, assemble, decode_section, supported_claims
from edw_api.task_contract import canonical
from hashlib import sha256


def test_missing_pack_blocks_generation():
    text, gaps = _input({'title': '范围'}, {'items': [], 'gaps': [], 'conflict_ids': [], 'version_conflicts': []})
    assert text is None and gaps == ['NO_CURRENT_SUPPORT']


def test_conflicting_sources_block_generation():
    text, gaps = _input({'title': '范围'}, {'items': [{'excerpt': '已核实'}], 'gaps': ['SOURCE_CONFLICT_REQUIRES_REVIEW'],
        'conflict_ids': ['conflict'], 'version_conflicts': []})
    assert text is None and 'SOURCE_CONFLICT_REQUIRES_REVIEW' in gaps


def test_unverified_output_cannot_claim_a_source():
    item = {'excerpt': '已核实事实', 'source_id': 'source', 'locator': 'page:1', 'version': 'v1'}
    assert supported_claims([{'text': '未核实推断', 'source_ref': 1}], [item]) == []
    assert supported_claims([{'text': '已核实事实', 'source_ref': 1}], [item])[0]['locator'] == 'page:1'


def test_structured_output_rejects_unrecognized_fields():
    try:
        decode_section('{"blocks":[{"text":"事实","source_ref":1,"execute":"shell"}]}')
    except ApiError as error:
        assert error.code == 'MODEL_OUTPUT_INVALID'
    else:
        raise AssertionError('Unrecognized model fields must fail closed')


def test_assembly_requires_every_section_and_preserves_order():
    first, second = uuid4(), uuid4()
    outline = {'snapshot': {'sections': [{'id': str(first)}, {'id': str(second)}]}}
    proposal = lambda section, source, version: {'section_id': str(section), 'claims': [{'source_id': source, 'version': version, 'locator': 'page:1', 'text': '事实'}]}
    a, b = proposal(first, 'source', 'v1'), proposal(second, 'source', 'v2')
    jobs = [{'section_id': second, 'state': 'SUCCEEDED', 'proposal': b, 'proposal_hash': sha256(canonical(b)).hexdigest()},
            {'section_id': first, 'state': 'SUCCEEDED', 'proposal': a, 'proposal_hash': sha256(canonical(a)).hexdigest()}]
    result = assemble(outline, jobs)
    assert result['sections'] == [a, b]
    assert result['conflicts'] == ['source']
    assert result['review_required'] is True
    jobs[0]['state'] = 'CANCELLED'
    try:
        assemble(outline, jobs)
    except ApiError as error:
        assert error.code == 'SECTION_ASSEMBLY_INCOMPLETE'
    else:
        raise AssertionError('Cancelled section must not assemble')
