import json
import re

import pytest
from botocore.exceptions import ClientError

from scripts.verify_local_environment import (
    IsolationError,
    ownership,
    record_runtime_images,
    validate_url,
    verify_database,
    verify_engine,
    verify_image_manifest,
    verify_keycloak,
    verify_rabbitmq,
    verify_runtime_images,
    verify_s3_configuration,
    verify_versions,
)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://eid_migrator:p@production:55432/eid_local_dev",
        "postgresql://eid_migrator:p@localhost:5432/eid_local_dev",
        "postgresql://postgres:p@localhost:55432/eid_local_dev",
        "postgresql://eid_migrator:p@localhost:55432/enterprise",
        "postgresql://eid_migrator:p@localhost:55432/eid_local_dev?host=production",
        "",
    ],
)
def test_foreign_targets_rejected(url):
    with pytest.raises(IsolationError):
        validate_url(url)


def test_local_target_accepted():
    validate_url("postgresql+psycopg://eid_migrator:p@localhost:55432/eid_local_dev")


@pytest.mark.parametrize(
    ("context_name", "endpoint", "os_type", "arch", "message"),
    [
        ("remote", "npipe://./pipe/docker_engine", "linux", "amd64", "desktop-linux"),
        ("desktop-linux", "tcp://remote.example:2376", "linux", "amd64", "远程 Docker"),
        ("desktop-linux", "npipe://./pipe/docker_engine", "windows", "amd64", "linux/amd64"),
        ("desktop-linux", "npipe://./pipe/docker_engine", "linux", "arm64", "linux/amd64"),
    ],
)
def test_verify_engine_rejects_nonlocal_or_windows_engine(
    monkeypatch, context_name, endpoint, os_type, arch, message
):
    import scripts.verify_local_environment as guard

    def fake_command(*args):
        if args[1:3] == ("context", "inspect"):
            return json.dumps(
                [{"Name": context_name, "Endpoints": {"docker": {"Host": endpoint}}}]
            )
        if args[1:3] == ("version", "--format"):
            return json.dumps({"Os": os_type, "Arch": arch, "Version": "29.1.3", "ApiVersion": "1.52"})
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)
    with pytest.raises(IsolationError, match=message):
        verify_engine()


@pytest.mark.parametrize(
    "invalid", ["node", "pnpm", "python", "uv", "package", "nvmrc", "python-version-file"]
)
def test_verify_versions_rejects_wrong_toolchain_predicates(monkeypatch, tmp_path, invalid):
    import scripts.verify_local_environment as guard

    files = {
        "package.json": json.dumps(
            {
                "packageManager": "npm@11.0.0" if invalid == "package" else "pnpm@10.17.1",
                "engines": {"node": "24.20.0", "pnpm": "10.17.1"},
            }
        ),
        ".nvmrc": "22.0.0" if invalid == "nvmrc" else "24.20.0",
        ".python-version": "3.11.9" if invalid == "python-version-file" else "3.12.14",
        "uv.lock": 'requires-python = "==3.12.14"',
        "pnpm-lock.yaml": "lockfileVersion: '9.0'",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    versions = {
        ("node", "--version"): "v22.0.0" if invalid == "node" else "v24.20.0",
        (("corepack.cmd" if guard.os.name == "nt" else "corepack"), "pnpm", "--version"):
            "9.0.0" if invalid == "pnpm" else "10.17.1",
        ("uv", "--version"): "uv 0.10.0" if invalid == "uv" else "uv 0.11.23",
    }
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "command", lambda *args: versions[args])
    monkeypatch.setattr(guard.sys, "version_info", (3, 11, 9) if invalid == "python" else (3, 12, 14))
    monkeypatch.setattr(guard, "verify_image_manifest", lambda: None)
    monkeypatch.setattr(guard, "verify_docker_capabilities", lambda: {})

    with pytest.raises(IsolationError) as exc_info:
        verify_versions()
    if invalid in {"node", "pnpm", "python", "uv"}:
        message = str(exc_info.value)
        assert "actual=" in message and "required=" in message and "remedy=" in message


@pytest.fixture
def isolated_image_sources(tmp_path, monkeypatch):
    import scripts.verify_local_environment as guard

    files = {
        ".dockerignore": "__pycache__\n",
        "deployment/python.Dockerfile": "FROM python\n",
        "deployment/web.Dockerfile": "FROM node\n",
        "deployment/nginx/web.conf": "server {}\n",
        "pyproject.toml": "[project]\nname = 'eid'\n",
        "uv.lock": "version = 1\n",
        "edw-api/pyproject.toml": "[project]\nname = 'edw-api'\n",
        "edw-worker/pyproject.toml": "[project]\nname = 'edw-worker'\n",
        "package.json": "{}\n",
        "pnpm-workspace.yaml": "packages: []\n",
        "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
        "edw-web/package.json": "{}\n",
        "edw-web/index.html": "<main></main>\n",
        "edw-web/eslint.config.js": "export default [];\n",
        "edw-web/tsconfig.app.json": "{}\n",
        "edw-web/tsconfig.json": "{}\n",
        "edw-web/tsconfig.node.json": "{}\n",
        "edw-web/vite.config.ts": "export default {};\n",
        "edw-api/src/edw_api/app.py": "API = True\n",
        "edw-worker/src/edw_worker/app.py": "WORKER = True\n",
        "edw-web/src/main.ts": "export const web = true;\n",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    return guard


def test_source_fingerprints_cover_dockerignore_and_web_copy_is_narrow(isolated_image_sources):
    from pathlib import Path

    guard = isolated_image_sources

    original = {service: guard.source_fingerprint(service) for service in ("api", "worker", "web")}
    dockerignore = guard.ROOT / ".dockerignore"
    dockerignore.write_text("__pycache__\n# fingerprint regression\n", encoding="utf-8")

    assert all(
        guard.source_fingerprint(service) != original[service]
        for service in ("api", "worker", "web")
    )
    dockerfile = (Path(__file__).parents[2] / "deployment" / "web.Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "COPY edw-web edw-web" not in dockerfile
    assert "COPY edw-web/src edw-web/src" in dockerfile


@pytest.mark.parametrize(
    ("mutated_relative", "expected_changed"),
    [
        ("edw-api/src/edw_api/app.py", {"api", "worker"}),
        ("edw-worker/src/edw_worker/app.py", {"api", "worker"}),
        ("edw-web/src/main.ts", {"web"}),
    ],
)
def test_service_source_mutation_invalidates_only_affected_runtime_images(
    isolated_image_sources, monkeypatch, tmp_path, mutated_relative, expected_changed
):
    guard = isolated_image_sources
    image_refs = {
        "api": "eid-local-api:0.1.0",
        "worker": "eid-local-worker:0.1.0",
        "web": "eid-local-web:0.1.0",
    }
    image_ids = {
        service: f"sha256:{digit * 64}"
        for service, digit in zip(image_refs, "123", strict=True)
    }
    manifest_path = tmp_path / "runtime-images.json"
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", manifest_path)
    monkeypatch.setattr(guard, "build_images", lambda: image_refs)
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    monkeypatch.setattr(guard, "infrastructure_images", lambda: {})

    def fake_command(*args):
        if args[1:3] == ("image", "inspect"):
            service = next(name for name, ref in image_refs.items() if ref == args[3])
            return json.dumps([{
                "Id": image_ids[service],
                "Config": {"Labels": {
                    "io.eid.source-fingerprint": guard.source_fingerprint(service)
                }},
            }])
        if args[1:3] == ("ps", "-q"):
            return f"container-{args[-1].rsplit('=', 1)[1]}"
        if args[1] == "inspect":
            service = args[2].removeprefix("container-")
            return json.dumps(
                [{
                    "Image": image_ids[service],
                    "State": {"Running": True, "Health": {"Status": "healthy"}},
                    "Config": {"Labels": {"io.eid.owner": "owner"}},
                }]
            )
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)
    target = guard.ROOT / mutated_relative
    for service in expected_changed:
        assert target in guard._source_paths(service)

    before = {service: guard.source_fingerprint(service) for service in image_refs}
    recorded_services = guard.current_runtime_images()
    manifest_path.write_text(
        json.dumps({
            "schema_version": 2,
            "source_fingerprint_algorithm": "sha256",
            "services": recorded_services,
        }),
        encoding="utf-8",
    )

    target.write_text(target.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    after = {service: guard.source_fingerprint(service) for service in image_refs}

    assert {service for service in image_refs if after[service] != before[service]} == expected_changed
    with pytest.raises(IsolationError, match="重新运行 bootstrap"):
        guard.verify_runtime_images()


def test_dynamic_health_routes_disable_caching():
    from pathlib import Path

    config = (Path(__file__).parents[2] / "deployment" / "nginx" / "default.conf").read_text(encoding="utf-8")
    health = next(line for line in config.splitlines() if "location /health/" in line)
    assert "Cache-Control no-store always" in health


@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        ("port", "端口映射"),
        ("volume", "存储卷"),
        ("database", "名称/身份/marker"),
        ("user", "名称/身份/marker"),
        ("marker", "名称/身份/marker"),
    ],
)
def test_verify_database_rejects_connected_identity_and_container_mismatch(
    monkeypatch, invalid, message
):
    import psycopg
    import scripts.verify_local_environment as guard

    port = "55431" if invalid == "port" else "55432"
    volume = "foreign-postgres" if invalid == "volume" else "eid-local-postgres"
    row = {
        "database": ("foreign", "eid_migrator", "eid-local-dev-v1"),
        "user": ("eid_local_dev", "postgres", "eid-local-dev-v1"),
        "marker": ("eid_local_dev", "eid_migrator", "foreign"),
    }.get(invalid, ("eid_local_dev", "eid_migrator", "eid-local-dev-v1"))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _sql):
            return type("Result", (), {"fetchone": lambda self: row})()

    def fake_command(*args):
        if args[1:3] == ("ps", "-q"):
            return "postgres-container"
        if args[1] == "inspect":
            return json.dumps(
                [{
                    "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": port}]}},
                    "Mounts": [{"Name": volume, "Destination": "/var/lib/postgresql/data"}],
                }]
            )
        raise AssertionError(args)

    monkeypatch.setattr(guard, "ownership", lambda: {"nonce": "owner"})
    monkeypatch.setattr(guard, "command", fake_command)
    def connect(*_args, **kwargs):
        assert kwargs == {"connect_timeout": 3, "options": "-c statement_timeout=5000 -c lock_timeout=2000"}
        return Connection()

    monkeypatch.setattr(psycopg, "connect", connect)

    with pytest.raises(IsolationError, match=message):
        verify_database(
            "postgresql+psycopg://eid_migrator:p@localhost:55432/eid_local_dev"
        )


