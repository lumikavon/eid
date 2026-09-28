"""Authorization boundary regression cases (suite deliberately not executed in this story)."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac

from edw_api.knowledge.gateway import canonical, signed
from edw_api.knowledge.routes import Search


def test_search_contract_rejects_unbounded_query_and_unknown_client_scope():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Search.model_validate({'query': 'x'*129, 'context_document_id': '00000000-0000-0000-0000-000000000001', 'workspace_id': 'spoof'})
    with pytest.raises(ValidationError):
        Search.model_validate({'query': 'MODEL\nSECRET', 'context_document_id': '00000000-0000-0000-0000-000000000001'})


def test_gateway_proof_rejects_tampering_expiry_and_nonce():
    key = 'key'*12
    body = {'nonce': 'nonce', 'operation': 'verify', 'expires_at': (datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat(), 'authorized': True}
    signature = hmac.new(key.encode(), canonical(body), sha256).hexdigest()
    assert signed({'body': body, 'signature': signature}, key, 'nonce', 'verify') == body
    assert signed({'body': body, 'signature': signature}, key, 'other', 'verify') is None
    assert signed({'body': {**body, 'authorized': False}, 'signature': signature}, key, 'nonce', 'verify') is None
    expired = {**body, 'expires_at': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    assert signed({'body': expired, 'signature': hmac.new(key.encode(), canonical(expired), sha256).hexdigest()}, key, 'nonce', 'verify') is None
