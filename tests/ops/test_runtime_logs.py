"""Runtime log gate unit tests; Docker access is replaced with bounded fixtures."""

import json
import subprocess

import pytest

from scripts import verify_runtime_logs


def _runtime_fixture(
    monkeypatch,
    logs=None,
    *,
    missing=None,
    foreign=None,
    manifest_mismatch=False,
    replace_after_logs=None,
    source_change_after_logs=False,
):
    services = [
        service for service in verify_runtime_logs.EXPECTED_SERVICES if service != missing
    ]
    container_ids = {service: f"container-{service}" for service in services}
    monkeypatch.setattr(
        verify_runtime_logs, "ownership", lambda create=False: {"nonce": "owned-nonce"}
    )
    manifest = {
        "schema_version": 1,
        "source_fingerprint_algorithm": "sha256",
        "services": {
            service: {
                "image_ref": f"eid-local-{service}:0.1.0",
                "image_id": f"sha256:{service:0<64}"[:71],
                "container_id": (
                    "different-container"
                    if manifest_mismatch and service == "api"
                    else container_ids[service]
                ),
                "source_fingerprint": f"sha256:{service:0<64}"[:71],
            }
            for service in ("api", "worker", "web")
        },
    }
    runtime_verifications = 0

    def verify_images():
        nonlocal runtime_verifications
        runtime_verifications += 1
        if source_change_after_logs and runtime_verifications > 1:
            raise RuntimeError("runtime source binding changed")
        return manifest

    monkeypatch.setattr(verify_runtime_logs, "verify_runtime_images", verify_images)

    def check_output(args, **kwargs):
        del kwargs
        if args[1:3] == ["ps", "-aq"]:
            return "\n".join(container_ids.values())
        if args[1] == "inspect":
            container_id = args[2]
            service = next(
                name for name, candidate in container_ids.items() if candidate == container_id
            )
            owner = "foreign-nonce" if service == foreign else "owned-nonce"
            return json.dumps(
                [
                    {
                        "Config": {
                            "Labels": {
                                "com.docker.compose.project": "eid-local",
                                "com.docker.compose.service": service,
                                "io.eid.owner": owner,
                            }
                        },
                        "State": {"Running": True},
                    }
                ]
            )
        raise AssertionError(args)

    def run(args, **kwargs):
        del kwargs
        service = next(
            name for name, candidate in container_ids.items() if candidate == args[2]
        )
        value = (logs or {}).get(service, "ordinary service output")
        if service == verify_runtime_logs.EXPECTED_SERVICES[-1] and replace_after_logs:
            container_ids[replace_after_logs] = f"replacement-{replace_after_logs}"
        if isinstance(value, int):
            return subprocess.CompletedProcess(args, value, stdout="", stderr="read failure")
        return subprocess.CompletedProcess(args, 0, stdout=value, stderr="")

    monkeypatch.setattr(verify_runtime_logs.subprocess, "check_output", check_output)
    monkeypatch.setattr(verify_runtime_logs.subprocess, "run", run)
    return container_ids


def test_scan_matches_every_pattern_class_and_complete_credential_inventory(monkeypatch):
    assert verify_runtime_logs.LOCAL_CREDENTIALS == {
        "browser_password": "eid-local-member",
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
    credentials = list(dict.fromkeys(verify_runtime_logs.LOCAL_CREDENTIALS.values()))
    logs = {
        "postgres": "eyJabcdefgh.ijklmnop.signature",
        "keycloak": 'access_token="abcdefghijkl"',
        "rabbitmq": "GET /callback?code=secret-code&state=ok",
        "redis": "Authorization: Bearer abcdefghijkl",
    }
    for service, credential in zip(
        verify_runtime_logs.EXPECTED_SERVICES[4:], credentials, strict=False
    ):
        logs[service] = " ".join([logs.get(service, ""), credential])
    if len(credentials) > 5:
        logs["nginx"] += " " + " ".join(credentials[5:])
    container_ids = _runtime_fixture(monkeypatch, logs)

    report = verify_runtime_logs.scan_runtime_logs()

    assert report["passed"] is False
    assert set(report["services"]) == set(verify_runtime_logs.EXPECTED_SERVICES)
    assert report["scanned_container_ids"] == container_ids
    assert report["credential_inventory"] == sorted(verify_runtime_logs.LOCAL_CREDENTIALS)
    totals = {
        pattern: sum(service["matches"][pattern] for service in report["services"].values())
        for pattern in ("jwt", "token_value", "authorization_code_url", "bearer_value", "local_credential")
    }
    assert all(count > 0 for count in totals.values())
    assert all(set(service) == {"matches"} for service in report["services"].values())
    encoded = json.dumps(report)
    assert all(secret not in encoded for secret in credentials)


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER", "bEaReR"])
def test_scan_rejects_bearer_scheme_case_variants(monkeypatch, scheme):
    _runtime_fixture(monkeypatch, {"api": f"Authorization: {scheme} abcdefghijkl"})
    report = verify_runtime_logs.scan_runtime_logs()
    assert report["passed"] is False
    assert report["services"]["api"]["matches"]["bearer_value"] == 1


@pytest.mark.parametrize("field", ["access_token", "ACCESS_TOKEN", "Id_ToKeN", "REFRESH_TOKEN"])
def test_scan_rejects_token_field_case_variants(monkeypatch, field):
    _runtime_fixture(monkeypatch, {"api": f'{field}="abcdefghijkl"'})
    report = verify_runtime_logs.scan_runtime_logs()
    assert report["passed"] is False
    assert report["services"]["api"]["matches"]["token_value"] == 1


def test_scan_clean_owned_nine_service_runtime_passes(monkeypatch):
    container_ids = _runtime_fixture(monkeypatch)

    report = verify_runtime_logs.scan_runtime_logs()

    assert report["passed"] is True
    assert report["scanned_container_ids"] == container_ids
    assert all(
        count == 0
        for service in report["services"].values()
        for count in service["matches"].values()
    )


def test_scan_rejects_missing_expected_service(monkeypatch):
    _runtime_fixture(monkeypatch, missing="nginx")

    with pytest.raises(RuntimeError, match="inventory does not match Compose"):
        verify_runtime_logs.scan_runtime_logs()


def test_scan_rejects_foreign_owner(monkeypatch):
    _runtime_fixture(monkeypatch, foreign="redis")

    with pytest.raises(RuntimeError, match="outside the owned EID project"):
        verify_runtime_logs.scan_runtime_logs()


def test_scan_rejects_log_read_failure(monkeypatch):
    _runtime_fixture(monkeypatch, {"worker": 1})

    with pytest.raises(RuntimeError, match="Unable to inspect worker logs"):
        verify_runtime_logs.scan_runtime_logs()


def test_scan_rejects_runtime_manifest_container_mismatch(monkeypatch):
    _runtime_fixture(monkeypatch, manifest_mismatch=True)

    with pytest.raises(RuntimeError, match="manifest does not match scanned containers"):
        verify_runtime_logs.scan_runtime_logs()


def test_scan_rejects_container_replaced_after_its_logs_are_read(monkeypatch):
    _runtime_fixture(monkeypatch, replace_after_logs="api")

    with pytest.raises(RuntimeError, match="changed during scan"):
        verify_runtime_logs.scan_runtime_logs()


def test_scan_rejects_source_binding_changed_after_logs_are_read(monkeypatch):
    _runtime_fixture(monkeypatch, source_change_after_logs=True)

    with pytest.raises(RuntimeError, match="source binding changed"):
        verify_runtime_logs.scan_runtime_logs()
