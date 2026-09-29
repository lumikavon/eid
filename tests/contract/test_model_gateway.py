"""Not run: model envelope, one repair, and no provider fallback contracts."""
import json as json_lib
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from edw_api.errors import ApiError
from edw_api.model_gateway.policy import Decision, PolicyDraft, PROMPT_HASH
from edw_api.model_gateway.transport import generate, endpoint_for


def policy():
    return PolicyDraft(provider='internal', model_id='approved-model', prompt_ref='generation-v1',
        prompt_sha256=PROMPT_HASH, capabilities=['structured_proposal'], max_classification=3,
        max_context_chars=1000, max_output_tokens=128, daily_token_budget=10000,
        max_cost_micros=5000, timeout_seconds=2, redact_rules=[])


def settings():
    return SimpleNamespace(model_internal_endpoint='https://models.example/generate',
        model_internal_key='local-secret', model_external_endpoint='', model_external_key='',
        model_external_approved_host='')


def test_missing_external_endpoint_never_falls_back():
    with pytest.raises(ApiError) as error:
        endpoint_for(settings(), 'external')
    assert error.value.code == 'MODEL_ROUTE_MISSING'


def test_external_endpoint_requires_server_approved_hostname():
    candidate = settings()
    candidate.model_external_endpoint = 'https://example.invalid/generate'
    candidate.model_external_key = 'secret'
    with pytest.raises(ApiError) as error:
        endpoint_for(candidate, 'external')
    assert error.value.code == 'MODEL_ROUTE_MISSING'


def test_repair_once_and_record_usage(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def stream(self, method, endpoint, headers, json):
            calls.append(json.copy())
            body = {'model':'approved-model', 'output':{} if len(calls)==1 else {'proposal':'draft'},
                    'usage':{'input_tokens':1,'output_tokens':2,'cost_micros':3}}
            content = json_lib.dumps(body).encode()
            response = MagicMock(status_code=200)
            response.iter_bytes.return_value = [content]
            response.__enter__.return_value = response
            return response
    monkeypatch.setattr(httpx, 'Client', Client)
    result, usage, repairs = generate(settings(), policy(), Decision('internal','safe','0'*64,0))
    assert result == {'proposal':'draft'} and usage['output_tokens'] == 2 and repairs == 1
    assert len(calls) == 2 and all('tools' not in call for call in calls)


def test_invalid_envelope_after_one_repair_records_repair_count(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def stream(self, *_args, **_kwargs):
            calls.append(1)
            response = MagicMock(status_code=200)
            response.iter_bytes.return_value = [json_lib.dumps({
                'model': 'approved-model', 'output': {},
                'usage': {'input_tokens': 1, 'output_tokens': 2, 'cost_micros': 3},
            }).encode()]
            response.__enter__.return_value = response
            return response
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(ApiError) as error:
        generate(settings(), policy(), Decision('internal', 'safe', '0'*64, 0))
    assert error.value.code == 'MODEL_OUTPUT_INVALID'
    assert error.value.details == {'repair_count': 1} and len(calls) == 2


def test_provider_cannot_report_input_usage_above_reserved_ceiling(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def stream(self, *_args, **_kwargs):
            response = MagicMock(status_code=200)
            response.iter_bytes.return_value = [json_lib.dumps({
                'model': 'approved-model', 'output': {'proposal': 'draft'},
                'usage': {'input_tokens': 2000, 'output_tokens': 2, 'cost_micros': 3},
            }).encode()]
            response.__enter__.return_value = response
            return response
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(ApiError) as error:
        generate(settings(), policy(), Decision('internal', 'safe', '0'*64, 0))
    assert error.value.code == 'MODEL_BUDGET_EXCEEDED'


def test_oversized_stream_stops_before_reading_entire_response(monkeypatch):
    def chunks():
        yield b'x' * 32769
        raise AssertionError('Oversized response should stop consumption')
    class Stream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def iter_bytes(self): return chunks()
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def stream(self, *_args, **_kwargs): return Stream()
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(ApiError) as error:
        generate(settings(), policy(), Decision('internal','safe','0'*64,0))
    assert error.value.code == 'MODEL_OUTPUT_INVALID'


def test_transport_failure_does_not_use_other_provider(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def stream(self, *_args, **_kwargs): raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(ApiError) as error:
        generate(settings(), policy(), Decision('internal','safe','0'*64,0))
    assert error.value.code == 'MODEL_PROVIDER_UNAVAILABLE'
