"""Exercise remote control and recovery with transport/host fixtures, never live faults."""

import base64
import copy
import io
import json
import socket
import subprocess
from types import SimpleNamespace

import pytest

from scripts import remote_environment as remote
from scripts import remote_service_operations as operations
from scripts import verify_local_environment as guard
from scripts import verify_runtime_logs as log_gate
from test_remote_guard import isolation_config


@pytest.fixture(autouse=True)
def closed_io(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "STATE", tmp_path / "ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")
    monkeypatch.setattr(guard, "environment_state_directory", lambda *args: tmp_path)
    monkeypatch.setattr(remote, "evidence_directory", lambda config: tmp_path / "remote")

    def forbidden(*args, **kwargs):
        pytest.fail("Remote operation tests prohibit implicit process or network access")

    for name in ("run", "check_output", "Popen"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def remote_runtime(monkeypatch):
    config = remote.load_config()
    receipt = remote.owner_receipt(config, "a" * 32)
    fingerprints = {name: "sha256:" + "b" * 64 for name in ("api", "worker", "web")}
    project = config["remote"]["compose_project"]
    containers = {name: {
        "id": f"{index:064x}", "name": f"{project}-{name}-1",
        "labels": {"com.docker.compose.project": project,
                   "com.docker.compose.service": name, "io.eid.owner": receipt["nonce"],
                   "io.eid.environment": config["environment"]},
        "state": "running", "health": None if name == "worker-scheduler" else "healthy",
        "mounts": [],
        "networks": [project + "_default"], "network_mode": project + "_default", "ports": {},
        "image_id": "sha256:" + "c" * 64, "referenced_image_id": "sha256:" + "c" * 64,
        "image_ref": f"{project}-{'worker' if name == 'worker-scheduler' else name}:locked",
        "image_labels": {"io.eid.source-fingerprint":
                         fingerprints[remote.APPLICATION_IMAGES[name]]}
                        if name in remote.APPLICATION_IMAGES else {},
        "isolation_config": isolation_config(),
        "runtime_config": {"command": "fixture", "entrypoint": "fixture", "environment": {},
                           "healthcheck": None,
                           "user": "eid" if name in {"api", "worker", "worker-scheduler"} else ""},
    } for index, name in enumerate(sorted(remote.SERVICES), 1)}
    volumes = [{"name": f"{project}-{name}",
                "mountpoint": f"/var/lib/docker/volumes/{project}-{name}/_data"}
               for name in ("postgres", "keycloak", "seaweedfs", "rabbitmq", "redis")]
    state = {"root_exists": True, "receipt": receipt, "containers": list(containers.values()),
             "volumes": volumes, "networks": [], "server": {"Version": "25.0.3"}}
    tunnels = {"pid": 1234, "started": "fixed-start", "ports": config["tunnels"]["ports"]}
    candidate = remote.render_compose(config, receipt["nonce"], remote.source_files(remote.ROOT))
    manifest = remote.runtime_manifest(config, receipt, state, containers, fingerprints, candidate)
    monkeypatch.setattr(guard, "remote_config", lambda: config)
    monkeypatch.setattr(guard, "verify_runtime_images", lambda: copy.deepcopy(manifest))
    monkeypatch.setattr(log_gate, "remote_config", lambda: guard.remote_config())
    monkeypatch.setattr(log_gate, "verify_runtime_images", lambda: guard.verify_runtime_images())
    monkeypatch.setattr(guard, "source_fingerprints", lambda: copy.deepcopy(fingerprints))
    monkeypatch.setattr(remote, "read_owner", lambda config: copy.deepcopy(receipt))
    monkeypatch.setattr(remote, "verify_tunnels", lambda config: copy.deepcopy(tunnels))
    inventory_calls = []

    def inventory(config, *, require_running=False):
        inventory_calls.append(require_running)
        if require_running:
            remote.require(all(item["state"] == "running" for item in containers.values()),
                           "Runtime is stopped")
        return copy.deepcopy((receipt, state, containers, tunnels))

    monkeypatch.setattr(remote, "guarded_inventory", inventory)
    commands = []
    transport = []
    logs = {}
    stderr_logs = {}
    # Execute the actual shipped function definitions with only the host/transport replaced.
    namespace = {}
    program = operations._remote_program()
    entrypoint = "try:\n payload = json.load(sys.stdin)"
    definitions, execution = program.split(entrypoint)
    exec(definitions, namespace)
    namespace["remote"].collect_remote_state = lambda config, connection: copy.deepcopy(state)

    def host_run(arguments, **kwargs):
        assert arguments[:3] == ["docker", "--host", "unix:///var/run/docker.sock"]
        assert kwargs["timeout"] == 30
        commands.append(arguments)
        action = arguments[3]
        identifier = arguments[-1] if action == "logs" else arguments[4]
        name = next(name for name, item in containers.items() if item["id"] == identifier)
        if action in {"stop", "start"}:
            containers[name]["state"] = "exited" if action == "stop" else "running"
        return subprocess.CompletedProcess(
            arguments, 0, logs.get(name, "safe stdout"), stderr_logs.get(name, ""))

    namespace["subprocess"] = SimpleNamespace(run=host_run, SubprocessError=subprocess.SubprocessError)

    def ssh_run(arguments, **kwargs):
        assert arguments[0] == "ssh", "Local Docker execution is forbidden"
        if "-G" in arguments:
            return subprocess.CompletedProcess(arguments, 0,
                "hostname 172.27.0.38\nuser seadee\nproxyjump jump-local\n"
                "port 22\nclearallforwardings no\n", "")
        assert "ClearAllForwardings=yes" in arguments
        assert "Port=22" in arguments
        assert "Hostname=172.27.0.38" in arguments and "User=seadee" in arguments
        assert arguments[-2] == "seadee-develop"
        assert base64.b64encode(program.encode()).decode() in arguments[-1]
        payload = json.loads(kwargs["input"])
        transport.append(payload)
        output = io.StringIO()
        execution_namespace = {**namespace, "sys": SimpleNamespace(
            stdin=io.StringIO(kwargs["input"]), argv=["remote", "172.16.10.3 2222 172.27.0.38 22"]),
            "print": lambda value: output.write(value + "\n")}
        exec(entrypoint + execution, execution_namespace)
        return subprocess.CompletedProcess(arguments, 0, output.getvalue(), "")

    monkeypatch.setattr(operations.subprocess, "run", ssh_run)
    return SimpleNamespace(config=config, receipt=receipt, state=state, containers=containers,
        fingerprints=fingerprints, manifest=manifest, tunnels=tunnels, commands=commands,
        transport=transport, logs=logs, stderr_logs=stderr_logs,
        inventory_calls=inventory_calls, ssh_run=ssh_run,
        namespace=namespace)


def test_stop_and_recovery_use_original_remote_id_even_when_test_fails(remote_runtime):
    with pytest.raises(AssertionError, match="acceptance failed"):
        with operations.stopped_service("postgres"):
            assert remote_runtime.containers["postgres"]["state"] == "exited"
            raise AssertionError("acceptance failed")
    identifier = remote_runtime.containers["postgres"]["id"]
    assert [args[3:] for args in remote_runtime.commands] == [["stop", identifier], ["start", identifier]]
    assert remote_runtime.inventory_calls == [True]


@pytest.mark.parametrize("mutation", ["owner", "replacement", "image", "mount", "network",
                                      "receipt", "foreign_attachment"])
def test_recovery_rejects_changed_ownership_identity_or_source(remote_runtime, mutation):
    with pytest.raises(operations.RemoteOperationError):
        with operations.stopped_service("worker"):
            item = remote_runtime.containers["worker"]
            if mutation == "owner":
                item["labels"]["io.eid.owner"] = "f" * 32
            elif mutation == "replacement":
                item["id"] = "f" * 64
            elif mutation == "image":
                item["image_id"] = "sha256:" + "f" * 64
            elif mutation == "mount":
                item["mounts"].append({"Type": "bind", "Source": "/foreign"})
            elif mutation == "network":
                item["networks"].append("foreign-network")
            elif mutation == "receipt":
                remote_runtime.state["receipt"] = {"nonce": "foreign"}
            else:
                foreign = copy.deepcopy(item)
                foreign["id"] = "f" * 64
                foreign["name"] = "foreign"
                foreign["labels"] = {"com.docker.compose.project": "foreign"}
                remote_runtime.state["containers"].append(foreign)
    assert len(remote_runtime.commands) == 1
    assert remote_runtime.commands[0][3] == "stop"


def test_stop_guard_rejection_does_not_attempt_recovery(remote_runtime, monkeypatch):
    original = remote_runtime.ssh_run

    def reject_before_stop(arguments, **kwargs):
        remote_runtime.containers["worker"]["labels"]["io.eid.owner"] = "foreign"
        return original(arguments, **kwargs)

    monkeypatch.setattr(operations.subprocess, "run", reject_before_stop)
    with pytest.raises(operations.RemoteOperationError):
        with operations.stopped_service("worker"):
            pytest.fail("Unowned target must not reach the test")
    assert len(remote_runtime.transport) == 1
    assert remote_runtime.commands == []


def test_lost_stop_response_recovers_only_the_captured_container(remote_runtime, monkeypatch):
    original = remote_runtime.ssh_run
    first = True

    def lose_stop_response(arguments, **kwargs):
        nonlocal first
        result = original(arguments, **kwargs)
        if first:
            first = False
            raise subprocess.TimeoutExpired(arguments, 240)
        return result

    monkeypatch.setattr(operations.subprocess, "run", lose_stop_response)
    with pytest.raises(operations.RemoteOperationError, match="unavailable"):
        with operations.stopped_service("postgres"):
            pytest.fail("Unknown stop outcome must not be accepted")
    assert [args[3] for args in remote_runtime.commands] == ["stop", "start"]
    assert remote_runtime.containers["postgres"]["state"] == "running"


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interrupted_stop_response_still_recovers_original_container(
        remote_runtime, monkeypatch, interruption):
    original = remote_runtime.ssh_run

    def interrupt_after_stop(arguments, **kwargs):
        result = original(arguments, **kwargs)
        if "input" in kwargs and json.loads(kwargs["input"])["operation"] == "stop":
            raise interruption("interrupted after remote stop")
        return result

    monkeypatch.setattr(operations.subprocess, "run", interrupt_after_stop)
    with pytest.raises(interruption, match="interrupted after remote stop"):
        with operations.stopped_service("postgres"):
            pytest.fail("Interrupted stop must not reach the test")
    identifier = remote_runtime.containers["postgres"]["id"]
    assert [args[3:] for args in remote_runtime.commands] == [
        ["stop", identifier], ["start", identifier]]
    assert remote_runtime.containers["postgres"]["state"] == "running"


def test_client_stop_guard_refusal_does_not_attempt_recovery(remote_runtime, monkeypatch):
    runtime = operations.captured_runtime()
    monkeypatch.setattr(operations, "captured_runtime", lambda: runtime)
    monkeypatch.setattr(guard, "remote_config", lambda: None)
    calls = []
    original = runtime.run

    def record_run(service, operation, **kwargs):
        calls.append(operation)
        return original(service, operation, **kwargs)

    monkeypatch.setattr(runtime, "run", record_run)
    with pytest.raises(remote.RemoteEnvironmentError, match="selection changed"):
        with operations.stopped_service("postgres"):
            pytest.fail("Rejected stop must not reach the test")
    assert calls == ["stop"]
    assert remote_runtime.commands == []
    assert remote_runtime.transport == []


@pytest.mark.parametrize("recover_first", ["postgres", "worker"])
def test_interleaved_independent_stop_operations_can_both_recover(
        remote_runtime, recover_first):
    # Two clients capture the same running runtime, then both validate stop before
    # either Docker command changes state. This reproduces the concurrent schedule.
    runtimes = {name: operations.captured_runtime() for name in ("postgres", "worker")}
    host_run = remote_runtime.namespace["subprocess"].run
    postgres_id = remote_runtime.containers["postgres"]["id"]

    def interleaved_host_run(arguments, **kwargs):
        if arguments[3:] == ["stop", postgres_id]:
            runtimes["worker"].run("worker", "stop")
        return host_run(arguments, **kwargs)

    remote_runtime.namespace["subprocess"].run = interleaved_host_run
    runtimes["postgres"].run("postgres", "stop")
    assert all(remote_runtime.containers[name]["state"] == "exited" for name in runtimes)
    runtimes[recover_first].run(recover_first, "start")
    recover_last = "worker" if recover_first == "postgres" else "postgres"
    assert remote_runtime.containers[recover_first]["state"] == "running"
    assert remote_runtime.containers[recover_last]["state"] == "exited"
    runtimes[recover_last].run(recover_last, "start")
    assert all(remote_runtime.containers[name]["state"] == "running" for name in runtimes)
    assert [command[3:] for command in remote_runtime.commands] == [
        ["stop", remote_runtime.containers["worker"]["id"]], ["stop", postgres_id],
        ["start", remote_runtime.containers[recover_first]["id"]],
        ["start", remote_runtime.containers[recover_last]["id"]]]


@pytest.mark.parametrize("other_state", ["exited", "restarting", "dead"])
def test_unrelated_service_exit_does_not_block_safe_recovery(remote_runtime, other_state):
    with operations.stopped_service("postgres") as runtime:
        remote_runtime.containers["worker"]["state"] = other_state
    assert [command[3:] for command in remote_runtime.commands] == [
        ["stop", remote_runtime.containers["postgres"]["id"]],
        ["start", remote_runtime.containers["postgres"]["id"]]]
    assert remote_runtime.containers["worker"]["state"] == other_state
    with pytest.raises(remote.RemoteEnvironmentError, match="Runtime is stopped"):
        runtime.verify_unchanged()


def _foreign_bind(source):
    return {"id": "f" * 64, "name": "foreign", "labels": {
        "com.docker.compose.project": "foreign"}, "mounts": [
            {"Type": "bind", "Source": source, "Destination": "/foreign-data"}],
        "networks": [], "state": "running"}


@pytest.mark.parametrize("resource", ["root", "volume"])
@pytest.mark.parametrize("overlap", ["exact", "parent", "child"])
@pytest.mark.parametrize("phase", ["stop", "recovery"])
def test_operation_rejects_foreign_bind_overlapping_eid_paths(
        remote_runtime, resource, overlap, phase):
    runtime = operations.captured_runtime()
    if phase == "recovery":
        runtime.run("postgres", "stop")
    path = (remote_runtime.config["remote"]["root"] if resource == "root"
            else remote_runtime.state["volumes"][0]["mountpoint"])
    source = {"exact": path, "parent": path.rsplit("/", 1)[0], "child": path + "/data"}[overlap]
    remote_runtime.state["containers"].append(_foreign_bind(source))
    with pytest.raises(operations.RemoteOperationError):
        runtime.run("postgres", "start" if phase == "recovery" else "stop")
    assert [command[3] for command in remote_runtime.commands] == (
        ["stop"] if phase == "recovery" else [])


@pytest.mark.parametrize("resource", ["root", "volume"])
def test_unrelated_foreign_bind_with_similar_prefix_does_not_block_recovery(remote_runtime, resource):
    with operations.stopped_service("postgres"):
        path = (remote_runtime.config["remote"]["root"] if resource == "root"
                else remote_runtime.state["volumes"][0]["mountpoint"])
        remote_runtime.state["containers"].append(_foreign_bind(path + "-unrelated/data"))
    assert [command[3] for command in remote_runtime.commands] == ["stop", "start"]


@pytest.mark.parametrize("change", ["selector", "owner", "tunnel", "source"])
def test_client_binding_drift_rejects_operations_without_transport(remote_runtime, monkeypatch, change):
    runtime = operations.captured_runtime()
    if change == "selector":
        monkeypatch.setattr(guard, "remote_config", lambda: None)
    elif change == "owner":
        remote_runtime.receipt["nonce"] = "f" * 32
    elif change == "tunnel":
        remote_runtime.tunnels["pid"] += 1
    else:
        remote_runtime.fingerprints["api"] = "sha256:" + "f" * 64
    with pytest.raises(remote.RemoteEnvironmentError):
        runtime.run("worker", "stop")
    assert remote_runtime.transport == []


def test_recovery_survives_lost_data_tunnel_and_uses_pinned_management_ssh(remote_runtime, monkeypatch):
    with operations.stopped_service("postgres") as runtime:
        def tunnel_lost(config):
            raise remote.RemoteEnvironmentError("Tunnel process exited")

        monkeypatch.setattr(remote, "verify_tunnels", tunnel_lost)
    assert [command[3:] for command in remote_runtime.commands] == [
        ["stop", runtime.container_ids["postgres"]], ["start", runtime.container_ids["postgres"]]]


@pytest.mark.parametrize("operation", ["stop", "logs", "worker-health"])
def test_normal_operations_still_require_data_tunnel(remote_runtime, monkeypatch, operation):
    runtime = operations.captured_runtime()

    def tunnel_lost(config):
        raise remote.RemoteEnvironmentError("Tunnel process exited")

    monkeypatch.setattr(remote, "verify_tunnels", tunnel_lost)
    with pytest.raises(remote.RemoteEnvironmentError, match="Tunnel process exited"):
        runtime.run("worker", operation,
                    cutoff="2026-09-16T00:00:00+00:00" if operation == "logs" else None)
    assert remote_runtime.commands == []
    assert remote_runtime.transport == []


@pytest.mark.parametrize("change", ["selector", "target", "owner", "ssh_target", "ssh_port"])
def test_lost_tunnel_recovery_still_rejects_environment_drift(remote_runtime, monkeypatch, change):
    runtime = operations.captured_runtime()
    runtime.run("postgres", "stop")
    monkeypatch.setattr(remote, "verify_tunnels", lambda config: pytest.fail(
        "Recovery must use independent management SSH"))
    if change == "selector":
        monkeypatch.setattr(guard, "remote_config", lambda: None)
    elif change == "target":
        changed = copy.deepcopy(remote_runtime.config)
        changed["remote"]["ports"]["redis"] += 1
        monkeypatch.setattr(guard, "remote_config", lambda: changed)
    elif change == "owner":
        remote_runtime.receipt["nonce"] = "f" * 32
    else:
        original = remote_runtime.ssh_run

        def changed_effective_config(arguments, **kwargs):
            result = original(arguments, **kwargs)
            if "-G" in arguments:
                result.stdout = result.stdout.replace(
                    "172.27.0.38" if change == "ssh_target" else "port 22",
                    "172.27.0.39" if change == "ssh_target" else "port 2222")
            return result

        monkeypatch.setattr(operations.subprocess, "run", changed_effective_config)
    with pytest.raises(remote.RemoteEnvironmentError):
        runtime.run("postgres", "start")
    assert [command[3] for command in remote_runtime.commands] == ["stop"]
    assert len(remote_runtime.transport) == 1


@pytest.mark.parametrize("change", ["schema", "provenance", "container", "source"])
def test_capture_requires_current_remote_manifest(remote_runtime, change):
    manifest = remote_runtime.manifest
    if change == "schema":
        manifest["schema_version"] = 2
    elif change == "provenance":
        manifest["provenance"]["owner"] = "f" * 32
    elif change == "container":
        manifest["services"]["postgres"]["container_id"] = "f" * 64
    else:
        manifest["services"]["worker"]["source_fingerprint"] = "sha256:" + "f" * 64
    with pytest.raises(remote.RemoteEnvironmentError):
        operations.captured_runtime()
    assert remote_runtime.transport == []


def test_dependency_operations_without_remote_selector_never_fall_back(monkeypatch):
    monkeypatch.setattr(guard, "remote_config", lambda: None)
    monkeypatch.setattr(operations.subprocess, "run", lambda *a, **k: pytest.fail("Executed locally"))
    with pytest.raises(remote.RemoteEnvironmentError, match="selector"):
        operations.captured_runtime()


def test_health_probe_accepts_failure_exit_without_leaking_tool_output(remote_runtime):
    runtime = operations.captured_runtime()

    def unhealthy(arguments, **kwargs):
        return subprocess.CompletedProcess(arguments, 1, "sensitive output", "secret error")

    remote_runtime.namespace["subprocess"].run = unhealthy
    assert runtime.run("worker", "worker-health") == {
        "attempted": True, "returncode": 1, "stdout": "", "stderr": ""}


def test_recovery_ignores_health_degradation_but_never_restarts_running_target(remote_runtime):
    runtime = operations.captured_runtime()
    remote_runtime.containers["api"]["health"] = "unhealthy"
    assert runtime.run("worker", "start")["attempted"] is False
    assert remote_runtime.commands == []


@pytest.mark.parametrize("service,operation", [("api", "stop"), ("postgres", "worker-health"),
                                              ("worker", "restart"), ("worker", "rm")])
def test_operations_are_an_explicit_allowlist(remote_runtime, service, operation):
    with pytest.raises(remote.RemoteEnvironmentError):
        operations.captured_runtime().run(service, operation)
    assert remote_runtime.transport == []


def test_remote_log_scan_binds_ten_ids_and_scans_secrets_without_local_docker(remote_runtime):
    secrets = list(log_gate.LOCAL_CREDENTIALS.values())
    remote_runtime.logs["api"] = " ".join(secrets) + " Bearer abcdefghijkl"
    result = log_gate.scan_runtime_logs()
    assert result["project"] == "eid-remote-dev"
    assert result["passed"] is False
    assert result["runtime_images"] == remote_runtime.manifest
    assert result["scanned_container_ids"] == {
        name: item["id"] for name, item in remote_runtime.containers.items()}
    assert set(result["services"]) == remote.SERVICES
    assert all(secret not in json.dumps(result) for secret in secrets)
    assert len(remote_runtime.commands) == len(remote.SERVICES)
    assert all(command[3:6] == ["logs", "--until", result["log_cutoff_utc"]]
               for command in remote_runtime.commands)
    assert all("--tail" not in command and "--since" not in command
               for command in remote_runtime.commands)
    assert remote_runtime.inventory_calls == [True, True]


def test_clean_remote_log_scan_passes(remote_runtime):
    assert log_gate.scan_runtime_logs()["passed"] is True


def test_successful_remote_logs_scan_stderr_only_secrets_and_redact_results(remote_runtime):
    bearer = "stderr_only_sensitive_bearer_value"
    fixture = log_gate.LOCAL_CREDENTIALS["access_fixture_password"]
    remote_runtime.stderr_logs["api"] = f"Authorization: Bearer {bearer}\n{fixture}\n{fixture}"
    result = log_gate.scan_runtime_logs()
    assert result["passed"] is False
    expected = {"jwt": 0, "token_value": 0, "authorization_code_url": 0,
                "bearer_value": 1, "local_credential": 2}
    assert result["services"]["api"] == {"matches": expected}
    assert all(count == 0 for name, service in result["services"].items() if name != "api"
               for count in service["matches"].values())
    serialized = json.dumps(result)
    assert bearer not in serialized and fixture not in serialized
    assert len(remote_runtime.commands) == len(remote.SERVICES)


@pytest.mark.parametrize("mutation", ["owner", "replacement", "source", "tunnel", "selection"])
def test_remote_log_scan_rejects_drift_after_last_log(remote_runtime, monkeypatch, mutation):
    original = remote_runtime.ssh_run

    def drift_after_last_log(arguments, **kwargs):
        result = original(arguments, **kwargs)
        if len(remote_runtime.transport) == len(remote.SERVICES):
            if mutation == "owner":
                remote_runtime.receipt["nonce"] = "f" * 32
            elif mutation == "replacement":
                remote_runtime.containers["postgres"]["id"] = "f" * 64
            elif mutation == "source":
                remote_runtime.fingerprints["api"] = "sha256:" + "f" * 64
            elif mutation == "tunnel":
                remote_runtime.tunnels["pid"] += 1
            else:
                monkeypatch.setattr(guard, "remote_config", lambda: None)
        return result

    monkeypatch.setattr(operations.subprocess, "run", drift_after_last_log)
    with pytest.raises(RuntimeError, match="changed"):
        log_gate.scan_runtime_logs()


def test_remote_log_command_failure_does_not_expose_stderr(remote_runtime):
    remote_runtime.namespace["subprocess"].run = lambda args, **kwargs: subprocess.CompletedProcess(
        args, 1, "", "access_token=secret_sensitive_payload")
    with pytest.raises(operations.RemoteOperationError) as error:
        log_gate.scan_runtime_logs()
    assert "secret_sensitive_payload" not in str(error.value)