def test_preexisting_volume_never_adopted(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard, "STATE", tmp_path / "ownership.json")
    monkeypatch.setattr(guard, "verify_engine", lambda: None)
    monkeypatch.setattr(
        guard, "command", lambda *args: "eid-local-postgres" if args[1] == "volume" else ""
    )
    with pytest.raises(IsolationError, match="预存"):
        ownership(create=True)
    assert not guard.STATE.exists()


def test_existing_ownership_nonce_mismatch_is_rejected(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard

    state = tmp_path / "ownership.json"
    state.write_text(
        json.dumps({"root": str(guard.ROOT), "project": guard.PROJECT, "nonce": "expected"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "STATE", state)
    monkeypatch.setattr(guard, "verify_engine", lambda: None)

    def fake_command(*args):
        if args[1:3] == ("volume", "ls"):
            return "eid-local-postgres"
        if args[1:3] == ("volume", "inspect"):
            return json.dumps(
                [
                    {
                        "Labels": {
                            "com.docker.compose.project": guard.PROJECT,
                            "io.eid.owner": "foreign",
                        }
                    }
                ]
            )
        return ""

    monkeypatch.setattr(guard, "command", fake_command)
    with pytest.raises(IsolationError, match="归属标记"):
        ownership()


@pytest.mark.parametrize(
    ("volume", "service"),
    [
        ("eid-local-postgres", "postgres"),
        ("eid-local-keycloak", "keycloak"),
        ("eid-local-seaweedfs", "seaweedfs"),
    ],
)
def test_ownership_accepts_exact_expected_stopped_volume_attachment(
    monkeypatch, tmp_path, volume, service
):
    import scripts.verify_local_environment as guard

    state = tmp_path / "ownership.json"
    owner = {"root": str(guard.ROOT), "project": guard.PROJECT, "nonce": "expected"}
    state.write_text(json.dumps(owner), encoding="utf-8")
    monkeypatch.setattr(guard, "STATE", state)
    monkeypatch.setattr(guard, "verify_engine", lambda: None)

    def fake_command(*args):
        if args[1:3] == ("volume", "ls"):
            return volume
        if args[1:3] == ("volume", "inspect"):
            return json.dumps([{"Labels": {
                "com.docker.compose.project": guard.PROJECT,
                "io.eid.owner": "expected",
            }}])
        if args[1:3] == ("ps", "-aq"):
            return "expected-container"
        if args[1] == "inspect":
            return json.dumps([{
                "Config": {"Labels": {
                    "com.docker.compose.project": guard.PROJECT,
                    "com.docker.compose.service": service,
                    "io.eid.owner": "expected",
                }},
                "Mounts": [{"Type": "volume", "Name": volume}],
                "State": {"Running": False},
            }])
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)
    assert ownership() == owner


@pytest.mark.parametrize(
    ("volume", "service"),
    [
        ("eid-local-postgres", "postgres"),
        ("eid-local-keycloak", "keycloak"),
        ("eid-local-seaweedfs", "seaweedfs"),
    ],
)
@pytest.mark.parametrize("invalid", ["foreign", "wrong-service", "wrong-nonce", "duplicate"])
def test_ownership_rejects_invalid_attachment_for_each_managed_volume(
    monkeypatch, tmp_path, volume, service, invalid
):
    import scripts.verify_local_environment as guard

    state = tmp_path / "ownership.json"
    state.write_text(
        json.dumps({"root": str(guard.ROOT), "project": guard.PROJECT, "nonce": "expected"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "STATE", state)
    monkeypatch.setattr(guard, "verify_engine", lambda: None)
    container_ids = ["first", "second"] if invalid == "duplicate" else ["first"]

    def container_metadata():
        labels = {
            "com.docker.compose.project": "foreign" if invalid == "foreign" else guard.PROJECT,
            "com.docker.compose.service": "api" if invalid == "wrong-service" else service,
            "io.eid.owner": "foreign" if invalid == "wrong-nonce" else "expected",
        }
        return {
            "Config": {"Labels": labels},
            "Mounts": [{"Type": "volume", "Name": volume}],
            "State": {"Running": False},
        }

    def fake_command(*args):
        if args[1:3] == ("volume", "ls"):
            return volume
        if args[1:3] == ("volume", "inspect"):
            return json.dumps([{"Labels": {
                "com.docker.compose.project": guard.PROJECT,
                "io.eid.owner": "expected",
            }}])
        if args[1:3] == ("ps", "-aq"):
            return "\n".join(container_ids)
        if args[1] == "inspect":
            assert args[2] in container_ids
            return json.dumps([container_metadata()])
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)
    with pytest.raises(IsolationError):
        ownership()


def test_s3_configuration_has_distinct_exact_least_privilege_identities():
    import scripts.verify_local_environment as guard

    verify_s3_configuration()
    payload = json.loads(guard.S3_CONFIG.read_text(encoding="utf-8"))
    identities = {identity["name"]: identity for identity in payload["identities"]}
    assert set(identities) == {"eid-s3-bootstrap", "eid-s3-api", "eid-s3-worker"}
    assert identities["eid-s3-bootstrap"]["actions"] == [
        "Admin",
        "Read:eid-local-artifacts",
    ]
    assert identities["eid-s3-api"]["actions"] == ["Read:eid-local-artifacts"]
    assert identities["eid-s3-worker"]["actions"] == ["Read:eid-local-artifacts"]
    credentials = [identity["credentials"][0] for identity in identities.values()]
    assert len({credential["accessKey"] for credential in credentials}) == 3
    assert len({credential["secretKey"] for credential in credentials}) == 3


def test_s3_guard_exercises_runtime_head_bucket_and_read_only_denials(monkeypatch):
    import scripts.verify_local_environment as guard

    calls = []

    class Client:
        def __init__(self, role):
            self.role = role

        def list_buckets(self):
            calls.append((self.role, "list-buckets"))
            return {"Buckets": [{"Name": guard.EXPECTED["bucket"]}]}

        def list_objects_v2(self, *, Bucket, MaxKeys):
            calls.append((self.role, "list-objects", Bucket, MaxKeys))
            raise ClientError(
                {"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
                "ListObjectsV2",
            )

        def get_bucket_acl(self, *, Bucket):
            calls.append((self.role, "get-acl", Bucket))
            raise ClientError(
                {"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
                "GetBucketAcl",
            )

        def head_bucket(self, *, Bucket):
            calls.append((self.role, "head", Bucket))
            if Bucket != guard.EXPECTED["bucket"]:
                raise ClientError(
                    {"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
                    "HeadBucket",
                )

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard, "s3_client", lambda role: Client(role))

    guard.verify_bucket()

    for role in ("api", "worker"):
        assert (role, "head", "eid-local-artifacts") in calls
        assert (role, "list-objects", "eid-local-artifacts", 1) in calls
        assert (role, "get-acl", "eid-local-artifacts") in calls
        assert (role, "head", "eid-local-foreign") in calls


def test_compose_injects_distinct_s3_runtime_identities_without_admin_secret():
    from pathlib import Path

    compose = (Path(__file__).parents[2] / "deployment" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    business = compose[compose.index("  api:") :]
    assert "EID_S3_ACCESS_KEY: eid-s3-api" in business
    assert "EID_S3_ACCESS_KEY: eid-s3-worker" in business
    assert "local-s3-bootstrap-admin-only" not in business


def test_check_only_verifies_database_and_all_external_isolation(monkeypatch):
    import scripts.verify_local_environment as guard

    calls = []
    monkeypatch.setattr(guard, "verify_versions", lambda: calls.append("versions"))
    monkeypatch.setattr(
        guard,
        "ownership",
        lambda create=False: calls.append(("ownership", create)) or {"nonce": "test-owner"},
    )
    monkeypatch.setattr(guard, "verify_database", lambda value: calls.append(("database", value)))
    monkeypatch.setattr(guard, "verify_external_isolation", lambda: calls.append("external"))
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", "guard-target")
    monkeypatch.setattr(guard.sys, "argv", ["verify_local_environment.py", "--check-only"])

    guard.main()

    assert calls == ["versions", ("ownership", False), ("database", "guard-target"), "external"]


def test_prepare_reports_only_ownership_as_verified(monkeypatch, capsys):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard, "verify_versions", lambda: None)
    ownership_modes = []
    monkeypatch.setattr(
        guard,
        "ownership",
        lambda create=False: ownership_modes.append(create) or {"nonce": "test-owner"},
    )
    monkeypatch.setattr(
        guard,
        "verify_migration_target",
        lambda _value: pytest.fail("prepare 不得核验尚未启动的实际资源"),
    )
    monkeypatch.setattr(guard.sys, "argv", ["verify_local_environment.py", "--prepare"])

    guard.main()

    assert ownership_modes == [True]
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "project": "eid-local",
        "owner": "test-owner",
        "ownership_verified": True,
        "live_resources_verified": False,
        "verified": False,
    }


@pytest.mark.parametrize(
    "actions",
    [
        ["--prepare", "--check-only"],
        ["--prepare", "--record-runtime-images"],
        ["--prepare", "--verify-runtime-images"],
        ["--check-only", "--record-runtime-images"],
        ["--record-runtime-images", "--verify-runtime-images"],
    ],
)
def test_environment_actions_are_mutually_exclusive(monkeypatch, actions):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard.sys, "argv", ["verify_local_environment.py", *actions])
    with pytest.raises(SystemExit) as exc_info:
        guard.main()
    assert exc_info.value.code == 2


def test_check_only_missing_owner_never_creates_state(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard, "STATE", tmp_path / "ownership.json")
    monkeypatch.setattr(guard, "verify_versions", lambda: None)
    monkeypatch.setattr(guard, "verify_engine", lambda: None)
    monkeypatch.setattr(guard, "command", lambda *_args: "")
    monkeypatch.setattr(guard.sys, "argv", ["verify_local_environment.py", "--check-only"])

    with pytest.raises(IsolationError, match="缺少初建归属记录"):
        guard.main()
    assert not guard.STATE.exists()


def test_migration_target_rejects_before_external_checks_when_database_is_wrong(monkeypatch):
    import scripts.verify_local_environment as guard

    called = False

    def reject_database(_value):
        raise IsolationError("wrong database")

    def external_checks():
        nonlocal called
        called = True

    monkeypatch.setattr(guard, "verify_database", reject_database)
    monkeypatch.setattr(guard, "verify_external_isolation", external_checks)

    with pytest.raises(IsolationError, match="wrong database"):
        guard.verify_migration_target("wrong")
    assert called is False


def test_bootstrap_provisions_and_verifies_resources_before_migration():
    from pathlib import Path

    script = (Path(__file__).parents[2] / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
    storage = script.index("scripts.initialize_local_storage")
    guard = script.index("scripts/verify_local_environment.py')", storage)
    migration = script.index("'alembic','upgrade','head'")
    source_capture = script.index("'--source-fingerprints'")
    build = script.index("'--build'")
    prepare = script.index("'--prepare'")
    compose_config = script.index("'config','--quiet'")
    nginx_reload = script.index("'nginx','-s','reload'")
    readiness = script.index("scripts.verify_readiness")
    record = script.index("'--record-runtime-images'")

    assert prepare < source_capture < compose_config < storage < guard < migration < build
    assert nginx_reload < readiness < record
    assert "Remove-Item -LiteralPath '.local/runtime-images.json'" in script
    assert "if ($LASTEXITCODE -ne 0)" in script


def test_api_broker_permissions_follow_installed_celery_pidbox_names():
    from kombu.pidbox import Mailbox
    from scripts.verify_local_environment import RABBITMQ_API_PERMISSIONS

    mailbox = Mailbox("celery")
    reply_queue = mailbox.reply_queue.name
    assert mailbox.exchange.name == "celery.pidbox"
    assert mailbox.reply_exchange.name == "reply.celery.pidbox"
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["configure"], mailbox.exchange.name)
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["configure"], mailbox.reply_exchange.name)
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["configure"], reply_queue)
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["read"], reply_queue)
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["write"], mailbox.exchange.name)
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["write"], reply_queue)
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["read"], mailbox.reply_exchange.name)
    for business_queue in ("generation", "retrieval", "review", "integration", "parse_ocr", "render"):
        assert re.fullmatch(RABBITMQ_API_PERMISSIONS["configure"], business_queue) is None
        assert re.fullmatch(RABBITMQ_API_PERMISSIONS["read"], business_queue) is None
        assert re.fullmatch(RABBITMQ_API_PERMISSIONS["write"], business_queue) is None


