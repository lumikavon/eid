"""Remote seed path contracts; service boundaries are simulated, never live acceptance."""

import builtins
import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest

from scripts import remote_environment as remote
from scripts import seed_access_fixtures as seed
from scripts import verify_local_environment as guard


OWNER = "c38d0f7481a6476ebc8b0fd2fe087db3"
USERNAME = "eid-access-author"
USER_ID = "created-author"
RECEIPT = {USERNAME: {"id": USER_ID, "nonce": OWNER}}
CONFIG_PATH = remote.DEFAULT_CONFIG.resolve()
REPOSITORY = Path(__file__).resolve().parents[2]


class ReachedFixtureDatabase(Exception):
    """Stop after identity validation, before any fixture SQL can execute."""


def _isolate_io(monkeypatch, root):
    """Install safety guards before creating fixtures or executing production code."""
    events = []

    def checked(path, write=False):
        if isinstance(path, int):
            return
        resolved = Path(path).resolve()
        if write or ".local" in resolved.parts:
            assert resolved.is_relative_to(root), f"Test I/O escaped temporary root: {resolved}"
        if ".local" in resolved.parts:
            events.append(resolved)

    def wrap_open(original):
        def guarded_open(file, mode="r", *args, **kwargs):
            checked(file, any(flag in mode for flag in "wax+"))
            return original(file, mode, *args, **kwargs)
        return guarded_open

    original_os_open = os.open
    original_replace = os.replace
    original_unlink = os.unlink
    original_mkdir = os.mkdir
    original_exists = Path.exists

    def guarded_os_open(path, flags, *args, **kwargs):
        checked(path, bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        return original_os_open(path, flags, *args, **kwargs)

    def guarded_replace(source, target, *args, **kwargs):
        checked(source, True)
        checked(target, True)
        return original_replace(source, target, *args, **kwargs)

    def guarded_unlink(path, *args, **kwargs):
        checked(path, True)
        return original_unlink(path, *args, **kwargs)

    def guarded_mkdir(path, *args, **kwargs):
        checked(path, True)
        return original_mkdir(path, *args, **kwargs)

    def guarded_exists(path):
        checked(path)
        return original_exists(path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Remote seed path tests prohibit real processes, network, and database access")

    monkeypatch.setattr(builtins, "open", wrap_open(builtins.open))
    monkeypatch.setattr(io, "open", wrap_open(io.open))
    monkeypatch.setattr(os, "open", guarded_os_open)
    monkeypatch.setattr(os, "replace", guarded_replace)
    monkeypatch.setattr(os, "unlink", guarded_unlink)
    monkeypatch.setattr(os, "mkdir", guarded_mkdir)
    monkeypatch.setattr(Path, "exists", guarded_exists)
    for name in ("run", "Popen", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(seed.psycopg, "connect", forbidden)
    return events


class KeycloakFixture:
    def __init__(self):
        self.user = None
        self.requests = []
        self.updates = []
        self.interrupt_after_create = False
        self.login_state = None

    def existing_user(self):
        self.user = {"id": USER_ID, "username": USERNAME, "enabled": True,
                     "firstName": "本地验收", "lastName": "author",
                     "email": USERNAME + "@eid.invalid", "emailVerified": True,
                     "attributes": {"unrelated": ["preserve"]}}

    def handle(self, request):
        path = request.url.path
        self.requests.append((request.method, path))
        if path == "/realms/master/protocol/openid-connect/token":
            return httpx.Response(200, json={"access_token": "fixture-token"})
        if path == "/admin/realms/eid-local/users/profile":
            assert request.method == "GET"
            return httpx.Response(200, json={"attributes": [{"name": "eid_fixture_owner",
                "permissions": {"view": ["admin"], "edit": ["admin"]}}]})
        if path == "/admin/realms/eid-local/users":
            if request.method == "POST":
                assert self.user is None
                declared = json.loads(request.content)
                assert declared["username"] == USERNAME
                assert declared["attributes"] == {"eid_fixture_owner": [OWNER]}
                # Model a successful create whose server response omits the owner attribute.
                # Only the persisted create receipt may authorize the recovery update.
                self.existing_user()
                return httpx.Response(201, headers={"Location": path + "/" + USER_ID})
            assert request.method == "GET"
            assert request.url.params["username"] == USERNAME
            if self.interrupt_after_create and self.user is not None:
                self.interrupt_after_create = False
                raise KeyboardInterrupt("injected interruption after persisted create receipt")
            return httpx.Response(200, json=[] if self.user is None else [self.user])
        if path == "/admin/realms/eid-local/users/" + USER_ID:
            if request.method == "PUT":
                update = json.loads(request.content)
                self.updates.append(copy.deepcopy(update))
                self.user.update(update)
                return httpx.Response(204)
            assert request.method == "GET"
            return httpx.Response(200, json=self.user)
        if path == "/realms/eid-local/protocol/openid-connect/auth":
            assert request.method == "GET"
            self.login_state = request.url.params["state"]
            return httpx.Response(200, text='<form id="kc-form-login" method="post" '
                'action="http://localhost:18080/realms/eid-local/login-actions/authenticate"></form>')
        if path == "/realms/eid-local/login-actions/authenticate":
            assert request.method == "POST"
            form = parse_qs(request.content.decode())
            assert form == {"username": [USERNAME], "password": [seed.FIXTURE_PASSWORD]}
            return httpx.Response(302, headers={"Location":
                "http://localhost:18080/auth/callback?code=fixture&state=" + self.login_state})
        pytest.fail(f"Unexpected simulated HTTP request: {request.method} {path}")


@pytest.fixture(params=["alias", "absolute-config-path"])
def remote_seed(monkeypatch, tmp_path, request):
    root = tmp_path.resolve()
    assert not root.is_relative_to(REPOSITORY)
    events = _isolate_io(monkeypatch, root)
    # Change only filesystem anchors. All selector and evidence-directory functions stay real.
    monkeypatch.setattr(remote, "ROOT", root)
    monkeypatch.setattr(guard, "ROOT", root)
    monkeypatch.setattr(guard, "STATE", root / ".local/ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", root / ".local/runtime-images.json")
    monkeypatch.setattr(seed, "__file__", str(root / "scripts/seed_access_fixtures.py"))
    selector = "seadee-develop" if request.param == "alias" else str(CONFIG_PATH)
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
    local = root / ".local"
    selected = local / "remote/seadee-develop"
    selected.mkdir(parents=True)
    local_lock = local / "access-fixtures.lock"
    local_receipt = local / "access-fixture-receipts.json"
    local_lock.write_bytes(b"old-local-lock-do-not-touch\n")
    local_receipt.write_bytes(b"old local receipt: deliberately invalid JSON\r\n")
    assert remote.selected_config()["environment"] == "seadee-develop"
    assert guard.environment_state_directory(root) == selected
    assert seed.environment_state_directory(root) == selected
    boundary_calls = []
    monkeypatch.setattr(seed, "verify_migration_target", lambda url: boundary_calls.append(url))
    monkeypatch.setattr(seed, "ownership", lambda **_: {"nonce": OWNER})
    monkeypatch.setattr(seed, "service_container", lambda name, *_: "remote-" + name)
    monkeypatch.setattr(seed, "ROLE_OPERATIONS", {"author": {"document:edit"}})
    keycloak = KeycloakFixture()
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs:
        real_client(transport=httpx.MockTransport(keycloak.handle), **kwargs))
    database_calls = []

    def database_boundary(*args, **kwargs):
        database_calls.append((args, kwargs))
        raise ReachedFixtureDatabase()

    monkeypatch.setattr(seed.psycopg, "connect", database_boundary)
    return SimpleNamespace(root=root, local=local, selected=selected, events=events,
        local_lock=local_lock, local_receipt=local_receipt, keycloak=keycloak,
        receipt=selected / "access-fixture-receipts.json",
        lock=selected / "access-fixtures.lock", database_calls=database_calls,
        boundary_calls=boundary_calls)


def _preserve_local_files(case):
    before = {path: path.read_bytes() for path in (case.local_lock, case.local_receipt)}
    case.events.clear()
    return before


def _assert_local_files_untouched(case, before):
    assert not set(before).intersection(case.events), "Remote seed accessed legacy local state"
    assert {path: path.read_bytes() for path in before} == before


def test_remote_lock_blocks_seed_before_identity_or_fixture_database(remote_seed):
    case = remote_seed
    with seed.fixture_lock(case.lock):
        before = _preserve_local_files(case)
        with pytest.raises(RuntimeError, match="Another local fixture seed is running"):
            seed.seed()
        assert not case.keycloak.requests
        assert not case.database_calls
        assert case.boundary_calls == [seed.development_database_url()]
        assert not case.receipt.exists()
        _assert_local_files_untouched(case, before)
    # Real lock is also released after the failed attempt.
    with seed.fixture_lock(case.lock):
        pass


def test_held_local_lock_does_not_block_remote_creation(remote_seed):
    case = remote_seed
    before = _preserve_local_files(case)
    with seed.fixture_lock(case.local_lock):
        case.events.clear()
        with pytest.raises(ReachedFixtureDatabase):
            seed.seed()
        assert not set(before).intersection(case.events)
    assert case.lock.is_file()
    assert json.loads(case.receipt.read_bytes()) == RECEIPT
    assert len(case.database_calls) == 1
    _assert_local_files_untouched(case, before)


def test_interrupted_creation_recovers_from_remote_receipt(remote_seed):
    case = remote_seed
    before = _preserve_local_files(case)
    case.keycloak.interrupt_after_create = True
    with pytest.raises(KeyboardInterrupt, match="persisted create receipt"):
        seed.seed()
    assert json.loads(case.receipt.read_bytes()) == RECEIPT
    receipt_bytes = case.receipt.read_bytes()
    assert not case.keycloak.updates
    assert not case.database_calls
    created_profile = copy.deepcopy(case.keycloak.user)
    with pytest.raises(ReachedFixtureDatabase):
        seed.seed()
    assert case.receipt.read_bytes() == receipt_bytes
    assert case.keycloak.updates == [{**created_profile, "attributes": {
        "unrelated": ["preserve"], "eid_fixture_owner": [OWNER]}}]
    assert sum(method == "POST" and path == "/admin/realms/eid-local/users"
               for method, path in case.keycloak.requests) == 1
    assert len(case.database_calls) == 1
    _assert_local_files_untouched(case, before)


@pytest.mark.parametrize("remote_receipt", [None,
    {USERNAME: {"id": "another-user", "nonce": OWNER}},
    {USERNAME: {"id": USER_ID, "nonce": "another-owner"}},
])
def test_missing_or_mismatched_remote_receipt_never_falls_back_to_local(remote_seed, remote_receipt):
    case = remote_seed
    case.local_receipt.write_bytes(json.dumps(RECEIPT, indent=4).encode() + b"\r\n")
    if remote_receipt is not None:
        case.receipt.write_text(json.dumps(remote_receipt), encoding="utf-8")
    before = _preserve_local_files(case)
    case.keycloak.existing_user()
    original_user = copy.deepcopy(case.keycloak.user)
    with pytest.raises(RuntimeError, match="No ownership proof for existing fixture identity"):
        seed.seed()
    assert case.keycloak.user == original_user
    assert not case.keycloak.updates
    assert not case.database_calls
    if remote_receipt is None:
        assert not case.receipt.exists()
    else:
        assert json.loads(case.receipt.read_bytes()) == remote_receipt
    _assert_local_files_untouched(case, before)
