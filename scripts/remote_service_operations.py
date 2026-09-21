"""Bounded operations on a captured, verified remote EID runtime only."""

from __future__ import annotations

import base64
import copy
import inspect
import json
import re
import shlex
import subprocess
from contextlib import contextmanager
from datetime import datetime

from scripts import remote_environment as remote
from scripts import verify_local_environment as guard


class RemoteOperationError(RuntimeError):
    def __init__(self, message, *, attempted=False):
        super().__init__(message)
        self.attempted = attempted


def runtime_binding(config, state):
    """Keep identities/configuration, including foreign attachments; exclude health/state."""
    project = config["remote"]["compose_project"]
    network = project + "_default"
    volumes = {project + "-" + name for name in ("postgres", "keycloak", "seaweedfs",
                                                "rabbitmq", "redis")}
    containers = []
    for item in state["containers"]:
        attached = network in item["networks"] or any(
            mount.get("Name") in volumes or remote.bind_mount_overlaps(config, state, mount)
            for mount in item["mounts"])
        if (item["labels"].get("com.docker.compose.project") == project
                or item["name"].startswith(project) or attached):
            containers.append({key: value for key, value in item.items()
                               if key not in {"state", "health"}})
    return {"root_exists": state["root_exists"], "receipt": state["receipt"],
            "server": state["server"],
            "containers": sorted(containers, key=lambda item: item["id"]),
            "volumes": sorted(state["volumes"], key=lambda item: item["name"]),
            "networks": sorted(state["networks"], key=lambda item: item["name"])}


def validate_operation_state(config, state, binding, service, operation):
    remote.require(runtime_binding(config, state) == binding,
                   "Remote runtime identity or ownership changed before operation")
    project = config["remote"]["compose_project"]
    containers = {item["labels"]["com.docker.compose.service"]: item
                  for item in state["containers"]
                  if item["labels"].get("com.docker.compose.project") == project}
    remote.require(service in containers, "Remote operation service is missing")
    if operation == "start":
        # Recovery depends on captured identity/ownership, not other services' liveness.
        # The final runtime health gate remains separate and still requires all services.
        remote.require(containers[service]["state"] in {"running", "exited"},
                       "Unexpected remote service state: " + service)
    else:
        for name, item in containers.items():
            remote.require(item["state"] == "running", "Unexpected remote service state: " + name)
    identifier = containers[service]["id"]
    remote.require(isinstance(identifier, str) and re.fullmatch(r"[0-9a-f]{64}", identifier),
                   "Remote operation requires a full container ID")
    return identifier, containers[service]["state"]


def operation_arguments(operation, service, identifier, cutoff):
    remote.require(operation in {"logs", "stop", "start", "worker-health"},
                   "Unsupported remote operation")
    remote.require(service in {"postgres", "worker"} or operation == "logs",
                   "Service is not authorized for dependency operations")
    if operation == "logs":
        instant = datetime.fromisoformat(cutoff)
        remote.require(instant.utcoffset() is not None and instant.utcoffset().total_seconds() == 0,
                       "Log cutoff must be UTC")
        return ["logs", "--until", cutoff, identifier]
    remote.require(cutoff is None, "Unexpected operation cutoff")
    if operation == "worker-health":
        remote.require(service == "worker", "Health probe is limited to Worker")
        return ["exec", identifier, "python", "-m", "edw_worker.health"]
    return [operation, identifier]