def test_worker_broker_permissions_cover_only_declared_task_and_control_entities():
    from kombu.transport.native_delayed_delivery import (
        CELERY_DELAYED_DELIVERY_EXCHANGE,
        MAX_LEVEL,
        level_name,
    )
    from scripts.verify_local_environment import RABBITMQ_WORKER_PERMISSIONS

    worker_resources = {
        "generation",
        "retrieval",
        "review",
        "integration",
        "parse_ocr",
        "render",
        CELERY_DELAYED_DELIVERY_EXCHANGE,
        *(level_name(level) for level in range(MAX_LEVEL + 1)),
    }
    for resource in worker_resources:
        assert all(
            re.fullmatch(pattern, resource)
            for pattern in RABBITMQ_WORKER_PERMISSIONS.values()
        )
    assert re.fullmatch(RABBITMQ_WORKER_PERMISSIONS["configure"], "eid-worker@worker.celery.pidbox")
    assert re.fullmatch(RABBITMQ_WORKER_PERMISSIONS["write"], "reply.celery.pidbox")
    for unrelated in (
        "amq.management",
        "foreign",
        "eid_api",
        "celery_delayed_28",
        "celery_delayed_-1",
        "celery_delayed_delivery_extra",
    ):
        assert all(re.fullmatch(pattern, unrelated) is None for pattern in RABBITMQ_WORKER_PERMISSIONS.values())


