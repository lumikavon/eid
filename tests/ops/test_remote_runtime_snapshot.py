import copy
import json
import socket

import pytest

from scripts import remote_environment as remote
from scripts import verify_local_environment as guard
from test_remote_guard import isolation_config


OWNER = "c38d0f7481a6476ebc8b0fd2fe087db3"
FINGERPRINTS = {"api": "sha256:" + "a" * 64}


@pytest.fixture
def config():
    return remote.load_config()


@pytest.fixture(autouse=True)
def no_process_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "STATE", tmp_path / "ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")
    monkeypatch.setattr(guard, "environment_state_directory", lambda *args: tmp_path)
    monkeypatch.setattr(remote, "evidence_directory", lambda config: tmp_path / "remote")

    def forbidden(*args, **kwargs):
        pytest.fail("Snapshot tests must not execute SSH, Docker or network access")

    for name in ("run", "check_output", "Popen"):
        monkeypatch.setattr(remote.subprocess, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def runtime_snapshot(owner=OWNER, container_id="api-one", tunnel_pid=10):
    """A guarded-inventory result; no SSH or Docker command is reachable."""
    return (
        {"nonce": owner},
        {"server": {"ID": "remote-daemon"}},
        {
            "api": {
                "health": "healthy",
                "id": container_id,
                "image_id": "sha256:" + "1" * 64,
                "image_ref": "eid-api:remote",
                "runtime_config": {"Env": [], "Cmd": []},
                "isolation_config": isolation_config(),
            }
        },
        {"pid": tunnel_pid, "ports": {"api": 18080}},
    )


def install_snapshots(monkeypatch, first, second, fingerprints=(FINGERPRINTS, FINGERPRINTS),
                      *, final_rechecks=0):
    snapshots = iter(copy.deepcopy((first, second) + (second,) * final_rechecks))
    sources = iter(copy.deepcopy(fingerprints + (fingerprints[-1],) * final_rechecks))
    monkeypatch.setattr(remote, "guarded_inventory", lambda *_args, **_kwargs: next(snapshots))
    monkeypatch.setattr(guard, "source_fingerprints", lambda: next(sources))
    monkeypatch.setattr(remote, "verify_tunnels", lambda config: copy.deepcopy(first[3]))


def test_runtime_images_records_stable_double_snapshot(config, monkeypatch):
    snapshot = runtime_snapshot()
    install_snapshots(monkeypatch, snapshot, snapshot)

    manifest = remote.runtime_images(config, FINGERPRINTS)

    assert manifest["services"]["api"] == {
        "container_id": "api-one",
        "image_id": "sha256:" + "1" * 64,
        "image_ref": "eid-api:remote",
        "source_fingerprint": FINGERPRINTS["api"],
        "runtime_config_sha256": remote.configuration_digest({
            "process": snapshot[2]["api"]["runtime_config"], "isolation": isolation_config()}),
    }
    assert manifest["provenance"]["owner"] == OWNER
    assert manifest["provenance"]["docker_server"] == {"ID": "remote-daemon"}


@pytest.mark.parametrize("change", ["container", "tunnel", "owner", "source"])
def test_runtime_images_rejects_any_second_snapshot_drift(config, monkeypatch, change):
    first = runtime_snapshot()
    second = copy.deepcopy(first)
    fingerprints = (FINGERPRINTS, FINGERPRINTS)
    if change == "container":
        second[2]["api"]["id"] = "api-two"
    elif change == "tunnel":
        second[3]["pid"] = 11
    elif change == "owner":
        second[0]["nonce"] = "d" * 32
    else:
        fingerprints = (FINGERPRINTS, {"api": "sha256:" + "b" * 64})
    install_snapshots(monkeypatch, first, second, fingerprints)

    with pytest.raises(remote.RemoteEnvironmentError, match="candidate changed"):
        remote.runtime_images(config, FINGERPRINTS)


def test_record_runtime_images_writes_stable_remote_manifest(config, monkeypatch, tmp_path):
    snapshot = runtime_snapshot()
    install_snapshots(monkeypatch, snapshot, snapshot, final_rechecks=2)
    readiness_calls = []
    monkeypatch.setattr(guard, "remote_config", lambda: config)
    monkeypatch.setattr(guard, "environment_state_directory", lambda: tmp_path)
    monkeypatch.setattr(remote, "evidence_directory", lambda config: tmp_path)
    monkeypatch.setattr(guard, "expected_build_source_fingerprints", lambda: FINGERPRINTS)
    import scripts.verify_readiness as readiness

    monkeypatch.setattr(readiness, "verify_public_readiness", lambda: readiness_calls.append("ready"))

    manifest = guard.record_runtime_images()

    assert readiness_calls == ["ready", "ready"]
    assert json.loads((tmp_path / "runtime-images.json").read_text(encoding="utf-8")) == manifest


def test_record_runtime_images_preserves_old_manifest_after_snapshot_drift(config, monkeypatch, tmp_path):
    first = runtime_snapshot()
    second = runtime_snapshot(container_id="api-two")
    install_snapshots(monkeypatch, first, second)
    manifest_path = tmp_path / "runtime-images.json"
    previous = '{"previous":"accepted evidence"}\\n'
    manifest_path.write_text(previous, encoding="utf-8")
    monkeypatch.setattr(guard, "remote_config", lambda: config)
    monkeypatch.setattr(guard, "environment_state_directory", lambda: tmp_path)
    monkeypatch.setattr(remote, "evidence_directory", lambda config: tmp_path)
    monkeypatch.setattr(guard, "expected_build_source_fingerprints", lambda: FINGERPRINTS)
    import scripts.verify_readiness as readiness

    monkeypatch.setattr(readiness, "verify_public_readiness", lambda: None)

    with pytest.raises(remote.RemoteEnvironmentError, match="candidate changed"):
        guard.record_runtime_images()
    assert manifest_path.read_text(encoding="utf-8") == previous
