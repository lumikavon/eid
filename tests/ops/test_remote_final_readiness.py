"""Exercise the recording entry point through real remote candidate validation."""

import copy
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import httpx
import pytest

from scripts import remote_environment as remote
from scripts import verify_local_environment as guard
from scripts import verify_readiness as readiness
from test_remote_guard import OWNER, guard_state, tunnel_snapshot


@pytest.fixture
def recording_environment(monkeypatch, tmp_path):
    # Only filesystem/process/network observations are substituted. Selection,
    # readiness, ownership, both inventory guards and runtime_images stay real.
    config = remote.load_config()
    config_path = tmp_path / "seadee-develop.yaml"
    config_path.write_text(remote.yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(remote, "DEFAULT_CONFIG", config_path)
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", str(config_path))
    directory = tmp_path / "evidence"
    directory.mkdir()
    monkeypatch.setattr(guard, "STATE", directory / "ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", directory / "runtime-images.json")
    monkeypatch.setattr(remote, "evidence_directory", lambda selected: directory)
    # The unfixed selector-drift path falls back to local evidence. Keep even
    # that regression confined to this test's temporary directory.
    monkeypatch.setattr(guard, "environment_state_directory", lambda: directory)
    receipt_path = directory / "ownership.json"
    receipt_path.write_text(json.dumps(remote.owner_receipt(config, OWNER)), encoding="utf-8")
    for service, fingerprint in guard.source_fingerprints().items():
        monkeypatch.setenv(guard.BUILD_SOURCE_ENV[service], fingerprint)

    fixture = {
        "config": config,
        "config_path": config_path,
        "directory": directory,
        "receipt_path": receipt_path,
        "state": guard_state(config),
        "tunnels": tunnel_snapshot(config),
        "events": [],
        "on_final_readiness": lambda: None,
    }

    def inventory(selected):
        fixture["events"].append("inventory")
        return copy.deepcopy(fixture["state"])

    def public_get(url, **kwargs):
        assert url == readiness.READINESS_URL
        fixture["events"].append("readiness")
        if fixture["events"].count("readiness") == 2:
            fixture["on_final_readiness"]()
        return httpx.Response(200, json={
            "status": "ready", "checks": dict.fromkeys(readiness.EXPECTED_CHECKS, "ready"),
        })

    monkeypatch.setattr(remote, "remote_inventory", inventory)
    monkeypatch.setattr(remote, "tunnel_inventory", lambda selected: copy.deepcopy(fixture["tunnels"]))
    monkeypatch.setattr(remote, "verify_ssh_config", lambda selected: None)
    monkeypatch.setattr(remote.shutil, "which", lambda command: "ssh.exe")
    monkeypatch.setattr(readiness.httpx, "get", public_get)
    def forbidden(*args, **kwargs):
        pytest.fail("Remote recording tests must not execute processes or network access")

    for name in ("run", "check_output", "Popen"):
        monkeypatch.setattr(remote.subprocess, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    return fixture


def test_recording_stable_candidate_rechecks_after_final_readiness(recording_environment):
    fixture = recording_environment

    manifest = guard.record_runtime_images()

    assert fixture["events"] == [
        "readiness", "inventory", "inventory", "readiness", "inventory", "inventory",
    ]
    assert set(manifest["services"]) == remote.SERVICES
    assert json.loads((fixture["directory"] / "runtime-images.json").read_text()) == manifest


@pytest.mark.parametrize("change", [
    "container", "tunnel", "owner", "source", "selector", "config", "expected_fingerprint",
])
def test_final_readiness_candidate_drift_preserves_old_evidence(
    recording_environment, monkeypatch, change,
):
    fixture = recording_environment
    manifest_path = fixture["directory"] / "runtime-images.json"
    previous = b'{"previous":"accepted evidence"}\n'
    manifest_path.write_bytes(previous)

    def mutate():
        if change == "container":
            fixture["state"]["containers"][0]["id"] = "replacement-container"
        elif change == "tunnel":
            for listener in fixture["tunnels"]["listeners"]:
                listener["OwningProcess"] = 11
            fixture["tunnels"]["processes"][0]["ProcessId"] = 11
        elif change == "owner":
            new_owner = "d" * 32
            receipt = remote.owner_receipt(fixture["config"], new_owner)
            fixture["receipt_path"].write_text(json.dumps(receipt), encoding="utf-8")
            fixture["state"]["receipt"] = receipt
            for resource in (fixture["state"]["containers"] + fixture["state"]["volumes"]
                             + fixture["state"]["networks"]):
                resource["labels"]["io.eid.owner"] = new_owner
        elif change == "source":
            source = guard._source_paths("api")[-1]
            read_bytes = Path.read_bytes
            monkeypatch.setattr(Path, "read_bytes", lambda path: read_bytes(path) + (
                b"\n# source changed during readiness\n" if path == source else b""))
        elif change == "selector":
            monkeypatch.delenv("EID_ENVIRONMENT_CONFIG")
        elif change == "config":
            updated = copy.deepcopy(fixture["config"])
            updated["remote"]["rabbitmq_health_timeout_seconds"] += 1
            fixture["config_path"].write_text(
                remote.yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
        else:
            monkeypatch.setenv(guard.BUILD_SOURCE_ENV["api"], "sha256:" + "f" * 64)

    fixture["on_final_readiness"] = mutate

    with pytest.raises((guard.IsolationError, remote.RemoteEnvironmentError)):
        guard.record_runtime_images()

    assert fixture["events"][:4] == ["readiness", "inventory", "inventory", "readiness"]
    assert manifest_path.read_bytes() == previous
    assert not list(fixture["directory"].glob("*.tmp"))


def test_concurrent_recorders_use_independent_temporary_files(recording_environment, monkeypatch):
    fixture = recording_environment
    rendezvous = Barrier(2)
    replacement_lock = Lock()
    temporary_paths = []
    replace = Path.replace

    def synchronized_replace(path, target):
        temporary_paths.append(path)
        rendezvous.wait(timeout=10)
        # Order the final OS calls: on Windows simultaneous target replacement
        # may fail due to file sharing, independently of temporary-name safety.
        with replacement_lock:
            return replace(path, target)

    monkeypatch.setattr(Path, "replace", synchronized_replace)
    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(lambda unused: guard.record_runtime_images(), range(2)))

    assert len(set(temporary_paths)) == 2
    assert records[0] == records[1]
    assert json.loads((fixture["directory"] / "runtime-images.json").read_text()) == records[0]
    assert not list(fixture["directory"].glob("*.tmp"))
