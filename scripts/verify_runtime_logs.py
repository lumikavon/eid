"""Read owned service logs and report only redacted match counts."""

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from scripts.verify_local_environment import ownership, remote_config, verify_runtime_images


PROJECT = "eid-local"
EXPECTED_SERVICES = (
    "postgres",
    "keycloak",
    "rabbitmq",
    "redis",
    "seaweedfs",
    "api",
    "worker",
    "worker-scheduler",
    "web",
    "nginx",
)
LOCAL_CREDENTIALS = {
    "browser_password": "eid-local-member",
    "access_fixture_password": "eid-local-access",
    "postgres_admin_password": "local-postgres-admin-only",
    "keycloak_admin_password": "local-keycloak-admin-only",
    "keycloak_monitor_client_secret": "local-keycloak-readiness-monitor-only",
    "postgres_migrator_password": "local-migrate-only",
    "postgres_api_password": "local-api-only",
    "postgres_worker_password": "local-worker-only",
    "rabbitmq_bootstrap_admin_password": "local-rabbitmq-bootstrap-admin-only",
    "rabbitmq_worker_password": "local-worker-only",
    "rabbitmq_api_password": "local-api-broker-only",
    "s3_bootstrap_secret_key": "local-s3-bootstrap-admin-only",
    "s3_api_secret_key": "local-s3-api-read-only",
    "s3_worker_secret_key": "local-s3-worker-read-only",
}


def _owned_service_containers(owner_nonce: str) -> dict[str, str]:
    if remote_config() is not None:
        raise RuntimeError("Remote environment cannot inspect local Docker containers")
    try:
        output = subprocess.check_output(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={PROJECT}",
            ],
            text=True,
            timeout=30,
        )
        container_ids = [item for item in output.splitlines() if item]
        services = {}
        if len(container_ids) != len(EXPECTED_SERVICES):
            raise RuntimeError("Runtime log service inventory does not match Compose")
        inspections = json.loads(subprocess.check_output(
            ["docker", "inspect", *container_ids], text=True, timeout=30))
        if not isinstance(inspections, list) or len(inspections) != len(container_ids):
            raise RuntimeError("Runtime log inspection inventory does not match Compose")
        for container_id, inspected in zip(container_ids, inspections, strict=True):
            if not isinstance(inspected.get("Id"), str) or not inspected["Id"].startswith(container_id):
                raise RuntimeError("Runtime log inspected container identity changed")
            labels = (inspected.get("Config") or {}).get("Labels") or {}
            service = labels.get("com.docker.compose.service")
            if (
                labels.get("com.docker.compose.project") != PROJECT
                or labels.get("io.eid.owner") != owner_nonce
            ):
                raise RuntimeError("Refusing log inspection outside the owned EID project")
            if service not in EXPECTED_SERVICES or service in services:
                raise RuntimeError("Runtime log service inventory does not match Compose")
            if not (inspected.get("State") or {}).get("Running"):
                raise RuntimeError(f"Unable to inspect stopped {service} service logs")
            services[service] = container_id
    except (subprocess.SubprocessError, json.JSONDecodeError, IndexError, KeyError) as exc:
        raise RuntimeError("Unable to verify owned runtime log containers") from exc
    if set(services) != set(EXPECTED_SERVICES):
        raise RuntimeError("Runtime log service inventory does not match Compose")
    return services


def scan_runtime_logs() -> dict:
    config = remote_config()
    remote_runtime = None
    if config is not None:
        from scripts.remote_service_operations import RemoteRuntime

        runtime_images = verify_runtime_images()
        remote_runtime = RemoteRuntime(config, runtime_images)
        containers = remote_runtime.container_ids
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            image_check = executor.submit(verify_runtime_images)
            state = ownership(create=False)
            containers = _owned_service_containers(state["nonce"])
            runtime_images = image_check.result()
    recorded_services = runtime_images["services"]
    if set(containers) != set(EXPECTED_SERVICES) or set(recorded_services) != set(EXPECTED_SERVICES):
        raise RuntimeError("Runtime log service inventory does not match Compose")
    if any(
        recorded_services[service]["container_id"] != containers[service]
        for service in EXPECTED_SERVICES
    ):
        raise RuntimeError("Runtime image manifest does not match scanned containers")
    credential_values = sorted(set(LOCAL_CREDENTIALS.values()), key=lambda value: (-len(value), value))
    rules = {
        "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"),
        "token_value": re.compile(
            r"(?:access_token|id_token|refresh_token)[=\"':\s]+[A-Za-z0-9_.-]{12,}",
            re.IGNORECASE,
        ),
        "authorization_code_url": re.compile(r"[?&]code=[^\s&\"]+"),
        "bearer_value": re.compile(r"bearer\s+[A-Za-z0-9_.-]{12,}", re.IGNORECASE),
        "local_credential": re.compile("|".join(map(re.escape, credential_values))),
    }
    results = {}
    cutoff = datetime.now(timezone.utc).isoformat()
    for service in EXPECTED_SERVICES:
        if remote_runtime is not None:
            completed = remote_runtime.run(service, "logs", cutoff=cutoff)
            log = completed["stdout"] + completed["stderr"]
        else:
            log = _local_service_logs(service, containers[service], cutoff)
        results[service] = {
            "matches": {name: len(rule.findall(log)) for name, rule in rules.items()},
        }
    if config is not None:
        if remote_config() != config:
            raise RuntimeError("Runtime environment selection changed during log scan")
        remote_runtime.verify_unchanged()
        final_runtime_images = verify_runtime_images()
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            image_check = executor.submit(verify_runtime_images)
            final_state = ownership(create=False)
            final_containers = _owned_service_containers(state["nonce"])
            final_runtime_images = image_check.result()
        if final_state.get("nonce") != state["nonce"]:
            raise RuntimeError("Runtime ownership changed during log scan")
        if final_containers != containers:
            raise RuntimeError("Runtime container inventory changed during scan")
    if final_runtime_images != runtime_images:
        raise RuntimeError("Runtime image or source binding changed during log scan")
    return {
        "project": config["remote"]["compose_project"] if config is not None else PROJECT,
        "log_cutoff_utc": cutoff,
        "passed": all(
            not count for result in results.values() for count in result["matches"].values()
        ),
        "credential_inventory": sorted(LOCAL_CREDENTIALS),
        "runtime_images": runtime_images,
        "scanned_container_ids": containers,
        "services": results,
    }


def _local_service_logs(service, identifier, cutoff):
    # Also guard the legacy path at the actual command boundary.
    if remote_config() is not None:
        raise RuntimeError("Remote environment cannot read local Docker logs")
    try:
        completed = subprocess.run(
            ["docker", "logs", "--until", cutoff, identifier],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.SubprocessError as exc:
        raise RuntimeError(f"Unable to inspect {service} logs") from exc
    if completed.returncode:
        raise RuntimeError(f"Unable to inspect {service} logs")
    return completed.stdout + completed.stderr


if __name__ == "__main__":
    result = scan_runtime_logs()
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
