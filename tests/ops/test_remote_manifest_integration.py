"""Production manifest generation/consumption with only filesystem/process I/O substituted."""

import base64
import builtins
import copy
import hashlib
import io
import json
import re
import shlex
import socket
import subprocess
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from scripts import remote_environment as remote
from scripts import remote_service_operations as operations
from scripts import verify_local_environment as guard
from scripts import verify_readiness as readiness
from scripts import verify_runtime_logs as log_gate
from test_remote_guard import OWNER, collector_fixture, tunnel_snapshot


@pytest.fixture
def production_io(monkeypatch, tmp_path):
    config = remote.load_config()
    files = remote.source_files(remote.ROOT)
    root = tmp_path / "candidate"
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    config_path = root / "deployment/environments/seadee-develop.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(remote.yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(remote, "ROOT", root)
    monkeypatch.setattr(guard, "ROOT", root)
    monkeypatch.setattr(remote, "DEFAULT_CONFIG", config_path)
    monkeypatch.setattr(guard, "STATE", root / ".local/ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", root / ".local/runtime-images.json")
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", str(config_path))
    directory = remote.evidence_directory(config)
    directory.mkdir(parents=True)
    (directory / "ownership.json").write_text(
        json.dumps(remote.owner_receipt(config, OWNER)), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Production-path fixture forbids real subprocess and network access")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    host = collector_fixture(config, monkeypatch)
    for index, container in enumerate(host.containers.values(), 1):
        container["Id"] = f"{index:064x}"
    snapshot = tunnel_snapshot(config)
    for process in snapshot["processes"]:
        process["CommandLine"] = subprocess.list2cmdline(process.pop("argv"))
    monkeypatch.setattr(remote.shutil, "which", lambda command: "ssh.exe")
    commands = []
    observed = {"collect": 0, "operate": 0}
    fixture = SimpleNamespace(config=config, root=root, directory=directory, host=host,
                              commands=commands, observed=observed, tunnel_alive=True)

    def host_run(arguments, **kwargs):
        if arguments[:3] == ["docker", "--host", config["remote"]["docker_endpoint"]]:
            action = arguments[3]
            if action in {"logs", "start", "stop"}:
                commands.append(arguments)
                identifier = arguments[-1]
                target = next(item for item in host.containers.values() if item["Id"] == identifier)
                if action in {"start", "stop"}:
                    target["State"]["Status"] = "running" if action == "start" else "exited"
                return subprocess.CompletedProcess(arguments, 0, "safe fixture log", "")
        return host.run(arguments, **kwargs)

    def run_program(program, arguments, payload):
        output = io.StringIO()
        imported = builtins.__import__
        modules = {
            "pathlib": SimpleNamespace(Path=host.path_type, PurePosixPath=PurePosixPath),
            "os": SimpleNamespace(geteuid=lambda: 0),
            "subprocess": SimpleNamespace(run=host_run, SubprocessError=subprocess.SubprocessError),
            "sys": SimpleNamespace(argv=arguments, stdin=io.StringIO(payload), stderr=io.StringIO(),
                                   exit=lambda code: pytest.fail(f"Remote program exited {code}")),
        }

        def import_io(name, *args, **kwargs):
            return modules[name] if name in modules else imported(name, *args, **kwargs)

        namespace = {"__builtins__": {**vars(builtins), "__import__": import_io},
                     "print": lambda value, **kwargs: output.write(str(value) + "\n")}
        exec(program, namespace)
        return output.getvalue()

    def client_run(arguments, **kwargs):
        if arguments[0] == "powershell.exe":
            # OS observation only; the actual tunnel parser and validator run unchanged.
            result = snapshot if fixture.tunnel_alive else {"listeners": [], "processes": []}
            return subprocess.CompletedProcess(arguments, 0, json.dumps(result), "")
        assert arguments[0] == "ssh"
        if "-G" in arguments:
            return subprocess.CompletedProcess(arguments, 0,
                "hostname 172.27.0.38\nuser seadee\nproxyjump jump-local\n"
                "port 22\nclearallforwardings no\n", "")
        assert "ClearAllForwardings=yes" in arguments
        assert arguments[-2] == config["ssh"]["alias"]
        command = shlex.split(arguments[-1])
        assert command[:4] == ["sudo", "-n", "python3", "-c"]
        program = base64.b64decode(re.search(r"b64decode\('([^']+)'\)", command[4])[1]).decode()
        connection = "172.16.10.3 2222 172.27.0.38 22"
        if "input" in kwargs:
            assert "Hostname=172.27.0.38" in arguments and "Port=22" in arguments
            observed["operate"] += 1
            argv, payload = ["remote", connection], kwargs["input"]
        else:
            observed["collect"] += 1
            argv, payload = ["remote", command[5], connection], ""
        return subprocess.CompletedProcess(arguments, 0, run_program(program, argv, payload), "")

    monkeypatch.setattr(subprocess, "run", client_run)
    return fixture


def record_generated_manifest(fixture):
    manifest = remote.runtime_images(fixture.config)
    (fixture.directory / "runtime-images.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


@pytest.fixture
def alternating_postgres_mounts(production_io, monkeypatch):
    fixture = production_io
    volume = next(mount for mount in fixture.host.containers["postgres-id"]["Mounts"]
                  if mount["Type"] == "volume")
    volume.update(Source=fixture.host.volumes[volume["Name"]]["Mountpoint"], RW=True)
    observation = SimpleNamespace(snapshots=[], change=lambda mounts: None)
    original_run = fixture.host.run

    def run(arguments, **kwargs):
        result = original_run(arguments, **kwargs)
        if arguments[3:] == ["inspect", "postgres-id"]:
            records = json.loads(result.stdout)
            mounts = records[0]["Mounts"]
            if len(observation.snapshots) % 2:
                mounts.reverse()
            if observation.snapshots:
                observation.change(mounts)
            observation.snapshots.append(copy.deepcopy(mounts))
            return subprocess.CompletedProcess(arguments, 0, json.dumps(records), "")
        return result

    monkeypatch.setattr(fixture.host, "run", run)
    return observation


@pytest.fixture
def recorder_io(production_io, monkeypatch):
    calls = []
    for service, fingerprint in guard.source_fingerprints().items():
        monkeypatch.setenv(guard.BUILD_SOURCE_ENV[service], fingerprint)

    def get(url, **kwargs):
        assert url == readiness.READINESS_URL and kwargs == {"timeout": 10}
        calls.append(url)
        return readiness.httpx.Response(200, json={"status": "ready", "checks": {
            name: "ready" for name in readiness.EXPECTED_CHECKS}})

    monkeypatch.setattr(readiness.httpx, "get", get)
    return calls


def test_production_collector_ignores_mount_order_and_preserves_rw(
        production_io, alternating_postgres_mounts):
    fixture = production_io
    first = remote.remote_inventory(fixture.config)
    second = remote.remote_inventory(fixture.config)
    raw_first, raw_second = alternating_postgres_mounts.snapshots
    assert [mount["Type"] for mount in raw_first] == ["volume", "bind"]
    assert raw_second == list(reversed(raw_first))
    assert first == second
    container = next(item for item in first["containers"]
                     if item["labels"]["com.docker.compose.service"] == "postgres")
    assert len(container["mounts"]) == 2
    for raw in raw_first:
        actual = next(mount for mount in container["mounts"] if mount["Type"] == raw["Type"])
        expected = {key: raw.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")}
        if raw["Type"] == "bind":
            expected["sha256"] = hashlib.sha256(
                fixture.host.path_type(raw["Source"]).read_bytes()).hexdigest()
        assert actual == expected
    assert not fixture.commands


def test_production_recorder_accepts_alternating_mount_order(
        production_io, alternating_postgres_mounts, recorder_io):
    fixture = production_io
    manifest = guard.record_runtime_images()
    recorded = fixture.directory / "runtime-images.json"
    assert json.loads(recorded.read_text(encoding="utf-8")) == manifest
    assert guard.verify_runtime_images() == manifest
    assert operations.captured_runtime().manifest == manifest
    assert set(manifest["services"]) == remote.SERVICES
    assert len(recorder_io) == 2
    snapshots = alternating_postgres_mounts.snapshots
    assert len(snapshots) >= 6
    assert all(mounts == (snapshots[0] if index % 2 == 0 else list(reversed(snapshots[0])))
               for index, mounts in enumerate(snapshots))
    assert not list(fixture.directory.glob(".runtime-images-*.tmp"))
    assert not fixture.commands


@pytest.mark.parametrize("change", ["bind_source", "volume_source", "bind_destination",
    "volume_destination", "bind_name", "volume_name", "bind_rw", "volume_rw", "hash",
    "duplicate_bind", "duplicate_volume", "missing_bind", "missing_volume"])
def test_production_recorder_rejects_mount_drift_between_reordered_snapshots(
        production_io, alternating_postgres_mounts, recorder_io, monkeypatch, change):
    fixture = production_io
    original_read = fixture.host.path_type.read_bytes
    bind = next(mount for mount in fixture.host.containers["postgres-id"]["Mounts"]
                if mount["Type"] == "bind")
    source = bind["Source"]
    replacement = source + ".replacement"
    fixture.host.metadata[replacement] = copy.copy(fixture.host.metadata[source])

    def read_bytes(path):
        if str(path) == replacement:
            return original_read(fixture.host.path_type(source))
        content = original_read(path)
        if change == "hash" and str(path) == source and fixture.observed["collect"] >= 2:
            return content + b"changed mounted content"
        return content

    def mutate(mounts):
        kind = "volume" if "volume" in change else "bind"
        mount = next(item for item in mounts if item["Type"] == kind)
        if change.endswith("source"):
            mount["Source"] = replacement if kind == "bind" else mount["Source"] + "-other"
        elif change.endswith("destination"):
            mount["Destination"] += "-other"
        elif change.endswith("name"):
            mount["Name"] = "foreign-volume"
        elif change.endswith("rw"):
            mount["RW"] = not mount["RW"]
        elif change.startswith("duplicate"):
            mounts.append(copy.deepcopy(mount))
        elif change.startswith("missing"):
            mounts.remove(mount)

    monkeypatch.setattr(fixture.host.path_type, "read_bytes", read_bytes)
    alternating_postgres_mounts.change = mutate
    recorded = fixture.directory / "runtime-images.json"
    original_evidence = b"previous evidence must not be replaced on failed verification\n"
    recorded.write_bytes(original_evidence)
    with pytest.raises(remote.RemoteEnvironmentError, match=(
            "Remote (candidate changed|bind mount destinations differ|data volume destination differs|"
            "service volume mapping differs|mounted configuration differs|volume count differs)")):
        guard.record_runtime_images()
    assert len(alternating_postgres_mounts.snapshots) == 2
    assert recorded.read_bytes() == original_evidence
    assert not list(fixture.directory.glob(".runtime-images-*.tmp"))
    assert not fixture.commands


def test_real_collector_manifest_capture_and_log_scan_share_complete_contract(production_io):
    fixture = production_io
    manifest = record_generated_manifest(fixture)
    candidate = remote.render_compose(fixture.config, OWNER, remote.source_files(fixture.root))
    assert manifest["provenance"]["compose_sha256"] == hashlib.sha256(candidate).hexdigest()
    assert all(len(record["runtime_config_sha256"]) == 64 for record in manifest["services"].values())
    runtime = operations.captured_runtime()
    assert runtime.manifest == manifest
    result = log_gate.scan_runtime_logs()
    assert result["passed"] and result["runtime_images"] == manifest
    assert len(fixture.commands) == 9
    assert all(command[3] == "logs" for command in fixture.commands)
    assert fixture.observed["collect"] >= 10 and fixture.observed["operate"] == 9


@pytest.mark.parametrize("change", ["compose", "runtime", "manifest_compose", "manifest_runtime",
                                   "extra_field", "missing_field"])
def test_production_manifest_consumer_rejects_changed_complete_binding(production_io, change):
    fixture = production_io
    manifest = record_generated_manifest(fixture)
    if change == "compose":
        path = fixture.root / "deployment/compose.yaml"
        compose = remote.yaml.safe_load(path.read_bytes())
        compose["x-reviewed-candidate"] = "new candidate metadata"
        path.write_text(remote.yaml.safe_dump(compose), encoding="utf-8")
    elif change == "runtime":
        fixture.host.containers["worker-id"]["Config"]["Cmd"] = ["unapproved-command"]
    elif change == "manifest_compose":
        manifest["provenance"]["compose_sha256"] = "f" * 64
    elif change == "manifest_runtime":
        manifest["services"]["worker"]["runtime_config_sha256"] = "f" * 64
    elif change == "extra_field":
        manifest["provenance"]["unchecked"] = "value"
    else:
        manifest["services"]["worker"].pop("runtime_config_sha256")
    with pytest.raises(remote.RemoteEnvironmentError, match="configuration differs|candidate binding"):
        operations.RemoteRuntime(fixture.config, manifest)
    assert not fixture.commands


def test_production_recovery_reaches_original_container_after_tunnel_process_exits(production_io):
    fixture = production_io
    record_generated_manifest(fixture)
    with operations.stopped_service("postgres") as runtime:
        fixture.tunnel_alive = False
    identifier = runtime.container_ids["postgres"]
    assert [command[3:] for command in fixture.commands] == [["stop", identifier], ["start", identifier]]
    assert fixture.host.containers["postgres-id"]["State"]["Status"] == "running"
    with pytest.raises(remote.RemoteEnvironmentError, match="tunnel listeners"):
        runtime.run("worker", "logs", cutoff="2026-09-16T00:00:00+00:00")


@pytest.mark.parametrize("change", ["owner", "replacement", "volume", "network", "privileged"])
def test_production_recovery_with_lost_tunnel_rejects_resource_drift(production_io, change):
    fixture = production_io
    record_generated_manifest(fixture)
    runtime = operations.captured_runtime()
    runtime.run("postgres", "stop")
    fixture.tunnel_alive = False
    container = fixture.host.containers["postgres-id"]
    if change == "owner":
        container["Config"]["Labels"]["io.eid.owner"] = "f" * 32
    elif change == "replacement":
        container["Id"] = "f" * 64
    elif change == "volume":
        next(iter(fixture.host.volumes.values()))["Mountpoint"] += "/changed"
    elif change == "network":
        container["NetworkSettings"]["Networks"]["foreign"] = {}
    else:
        container["HostConfig"]["Privileged"] = True
    with pytest.raises(operations.RemoteOperationError):
        runtime.run("postgres", "start")
    assert [command[3] for command in fixture.commands] == ["stop"]