def test_compose_separates_api_and_worker_broker_credentials():
    from pathlib import Path

    compose = (Path(__file__).parents[2] / "deployment" / "compose.yaml").read_text(encoding="utf-8")
    assert "RABBITMQ_DEFAULT_USER: eid_broker_admin" in compose
    assert "RABBITMQ_DEFAULT_PASS: local-rabbitmq-bootstrap-admin-only" in compose
    assert "amqp://eid_api:local-api-broker-only@rabbitmq:5672/eid-local" in compose
    assert "EID_RABBITMQ_URL: amqp://eid_worker:local-worker-only@rabbitmq:5672/eid-local" in compose
    runtime = compose[compose.index("  api:"):]
    assert "local-rabbitmq-bootstrap-admin-only" not in runtime


def test_rabbitmq_healthcheck_waits_for_required_application_interfaces():
    from pathlib import Path

    compose = (Path(__file__).parents[2] / "deployment" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    rabbitmq = compose[compose.index("  rabbitmq:") : compose.index("  redis:")]

    assert "rabbitmq-diagnostics -q check_running" in rabbitmq
    assert "rabbitmq-diagnostics -q check_virtual_hosts" in rabbitmq
    assert "rabbitmq-diagnostics -q check_port_listener 5672" in rabbitmq
    assert "GET /api/whoami HTTP/1.0" in rabbitmq
    assert "Authorization: Basic %s" in rabbitmq
    assert '"$${RABBITMQ_DEFAULT_USER}:$${RABBITMQ_DEFAULT_PASS}"' in rabbitmq
    assert "rabbitmq-diagnostics\", \"-q\", \"ping" not in rabbitmq


def test_rabbitmq_guard_accepts_exact_admin_and_runtime_identities(monkeypatch):
    import scripts.verify_local_environment as guard

    broker_urls = []

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, path):
            payloads = {
                "/api/whoami": {"name": "eid_broker_admin", "tags": ["administrator"]},
                "/api/vhosts/eid-local": {"name": "eid-local"},
                "/api/users/eid_broker_admin": {
                    "name": "eid_broker_admin", "tags": ["administrator"]
                },
                "/api/users/eid_broker_admin/permissions": [
                    {"vhost": "eid-local", "configure": ".*", "write": ".*", "read": ".*"}
                ],
                "/api/users/eid_worker": {"name": "eid_worker", "tags": []},
                "/api/users/eid_worker/permissions": [
                    {"vhost": "eid-local", **guard.RABBITMQ_WORKER_PERMISSIONS}
                ],
                "/api/users/eid_api": {"name": "eid_api", "tags": []},
                "/api/users/eid_api/permissions": [
                    {"vhost": "eid-local", **guard.RABBITMQ_API_PERMISSIONS}
                ],
            }
            return Response(200, payloads[path])

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def connect(self):
            return None

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(
        guard,
        "BrokerConnection",
        lambda url, **_kwargs: broker_urls.append(url) or Connection(),
    )
    assert verify_rabbitmq() == "ready"
    assert set(broker_urls) == {
        "amqp://eid_broker_admin:local-rabbitmq-bootstrap-admin-only@localhost:55672/eid-local",
        "amqp://eid_api:local-api-broker-only@localhost:55672/eid-local",
        "amqp://eid_worker:local-worker-only@localhost:55672/eid-local",
    }


def test_rabbitmq_guard_rejects_partial_runtime_user_setup(monkeypatch):
    import scripts.verify_local_environment as guard

    class Response:
        status_code = 200

        def __init__(self, payload): self._payload = payload
        def json(self): return self._payload

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def get(self, path):
            return Response(
                {"name": "eid_broker_admin", "tags": ["administrator"]}
                if path == "/api/whoami"
                else {"name": "eid-local"}
            )

    states = iter(["ready", "missing", "ready"])
    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(guard, "_rabbitmq_user_state", lambda *_args, **_kwargs: next(states))
    with pytest.raises(IsolationError, match="部分初始化状态"):
        guard.verify_rabbitmq(allow_missing_runtime=True)


def test_rabbitmq_runtime_user_state_rejects_management_tag():
    import scripts.verify_local_environment as guard

    class Response:
        status_code = 200

        def json(self): return {"name": "eid_worker", "tags": ["administrator"]}

    class Client:
        def get(self, _path): return Response()

    with pytest.raises(IsolationError, match="不得拥有管理标签"):
        guard._rabbitmq_user_state(
            Client(), user_name="eid_worker", password="local-worker-only",
            permissions=guard.RABBITMQ_WORKER_PERMISSIONS, label="Worker",
            expected_tags=set(), allow_missing=False,
        )


def test_rabbitmq_guard_rejects_existing_api_permission_mismatch(monkeypatch):
    import scripts.verify_local_environment as guard

    class Response:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, path):
            if path == "/api/vhosts/eid-local":
                return Response({"name": "eid-local"})
            if path == "/api/whoami":
                return Response({"name": "eid_broker_admin", "tags": ["administrator"]})
            if path == "/api/users/eid_broker_admin":
                return Response({"name": "eid_broker_admin", "tags": ["administrator"]})
            if path == "/api/users/eid_broker_admin/permissions":
                return Response([{"vhost": "eid-local", **guard.RABBITMQ_ADMIN_PERMISSIONS}])
            if path == "/api/users/eid_worker":
                return Response({"name": "eid_worker", "tags": []})
            if path == "/api/users/eid_worker/permissions":
                return Response([{"vhost": "eid-local", **guard.RABBITMQ_WORKER_PERMISSIONS}])
            if path == "/api/users/eid_api":
                return Response({"name": "eid_api", "tags": []})
            return Response([
                {"vhost": "eid-local", "configure": ".*", "write": ".*", "read": ".*"}
            ])

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", lambda **_kwargs: Client())
    with pytest.raises(IsolationError, match="拒绝覆盖"):
        verify_rabbitmq(allow_missing_runtime=True)


def test_storage_checks_owned_s3_port_before_first_request(monkeypatch):
    import scripts.initialize_local_storage as storage
    monkeypatch.setattr(storage, "storage_boundary", lambda: ("owner", "rabbit", "keycloak", "s3"))

    calls = []

    class Client:
        def list_buckets(self):
            calls.append("list")
            return {"Buckets": [{"Name": "eid-local-artifacts"}]}

        def head_bucket(self, *, Bucket):
            calls.append(("head", Bucket))

    monkeypatch.setattr(storage, "verify_database", lambda _url: calls.append("database"))
    monkeypatch.setattr(
        storage,
        "service_container",
        lambda service, container_port, host_port: calls.append(
            ("port", service, container_port, host_port)
        ),
    )
    monkeypatch.setattr(
        storage,
        "verify_rabbitmq",
        lambda **_kwargs: calls.append("rabbitmq") or "ready",
    )
    monkeypatch.setattr(
        storage,
        "create_rabbitmq_runtime_users",
        lambda: pytest.fail("matching identity must not be recreated"),
    )
    monkeypatch.setattr(
        storage,
        "verify_keycloak",
        lambda **_kwargs: calls.append("keycloak") or "ready",
    )
    monkeypatch.setattr(
        storage, "verify_s3_configuration", lambda: calls.append("s3-config")
    )
    monkeypatch.setattr(
        storage, "verify_migration_target", lambda _url: calls.append("post-full-guard")
    )
    monkeypatch.setattr(storage, "s3_client", lambda role: Client() if role == "bootstrap" else None)
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", "guarded")

    storage.main()

    assert calls == [
        "database",
        ("port", "seaweedfs", 8333, 58333),
        "rabbitmq",
        "keycloak",
        "s3-config",
        "list",
        ("head", "eid-local-artifacts"),
        "post-full-guard",
    ]