def execute_remote_operation(config, connection, binding, service, operation, cutoff):
    """Executed remotely; recheck the captured identities immediately before using the ID."""
    state = remote.collect_remote_state(config, connection)
    identifier, status = validate_operation_state(config, state, binding, service, operation)
    arguments = operation_arguments(operation, service, identifier, cutoff)
    if operation == "start" and status == "running":
        return {"attempted": False, "returncode": 0, "stdout": "", "stderr": ""}
    try:
        completed = subprocess.run(
            ["docker", "--host", config["remote"]["docker_endpoint"], *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {"attempted": True, "error": "Remote container command failed"}
    # Only logs need raw output, and callers scan it in memory without emitting secrets.
    return {"attempted": True, "returncode": completed.returncode,
            "stdout": completed.stdout if operation == "logs" else "",
            "stderr": completed.stderr if operation == "logs" else ""}


def _remote_program():
    program = (
        "import hashlib, json, os, re, stat, subprocess, sys\n"
        "from pathlib import Path\nfrom datetime import datetime\n"
        "from types import SimpleNamespace\n"
        "class RemoteEnvironmentError(RuntimeError): pass\n"
        + inspect.getsource(remote.require) + "\n"
        + inspect.getsource(remote.inspected_healthcheck) + "\n"
        + inspect.getsource(remote.collect_remote_state) + "\n"
        + inspect.getsource(remote.bind_mount_overlaps) + "\n"
        + "remote = SimpleNamespace(require=require, collect_remote_state=collect_remote_state, "
          "bind_mount_overlaps=bind_mount_overlaps)\n"
    )
    for function in (runtime_binding, validate_operation_state, operation_arguments,
                     execute_remote_operation):
        program += inspect.getsource(function) + "\n"
    return program + (
        "try:\n payload = json.load(sys.stdin)\n"
        " result = execute_remote_operation(connection=sys.argv[1], **payload)\n"
        "except Exception:\n result = {'attempted': False, 'error': 'Remote operation guard failed'}\n"
        "print(json.dumps(result))\n"
    )


class RemoteRuntime:
    def __init__(self, config, manifest):
        remote.validate_config(config)
        self.config = copy.deepcopy(config)
        self.manifest = copy.deepcopy(manifest)
        receipt, state, containers, tunnels = remote.guarded_inventory(config, require_running=True)
        remote.require(set(containers) == remote.SERVICES, "Remote runtime is incomplete")
        self.fingerprints = guard.source_fingerprints()
        candidate = remote.render_compose(config, receipt["nonce"], remote.source_files(remote.ROOT))
        expected = remote.runtime_manifest(config, receipt, state, containers,
                                           self.fingerprints, candidate)
        remote.require(manifest == expected,
                       "Runtime manifest does not match complete remote candidate binding")
        for item in containers.values():
            remote.require(re.fullmatch(r"[0-9a-f]{64}", item["id"]) is not None,
                           "Remote operation requires a full container ID")
        self.receipt = copy.deepcopy(receipt)
        self.tunnels = copy.deepcopy(tunnels)
        self.binding = copy.deepcopy(runtime_binding(config, state))
        self.container_ids = {name: item["id"] for name, item in containers.items()}

    def verify_unchanged(self):
        remote.require(guard.remote_config() == self.config,
                       "Remote environment selection changed during operation")
        receipt, state, _, tunnels = remote.guarded_inventory(self.config, require_running=True)
        remote.require(receipt == self.receipt and tunnels == self.tunnels
                       and runtime_binding(self.config, state) == self.binding
                       and guard.source_fingerprints() == self.fingerprints,
                       "Remote runtime changed during operation")

    def run(self, service, operation, *, cutoff=None):
        remote.require(service in self.container_ids, "Unknown remote runtime service")
        operation_arguments(operation, service, self.container_ids[service], cutoff)
        remote.require(guard.remote_config() == self.config,
                       "Remote environment selection changed before operation")
        remote.require(remote.read_owner(self.config) == self.receipt
                       and guard.source_fingerprints() == self.fingerprints,
                       "Remote owner or source changed before operation")
        if operation == "start":
            # Recovery uses the independent, pinned management connection. A stopped
            # service or lost forwarding process must not prevent restoring its original ID.
            remote.verify_ssh_config(self.config)
        else:
            remote.require(remote.verify_tunnels(self.config) == self.tunnels,
                           "Remote tunnel changed before operation")
        payload = {"config": self.config, "binding": self.binding, "service": service,
                   "operation": operation, "cutoff": cutoff}
        encoded = base64.b64encode(_remote_program().encode()).decode()
        boot = f"import base64; exec(base64.b64decode('{encoded}'))"
        command = "sudo -n python3 -c " + shlex.quote(boot) + ' "$SSH_CONNECTION"'
        ssh = self.config["ssh"]
        arguments = ["ssh", *remote.ssh_options(), "-o", "ClearAllForwardings=yes",
                     "-o", "Hostname=" + ssh["hostname"], "-o", "User=" + ssh["user"],
                     "-o", "Port=22", "-o", "ProxyJump=" + ssh["proxy_jump"],
                     "-T", ssh["alias"], command]
        try:
            completed = subprocess.run(arguments, input=json.dumps(payload), capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", timeout=240)
            if completed.returncode:
                raise RemoteOperationError("Remote operation transport failed", attempted=True)
            result = json.loads(completed.stdout)
            if result.get("error"):
                raise RemoteOperationError("Remote operation failed", attempted=result["attempted"])
            if operation != "worker-health" and result["returncode"]:
                raise RemoteOperationError("Remote container command failed",
                                           attempted=result["attempted"])
            return result
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
            # Transport loss leaves stop outcome unknown; recovery still rechecks the original ID.
            raise RemoteOperationError("Remote operation result unavailable", attempted=True) from exc


def captured_runtime():
    config = guard.remote_config()
    remote.require(config is not None, "Dependency operations require the remote environment selector")
    return RemoteRuntime(config, guard.verify_runtime_images())


@contextmanager
def stopped_service(service):
    runtime = captured_runtime()
    attempted = False
    try:
        try:
            # Until an explicit guard refusal arrives, an interruption can leave
            # the remote stop outcome unknown. Recovery revalidates the original ID.
            attempted = True
            result = runtime.run(service, "stop")
            attempted = result["attempted"]
        except RemoteOperationError as exc:
            attempted = exc.attempted
            raise
        except remote.RemoteEnvironmentError:
            attempted = False
            raise
        yield runtime
    finally:
        if attempted:
            runtime.run(service, "start")
