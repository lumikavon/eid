"""Package EID for one explicitly authorized SSH host; never deploy or migrate implicitly.

The remote probe uses only Python's standard library and read-only Docker commands.
Local artifacts are not local or remote runtime acceptance evidence.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import inspect
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "deployment/environments/seadee-develop.yaml"
SERVICES = {"postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "api", "worker",
            "worker-scheduler", "web", "nginx"}
APPLICATION_IMAGES = {"api": "api", "worker": "worker", "worker-scheduler": "worker",
                      "web": "web"}
PORTS = {"postgres": ("postgres", 5432), "keycloak": ("keycloak", 8080),
         "rabbitmq": ("rabbitmq", 5672), "rabbitmq_management": ("rabbitmq", 15672),
         "redis": ("redis", 6379), "seaweedfs": ("seaweedfs", 8333), "nginx": ("nginx", 8080)}
BASE_VOLUME_SERVICES = {"postgres", "keycloak", "seaweedfs"}
VOLUME_SERVICES = BASE_VOLUME_SERVICES | {"rabbitmq", "redis"}
FIXED_FILES = {
    ".dockerignore", ".nvmrc", ".python-version", "pyproject.toml", "uv.lock",
    "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "alembic.ini",
    "edw-api/pyproject.toml", "edw-worker/pyproject.toml", "edw-web/package.json",
    "edw-web/index.html", "edw-web/eslint.config.js", "edw-web/tsconfig.app.json",
    "edw-web/tsconfig.json", "edw-web/tsconfig.node.json", "edw-web/vite.config.ts",
    "deployment/compose.yaml", "deployment/images.lock.json", "deployment/python.Dockerfile",
    "deployment/web.Dockerfile", "deployment/nginx/default.conf", "deployment/nginx/web.conf",
    "deployment/postgres/001-isolated-database.sql", "deployment/seaweedfs/s3.json",
    "deployment/keycloak/eid-local-realm.json",
}
SOURCE_TREES = {
    "edw-api/src": None, "edw-worker/src": None, "edw-web/src": None,
    "scripts": {".py"}, "migrations": {".py", ".mako"}, "contracts": {".json"},
}
OPTIONAL_SOURCE_TREES = {"edw-web/public"}
IMAGE_EXCLUDED_PARTS = {"node_modules", "dist", "__pycache__"}
FORBIDDEN_PARTS = {".git", ".local", ".venv", ".agents", ".claude", ".codex", "_bmad",
                   "_bmad-output", "__pycache__", "node_modules", "dist", "secrets",
                   ".ssh", ".aws", ".azure", ".kube", ".gnupg"}


class RemoteEnvironmentError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise RemoteEnvironmentError(message)


def validate_config(config):
    """Configuration cannot turn this helper into an arbitrary SSH/deployment client."""
    require(isinstance(config, dict), "Environment configuration must be a mapping")
    require(set(config) == {"schema_version", "environment", "ssh", "remote", "tunnels",
                            "application"}, "Unknown or missing environment configuration keys")
    require(type(config["schema_version"]) is int and config["schema_version"] == 1,
            "Unsupported environment schema")
    require(config["environment"] == "seadee-develop", "Environment is not authorized")
    require(config["ssh"] == {"alias": "seadee-develop", "hostname": "172.27.0.38",
                              "user": "seadee", "proxy_jump": "jump-local"},
            "SSH target is not the authorized seadee-develop host")
    remote = config["remote"]
    require(isinstance(remote, dict) and set(remote) == {"root", "compose_project",
            "docker_endpoint", "platform", "bind_address", "ports", "ancestors",
            "rabbitmq_health_timeout_seconds", "rabbitmq_identity"}, "Invalid remote settings")
    require(type(remote["rabbitmq_health_timeout_seconds"]) is int
            and 10 <= remote["rabbitmq_health_timeout_seconds"] <= 30,
            "Remote RabbitMQ health timeout must be bounded to 10-30 seconds")
    # This is the observed active node in the existing volume, not a new default.
    # Changing it requires new evidence and a reviewed data-preservation decision.
    require(remote["rabbitmq_identity"] == {
        "hostname": "5e8cac11b089", "nodename": "rabbit@5e8cac11b089",
        "data_dir": "/var/lib/rabbitmq/mnesia/rabbit@5e8cac11b089",
    }, "Remote RabbitMQ identity differs from the verified existing node")
    require(remote["root"] == "/opt/eid", "Remote root must be /opt/eid")
    require(remote["compose_project"] == "eid-remote-dev", "Foreign Compose project rejected")
    require(remote["docker_endpoint"] == "unix:///var/run/docker.sock",
            "Docker endpoint must be the remote host's local socket")
    require(remote["platform"] == "linux/amd64", "Unsupported remote platform")
    require(remote["ancestors"] == {
        "/": {"uid": 0, "gid": 0, "mode": "0555"},
        "/opt": {"uid": 0, "gid": 0, "mode": "0755"},
    }, "Remote ancestor ownership differs from the reviewed host inventory")
    for settings in (remote, config["tunnels"]):
        require(isinstance(settings, dict) and settings.get("bind_address") == "127.0.0.1",
                "Only explicit IPv4 loopback listeners are allowed")
        ports = settings.get("ports")
        require(isinstance(ports, dict) and set(ports) == set(PORTS), "Port mapping is incomplete")
        require(all(type(value) is int and 1024 <= value <= 65535 for value in ports.values()),
                "Ports must be non-privileged integers")
        require(len(set(ports.values())) == len(ports), "Duplicate listener port")
    require(set(config["tunnels"]) == {"bind_address", "ports"}, "Unknown tunnel settings")
    require(config["tunnels"]["ports"]["nginx"] == 18080 and remote["ports"]["nginx"] == 18080,
            "The existing localhost OIDC contract requires web port 18080")
    require(not any(56347 <= port <= 56446 for port in config["tunnels"]["ports"].values()),
            "Local tunnel port overlaps the known Windows excluded range")
    require(config["application"] == {
        "public_origin": "http://localhost:18080", "database": "eid_local_dev",
        "database_marker": "eid-local-dev-v1", "bucket": "eid-local-artifacts",
        "rabbitmq_vhost": "eid-local", "keycloak_realm": "eid-local",
        "credentials": "repository-development-fixtures",
    }, "Application fixture/identity contract differs; explicit integration is required")
    return config


def load_config(path=DEFAULT_CONFIG):
    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            mapping = super().construct_mapping(node, deep=deep)
            require(len(node.value) == len(mapping), "Duplicate environment configuration key")
            return mapping

    return validate_config(yaml.load(Path(path).read_text(encoding="utf-8"), Loader=UniqueKeyLoader))


def selected_config():
    """Absent selector preserves the legacy local guard; invalid selectors never fall back."""
    selector = os.environ.get("EID_ENVIRONMENT_CONFIG")
    if selector is None:
        return None
    require(bool(selector.strip()), "EID_ENVIRONMENT_CONFIG must not be empty")
    path = DEFAULT_CONFIG if selector == "seadee-develop" else Path(selector)
    if not path.is_absolute():
        path = ROOT / path
    require(path.resolve() == DEFAULT_CONFIG.resolve(), "Unapproved environment configuration path")
    config = load_config(path)
    require(config["tunnels"]["ports"] == {"postgres": 15432, "keycloak": 58080,
        "rabbitmq": 55672, "rabbitmq_management": 55673, "redis": 16379,
        "seaweedfs": 58333, "nginx": 18080}, "Selected environment must match existing client endpoints")
    return config


def evidence_directory(config):
    return ROOT / ".local" / "remote" / config["environment"]


def read_owner(config):
    path = evidence_directory(config) / "ownership.json"
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
            "Missing or linked remote ownership receipt; installation must record its nonce")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    require(receipt == owner_receipt(config, receipt.get("nonce")),
            "Local remote-ownership receipt differs from selected target")
    return receipt


def validate_owner(owner):
    require(isinstance(owner, str) and re.fullmatch(r"[0-9a-f]{32}", owner),
            "Owner must be a persistent, randomly generated 32-character lowercase hex nonce")
    return owner


def owner_receipt(config, owner):
    return {"schema_version": 1, "environment": config["environment"],
            "hostname": config["ssh"]["hostname"], "root": config["remote"]["root"],
            "compose_project": config["remote"]["compose_project"], "nonce": validate_owner(owner)}


def allowed_source(relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        return False
    if any(part.lower() in FORBIDDEN_PARTS or part.lower().startswith(".env")
           or "secret" in part.lower()
           or part.lower().startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"))
           for part in path.parts):
        return False
    if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".tsbuildinfo"}:
        return False
    if relative in FIXED_FILES:
        return True
    return any(relative.startswith(tree + "/") and (suffixes is None or path.suffix in suffixes)
               for tree, suffixes in (SOURCE_TREES | dict.fromkeys(OPTIONAL_SOURCE_TREES)).items())


def source_files(root):
    """Read only approved build/ops inputs, rejecting links and hidden payloads."""
    root = Path(root).resolve()
    candidates = set(FIXED_FILES)
    for tree in SOURCE_TREES.keys() | OPTIONAL_SOURCE_TREES:
        start = root / tree
        if tree in OPTIONAL_SOURCE_TREES and not start.exists() and not start.is_symlink():
            continue
        require(start.is_dir() and not start.is_symlink() and not start.is_junction(),
                f"Required source tree is absent or linked: {tree}")
        image_tree = tree.startswith("edw-")
        for directory, children, names in os.walk(start, followlinks=False):
            for child in list(children):
                item = Path(directory) / child
                relative = item.relative_to(root).as_posix()
                if item.is_symlink() or item.is_junction():
                    raise RemoteEnvironmentError(f"Linked source directory rejected: {relative}")
                if child in IMAGE_EXCLUDED_PARTS or (not image_tree and (
                        child.lower() in FORBIDDEN_PARTS or child.startswith("."))):
                    children.remove(child)
            for name in names:
                relative = (Path(directory) / name).relative_to(root).as_posix()
                if image_tree and Path(name).suffix != ".tsbuildinfo":
                    require(allowed_source(relative),
                            f"Image fingerprint input is forbidden in source package: {relative}")
                candidates.add(relative)
    result = {}
    for relative in sorted(candidates):
        if not allowed_source(relative):
            continue
        path = root / relative
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root),
                f"Missing, linked or escaped source input: {relative}")
        require(all(not parent.is_symlink() and not parent.is_junction()
                    for parent in path.parents if parent != root and parent.is_relative_to(root)),
                f"Linked source ancestor: {relative}")
        require(path.stat().st_nlink == 1, f"Hard-linked source rejected: {relative}")
        data = path.read_bytes()
        require(len(data) <= 16 * 1024 * 1024, f"Oversized source input: {relative}")
        result[relative] = data
    return result


def source_digest(files):
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode("utf-8") + b"\0" + len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def image_source_fingerprint(service, files):
    """Keep image labels compatible with the existing per-image source fingerprint contract."""
    if service in {"api", "worker"}:
        fixed = {".dockerignore", "deployment/python.Dockerfile", "pyproject.toml", "uv.lock",
                 "edw-api/pyproject.toml", "edw-worker/pyproject.toml"}
        trees = ("edw-api/src/", "edw-worker/src/")
    else:
        require(service == "web", "Unknown application image")
        fixed = {name for name in FIXED_FILES if name.startswith("edw-web/")} | {
            ".dockerignore", "deployment/web.Dockerfile", "deployment/nginx/web.conf",
            "package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml"}
        trees = ("edw-web/src/", "edw-web/public/")
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        if name in fixed or name.startswith(trees):
            relative = name.encode("utf-8")
            digest.update(len(relative).to_bytes(4, "big") + relative)
            digest.update(len(content).to_bytes(8, "big") + content)
    return "sha256:" + digest.hexdigest()


def render_compose(config, owner, files):
    validate_config(config)
    validate_owner(owner)
    compose = copy.deepcopy(yaml.safe_load(files["deployment/compose.yaml"]))
    lock = json.loads(files["deployment/images.lock.json"])
    require(set(compose["services"]) == SERVICES, "Unexpected base service inventory")
    require(set(compose["volumes"]) == {f"eid-{name}" for name in BASE_VOLUME_SERVICES},
            "Unexpected base volume inventory")
    project = config["remote"]["compose_project"]
    compose["name"] = project
    labels = {"io.eid.owner": owner, "io.eid.environment": config["environment"]}
    for service_name, service in compose["services"].items():
        require(not any(key in service for key in ("container_name", "network_mode", "privileged",
                "devices", "volumes_from", "env_file", "extends", "networks", "pid", "ipc",
                "uts", "userns_mode", "cgroup", "cap_add", "device_cgroup_rules",
                )),
                f"Unsupported isolation-affecting service configuration: {service_name}")
        require(service.get('security_opt', []) in ([], ['no-new-privileges:true']),
                f"Unsupported isolation-affecting security options: {service_name}")
        # Pin the namespace independently of the remote Docker daemon's default.
        service["cgroup"] = "private"
        service["labels"] = dict(labels)
        service["platform"] = config["remote"]["platform"]
        if service_name == "rabbitmq":
            service["healthcheck"]["timeout"] = (
                f"{config['remote']['rabbitmq_health_timeout_seconds']}s")
            identity = config["remote"]["rabbitmq_identity"]
            service["hostname"] = identity["hostname"]
            service["environment"].update({"RABBITMQ_NODENAME": identity["nodename"],
                                           "RABBITMQ_MNESIA_DIR": identity["data_dir"]})
        service["ports"] = [f"127.0.0.1:{config['remote']['ports'][name]}:{port}"
                            for name, (target, port) in PORTS.items() if target == service_name]
        if service_name in APPLICATION_IMAGES:
            image_service = APPLICATION_IMAGES[service_name]
            fingerprint = image_source_fingerprint(image_service, files)
            service["image"] = f"{project}-{image_service}:{fingerprint[7:23]}"
            service["build"]["args"] = {"EID_SOURCE_FINGERPRINT": fingerprint}
        else:
            require(service["image"] == lock["base_images"][service_name]
                    and re.search(r"@sha256:[0-9a-f]{64}$", service["image"]),
                    f"Unpinned or mismatched base image: {service_name}")
    for name, volume in compose["volumes"].items():
        require(set(volume) == {"name", "labels"}, "Unsupported base volume configuration")
        volume["name"] = f"{project}-{name.removeprefix('eid-')}"
        volume["labels"] = dict(labels)
    # Image-declared data volumes must not silently become unowned anonymous volumes.
    for service, destination in (("rabbitmq", "/var/lib/rabbitmq"), ("redis", "/data")):
        require(not compose["services"][service].get("volumes"),
                "Unexpected existing broker/cache mounts")
        compose["services"][service]["volumes"] = [f"eid-{service}:{destination}"]
        compose["volumes"][f"eid-{service}"] = {"name": f"{project}-{service}",
                                                "labels": dict(labels)}
    require("networks" not in compose, "Unexpected base network configuration")
    compose["networks"] = {"default": {"name": project + "_default", "labels": dict(labels)}}
    result = yaml.safe_dump(compose, sort_keys=False, allow_unicode=True, width=4096)
    # Secrets remain runtime inputs, never materialized in the source package.
    runtime_inputs = {
        'EID_BGE_M3_ENDPOINT', 'EID_RERANKER_ENDPOINT', 'EID_KNOWLEDGE_GATEWAY_URL',
        'EID_KNOWLEDGE_GATEWAY_KEY', 'EID_MODEL_INTERNAL_ENDPOINT', 'EID_MODEL_INTERNAL_KEY',
        'EID_MODEL_EXTERNAL_ENDPOINT', 'EID_MODEL_EXTERNAL_KEY', 'EID_MODEL_EXTERNAL_APPROVED_HOST',
    }
    allowed = {f'${{{name}:-}}' for name in runtime_inputs} | {
        '${EID_EVIDENCE_WAKE_KEY:?Set a unique 32+ character API-worker wake key}',
        '${EID_MODEL_WAKE_KEY:?Set a unique 32+ character model wake key}',
    }
    checked_result = result.replace('$$', '')
    for placeholder in allowed:
        checked_result = checked_result.replace(placeholder, '')
    require(not re.search(r"\$(?:[A-Za-z_]|\{)", checked_result),
            "Unresolved Compose interpolation is forbidden")
    return result.encode("utf-8")


def generated_files(config, owner, files):
    receipt = owner_receipt(config, owner)
    return {
        "deployment/remote.compose.yaml": render_compose(config, owner, files),
        "deployment/environments/seadee-develop.yaml": yaml.safe_dump(
            config, sort_keys=False).encode(),
        ".eid-remote-owner.json": (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(),
        "deployment/remote-package.json": (json.dumps({
            "schema_version": 1, "kind": "source-package-not-runtime-evidence",
            "environment": config["environment"], "owner": owner,
            "source_sha256": source_digest(files),
            "files": {name: hashlib.sha256(content).hexdigest()
                      for name, content in sorted(files.items())},
        }, sort_keys=True, indent=2) + "\n").encode(),
    }


def create_artifact(config, owner, output, *, package, root=ROOT):
    files = source_files(root)
    generated = generated_files(config, owner, files)
    output = Path(output).absolute()
    require(not output.exists(), "Artifact path already exists; refusing overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    if package:
        with output.open("xb") as handle, tarfile.open(fileobj=handle, mode="w:gz") as archive:
            for name, content in sorted((files | generated).items()):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o600 if name == ".eid-remote-owner.json" else 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
        return {"artifact": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source_sha256": source_digest(files), "runtime_verified": False}
    output.mkdir()
    for name, content in generated.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(content)
    return {"artifact": str(output), "source_sha256": source_digest(files),
            "runtime_verified": False}


def inspected_healthcheck(settings):
    """Canonical effective Docker probe, including engine defaults; omit raw commands."""
    if settings is None:
        return None
    require(isinstance(settings, dict) and set(settings) <= {
        "Test", "Interval", "Timeout", "Retries", "StartPeriod", "StartInterval"},
        "Unsupported remote health check configuration")
    test = settings.get("Test") or []
    require(isinstance(test, list) and all(isinstance(part, str) for part in test),
            "Invalid remote health check command")
    defaults = {"Interval": 30_000_000_000, "Timeout": 30_000_000_000,
                "Retries": 3, "StartPeriod": 0, "StartInterval": 5_000_000_000}
    values = {}
    for field, default in defaults.items():
        value = settings.get(field, 0)
        require(type(value) is int and value >= 0, "Invalid remote health check budget")
        values[field] = value or default
    if not test or test == ["NONE"]:
        return None
    require(test[0] in {"CMD", "CMD-SHELL"} and len(test) > 1,
            "Unsupported remote health check command")
    values["Test"] = hashlib.sha256(json.dumps(test, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    return values


def collect_remote_state(config, connection):
    """Executed as remote root over SSH; intentionally contains no remote writes."""
    require(connection.split()[2:3] == [config["ssh"]["hostname"]],
            "SSH server connection address differs from authorized target")
    require(os.geteuid() == 0, "Remote inventory requires sudo -n")
    target = Path(config["remote"]["root"])
    for name, expected in config["remote"]["ancestors"].items():
        directory = Path(name)
        metadata = directory.lstat()
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == expected["uid"]
                and metadata.st_gid == expected["gid"]
                and stat.S_IMODE(metadata.st_mode) == int(expected["mode"], 8)
                and not metadata.st_mode & 0o022 and directory.resolve() == directory,
                "Remote ancestor ownership/mode mismatch: " + name)
    # The retained deployment is still protected, even though its parent is not
    # part of the new root's trust chain. Do not let redirection erase its identity.
    retained = Path("/opt/docker/eid")
    require(retained.resolve(strict=False) == retained,
            "Retained EID root must not be redirected")
    try:
        retained_metadata = retained.lstat()
    except FileNotFoundError:
        pass  # A fresh environment need not have a former deployment.
    else:
        require(stat.S_ISDIR(retained_metadata.st_mode),
                "Retained EID root must be a real directory when present")
    state = {"root_exists": target.exists() or target.is_symlink(), "receipt": None,
             "containers": [], "volumes": [], "networks": [], "listeners": []}
    if state["root_exists"]:
        metadata = target.lstat()
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_gid == 0
                and stat.S_IMODE(metadata.st_mode) == 0o700 and target.resolve() == target,
                "Remote EID root must be a real root-owned private directory (0700)")
        receipt = target / ".eid-remote-owner.json"
        metadata = receipt.lstat()
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_gid == 0
                and metadata.st_nlink == 1 and stat.S_IMODE(metadata.st_mode) == 0o600,
                "Remote ownership receipt is not a private regular root-owned file")
        require(metadata.st_size < 4096, "Oversized remote ownership receipt")
        state["receipt"] = json.loads(receipt.read_text())
    docker = ["docker", "--host", config["remote"]["docker_endpoint"]]

    def run(arguments, optional=False):
        result = subprocess.run(docker + arguments, capture_output=True, text=True, timeout=30)
        if optional and result.returncode:
            return ""
        require(result.returncode == 0, "Remote Docker inventory command failed")
        return result.stdout.strip()

    def runtime_configuration(settings):
        # Compare all image defaults and Compose overrides without returning secret values.
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()

        require(isinstance(settings, dict) and isinstance(settings.get("User"), str),
                "Missing or invalid remote runtime user")
        values = settings.get("Env") or []
        require(isinstance(values, list) and all(isinstance(value, str) and "=" in value
                for value in values), "Invalid remote container environment")
        environment = {value.partition("=")[0]: digest(value.partition("=")[2])
                       for value in values}
        require(len(environment) == len(values), "Duplicate remote container environment")
        arguments = {key: settings.get(key) or [] for key in ("Cmd", "Entrypoint")}
        require(all(isinstance(value, list) and all(isinstance(part, str) for part in value)
                    for value in arguments.values()), "Invalid remote container command")
        return {"command": digest(arguments["Cmd"]),
                "entrypoint": digest(arguments["Entrypoint"]), "environment": environment,
                "user": settings["User"],
                "healthcheck": inspected_healthcheck(settings.get("Healthcheck"))}

    state["server"] = json.loads(run(["version", "--format", "{{json .Server}}"]))
    state["compose"] = run(["compose", "version", "--short"])
    help_text = run(["compose", "up", "--help"])
    state["compose_wait"] = "--wait" in help_text and "--wait-timeout" in help_text
    state["buildx"] = run(["buildx", "version"], optional=True)
    listeners = subprocess.run(["ss", "-H", "-ltn"], capture_output=True, text=True, timeout=10)
    require(listeners.returncode == 0, "Cannot inspect remote host TCP listeners")
    for line in listeners.stdout.splitlines():
        fields = line.split()
        require(len(fields) >= 5, "Unknown remote listener inventory format")
        address, port = fields[3].rsplit(":", 1)
        state["listeners"].append({"address": address.strip("[]"), "port": int(port)})
    ids = run(["ps", "--all", "--quiet"]).split()
    for identifier in ids:
        item = json.loads(run(["inspect", identifier]))[0]
        # Deliberately omit raw environment/command values and log output.
        record = {
            "id": item["Id"], "name": item["Name"].lstrip("/"),
            "labels": item["Config"].get("Labels") or {},
            "ports": item["HostConfig"].get("PortBindings") or {},
            "mounts": [{key: mount.get(key) for key in ("Type", "Name", "Source", "Destination")}
                       for mount in item.get("Mounts", [])],
            "networks": list(item.get("NetworkSettings", {}).get("Networks", {})),
            "network_mode": item["HostConfig"].get("NetworkMode"),
            "state": item.get("State", {}).get("Status"),
        }
        if record["labels"].get("com.docker.compose.project") == config["remote"]["compose_project"]:
            host = item["HostConfig"]
            record["isolation_config"] = {key: host.get(key) for key in (
                "Privileged", "PidMode", "IpcMode", "UTSMode", "UsernsMode", "CgroupnsMode")}
            record["isolation_config"].update({key: host.get(key) or [] for key in (
                "CapAdd", "Devices", "DeviceRequests", "DeviceCgroupRules", "SecurityOpt",
                "VolumesFrom")})
            record["image_ref"] = item["Config"]["Image"]
            record["image_id"] = item["Image"]
            image = json.loads(run(["image", "inspect", record["image_id"]]))[0]
            reference = run(["image", "inspect", record["image_ref"]], optional=True)
            record["referenced_image_id"] = json.loads(reference)[0]["Id"] if reference else None
            record["image_labels"] = image.get("Config", {}).get("Labels") or {}
            record["runtime_config"] = runtime_configuration(item["Config"])
            record["image_runtime_config"] = runtime_configuration(image.get("Config") or {})
            record["health"] = item.get("State", {}).get("Health", {}).get("Status")
            if record["labels"].get("com.docker.compose.service") == "rabbitmq":
                record["hostname"] = item["Config"]["Hostname"]
                record["rabbitmq_identity_env"] = [value for value in item["Config"].get("Env", [])
                    if value.partition("=")[0] in {"RABBITMQ_NODENAME", "RABBITMQ_MNESIA_DIR",
                                                   "RABBITMQ_MNESIA_BASE", "RABBITMQ_USE_LONGNAME"}]
            for mount in record["mounts"]:
                if mount["Type"] == "bind":
                    source = Path(mount["Source"])
                    require(source.is_relative_to(target) and source.resolve(strict=True) == source,
                            "Remote bind mount source is linked or escapes EID root")
                    for ancestor in (source, *source.parents):
                        if ancestor == target:
                            break
                        metadata = ancestor.lstat()
                        require(metadata.st_uid == 0 and not metadata.st_mode & 0o022,
                                "Remote bind mount input is not protected by root")
                    metadata = source.lstat()
                    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
                            and metadata.st_size < 16 * 1024 * 1024, "Unsafe remote bind mount input")
                    mount["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            record["mounts"] = [{**mount, "RW": raw.get("RW")}
                                for mount, raw in zip(record["mounts"], item.get("Mounts", []))]
        for mount in record["mounts"]:
            if mount["Type"] == "bind":
                source = Path(mount["Source"])
                require(source.is_absolute(), "Remote bind mount source is not absolute")
                # A stopped foreign container may retain a deleted bind source. Resolve
                # existing symlinks before checking overlap, but tolerate missing tails.
                resolved = source.resolve(strict=False)
                ancestor = resolved
                while True:
                    try:
                        ancestor.lstat()
                        break
                    except FileNotFoundError:
                        require(ancestor.parent != ancestor, "Remote bind source has no existing ancestor")
                        ancestor = ancestor.parent
                require(ancestor.resolve(strict=True) == ancestor,
                        "Remote bind source ancestor cannot be resolved safely")
                if str(resolved) != mount["Source"]:
                    mount["OriginalSource"] = mount["Source"]
                mount["Source"] = str(resolved)
        record["mounts"].sort(key=lambda mount: json.dumps(mount, sort_keys=True))
        state["containers"].append(record)
    project = config["remote"]["compose_project"]
    for kind in ("volume", "network"):
        for name in run([kind, "ls", "--format", "{{.Name}}"]).splitlines():
            if name.startswith(project):
                item = json.loads(run([kind, "inspect", name]))[0]
                record = {"name": item["Name"],
                                           "labels": item.get("Labels") or {},
                                           "driver": item.get("Driver"),
                                           "options": item.get("Options") or {}}
                if kind == "volume":
                    mountpoint = Path(item["Mountpoint"])
                    require(mountpoint.is_absolute(), "Remote volume mountpoint is not absolute")
                    record["mountpoint"] = str(mountpoint.resolve(strict=True))
                state[kind + "s"].append(record)
    return state


def bind_mount_overlaps(config, state, mount):
    """A bind to a protected directory, descendant or ancestor is an EID attachment."""
    import posixpath
    from pathlib import PurePosixPath

    def normalized(value):
        require(isinstance(value, str) and value.startswith("/") and "\\" not in value
                and "\0" not in value, "Invalid remote resource path")
        return PurePosixPath(posixpath.normpath("/" + value.lstrip("/")))

    # The retained former deployment still belongs to EID; foreign attachments to
    # either location remain forbidden after the fixed-root contract changes.
    protected = [normalized(config["remote"]["root"]), normalized("/opt/docker/eid")]
    protected.extend(normalized(item.get("mountpoint")) for item in state["volumes"])
    if mount.get("Type") != "bind":
        return False
    sources = [normalized(mount.get("Source"))]
    if "OriginalSource" in mount:
        sources.append(normalized(mount["OriginalSource"]))
    return any(source.is_relative_to(path) or path.is_relative_to(source)
               for source in sources for path in protected)


def validate_remote_state(config, state, owner=None, *, require_running=False,
                          require_build=False):
    """Reject adopted resources, foreign attachments, listener collisions and host networks."""
    validate_config(config)
    project = config["remote"]["compose_project"]
    if owner is not None:
        validate_owner(owner)
    require(state["server"].get("Os") == "linux" and state["server"].get("Arch") == "amd64",
            "Remote Docker must run linux/amd64")
    require(state["compose_wait"], "Remote Compose lacks bounded --wait support")
    require(not require_build or bool(state["buildx"]), "Remote buildx is unavailable")
    require(not require_running or state["root_exists"], "Remote environment is not installed")
    if state["root_exists"]:
        require(owner is not None and state["receipt"] == owner_receipt(config, owner),
                "Remote ownership receipt mismatch; refusing adoption")
    else:
        require(state["receipt"] is None, "Unexpected ownership receipt without remote root")
    volume_names = {f"{project}-{name}" for name in VOLUME_SERVICES}
    network_name = project + "_default"

    def owned(labels):
        return bool(owner and state["root_exists"] and labels.get("io.eid.owner") == owner
                    and labels.get("io.eid.environment") == config["environment"]
                    and labels.get("com.docker.compose.project") == project)

    for kind, allowed, driver in (("volumes", volume_names, "local"),
                                  ("networks", {network_name}, "bridge")):
        for item in state[kind]:
            require(item["name"] in allowed and owned(item["labels"]),
                    f"Unowned or unexpected remote {kind} rejected")
            require(item["driver"] == driver and not item["options"],
                    f"Nonstandard remote {kind} driver/options rejected")
    # Also fail closed if the collector did not supply a volume's real host path.
    bind_mount_overlaps(config, state, {"Type": "volume"})
    found = {}
    for container in state["containers"]:
        labels = container["labels"]
        is_project = labels.get("com.docker.compose.project") == project
        relevant_name = container["name"].startswith(project)
        used_volumes = {mount.get("Name") for mount in container["mounts"]
                        if mount["Type"] == "volume"}
        attached = bool(used_volumes & volume_names or network_name in container["networks"]
                        or any(bind_mount_overlaps(config, state, mount)
                               for mount in container["mounts"]))
        if is_project or relevant_name or attached:
            require(is_project and owned(labels), "Foreign container owns or attaches to EID resources")
            service = labels.get("com.docker.compose.service")
            require(service in SERVICES and service not in found, "Unexpected or duplicate EID service")
            found[service] = container["state"]
            expected_ports = {f"{port}/tcp": [{"HostIp": "127.0.0.1",
                "HostPort": str(config["remote"]["ports"][name])}]
                for name, (target, port) in PORTS.items() if target == service}
            require(container["ports"] == expected_ports, "Remote service port binding differs")
            require(container["networks"] == [network_name]
                    and container["network_mode"] == network_name,
                    "Remote service uses a foreign or host network")
            isolation = container.get("isolation_config")
            expected_isolation = {"Privileged": False, "PidMode": "", "IpcMode": "private",
                "UTSMode": "", "UsernsMode": "", "CgroupnsMode": "private", "CapAdd": [],
                "Devices": [], "DeviceRequests": [], "DeviceCgroupRules": [], "SecurityOpt": [],
                "VolumesFrom": []}
            require(isolation == expected_isolation and isolation["Privileged"] is False,
                    "Remote service isolation configuration is not authorized: " + service)
            expected_volumes = {f"{project}-{service}"} if service in VOLUME_SERVICES else set()
            require(used_volumes == expected_volumes, "Remote service volume mapping differs")
            for mount in container["mounts"]:
                if mount["Type"] == "bind":
                    for value in (mount["Source"], mount.get("OriginalSource", mount["Source"])):
                        source = PurePosixPath(value)
                        require(source.is_relative_to(config["remote"]["root"])
                                and ".." not in source.parts, "Remote bind mount escapes EID root")
                else:
                    require(mount["Type"] == "volume", "Unsupported remote mount type")
        else:
            for bindings in container["ports"].values():
                for binding in bindings or []:
                    conflict = str(binding["HostPort"]) in {
                        str(port) for port in config["remote"]["ports"].values()}
                    require(not conflict or binding["HostIp"] not in {"", "0.0.0.0", "::",
                            "127.0.0.1", "::1"}, "An unrelated container occupies an EID port")
    if require_running:
        require(set(found) == SERVICES and set(found.values()) == {"running"},
                "The complete ten-service EID environment is not running")
        require({item["name"] for item in state["volumes"]} == volume_names
                and {item["name"] for item in state["networks"]} == {network_name},
                "Remote persistent resources are incomplete")
    for listener in state["listeners"]:
        if listener["address"] in {"*", "", "0.0.0.0", "::", "127.0.0.1", "::1"}:
            for name, port in config["remote"]["ports"].items():
                require(listener["port"] != port or PORTS[name][0] in found,
                        "An unmanaged host listener occupies an EID port")
    return {"environment": config["environment"], "host": config["ssh"]["hostname"],
            "root": config["remote"]["root"], "compose_project": project,
            "root_exists": state["root_exists"], "services": found,
            "docker_version": state["server"].get("Version"), "compose": state["compose"],
            "buildx_available": bool(state["buildx"]), "isolation_verified": True,
            "runtime_verified": False}


def ssh_options():
    return ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no",
            "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1", "-o", "ForwardAgent=no",
            "-o", "PermitLocalCommand=no", "-o", "ControlMaster=no", "-o", "ControlPath=none"]


def verify_ssh_config(config):
    result = subprocess.run(["ssh", *ssh_options(), "-G", config["ssh"]["alias"]],
                            capture_output=True, text=True, timeout=15)
    require(result.returncode == 0, "Cannot resolve SSH alias")
    resolved = {}
    for line in result.stdout.splitlines():
        fields = line.split(None, 1)
        require(len(fields) == 2, "Malformed effective SSH configuration")
        resolved.setdefault(fields[0].lower(), []).append(fields[1].strip())
    require(not {"localforward", "remoteforward", "dynamicforward"}.intersection(resolved),
            "Additional effective SSH forwarding configuration is forbidden")
    require(all(resolved.get(key) == [config["ssh"][setting]]
                for key, setting in (("hostname", "hostname"), ("user", "user"),
                                     ("proxyjump", "proxy_jump"))),
            "Effective SSH hostname/user/jump differs from YAML")
    require(resolved.get("port") == ["22"] and resolved.get("clearallforwardings") == ["no"],
            "Effective SSH port or forwarding mode differs from the reviewed contract")


def remote_inventory(config):
    validate_config(config)
    verify_ssh_config(config)
    # The inspected function's only external helpers are require and stdlib imports.
    program = ("import hashlib, json, os, stat, subprocess, sys\nfrom pathlib import Path\n"
               "class RemoteEnvironmentError(RuntimeError): pass\n" + inspect.getsource(require)
               + "\n" + inspect.getsource(inspected_healthcheck)
               + "\n" + inspect.getsource(collect_remote_state)
               + "\ntry:\n print(json.dumps(collect_remote_state(json.loads(sys.argv[1]), "
               "sys.argv[2])))\nexcept RemoteEnvironmentError as exc:\n"
               " print(str(exc), file=sys.stderr)\n sys.exit(1)\nexcept Exception:\n"
               " print('Remote isolation inventory failed', file=sys.stderr)\n sys.exit(1)\n")
    encoded = base64.b64encode(program.encode()).decode()
    boot = f"import base64; exec(base64.b64decode('{encoded}'))"
    command = "sudo -n python3 -c " + shlex.quote(boot) + " " + shlex.quote(json.dumps(config))
    command += ' "$SSH_CONNECTION"'
    result = subprocess.run(["ssh", *ssh_options(), "-o", "ClearAllForwardings=yes", "-T",
                             config["ssh"]["alias"], command],
                            capture_output=True, text=True, timeout=180)
    # Only controlled guard messages are emitted by the remote program, never tool stderr/env.
    require(result.returncode == 0, "Remote isolation probe failed: " + result.stderr.strip()[:512])
    return json.loads(result.stdout)


def remote_check(config, owner=None, *, require_running=False, require_build=False):
    return validate_remote_state(config, remote_inventory(config), owner,
                                 require_running=require_running, require_build=require_build)


def tunnel_command(config):
    validate_config(config)
    # Pin the live process's destination, so a later SSH-config edit cannot make an
    # old alias-based tunnel appear to point to the currently approved host.
    arguments = ["ssh", *ssh_options(), "-o", "Hostname=" + config["ssh"]["hostname"],
                 "-o", "User=" + config["ssh"]["user"],
                 "-o", "Port=22",
                 "-o", "ProxyJump=" + config["ssh"]["proxy_jump"],
                 "-o", "ExitOnForwardFailure=yes", "-N", "-T"]
    for name, local_port in config["tunnels"]["ports"].items():
        arguments += ["-L", f"127.0.0.1:{local_port}:127.0.0.1:{config['remote']['ports'][name]}"]
    return arguments + [config["ssh"]["alias"]]


def windows_command_line(arguments):
    import ctypes
    from ctypes import wintypes

    count = ctypes.c_int()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    pointer = parse(arguments, ctypes.byref(count))
    require(bool(pointer), "Cannot parse SSH tunnel process arguments")
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free(pointer)


def tunnel_inventory(config):
    """Read actual listener owners, not a claimed PID file or an old tunnel receipt."""
    require(os.name == "nt", "Tunnel process verification currently requires the Windows workstation")
    ports = ",".join(str(port) for port in config["tunnels"]["ports"].values())
    program = (
        "$ErrorActionPreference='Stop'; $eidPorts=@(" + ports + "); "
        "$eidAllListeners=@(Get-NetTCPConnection -State Listen); "
        "$eidOwners=@($eidAllListeners | Where-Object {$_.LocalPort -in $eidPorts} | "
        "Select-Object -ExpandProperty OwningProcess -Unique); "
        "$eidListeners=@($eidAllListeners | Where-Object {"
        "$_.LocalPort -in $eidPorts -or $_.OwningProcess -in $eidOwners} | "
        "Select-Object LocalAddress,LocalPort,OwningProcess); "
        "$eidProcesses=@($eidOwners | ForEach-Object {"
        "Get-CimInstance Win32_Process -Filter ('ProcessId = '+$_) | "
        "Select-Object ProcessId,ExecutablePath,CommandLine,CreationDate}); "
        "@{listeners=$eidListeners;processes=$eidProcesses} | ConvertTo-Json -Depth 4 -Compress"
    )
    encoded = base64.b64encode(program.encode("utf-16le")).decode()
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                             encoded], capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, "Cannot verify Windows SSH tunnel listeners/processes")
    snapshot = json.loads(result.stdout)
    for process in snapshot["processes"]:
        process["argv"] = windows_command_line(process["CommandLine"] or "")
        del process["CommandLine"]
    return snapshot


def validate_tunnels(config, snapshot, ssh_executable):
    expected_ports = set(config["tunnels"]["ports"].values())
    listeners = snapshot["listeners"]
    require(len(listeners) == len(expected_ports) and {
        item["LocalPort"] for item in listeners} == expected_ports,
        "SSH tunnel listeners are missing, competing, or include additional process listeners")
    require(all(item["LocalAddress"] == "127.0.0.1" for item in listeners),
            "Tunnel listener must bind exclusively to IPv4 loopback")
    owners = {item["OwningProcess"] for item in listeners}
    require(len(owners) == 1 and len(snapshot["processes"]) == 1,
            "All EID tunnels must belong to one verified SSH process")
    process = snapshot["processes"][0]
    require(process["ProcessId"] in owners and process["CreationDate"],
            "Tunnel process identity differs from socket ownership")
    require(ssh_executable and process["ExecutablePath"] and
            Path(process["ExecutablePath"]).resolve() == Path(ssh_executable).resolve(),
            "Tunnel listener is not the selected OpenSSH executable")
    require(process["argv"][1:] == tunnel_command(config)[1:],
            "SSH tunnel process arguments differ from the selected forwarding contract")
    return {"pid": process["ProcessId"], "started": process["CreationDate"],
            "ports": config["tunnels"]["ports"]}


def verify_tunnels(config):
    verify_ssh_config(config)
    return validate_tunnels(config, tunnel_inventory(config), shutil.which("ssh"))


def configuration_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def candidate_healthcheck(definition, image_healthcheck):
    """Apply Compose overrides to the image probe with Docker's nanosecond/default semantics."""
    from decimal import Decimal

    healthcheck = definition.get("healthcheck")
    if healthcheck is None:
        return copy.deepcopy(image_healthcheck)
    require(isinstance(healthcheck, dict) and set(healthcheck) <= {
        "test", "interval", "timeout", "retries", "start_period", "start_interval", "disable"},
        "Unsupported Compose health check")
    require(type(healthcheck.get("disable", False)) is bool, "Invalid Compose health check disable")
    if healthcheck.get("disable"):
        return None
    result = copy.deepcopy(image_healthcheck)
    test = healthcheck.get("test")
    if test is not None:
        if isinstance(test, str):
            test = ["CMD-SHELL", test]
        require(isinstance(test, list) and all(isinstance(part, str) for part in test),
                "Invalid Compose health check test")
        probe = inspected_healthcheck({"Test": [part.replace("$$", "$") for part in test]})
        if probe is None:
            return None
        if result is None:
            result = probe
        else:
            result["Test"] = probe["Test"]
    require(result is not None, "Compose health check has no image or explicit probe")
    units = {"h": 3_600_000_000_000, "m": 60_000_000_000, "s": 1_000_000_000,
             "ms": 1_000_000, "us": 1000, "µs": 1000, "ns": 1}
    for key, field in (("interval", "Interval"), ("timeout", "Timeout"),
                       ("start_period", "StartPeriod"), ("start_interval", "StartInterval")):
        if key not in healthcheck:
            continue
        value = healthcheck[key]
        require(isinstance(value, str), "Compose health check duration must use explicit units")
        parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|us|µs|ns|h|m|s)", value)
        require(bool(parts) and "".join(number + unit for number, unit in parts) == value,
                "Invalid Compose health check duration")
        nanoseconds = sum(Decimal(number) * units[unit] for number, unit in parts)
        require(nanoseconds == int(nanoseconds), "Sub-nanosecond health check budget")
        if nanoseconds:
            result[field] = int(nanoseconds)
    if "retries" in healthcheck:
        retries = healthcheck["retries"]
        require(type(retries) is int and retries >= 0, "Invalid Compose health check retries")
        if retries:
            result["Retries"] = retries
    return result


