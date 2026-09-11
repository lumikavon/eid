import json

import httpx
import pytest

from scripts.verify_local_environment import IsolationError
from scripts.verify_readiness import EXPECTED_CHECKS, READINESS_URL, verify_public_readiness


class Response:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


def ready_payload():
    return {"status": "ready", "checks": dict.fromkeys(EXPECTED_CHECKS, "ready")}


def test_public_readiness_accepts_exact_ready_contract(monkeypatch):
    calls = []

    def get(url, *, timeout):
        calls.append((url, timeout))
        return Response(payload=ready_payload())

    monkeypatch.setattr(httpx, "get", get)

    assert verify_public_readiness() == ready_payload()
    assert calls == [(READINESS_URL, 10)]


@pytest.mark.parametrize(
    "response",
    [
        Response(status_code=503, payload=ready_payload()),
        Response(payload={"status": "live", "checks": dict.fromkeys(EXPECTED_CHECKS, "ready")}),
        Response(payload={"status": "ready", "checks": {"postgres": "ready"}}),
        Response(
            payload={
                "status": "ready",
                "checks": {**dict.fromkeys(EXPECTED_CHECKS, "ready"), "redis": "unavailable"},
            }
        ),
        Response(payload=["ready"]),
        Response(json_error=json.JSONDecodeError("invalid", "not-json", 0)),
    ],
)
def test_public_readiness_rejects_nonready_or_malformed_response(monkeypatch, response):
    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: response)

    with pytest.raises((IsolationError, json.JSONDecodeError)):
        verify_public_readiness()


def test_public_readiness_propagates_timeout_as_failure(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("bounded readiness timeout")

    monkeypatch.setattr(httpx, "get", timeout)

    with pytest.raises(httpx.ReadTimeout):
        verify_public_readiness()