@pytest.mark.parametrize("failed_guard", ["rabbitmq", "keycloak"])
def test_storage_does_not_touch_s3_when_existing_resource_guard_fails(
    monkeypatch, failed_guard
):
    import scripts.initialize_local_storage as storage
    monkeypatch.setattr(storage, "storage_boundary", lambda: ("owner", "rabbit", "keycloak", "s3"))

    calls = []
    monkeypatch.setattr(storage, "verify_database", lambda _url: calls.append("database"))
    monkeypatch.setattr(storage, "service_container", lambda *_args: calls.append("s3-port"))

    def rabbitmq():
        calls.append("rabbitmq")
        if failed_guard == "rabbitmq":
            raise IsolationError("rabbit rejected")

    def keycloak(**_kwargs):
        calls.append("keycloak")
        if failed_guard == "keycloak":
            raise IsolationError("keycloak rejected")

    monkeypatch.setattr(storage, "verify_rabbitmq", lambda **_kwargs: rabbitmq())
    monkeypatch.setattr(storage, "verify_keycloak", keycloak)
    monkeypatch.setattr(storage, "verify_s3_configuration", lambda: calls.append("s3-config"))
    monkeypatch.setattr(
        storage,
        "s3_client",
        lambda _role: pytest.fail("guard 失败后不得发出任何 S3 请求"),
    )
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", "guarded")

    with pytest.raises(IsolationError, match="rejected"):
        storage.main()

    expected = ["database", "s3-port", "rabbitmq"]
    if failed_guard == "keycloak":
        expected.append("keycloak")
    assert calls == expected


def test_storage_creates_only_from_empty_inventory_then_runs_full_guard(monkeypatch):
    import scripts.initialize_local_storage as storage
    monkeypatch.setattr(storage, "storage_boundary", lambda: ("owner", "rabbit", "keycloak", "s3"))

    calls = []

    class Client:
        def list_buckets(self):
            calls.append("list")
            return {"Buckets": []}

        def create_bucket(self, *, Bucket):
            calls.append(("create", Bucket))

        def head_bucket(self, *, Bucket):
            calls.append(("head", Bucket))

    monkeypatch.setattr(storage, "verify_database", lambda _url: calls.append("database"))
    monkeypatch.setattr(storage, "service_container", lambda *_args: calls.append("s3-port"))
    monkeypatch.setattr(
        storage,
        "verify_rabbitmq",
        lambda **_kwargs: calls.append("rabbitmq") or "missing",
    )
    monkeypatch.setattr(
        storage, "create_rabbitmq_runtime_users", lambda: calls.append("create-rabbit-runtime")
    )
    monkeypatch.setattr(
        storage,
        "verify_keycloak",
        lambda **_kwargs: calls.append("keycloak") or "ready",
    )
    monkeypatch.setattr(
        storage, "verify_s3_configuration", lambda: calls.append("s3-config")
    )
    monkeypatch.setattr(storage, "s3_client", lambda role: Client() if role == "bootstrap" else None)
    monkeypatch.setattr(
        storage, "verify_migration_target", lambda _url: calls.append("post-full-guard")
    )
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", "guarded")

    storage.main()

    assert calls == [
        "database",
        "s3-port",
        "rabbitmq",
        "keycloak",
        "s3-config",
        "list",
        "create-rabbit-runtime",
        ("create", "eid-local-artifacts"),
        ("head", "eid-local-artifacts"),
        "post-full-guard",
    ]


def test_storage_rejects_mixed_or_foreign_inventory_without_writing(monkeypatch):
    import scripts.initialize_local_storage as storage
    monkeypatch.setattr(storage, "storage_boundary", lambda: ("owner", "rabbit", "keycloak", "s3"))

    calls = []

    class Client:
        def list_buckets(self):
            calls.append("list")
            return {
                "Buckets": [
                    {"Name": "eid-local-artifacts"},
                    {"Name": "foreign-artifacts"},
                ]
            }

        def create_bucket(self, **_kwargs):
            pytest.fail("非专属 bucket 清单不得触发创建")

        def head_bucket(self, **_kwargs):
            pytest.fail("非专属 bucket 清单不得继续探测")

    monkeypatch.setattr(storage, "verify_database", lambda _url: None)
    monkeypatch.setattr(storage, "service_container", lambda *_args: None)
    monkeypatch.setattr(storage, "verify_rabbitmq", lambda **_kwargs: "ready")
    monkeypatch.setattr(storage, "verify_keycloak", lambda **_kwargs: "roles-missing")
    monkeypatch.setattr(
        storage,
        "provision_keycloak_readiness_monitor",
        lambda: pytest.fail("非法 bucket 清单不得触发 Keycloak 写入"),
    )
    monkeypatch.setattr(storage, "verify_s3_configuration", lambda: None)
    monkeypatch.setattr(storage, "s3_client", lambda role: Client() if role == "bootstrap" else None)
    monkeypatch.setattr(
        storage,
        "verify_migration_target",
        lambda _url: pytest.fail("非法清单不得运行创建后完整守卫"),
    )
    monkeypatch.setenv("EID_MIGRATION_DATABASE_URL", "guarded")

    with pytest.raises(RuntimeError, match="必须为空或仅包含"):
        storage.main()

    assert calls == ["list"]


def _keycloak_client_payload():
    return {
        "id": "persisted-client-id",
        "clientId": "eid-web",
        "enabled": True,
        "publicClient": True,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "redirectUris": ["http://localhost:18080/auth/callback"],
        "webOrigins": ["http://localhost:18080"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": "http://localhost:18080/",
        },
    }


def _keycloak_realm_payload():
    return {"realm": "eid-local"}


def _keycloak_admin_realm_payload():
    return {"realm": "eid-local", "registrationAllowed": False}


def _audience_mapper_payload():
    return {
        "name": "audience-eid-web",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": {
            "included.client.audience": "eid-web",
            "access.token.claim": "true",
        },
    }


def _keycloak_monitor_payload():
    return {
        "id": "persisted-monitor-id",
        "clientId": "eid-readiness-monitor",
        "enabled": True,
        "publicClient": False,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
    }


def test_keycloak_guard_reads_and_accepts_persisted_audience_mapper(monkeypatch):
    import scripts.verify_local_environment as guard

    requested = []

    class Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, path, **_kwargs):
            requested.append(path)
            return Response({"access_token": "admin-token"})

        def get(self, path, **kwargs):
            requested.append(path)
            if path == "/realms/eid-local":
                return Response(_keycloak_realm_payload())
            if path == "/admin/realms/eid-local":
                return Response(_keycloak_admin_realm_payload())
            if path == "/admin/realms/eid-local/clients":
                if kwargs.get("params", {}).get("clientId") == "eid-readiness-monitor":
                    return Response([])
                return Response([_keycloak_client_payload()])
            if path == "/admin/realms/eid-local/users":
                return Response([])
            return Response([_audience_mapper_payload()])

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", Client)

    assert verify_keycloak(allow_incomplete_monitor=True) == "missing"

    assert requested[-1] == "/admin/realms/eid-local/users"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("implicitFlowEnabled", True),
        ("post.logout.redirect.uris", "http://localhost:18080/*"),
    ],
)
def test_keycloak_guard_rejects_unsafe_flow_or_logout_redirect(monkeypatch, field, value):
    import scripts.verify_local_environment as guard

    client_payload = _keycloak_client_payload()
    if field == "post.logout.redirect.uris":
        client_payload["attributes"][field] = value
    else:
        client_payload[field] = value

    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, _path, **_kwargs):
            return Response({"access_token": "admin-token"})

        def get(self, path, **_kwargs):
            if path == "/realms/eid-local":
                return Response(_keycloak_realm_payload())
            if path == "/admin/realms/eid-local":
                return Response(_keycloak_admin_realm_payload())
            if path == "/admin/realms/eid-local/clients":
                return Response([client_payload])
            pytest.fail("非法 client 配置不得继续读取 mapper")

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", Client)

    with pytest.raises(IsolationError, match=r"Code \+ PKCE"):
        verify_keycloak()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocolMapper", "oidc-hardcoded-claim-mapper"),
        ("included.client.audience", "another-client"),
        ("access.token.claim", "false"),
    ],
)
def test_keycloak_guard_rejects_invalid_persisted_audience_mapper(monkeypatch, field, value):
    import scripts.verify_local_environment as guard

    mapper = _audience_mapper_payload()
    if field in mapper:
        mapper[field] = value
    else:
        mapper["config"][field] = value

    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, _path, **_kwargs):
            return Response({"access_token": "admin-token"})

        def get(self, path, **_kwargs):
            if path == "/realms/eid-local":
                return Response(_keycloak_realm_payload())
            if path == "/admin/realms/eid-local":
                return Response(_keycloak_admin_realm_payload())
            if path == "/admin/realms/eid-local/clients":
                return Response([_keycloak_client_payload()])
            return Response([mapper])

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", Client)

    with pytest.raises(IsolationError, match="audience mapper"):
        verify_keycloak()