def candidate_runtime_config(definition, image_config):
    """Merge rendered Compose overrides with hashed defaults from the exact inspected image."""
    require(isinstance(image_config, dict)
            and set(image_config) == {"command", "entrypoint", "environment", "healthcheck", "user"}
            and isinstance(image_config["environment"], dict)
            and isinstance(image_config["user"], str),
            "Missing remote image runtime configuration")
    result = copy.deepcopy(image_config)
    if "user" in definition:
        require(isinstance(definition["user"], str), "Unsupported Compose user")
        # Docker inherits the image user for an empty override; an empty image user
        # means the engine's root default, and must remain distinct from missing data.
        if definition["user"]:
            result["user"] = definition["user"].replace("$$", "$")
    for key, field in (("command", "command"), ("entrypoint", "entrypoint")):
        value = definition.get(key)
        if value is not None:
            if isinstance(value, str):
                value = shlex.split(value)
            require(isinstance(value, list) and all(isinstance(part, str) for part in value),
                    "Unsupported Compose command/entrypoint")
            result[field] = configuration_digest([part.replace("$$", "$") for part in value])
        elif key == "command" and definition.get("entrypoint") is not None:
            result[field] = configuration_digest([])
    environment = definition.get("environment") or {}
    require(isinstance(environment, dict) and all(isinstance(key, str) and isinstance(value, str)
            for key, value in environment.items()), "Unsupported Compose environment values")
    result["environment"].update({key: configuration_digest(value.replace("$$", "$"))
                                  for key, value in environment.items()})
    result["healthcheck"] = candidate_healthcheck(definition, image_config["healthcheck"])
    return result


