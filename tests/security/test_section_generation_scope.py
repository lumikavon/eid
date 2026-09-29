"""Source-backed section operations fail closed on changed scope and policy."""
from uuid import uuid4

import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.sections import pinned


class Connection:
    def __init__(self, policy):
        self.policy = policy


def test_changed_outline_rejected(monkeypatch):
    from edw_api.model_gateway import sections
    monkeypatch.setattr(sections, 'current_document', lambda *args: type('Auth', (), {'policy_epoch': (1, 1, 1), 'actor_id': str(uuid4())})())
    monkeypatch.setattr(sections, 'read_outline', lambda *args: {'version_id': uuid4(), 'context_version_id': uuid4(),
        'snapshot': {'sections': []}})
    job = {'subject': 'actor', 'workspace_id': uuid4(), 'document_id': uuid4(),
           'document_version_id': uuid4(), 'document_revision': 1, 'outline_version_id': uuid4(),
           'context_version_id': uuid4(), 'policy_epoch': [1, 1, 1], 'actor_id': uuid4()}
    with pytest.raises(ApiError, match='SECTION_SCOPE_CHANGED'):
        pinned(Connection(None), job)