@pytest.mark.parametrize(
    "admin_realm_payload",
    [
        {"realm": "eid-local", "registrationAllowed": True},
        {"realm": "eid-local"},
        {"realm": "eid-local", "registrationAllowed": "false"},
        {"realm": "foreign", "registrationAllowed": False},
        [],
    ],
    ids=[
        "registration-enabled",
        "registration-setting-missing",
        "registration-setting-malformed",
        "realm-name-mismatch",
        "representation-not-an-object",
    ],
)
def test_keycloak_guard_rejects_admin_realm_without_literal_disabled_registration(
    monkeypatch, admin_realm_payload
):
    import scripts.verify_local_environment as guard

    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, path, **_kwargs):
            assert path == "/realms/master/protocol/openid-connect/token"
            return Response({"access_token": "admin-token"})

        def get(self, path, **_kwargs):
            if path == "/realms/eid-local":
                return Response({"realm": "eid-local", "registrationAllowed": False})
            assert path == "/admin/realms/eid-local"
            return Response(admin_realm_payload)

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", Client)

    with pytest.raises(IsolationError, match="禁用自助注册"):
        verify_keycloak()


def test_keycloak_monitor_with_excess_role_is_rejected_without_configuration_write(
    monkeypatch,
):
    import scripts.verify_local_environment as guard

    calls = []

    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def get(self, path, **_kwargs):
            calls.append(("get", path))
            return Response([_keycloak_monitor_payload()])

        def post(self, path, **_kwargs):
            calls.append(("post", path))
            return Response({"access_token": "monitor-token"})

    monkeypatch.setattr(
        guard,
        "monitor_roles_from_token",
        lambda _token: frozenset({"view-clients", "view-realm", "manage-realm"}),
    )

    with pytest.raises(IsolationError, match="非只读"):
        guard._keycloak_monitor_state(Client(), {"Authorization": "admin"}, allow_incomplete=True)

    assert [path for method, path in calls if method == "post"] == [
        "/realms/eid-local/protocol/openid-connect/token"
    ]


def test_keycloak_monitor_accepts_exact_effective_composite_roles(monkeypatch):
    import scripts.verify_local_environment as guard

    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class Client:
        def get(self, path, **_kwargs):
            assert path == "/admin/realms/eid-local/clients"
            return Response([_keycloak_monitor_payload()])

        def post(self, path, **_kwargs):
            assert path == "/realms/eid-local/protocol/openid-connect/token"
            return Response({"access_token": "monitor-token"})

    monkeypatch.setattr(
        guard,
        "monitor_roles_from_token",
        lambda _token: frozenset({"query-clients", "view-clients", "view-realm"}),
    )

    assert guard._keycloak_monitor_state(
        Client(), {"Authorization": "admin"}, allow_incomplete=False
    ) == ("ready", {"monitor_id": "persisted-monitor-id"})


@pytest.mark.parametrize("initial_state", ["missing", "roles-missing"])
def test_keycloak_monitor_provisioning_creates_only_missing_parts(
    monkeypatch, initial_state
):
    import scripts.verify_local_environment as guard

    auth_headers = {"Authorization": "admin"}
    states = []
    if initial_state == "missing":
        states.append(("missing", {}, auth_headers))
    missing_roles = (
        frozenset({"view-clients", "view-realm"})
        if initial_state == "missing"
        else frozenset({"view-realm"})
    )
    states.extend(
        [
            (
                "roles-missing",
                {
                    "monitor_id": "persisted-monitor-id",
                    "missing_roles": missing_roles,
                },
                auth_headers,
            ),
            ("ready", {"monitor_id": "persisted-monitor-id"}, auth_headers),
        ]
    )
    calls = []

    class Response:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, path, **kwargs):
            calls.append(("get", path, kwargs))
            if path.endswith("/service-account-user"):
                return Response({"id": "service-account-id"})
            if path == "/admin/realms/eid-local/clients":
                return Response([{"id": "realm-management-id"}])
            role_name = path.rsplit("/", 1)[-1]
            return Response({"id": f"role-{role_name}", "name": role_name})

        def post(self, path, **kwargs):
            calls.append(("post", path, kwargs))
            return Response({}, 201 if path == "/admin/realms/eid-local/clients" else 204)

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", Client)
    monkeypatch.setattr(guard, "_verify_keycloak", lambda *_args, **_kwargs: states.pop(0))

    guard.provision_keycloak_readiness_monitor()

    create_calls = [
        call for call in calls
        if call[0:2] == ("post", "/admin/realms/eid-local/clients")
    ]
    assert bool(create_calls) is (initial_state == "missing")
    if create_calls:
        assert create_calls[0][2]["json"]["clientId"] == "eid-readiness-monitor"
        assert create_calls[0][2]["json"]["secret"] == guard.MONITOR_CLIENT_SECRET
    mapping_call = next(
        call for call in calls if call[0] == "post" and "/role-mappings/clients/" in call[1]
    )
    assert [role["name"] for role in mapping_call[2]["json"]] == sorted(missing_roles)
    assert states == []


def test_ready_keycloak_monitor_is_never_overwritten(monkeypatch):
    import scripts.verify_local_environment as guard

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            pytest.fail("matching monitor must not be overwritten")

    monkeypatch.setattr(guard, "service_container", lambda *_args: None)
    monkeypatch.setattr(guard.httpx, "Client", Client)
    monkeypatch.setattr(
        guard,
        "_verify_keycloak",
        lambda *_args, **_kwargs: (
            "ready",
            {"monitor_id": "persisted-monitor-id"},
            {"Authorization": "admin"},
        ),
    )

    guard.provision_keycloak_readiness_monitor()


def test_image_manifest_matches_compose_and_dockerfiles():
    verify_image_manifest()


def test_image_manifest_rejects_unpinned_base(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard

    manifest = json.loads(guard.IMAGE_LOCK.read_text(encoding="utf-8"))
    manifest["base_images"]["redis"] = "redis:8.2.1-alpine3.22"
    lock = tmp_path / "images.lock.json"
    lock.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(guard, "IMAGE_LOCK", lock)

    with pytest.raises(IsolationError, match="redis.*sha256"):
        verify_image_manifest()


@pytest.mark.parametrize("surface", ["compose", "python", "web"])
def test_image_lock_cannot_be_satisfied_by_comments(monkeypatch, tmp_path, surface):
    import scripts.verify_local_environment as guard

    (tmp_path / "deployment").mkdir()
    for name in ("compose.yaml", "python.Dockerfile", "web.Dockerfile"):
        text = (guard.ROOT / "deployment" / name).read_text(encoding="utf-8")
        target = {"compose": "compose.yaml", "python": "python.Dockerfile", "web": "web.Dockerfile"}[surface]
        if name == target:
            if surface == "compose":
                old = next(line for line in text.splitlines() if "image: redis:" in line)
                text = text.replace(old, "    # " + old.strip() + "\n    image: redis:latest")
            else:
                old = text.splitlines()[0]
                text = text.replace(old, "# " + old + "\nFROM python:latest", 1)
        (tmp_path / "deployment" / name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "COMPOSE_FILE", tmp_path / "deployment/compose.yaml")
    with pytest.raises(IsolationError, match="镜像"):
        verify_image_manifest()


@pytest.mark.parametrize("drift", ["replacement", "stopped", "unhealthy", "wrong-image", "owner-record"])
def test_runtime_image_collection_rechecks_earlier_containers(monkeypatch, drift):
    import scripts.verify_local_environment as guard

    services = {"api": "api:0.1.0", "web": "web:0.1.0", "worker": "worker:0.1.0"}
    fingerprint = f"sha256:{'a' * 64}"
    image_id = f"sha256:{'b' * 64}"
    monkeypatch.setattr(guard, "build_images", lambda: services)
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    monkeypatch.setattr(guard, "infrastructure_images", lambda: {})
    monkeypatch.setattr(guard, "source_fingerprint", lambda service: fingerprint)
    collected = set()
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "other-owner" if drift == "owner-record" and len(collected) == 3 else "owner")

    def fake_command(*args):
        if args[1:3] == ("image", "inspect"):
            collected.add(args[3].split(":")[0])
            return json.dumps([{"Id": image_id, "Config": {"Labels": {"io.eid.source-fingerprint": fingerprint}}}])
        changed = len(collected) == 3
        if args[1:3] == ("ps", "-q"):
            service = args[-1].rsplit("=", 1)[1]
            return "replacement-api" if changed and service == "api" and drift == "replacement" else f"container-{service}"
        if args[1] == "inspect":
            changed = changed and args[2].endswith("api")
            return json.dumps([{
                "Image": f"sha256:{'c' * 64}" if changed and drift == "wrong-image" else image_id,
                "Config": {"Labels": {"io.eid.owner": "owner"}},
                "State": {"Running": not (changed and drift == "stopped"), "Health": {"Status": "unhealthy" if changed and drift == "unhealthy" else "healthy"}},
            }])
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)
    with pytest.raises(IsolationError):
        guard.current_runtime_images()