def validate_guard_state(config, state, owner, *, require_running=False):
    """Check migration ownership by default; bind all services to the final candidate on demand."""
    validate_remote_state(config, state, owner, require_running=require_running)
    require(state["root_exists"], "Remote environment is not installed")
    lock = json.loads((ROOT / "deployment/images.lock.json").read_text(encoding="utf-8"))
    binds = {
        "postgres": {"/docker-entrypoint-initdb.d/001-isolated-database.sql":
                     "deployment/postgres/001-isolated-database.sql"},
        "keycloak": {"/opt/keycloak/data/import/eid-local-realm.json":
                     "deployment/keycloak/eid-local-realm.json"},
        "seaweedfs": {"/etc/eid/s3.json": "deployment/seaweedfs/s3.json"},
        "nginx": {"/etc/nginx/conf.d/default.conf": "deployment/nginx/default.conf"},
    }
    volumes = {"postgres": "/var/lib/postgresql/data", "keycloak": "/opt/keycloak/data",
               "seaweedfs": "/data", "rabbitmq": "/var/lib/rabbitmq", "redis": "/data"}
    from scripts.verify_local_environment import source_fingerprint

    candidate = yaml.safe_load(render_compose(config, owner, source_files(ROOT))) if require_running else None
    found = {}
    for container in state["containers"]:
        if container["labels"].get("com.docker.compose.project") != config["remote"]["compose_project"]:
            continue
        service = container["labels"]["com.docker.compose.service"]
        found[service] = container
        if service in {"api", "worker", "worker-scheduler"}:
            user = (container.get("runtime_config") or {}).get("user")
            require(isinstance(user, str) and bool(user),
                    "Remote Python service requires a non-root runtime user: " + service)
            account = user.partition(":")[0]
            require(bool(account) and account != "root"
                    and not (re.fullmatch(r"[+-]?[0-9]+", account) and int(account) == 0),
                    "Remote Python service requires a non-root runtime user: " + service)
        candidate_required = require_running or service in VOLUME_SERVICES
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", container["image_id"]),
                "Invalid remote image ID: " + service)
        if candidate_required:
            require(container["state"] == "running", "Remote EID service is not running: " + service)
            require(container["image_id"] == container["referenced_image_id"],
                    "Remote running image ID differs from its reference: " + service)
            if service in APPLICATION_IMAGES:
                image_service = APPLICATION_IMAGES[service]
                fingerprint = source_fingerprint(image_service)
                expected_image = (f"{config['remote']['compose_project']}-{image_service}:"
                                  f"{fingerprint[7:23]}")
                require(container["image_labels"].get("io.eid.source-fingerprint") == fingerprint,
                        "Remote image source fingerprint differs from current candidate: " + service)
            else:
                expected_image = lock["base_images"][service]
            require(container["image_ref"] == expected_image,
                    "Remote image reference differs from locked candidate: " + service)
        if require_running:
            expected_config = candidate_runtime_config(candidate["services"][service],
                                                       container.get("image_runtime_config"))
            require(container.get("runtime_config") == expected_config,
                    "Remote runtime configuration differs from current candidate: " + service)
        if service == "rabbitmq":
            identity = config["remote"]["rabbitmq_identity"]
            require(container.get("hostname") == identity["hostname"],
                    "Remote RabbitMQ hostname differs from the verified existing node")
            values = container.get("rabbitmq_identity_env", [])
            environment = dict(value.split("=", 1) for value in values)
            require(len(environment) == len(values), "Duplicate remote RabbitMQ identity settings")
            expected = {"RABBITMQ_NODENAME": identity["nodename"],
                        "RABBITMQ_MNESIA_DIR": identity["data_dir"]}
            require(all(environment.get(key, value) == value for key, value in expected.items())
                    and environment.get("RABBITMQ_MNESIA_BASE", "/var/lib/rabbitmq/mnesia") ==
                    "/var/lib/rabbitmq/mnesia"
                    and environment.get("RABBITMQ_USE_LONGNAME", "false") == "false",
                    "Remote RabbitMQ node/data identity differs from the verified existing node")
            require(not require_running or expected.items() <= environment.items(),
                    "Final RabbitMQ candidate must explicitly preserve node/data identity")
        actual_binds = {mount["Destination"]: mount for mount in container["mounts"]
                        if mount["Type"] == "bind"}
        expected_binds = binds.get(service, {})
        require(len(actual_binds) == sum(mount["Type"] == "bind" for mount in container["mounts"])
                and set(actual_binds) == set(expected_binds), "Remote bind mount destinations differ")
        for destination, relative in expected_binds.items():
            mount = actual_binds[destination]
            require(mount.get("RW") is False and (not candidate_required or mount.get("sha256") ==
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()),
                    "Remote mounted configuration differs from current candidate: " + service)
        actual_volumes = [mount for mount in container["mounts"] if mount["Type"] == "volume"]
        require(len(actual_volumes) == int(service in volumes), "Remote volume count differs")
        if actual_volumes:
            require(actual_volumes[0]["Destination"] == volumes[service], "Remote data volume destination differs")
    require(VOLUME_SERVICES.issubset(found), "Remote infrastructure is incomplete")
    return found


