"""Read owned local service logs and report only redacted match counts."""

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from scripts.verify_local_environment import ownership, verify_runtime_images


PROJECT = "eid-local"
EXPECTED_SERVICES = (
    "postgres",
    "keycloak",
    "rabbitmq",
    "redis",
    "seaweedfs",
    "api",
    "worker",
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
    with ThreadPoolExecutor(max_workers=2) as executor:
        image_check = executor.submit(verify_runtime_images)
        state = ownership(create=False)
        containers = _owned_service_containers(state["nonce"])
        runtime_images = image_check.result()
    recorded_services = runtime_images["services"]
    if any(
        recorded_services[service]["container_id"] != containers[service]
        for service in ("api", "worker", "web")
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
        try:
            completed = subprocess.run(
                ["docker", "logs", "--until", cutoff, containers[service]],
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
        log = completed.stdout + completed.stderr
        results[service] = {
            "matches": {name: len(rule.findall(log)) for name, rule in rules.items()},
        }
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
        "project": PROJECT,
        "log_cutoff_utc": cutoff,
        "passed": all(
            not count for result in results.values() for count in result["matches"].values()
        ),
        "credential_inventory": sorted(LOCAL_CREDENTIALS),
        "runtime_images": runtime_images,
        "scanned_container_ids": containers,
        "services": results,
    }


if __name__ == "__main__":
    result = scan_runtime_logs()
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