def test_keycloak_readiness_is_a_bounded_bootstrap_gate():
    from pathlib import Path

    compose = (Path(__file__).parents[2] / "deployment" / "compose.yaml").read_text(
        encoding="utf-8"
    )
    assert "/health/ready" in compose
    assert "retries: 40" in compose
    assert "keycloak: {condition: service_healthy}" in compose


@pytest.mark.parametrize(
    "arguments",
    [
        ["--prepare", "--check-only"],
        ["--prepare", "--record-runtime-images"],
        ["--prepare", "--verify-runtime-images"],
        ["--check-only", "--record-runtime-images"],
        ["--record-runtime-images", "--verify-runtime-images"],
    ],
)
def test_guard_actions_are_mutually_exclusive(monkeypatch, arguments):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard.sys, "argv", ["verify_local_environment.py", *arguments])
    with pytest.raises(SystemExit) as exc_info:
        guard.main()
    assert exc_info.value.code == 2


def test_direct_runtime_record_requires_public_readiness_before_inspection(
    monkeypatch, tmp_path
):
    import scripts.verify_local_environment as guard
    import scripts.verify_readiness as readiness

    manifest = tmp_path / "runtime-images.json"
    manifest.write_text('{"stale": true}\n', encoding="utf-8")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", manifest)
    monkeypatch.setattr(
        readiness,
        "verify_public_readiness",
        lambda: (_ for _ in ()).throw(IsolationError("public not ready")),
    )
    monkeypatch.setattr(
        guard,
        "current_runtime_images",
        lambda: pytest.fail("readiness 失败后不得检查或记录运行镜像"),
    )

    with pytest.raises(IsolationError, match="public not ready"):
        record_runtime_images()
    assert manifest.read_text(encoding="utf-8") == '{"stale": true}\n'


def test_runtime_image_manifest_binds_source_image_and_healthy_container(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard
    import scripts.verify_readiness as readiness

    image_ids = {
        "eid-local-api:0.1.0": f"sha256:{'1' * 64}",
        "eid-local-worker:0.1.0": f"sha256:{'2' * 64}",
        "eid-local-web:0.1.0": f"sha256:{'3' * 64}",
    }
    services = {image_ref.split("-")[-1].split(":")[0]: image_ref for image_ref in image_ids}
    fingerprints = {
        "api": f"sha256:{'a' * 64}",
        "worker": f"sha256:{'b' * 64}",
        "web": f"sha256:{'c' * 64}",
    }
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")
    monkeypatch.setattr(readiness, "verify_public_readiness", lambda: {"status": "ready"})
    monkeypatch.setattr(guard, "build_images", lambda: services)
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    monkeypatch.setattr(guard, "infrastructure_images", lambda: {})
    monkeypatch.setattr(guard, "source_fingerprint", fingerprints.__getitem__)
    for service, fingerprint in fingerprints.items():
        monkeypatch.setenv(guard.BUILD_SOURCE_ENV[service], fingerprint)

    def fake_command(*args):
        if args[1:3] == ("image", "inspect"):
            service = next(name for name, ref in services.items() if ref == args[3])
            return json.dumps([{
                "Id": image_ids[args[3]],
                "Config": {"Labels": {"io.eid.source-fingerprint": fingerprints[service]}},
            }])
        if args[1:3] == ("ps", "-q"):
            service = args[-1].rsplit("=", 1)[1]
            return f"container-{service}"
        if args[1] == "inspect":
            service = args[2].removeprefix("container-")
            return json.dumps(
                [
                    {
                        "Image": image_ids[services[service]],
                        "State": {"Running": True, "Health": {"Status": "healthy"}},
                    "Config": {"Labels": {"io.eid.owner": "owner"}},
                    }
                ]
            )
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)
    manifest = record_runtime_images()

    assert manifest["services"]["api"]["container_id"] == "container-api"
    assert verify_runtime_images() == manifest

    monkeypatch.setattr(guard, "source_fingerprint", lambda _service: f"sha256:{'f' * 64}")
    with pytest.raises(IsolationError, match="重新运行 bootstrap"):
        verify_runtime_images()


def test_runtime_image_record_rejects_source_changed_after_build(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard
    import scripts.verify_readiness as readiness

    services = {
        "api": "eid-local-api:0.1.0",
        "worker": "eid-local-worker:0.1.0",
        "web": "eid-local-web:0.1.0",
    }
    fingerprints = {
        "api": f"sha256:{'a' * 64}",
        "worker": f"sha256:{'b' * 64}",
        "web": f"sha256:{'c' * 64}",
    }
    image_ids = {service: f"sha256:{digit * 64}" for service, digit in zip(services, "123")}
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")
    monkeypatch.setattr(readiness, "verify_public_readiness", lambda: {"status": "ready"})
    monkeypatch.setattr(guard, "build_images", lambda: services)
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    monkeypatch.setattr(guard, "infrastructure_images", lambda: {})
    for service, fingerprint in fingerprints.items():
        monkeypatch.setenv(guard.BUILD_SOURCE_ENV[service], fingerprint)
    monkeypatch.setattr(
        guard,
        "source_fingerprint",
        lambda service: f"sha256:{'d' * 64}" if service == "web" else fingerprints[service],
    )

    def fake_command(*args):
        if args[1:3] == ("image", "inspect"):
            service = next(name for name, ref in services.items() if ref == args[3])
            return json.dumps([{
                "Id": image_ids[service],
                "Config": {"Labels": {"io.eid.source-fingerprint": fingerprints[service]}},
            }])
        if args[1:3] == ("ps", "-q"):
            return f"container-{args[-1].rsplit('=', 1)[1]}"
        if args[1] == "inspect":
            service = args[2].removeprefix("container-")
            return json.dumps([{
                "Image": image_ids[service],
                "State": {"Running": True, "Health": {"Status": "healthy"}},
                    "Config": {"Labels": {"io.eid.owner": "owner"}},
            }])
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)

    with pytest.raises(IsolationError, match="构建前指纹"):
        record_runtime_images()
    assert not guard.RUNTIME_IMAGE_MANIFEST.exists()