def guarded_inventory(config, *, require_running=False):
    receipt = read_owner(config)
    tunnels = verify_tunnels(config)
    state = remote_inventory(config)
    containers = validate_guard_state(config, state, receipt["nonce"], require_running=require_running)
    require(read_owner(config) == receipt and verify_tunnels(config) == tunnels,
            "Remote ownership or tunnel process changed during verification")
    return receipt, state, containers, tunnels


def guarded_service(config, service, container_port, local_port):
    names = [name for name, target in PORTS.items() if target == (service, container_port)]
    require(len(names) == 1 and config["tunnels"]["ports"][names[0]] == local_port,
            "Requested client endpoint differs from the selected SSH tunnel")
    _, _, containers, _ = guarded_inventory(config)
    require(service in containers, "Remote service is missing: " + service)
    return containers[service]["id"]


def runtime_manifest(config, receipt, state, containers, fingerprints, candidate):
    """One complete manifest contract shared by runtime recording and operation capture."""
    definitions = yaml.safe_load(candidate)["services"]
    require(set(containers) == SERVICES and set(definitions) == SERVICES,
            "Remote runtime manifest requires the complete ten-service candidate")
    records = {}
    for service, container in containers.items():
        require(container["health"] == "healthy" or
                (not definitions[service].get("healthcheck")
                 and not container["runtime_config"].get("healthcheck")
                 and container["health"] is None),
                "Remote service health check failed: " + service)
        record = {"image_ref": container["image_ref"], "image_id": container["image_id"],
                  "container_id": container["id"],
                  "runtime_config_sha256": configuration_digest({
                      "process": container["runtime_config"],
                      "isolation": container["isolation_config"]})}
        if service in APPLICATION_IMAGES:
            record["source_fingerprint"] = fingerprints[APPLICATION_IMAGES[service]]
        records[service] = record
    return {"schema_version": 3, "source_fingerprint_algorithm": "sha256", "services": records,
            "provenance": {"environment": config["environment"], "ssh": config["ssh"],
                           "remote_root": config["remote"]["root"],
                           "compose_project": config["remote"]["compose_project"],
                           "owner": receipt["nonce"], "docker_server": state["server"],
                           "compose_sha256": hashlib.sha256(candidate).hexdigest()}}


