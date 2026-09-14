"""Stored correlation is mandatory before the Worker authorizes protected use."""
import os
import json
from pathlib import Path
from uuid import uuid4
from unittest.mock import Mock

import pytest
import jsonschema

os.environ.setdefault("EID_RABBITMQ_URL", "amqp://guest:guest@localhost//")
from edw_worker import access, app  # noqa: E402
from edw_api.access.policy import AccessDenied, AuthContext  # noqa: E402


@pytest.mark.parametrize("field,value", [
    ("request_id", None), ("request_id", ""), ("request_id", 1),
    ("trace_id", None), ("trace_id", "A"*32), ("trace_id", "a"*31),
    ("trace_id", []),
])
def test_malformed_stored_correlation_denies_before_authorize(monkeypatch, field, value):
    delegation = {"request_id": "request", "trace_id": "a"*32, field: value}
    payload = {"delegation": delegation, "facts": {}, "resource": {}}

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def execute(self, sql, *_):
            return Mock(fetchone=lambda: ("eid_worker",) if sql=="SELECT current_user" else (payload,))

    monkeypatch.setenv("EID_DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(access.psycopg, "connect", lambda *a, **k: Connection())
    decision = Mock(return_value=AuthContext("actor", "eid-worker", "tenant", "workspace",
                                          (1,1,1), 1, "resource:read", "stage", "d"))
    monkeypatch.setattr(access, "authorize", decision)
    args = ("11111111-1111-4111-8111-111111111111", "resource:read", "stage")
    with pytest.raises(AccessDenied):
        access.current_access(*args)
    assert app.check_current_access(None, *args)=={"status": "denied"}
    decision.assert_not_called()


def test_allowed_worker_control_preserves_both_correlation_fields_and_c1(monkeypatch):
    delegation = {"request_id": "stored-request", "trace_id": "a"*32}
    payload = {"delegation": delegation, "facts": {}, "resource": {}}
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def execute(self, sql, *_):
            return Mock(fetchone=lambda: ("eid_worker",) if sql=="SELECT current_user" else (payload,))
    identifier = str(uuid4())
    monkeypatch.setenv("EID_DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(access.psycopg, "connect", lambda *a, **k: Connection())
    monkeypatch.setattr(access, "authorize", Mock(return_value=AuthContext(
        str(uuid4()), "eid-worker", str(uuid4()), str(uuid4()),
        (1,2,3), 1, "resource:read", "stage", identifier)))
    result = json.loads(json.dumps(app.check_current_access(None, identifier, "resource:read", "stage")))
    assert result["status"] == "allowed"
    assert result["context"]["request_id"] == delegation["request_id"]
    assert result["context"]["trace_id"] == delegation["trace_id"]
    schema = json.loads((Path(__file__).parents[2]/"contracts/access-context.schema.json").read_text())
    jsonschema.validate(result["context"], schema, format_checker=jsonschema.FormatChecker())