@pytest.mark.parametrize("image_label", [None, f"sha256:{'f' * 64}"])
def test_direct_runtime_image_record_rejects_missing_or_mismatched_image_label(
    monkeypatch, tmp_path, image_label
):
    import scripts.verify_local_environment as guard
    import scripts.verify_readiness as readiness

    services = {"api": "eid-local-api:0.1.0", "worker": "eid-local-worker:0.1.0", "web": "eid-local-web:0.1.0"}
    fingerprints = {service: f"sha256:{digit * 64}" for service, digit in zip(services, "abc")}
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")
    monkeypatch.setattr(readiness, "verify_public_readiness", lambda: {"status": "ready"})
    monkeypatch.setattr(guard, "build_images", lambda: services)
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    monkeypatch.setattr(guard, "infrastructure_images", lambda: {})
    monkeypatch.setattr(guard, "source_fingerprint", fingerprints.__getitem__)
    for service, fingerprint in fingerprints.items():
        monkeypatch.setenv(guard.BUILD_SOURCE_ENV[service], fingerprint)

    def fake_command(*args):
        if args[1:3] == ("image", "inspect"):
            service = next(name for name, ref in services.items() if ref == args[3])
            label = image_label if service == "api" else fingerprints[service]
            labels = {} if label is None else {"io.eid.source-fingerprint": label}
            return json.dumps([{"Id": f"sha256:{'1' * 64}", "Config": {"Labels": labels}}])
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", fake_command)

    with pytest.raises(IsolationError, match="源指纹标签"):
        record_runtime_images()
    assert not guard.RUNTIME_IMAGE_MANIFEST.exists()


@pytest.mark.parametrize("changed_service", ["postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx"])
def test_pinned_infrastructure_runtime_image_drift_is_rejected(monkeypatch, changed_service):
    import scripts.verify_local_environment as guard

    applications = {name: f"{name}:0.1.0" for name in ("api", "worker", "web")}
    infrastructure = {name: f"{name}:1.0@sha256:{'f' * 64}" for name in ("postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx")}
    image_id = f"sha256:{'a' * 64}"
    fingerprint = f"sha256:{'b' * 64}"
    monkeypatch.setattr(guard, "build_images", lambda: applications)
    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    monkeypatch.setattr(guard, "infrastructure_images", lambda: infrastructure)
    monkeypatch.setattr(guard, "source_fingerprint", lambda service: fingerprint)
    drift = False

    def command(*args):
        if args[1:3] == ("image", "inspect"):
            return json.dumps([{"Id": image_id, "Config": {"Labels": {"io.eid.source-fingerprint": fingerprint}}}])
        if args[1:3] == ("ps", "-q"):
            return "container-" + args[-1].rsplit("=", 1)[1]
        if args[1] == "inspect":
            wrong = drift and args[2] == f"container-{changed_service}"
            return json.dumps([{"Image": f"sha256:{'c' * 64}" if wrong else image_id, "State": {"Running": True, "Health": {"Status": "healthy"}}, "Config": {"Labels": {"io.eid.owner": "owner"}}}])
        raise AssertionError(args)

    monkeypatch.setattr(guard, "command", command)
    records = guard.current_runtime_images()
    assert set(records) == set(applications) | set(infrastructure)
    assert records[changed_service] == {"image_ref": infrastructure[changed_service], "image_id": image_id, "container_id": f"container-{changed_service}"}
    drift = True
    with pytest.raises(IsolationError, match="运行容器未使用当前构建镜像 ID"):
        guard.current_runtime_images()


@pytest.mark.parametrize("changed_before", ["rabbitmq", "keycloak", "s3"])
def test_storage_rechecks_instance_before_each_write(monkeypatch, changed_before):
    import scripts.initialize_local_storage as storage

    writes = []
    replaced = False
    monkeypatch.setattr(storage, "verify_database", lambda url: None)
    monkeypatch.setattr(storage, "ownership", lambda: {"nonce": "owner"})
    monkeypatch.setattr(storage, "service_container", lambda service, *args: f"{service}-{'new' if replaced else 'old'}")
    monkeypatch.setattr(storage, "verify_rabbitmq", lambda **kwargs: "missing")
    monkeypatch.setattr(storage, "verify_keycloak", lambda **kwargs: "missing")
    monkeypatch.setattr(storage, "verify_s3_configuration", lambda: None)

    class Client:
        def list_buckets(self):
            nonlocal replaced
            replaced = changed_before == "rabbitmq"
            return {"Buckets": []}

        def create_bucket(self, **kwargs):
            pytest.fail("replacement must be rejected before S3 write")

    def rabbitmq_write():
        nonlocal replaced
        writes.append("rabbitmq")
        replaced = changed_before == "keycloak"

    def keycloak_write():
        nonlocal replaced
        writes.append("keycloak")
        replaced = changed_before == "s3"

    monkeypatch.setattr(storage, "s3_client", lambda role: Client())
    monkeypatch.setattr(storage, "create_rabbitmq_runtime_users", rabbitmq_write)
    monkeypatch.setattr(storage, "provision_keycloak_readiness_monitor", keycloak_write)
    with pytest.raises(RuntimeError, match="实例已变化"):
        storage.main()
    assert writes == {"rabbitmq": [], "keycloak": ["rabbitmq"], "s3": ["rabbitmq", "keycloak"]}[changed_before]


def test_service_port_match_does_not_accept_foreign_owner(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard

    state = tmp_path / "ownership.json"
    state.write_text('{"nonce":"expected-owner"}', encoding="utf-8")
    monkeypatch.setattr(guard, "STATE", state)
    metadata = {"Config": {"Labels": {"io.eid.owner": "foreign-owner"}}, "HostConfig": {"PortBindings": {"8333/tcp": [{"HostIp": "127.0.0.1", "HostPort": "58333"}]}}}
    monkeypatch.setattr(guard, "command", lambda *args: "container-s3" if args[1] == "ps" else json.dumps([metadata]))
    with pytest.raises(IsolationError, match="归属不匹配"):
        guard.service_container("seaweedfs", 8333, 58333)


@pytest.mark.parametrize(("required", "health", "accepted"), [(True, None, False), (False, None, True), (False, "unhealthy", False), (True, "healthy", True)])
def test_container_health_contract_distinguishes_unconfigured_infrastructure(monkeypatch, required, health, accepted):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "owner")
    state = {"Running": True}
    if health is not None:
        state["Health"] = {"Status": health}
    monkeypatch.setattr(guard, "command", lambda *args: "container" if args[1] == "ps" else json.dumps([{"Image": "image", "State": state, "Config": {"Labels": {"io.eid.owner": "owner"}}}]))
    if accepted:
        assert guard._runtime_container_id("service", "image", require_health=required) == "container"
    else:
        with pytest.raises(IsolationError, match="健康"):
            guard._runtime_container_id("service", "image", require_health=required)


@pytest.mark.parametrize("service", ["api", "seaweedfs"])
def test_same_image_healthy_container_with_foreign_nonce_is_rejected(monkeypatch, service):
    import scripts.verify_local_environment as guard

    monkeypatch.setattr(guard, "_recorded_owner_nonce", lambda: "expected-owner")
    metadata = {"Image": "expected-image", "State": {"Running": True, "Health": {"Status": "healthy"}}, "Config": {"Labels": {"io.eid.owner": "foreign-owner"}}}
    monkeypatch.setattr(guard, "command", lambda *args: "same-image-container" if args[1] == "ps" else json.dumps([metadata]))
    with pytest.raises(IsolationError, match="归属不匹配"):
        guard._runtime_container_id(service, "expected-image", require_health=service == "api")


def test_readiness_loss_during_image_capture_preserves_previous_manifest(monkeypatch, tmp_path):
    import scripts.verify_local_environment as guard
    import scripts.verify_readiness as readiness

    events = []
    manifest = tmp_path / "runtime-images.json"
    manifest.write_text('{"previous":"evidence"}\n', encoding="utf-8")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", manifest)
    monkeypatch.setattr(guard, "expected_build_source_fingerprints", lambda: {})

    def verify_ready():
        events.append("readiness")
        if len(events) > 1:
            raise IsolationError("dependency lost after image capture")

    def capture(expected):
        events.append("image-capture")
        return {}

    monkeypatch.setattr(readiness, "verify_public_readiness", verify_ready)
    monkeypatch.setattr(guard, "current_runtime_images", capture)
    with pytest.raises(IsolationError, match="dependency lost"):
        guard.record_runtime_images()
    assert events == ["readiness", "image-capture", "readiness"]
    assert manifest.read_text(encoding="utf-8") == '{"previous":"evidence"}\n'