def runtime_images(config, expected_source_fingerprints=None):
    from scripts.verify_local_environment import source_fingerprints

    fingerprints = source_fingerprints()
    require(expected_source_fingerprints is None or expected_source_fingerprints == fingerprints,
            "Source differs from the captured build candidate")
    receipt, state, containers, tunnels = guarded_inventory(config, require_running=True)
    candidate = render_compose(config, receipt["nonce"], source_files(ROOT))
    manifest = runtime_manifest(config, receipt, state, containers, fingerprints, candidate)
    final_receipt, _, final_containers, final_tunnels = guarded_inventory(config, require_running=True)
    require(receipt == final_receipt and containers == final_containers and tunnels == final_tunnels
            and source_fingerprints() == fingerprints
            and render_compose(config, receipt["nonce"], source_files(ROOT)) == candidate,
            "Remote candidate changed during runtime verification")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("render", "package", "check", "inspect", "tunnel-command"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--owner", help="Persist one random nonce per remote environment")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-build", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.action in {"render", "package"}:
        require(args.output is not None, "An explicit unused --output path is required")
        result = create_artifact(config, validate_owner(args.owner), args.output,
                                 package=args.action == "package")
    elif args.action == "tunnel-command":
        verify_ssh_config(config)
        result = {"argv": tunnel_command(config), "runtime_verified": False}
    else:
        result = remote_check(config, args.owner, require_running=args.action == "inspect",
                              require_build=args.require_build)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RemoteEnvironmentError, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError, yaml.YAMLError) as exc:
        print(f"Remote environment operation refused: {exc}", file=sys.stderr)
        sys.exit(1)
