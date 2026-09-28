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

def test_signed_search_cannot_bypass_denied_current_acl(monkeypatch):
    import hashlib
    import hmac
    from datetime import datetime, timedelta, timezone
    from edw_api.knowledge import gateway
    key = 'k' * 32
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat()
    source = {'source_id': 'e-1', 'version': 'v1', 'chunk_hash': hashlib.sha256(b'proof').hexdigest(),
              'locator': 'section:1', 'excerpt': 'proof', 'classification': 0, 'project_id': 'p',
              'valid_until': expiry, 'category': 'enterprise'}
    calls = []

    class Reply:
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    class Client:
        def __init__(self, **_kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def post(self, url, json):
            request = json['body']
            operation = request['operation']
            calls.append(operation)
            binding = {field: request[field] for field in ('subject', 'workspace_id', 'actor_id',
                       'policy_epoch', 'project_id', 'classification', 'context_document_id', 'context_version_id')}
            body = {'nonce': request['nonce'], 'operation': operation, 'expires_at': expiry, 'binding': binding}
            if operation == 'capabilities':
                body['features'] = {'acl_prefilter': True, 'current_acl_verify': True,
                    'exact_locator': True, 'source_version': True, 'expiry': True, 'keyword': True}
            elif operation == 'search':
                body.update(query_sha256=hashlib.sha256(request['query'].encode()).hexdigest(),
                            items=[source])
            else:
                body.update(sources=request['sources'], authorized=False, current=True)
            signature = hmac.new(key.encode(), gateway.canonical(body), hashlib.sha256).hexdigest()
            return Reply({'body': body, 'signature': signature})

    monkeypatch.setattr(gateway.httpx, 'Client', Client)
    context = SimpleNamespace(actor_id='actor', policy_epoch=(1, 1, 1), classification=0)
    anchor = {'id': 'doc', 'project_id': 'p'}
    hits, usable = retrieve(SimpleNamespace(knowledge_gateway_url='https://gateway.invalid',
                                           knowledge_gateway_key=key), 'subject', 'workspace', anchor,
                            context, 'proof', 'all', 10)
    assert calls == ['capabilities', 'search', 'verify']
    assert hits == [] and usable is False
