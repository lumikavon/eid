"""Story 2.4 sandbox/queue contract source; not executed under current policy."""
from hashlib import sha256
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from edw_worker import template_validation as validation


def test_parser_fails_closed_without_namespace_tool(monkeypatch):
    monkeypatch.setattr(validation, "sandbox_available", lambda: False)
    child = Mock()
    monkeypatch.setattr(validation.subprocess, "run", child)
    with pytest.raises(RuntimeError, match="isolation unavailable"):
        validation.inspect_package(b"PK")
    child.assert_not_called()


def test_sandbox_command_unshares_network_and_mounts_only_trusted_paths():
    command = validation._sandbox_command(Path(validation.__file__).with_name(
        "template_validator_process.py").resolve())
    assert Path(command[0]) == Path('/usr/bin/bwrap')
    assert all(flag in command for flag in ("--unshare-user", "--unshare-pid", "--unshare-net",
                                         "--unshare-ipc", "--unshare-uts", "--unshare-cgroup",
                                         "--clearenv", "--die-with-parent", "--new-session"))
    assert "--ro-bind" in command and "--tmpfs" in command
    assert "--bind" not in command and "--share-net" not in command
    assert command[-2] == "-I"
    assert command[command.index("--chdir") + 1] == "/tmp"


@pytest.mark.skipif(os.name != "posix", reason="bubblewrap preflight requires Linux")
def test_preflight_rejects_failed_namespace_before_claim(monkeypatch):
    validation.sandbox_available.cache_clear()
    monkeypatch.setattr(validation, "SANDBOX", Mock(is_file=Mock(return_value=True)))
    monkeypatch.setattr(validation.os, "access", lambda *args: True)
    monkeypatch.setattr(validation.subprocess, "run", lambda *args, **kwargs: Mock(returncode=1))
    assert validation.sandbox_available() is False
    validation.sandbox_available.cache_clear()


def test_validate_once_claims_and_finishes_with_same_lease(monkeypatch):
    candidate = uuid4()
    monkeypatch.setattr(validation, "sandbox_available", lambda: True)
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [(candidate,)]
    context = MagicMock()
    context.__enter__.return_value = conn
    monkeypatch.setattr(validation, "connection", lambda: context)
    calls = []

    def call(sql, args):
        calls.append((sql, args))
        if "claim_v1" in sql:
            return {"package_base64": "UEs=", "sha256": sha256(b"PK").hexdigest()}
        return True

    monkeypatch.setattr(validation, "call", call)
    monkeypatch.setattr(validation, "inspect_package", lambda raw: ({"source_sha256":
        sha256(raw).hexdigest()}, None))
    assert validation.validate_once() is True
    assert len(calls) == 2 and "claim_v1" in calls[0][0] and "finish_v1" in calls[1][0]
    assert calls[0][1][0] == calls[1][1][0] == candidate
    assert calls[0][1][1] == calls[1][1][1]
