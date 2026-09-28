"""Gateway outage and absent capability examples; suite remains not-run."""
from types import SimpleNamespace

from edw_api.knowledge.gateway import retrieve


def test_no_trust_anchor_never_calls_gateway():
    hits, usable = retrieve(SimpleNamespace(knowledge_gateway_url='', knowledge_gateway_key=''),
                            'subject', '00000000-0000-0000-0000-000000000001',
                            {'id': '00000000-0000-0000-0000-000000000001', 'project_id': 'p'},
                            SimpleNamespace(actor_id='00000000-0000-0000-0000-000000000001',
                                            policy_epoch=(1, 1, 1), classification=0),
                            'GB/T 12345', 'all', 10)
    assert hits == [] and usable is False
