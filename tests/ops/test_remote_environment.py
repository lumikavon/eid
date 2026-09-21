import copy
import json
import os
import socket
import tarfile

import pytest
import yaml

from scripts import remote_environment as remote
from scripts import remote_service_operations as operations
from scripts import verify_local_environment as guard
from test_remote_guard import isolation_config
import test_remote_manifest_integration as manifest_integration
from test_remote_manifest_integration import record_generated_manifest


OWNER = "c38d0f7481a6476ebc8b0fd2fe087db3"
production_io = manifest_integration.production_io


@pytest.fixture(autouse=True)
def closed_io(monkeypatch, tmp_path):
    monkeypatch.setattr(guard, "STATE", tmp_path / "ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / "runtime-images.json")
    monkeypatch.setattr(guard, "environment_state_directory", lambda *args: tmp_path)
    monkeypatch.setattr(remote, "evidence_directory", lambda config: tmp_path / "remote")

    def forbidden(*args, **kwargs):
        pytest.fail("Remote environment tests prohibit implicit process or network access")

    for name in ("run", "check_output", "Popen"):
        monkeypatch.setattr(remote.subprocess, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def config():
    return remote.load_config()


@pytest.mark.parametrize(("section", "key", "value"), [
    ("ssh", "alias", "production"), ("ssh", "hostname", "172.27.0.39"),
    ("ssh", "user", "root"), ("ssh", "proxy_jump", "other-jump"),
    ("remote", "root", "/opt/docker"), ("remote", "root", "/opt/docker/eid/../other"),
    ("remote", "root", "/opt/docker/eid"), ("remote", "root", "/opt/eid/../other"),
    ("remote", "compose_project", "other-project"),
    ("remote", "docker_endpoint", "tcp://production:2375"),
    ("remote", "bind_address", "0.0.0.0"), ("tunnels", "bind_address", "::"),
    ("application", "database", "enterprise"),
    ("application", "public_origin", "http://172.27.0.38:18080"),
])
def test_foreign_target_and_scope_rejected(config, section, key, value):
    config[section][key] = value
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_config(config)


def test_unknown_config_and_duplicate_ports_rejected(config):
    config["remote"]["mounts"] = ["/var/run/docker.sock"]
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_config(config)
    del config["remote"]["mounts"]
    config["tunnels"]["ports"]["redis"] = 18080
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_config(config)


@pytest.mark.parametrize("extra", ["schema_version: 1\n", "  credentials: repository-development-fixtures\n"])
def test_duplicate_yaml_keys_are_rejected_even_when_values_match(tmp_path, extra):
    path = tmp_path / "duplicate.yaml"
    path.write_text(remote.DEFAULT_CONFIG.read_text(encoding="utf-8") + extra, encoding="utf-8")
    with pytest.raises(remote.RemoteEnvironmentError, match="Duplicate environment configuration key"):
        remote.load_config(path)


def test_windows_excluded_port_rejected(config):
    config["tunnels"]["ports"]["redis"] = 56379
    with pytest.raises(remote.RemoteEnvironmentError, match="Windows excluded"):
        remote.validate_config(config)


def test_actual_compose_render_has_nine_services_and_isolated_names(config):
    files = remote.source_files(remote.ROOT)
    rendered = yaml.safe_load(remote.render_compose(config, OWNER, files))
    assert set(rendered["services"]) == remote.SERVICES
    assert rendered["name"] == "eid-remote-dev"
    assert {value["name"] for value in rendered["volumes"].values()} == {
        "eid-remote-dev-postgres", "eid-remote-dev-seaweedfs", "eid-remote-dev-keycloak",
        "eid-remote-dev-rabbitmq", "eid-remote-dev-redis"}
    assert rendered["networks"]["default"]["name"] == "eid-remote-dev_default"
    for service in rendered["services"].values():
        assert service["labels"]["io.eid.owner"] == OWNER
        assert service["cgroup"] == "private"
        assert all(port.startswith("127.0.0.1:") for port in service["ports"])
    assert rendered["services"]["api"]["environment"]["EID_DATABASE_URL"].endswith(
        "@postgres:5432/eid_local_dev")
    assert rendered["services"]["worker"]["environment"]["EID_DATABASE_URL"].startswith(
        "postgresql://eid_worker:")
    assert rendered["services"]["api"]["build"]["args"]["EID_SOURCE_FINGERPRINT"].startswith(
        "sha256:")
    assert "$${RABBITMQ_DEFAULT_USER}" in remote.render_compose(config, OWNER, files).decode()


def test_image_fingerprints_match_existing_source_contract():
    from scripts.verify_local_environment import source_fingerprint

    files = remote.source_files(remote.ROOT)
    for service in ("api", "worker", "web"):
        assert remote.image_source_fingerprint(service, files) == source_fingerprint(service)


def test_remote_health_budget_preserves_every_rabbitmq_check(config):
    files = remote.source_files(remote.ROOT)
    original = yaml.safe_load(files["deployment/compose.yaml"])["services"]["rabbitmq"]["healthcheck"]
    rendered = yaml.safe_load(remote.render_compose(config, OWNER, files))
    actual = rendered["services"]["rabbitmq"]["healthcheck"]
    assert actual == original | {"timeout": "20s"}
    for invalid in (True, 0, 31, "20"):
        config["remote"]["rabbitmq_health_timeout_seconds"] = invalid
        with pytest.raises(remote.RemoteEnvironmentError, match="health timeout"):
            remote.validate_config(config)


def test_recreated_broker_keeps_observed_node_and_data_directory(config):
    files = remote.source_files(remote.ROOT)
    first = yaml.safe_load(remote.render_compose(config, OWNER, files))
    files["edw-api/src/candidate_change.py"] = b"# next release\n"
    second = yaml.safe_load(remote.render_compose(config, OWNER, files))
    assert first["services"]["api"]["image"] != second["services"]["api"]["image"]
    for rendered in (first, second):
        broker = rendered["services"]["rabbitmq"]
        assert broker["hostname"] == "5e8cac11b089"
        assert broker["environment"]["RABBITMQ_NODENAME"] == "rabbit@5e8cac11b089"
        assert broker["environment"]["RABBITMQ_MNESIA_DIR"] == (
            "/var/lib/rabbitmq/mnesia/rabbit@5e8cac11b089")
        assert broker["volumes"] == ["eid-rabbitmq:/var/lib/rabbitmq"]
        assert rendered["volumes"]["eid-rabbitmq"]["name"] == "eid-remote-dev-rabbitmq"


@pytest.mark.parametrize("key", ["hostname", "nodename", "data_dir"])
def test_unverified_broker_identity_cannot_select_new_or_old_node(config, key):
    config["remote"]["rabbitmq_identity"][key] = "rabbit@06043a6c248a"
    with pytest.raises(remote.RemoteEnvironmentError, match="verified existing node"):
        remote.render_compose(config, OWNER, remote.source_files(remote.ROOT))


def test_yaml_ports_drive_remote_compose_and_tunnel_independently(config):
    config["remote"]["ports"]["redis"] = 56380
    config["tunnels"]["ports"]["redis"] = 16380
    rendered = yaml.safe_load(remote.render_compose(config, OWNER, remote.source_files(remote.ROOT)))
    assert rendered["services"]["redis"]["ports"] == ["127.0.0.1:56380:6379"]
    args = remote.tunnel_command(config)
    assert "127.0.0.1:16380:127.0.0.1:56380" in args
    assert "127.0.0.1:18080:127.0.0.1:18080" in args
    assert "ExitOnForwardFailure=yes" in args
    assert "StrictHostKeyChecking=yes" in args
    assert "Port=22" in args


@pytest.mark.parametrize("change", ["image", "network", "volume", "service", "interpolation"])
def test_changed_base_isolation_contract_is_rejected(config, change):
    files = remote.source_files(remote.ROOT)
    compose = yaml.safe_load(files["deployment/compose.yaml"])
    if change == "image":
        compose["services"]["postgres"]["image"] = "postgres:latest"
    elif change == "network":
        compose["services"]["api"]["network_mode"] = "host"
    elif change == "volume":
        compose["volumes"]["eid-postgres"]["external"] = True
    elif change == "service":
        compose["services"]["unrelated"] = {"image": "postgres:latest"}
    else:
        compose["services"]["postgres"]["environment"]["POSTGRES_DB"] = "${TARGET_DB}"
    files["deployment/compose.yaml"] = yaml.safe_dump(compose).encode()
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.render_compose(config, OWNER, files)


@pytest.mark.parametrize("field,value", [("privileged", True), ("pid", "host"),
    ("ipc", "host"), ("uts", "host"), ("userns_mode", "host"), ("cgroup", "host"),
    ("cap_add", ["SYS_ADMIN"]), ("devices", ["/dev/mem"]),
    ("device_cgroup_rules", ["a *:* rwm"]), ("security_opt", ["seccomp=unconfined"])])
def test_renderer_rejects_unreviewed_isolation_settings(config, field, value):
    files = remote.source_files(remote.ROOT)
    compose = yaml.safe_load(files["deployment/compose.yaml"])
    compose["services"]["worker"][field] = value
    files["deployment/compose.yaml"] = yaml.safe_dump(compose).encode()
    with pytest.raises(remote.RemoteEnvironmentError, match="isolation-affecting"):
        remote.render_compose(config, OWNER, files)


@pytest.mark.parametrize("service", sorted(remote.SERVICES))
@pytest.mark.parametrize("namespace", ["host", "private"])
def test_renderer_rejects_base_cgroup_overrides(config, service, namespace):
    files = remote.source_files(remote.ROOT)
    compose = yaml.safe_load(files["deployment/compose.yaml"])
    compose["services"][service]["cgroup"] = namespace
    files["deployment/compose.yaml"] = yaml.safe_dump(compose).encode()
    with pytest.raises(remote.RemoteEnvironmentError, match="isolation-affecting"):
        remote.render_compose(config, OWNER, files)


@pytest.mark.parametrize("name", [".env", ".env.production", "scripts/.env", "scripts/secrets.py",
    "scripts/secrets/token.py", "edw-web/src/.env.local", "edw-api/src/id_rsa.py",
    "_bmad/config.yaml", ".local/ownership.json", ".git/config", "docs/report.md",
    "scripts/id_rsa", "scripts/token.pem", "../escape.py", "/scripts/app.py",
    "scripts\\escape.py", "edw-web/src/node_modules/pkg/index.ts"])
def test_private_files_are_not_source_package_members(name):
    assert not remote.allowed_source(name)


def fixture_source_tree(tmp_path):
    for relative in remote.FIXED_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((remote.ROOT / relative).read_bytes())
    for directory in remote.SOURCE_TREES:
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    for relative in ("scripts/minimal.py", "edw-api/src/app.py", "edw-worker/src/app.py",
                     "edw-web/src/main.ts", "migrations/env.py", "contracts/result.json"):
        (tmp_path / relative).write_text("{}")


def test_package_allowlist_omits_secrets_and_never_copies_runtime_receipts(config, tmp_path):
    source = tmp_path / "source"
    fixture_source_tree(source)
    for relative in ("scripts/.env", "scripts/secrets.py", ".local/runtime-images.json",
                     ".git/config", "_bmad/private.yaml"):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DO-NOT-SHIP")
    output = tmp_path / "package.tar.gz"
    result = remote.create_artifact(config, OWNER, output, package=True, root=source)
    assert result["runtime_verified"] is False
    with tarfile.open(output) as archive:
        names = set(archive.getnames())
        assert "scripts/minimal.py" in names
        assert "deployment/remote.compose.yaml" in names
        assert ".eid-remote-owner.json" in names
        assert not any(".local" in name or "secret" in name or ".env" in name for name in names)
        assert all(member.isfile() for member in archive.getmembers())
        for member in archive.getmembers():
            assert b"DO-NOT-SHIP" not in archive.extractfile(member).read()
        receipt = json.load(archive.extractfile(".eid-remote-owner.json"))
        assert receipt == remote.owner_receipt(config, OWNER)
        manifest = json.load(archive.extractfile("deployment/remote-package.json"))
        assert manifest["kind"] == "source-package-not-runtime-evidence"
    with pytest.raises(remote.RemoteEnvironmentError, match="refusing overwrite"):
        remote.create_artifact(config, OWNER, output, package=True, root=source)


def test_linked_source_is_rejected(tmp_path):
    fixture_source_tree(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("credential")
    os.link(outside, tmp_path / "scripts/linked.py")
    with pytest.raises(remote.RemoteEnvironmentError, match="Hard-linked"):
        remote.source_files(tmp_path)


def test_package_preserves_all_image_fingerprint_inputs(config, tmp_path, monkeypatch):
    from scripts import verify_local_environment as guard

    fixture_source_tree(tmp_path)
    assets = {"edw-api/src/schema.json": b'{"api":true}',
              "edw-worker/src/template.jinja": b"worker template",
              "edw-web/src/assets/logo.png": b"\x89PNG\r\n\x1a\nfixture",
              "edw-web/src/options.json": b'{"ui":true}',
              "edw-web/public/favicon.ico": b"icon", "edw-web/src/.assets/visible.txt": b"asset"}
    for relative, content in assets.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    files = remote.source_files(tmp_path)
    assert {name: files[name] for name in assets} == assets
    for service in ("api", "worker", "web"):
        assert remote.image_source_fingerprint(service, files) == guard.source_fingerprint(service)
    artifact = tmp_path / "candidate.tar.gz"
    remote.create_artifact(config, OWNER, artifact, package=True, root=tmp_path)
    with tarfile.open(artifact) as archive:
        for name, content in assets.items():
            assert archive.extractfile(name).read() == content


@pytest.mark.parametrize("relative", ["edw-web/src/.env.local", "edw-api/src/token.pem",
    "edw-web/public/secrets/token.json", "edw-worker/src/.local/config.json"])
def test_forbidden_image_input_fails_instead_of_silently_changing_fingerprint(tmp_path, relative):
    fixture_source_tree(tmp_path)
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"DO-NOT-SHIP")
    with pytest.raises(remote.RemoteEnvironmentError, match="fingerprint input is forbidden"):
        remote.source_files(tmp_path)


def test_newly_supported_image_assets_still_reject_hardlinks(tmp_path):
    fixture_source_tree(tmp_path)
    (tmp_path / "external.png").write_bytes(b"private")
    os.link(tmp_path / "external.png", tmp_path / "edw-web/src/linked.png")
    with pytest.raises(remote.RemoteEnvironmentError, match="Hard-linked"):
        remote.source_files(tmp_path)


def clean_state():
    return {"root_exists": False, "receipt": None, "containers": [], "volumes": [],
            "networks": [], "listeners": [],
            "server": {"Os": "linux", "Arch": "amd64", "Version": "25.0.3"},
            "compose": "2.32.4", "compose_wait": True, "buildx": ""}


def owned_state(config):
    state = clean_state()
    state["root_exists"] = True
    state["receipt"] = remote.owner_receipt(config, OWNER)
    project = config["remote"]["compose_project"]
    labels = {"io.eid.owner": OWNER, "io.eid.environment": config["environment"],
              "com.docker.compose.project": project}
    for name in remote.VOLUME_SERVICES:
        state["volumes"].append({"name": project + "-" + name, "labels": dict(labels),
                                 "driver": "local", "options": {},
                                 "mountpoint": "/var/lib/docker/volumes/" + project + "-" + name + "/_data"})
    state["networks"] = [{"name": project + "_default", "labels": dict(labels),
                          "driver": "bridge", "options": {}}]
    for service in sorted(remote.SERVICES):
        state["containers"].append({
            "id": service + "-id", "name": f"{project}-{service}-1",
            "labels": {**labels, "com.docker.compose.service": service},
            "ports": {f"{port}/tcp": [{"HostIp": "127.0.0.1",
                "HostPort": str(config["remote"]["ports"][name])}]
                for name, (target, port) in remote.PORTS.items() if target == service},
            "mounts": [{"Type": "volume", "Name": project + "-" + service}]
                      if service in remote.VOLUME_SERVICES else [],
            "networks": [project + "_default"], "network_mode": project + "_default",
            "state": "running", "isolation_config": isolation_config(),
        })
    return state


def test_unclaimed_empty_remote_can_be_inspected_but_missing_buildx_stays_blocked(config):
    result = remote.validate_remote_state(config, clean_state())
    assert result["isolation_verified"] is True
    assert result["runtime_verified"] is False
    assert result["buildx_available"] is False
    with pytest.raises(remote.RemoteEnvironmentError, match="buildx"):
        remote.validate_remote_state(config, clean_state(), require_build=True)
    with pytest.raises(remote.RemoteEnvironmentError, match="not installed"):
        remote.validate_remote_state(config, clean_state(), require_running=True)


def test_owned_nine_service_inventory_is_not_application_acceptance(config):
    result = remote.validate_remote_state(config, owned_state(config), OWNER, require_running=True)
    assert len(result["services"]) == 9
    assert result["runtime_verified"] is False


@pytest.mark.parametrize("mutation", ["owner", "root", "volume_owner", "external_volume",
    "duplicate_service", "network_mode", "binding", "foreign_volume", "foreign_network",
    "escape_mount", "extra_network", "stopped", "unmanaged_listener"])
def test_remote_guard_rejects_foreign_or_incomplete_resources(config, mutation):
    state = owned_state(config)
    if mutation == "owner":
        state["receipt"]["nonce"] = "b" * 32
    elif mutation == "root":
        state["root_exists"] = False
        state["receipt"] = None
    elif mutation == "volume_owner":
        state["volumes"][0]["labels"]["io.eid.owner"] = "foreign"
    elif mutation == "external_volume":
        state["volumes"][0]["options"] = {"device": "/enterprise/data", "type": "none"}
    elif mutation == "duplicate_service":
        state["containers"].append(copy.deepcopy(state["containers"][0]))
    elif mutation == "network_mode":
        state["containers"][0]["network_mode"] = "host"
    elif mutation == "binding":
        container = next(item for item in state["containers"] if item["ports"])
        next(iter(container["ports"].values()))[0]["HostIp"] = "0.0.0.0"
    elif mutation in {"foreign_volume", "foreign_network"}:
        container = next(item for item in state["containers"] if item["mounts"])
        container["labels"]["com.docker.compose.project"] = "unrelated"
        container["name"] = "unrelated-container"
        if mutation == "foreign_network":
            container["mounts"] = []
    elif mutation == "escape_mount":
        state["containers"][0]["mounts"].append({"Type": "bind", "Source": "/opt/docker/other"})
    elif mutation == "extra_network":
        state["containers"][0]["networks"].append("enterprise_default")
    elif mutation == "stopped":
        state["containers"][0]["state"] = "exited"
    else:
        state = clean_state()
        state["listeners"] = [{"address": "127.0.0.1", "port": 55432}]
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_remote_state(config, state, OWNER, require_running=mutation != "unmanaged_listener")


def test_foreign_container_port_collision_blocks_empty_environment(config):
    state = clean_state()
    state["containers"] = [{"name": "unrelated", "labels": {}, "networks": [], "mounts": [],
        "ports": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "55432"}]}}]
    with pytest.raises(remote.RemoteEnvironmentError, match="occupies an EID port"):
        remote.validate_remote_state(config, state)


def test_ssh_alias_change_rejected_before_remote_connection(config, monkeypatch):
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        return remote.subprocess.CompletedProcess(arguments, 0,
            "hostname 172.27.0.39\nuser seadee\nproxyjump jump-local\n", "")

    monkeypatch.setattr(remote.subprocess, "run", run)
    with pytest.raises(remote.RemoteEnvironmentError, match="Effective SSH"):
        remote.remote_check(config)
    assert len(calls) == 1
    assert "-G" in calls[0]


@pytest.mark.parametrize("extra", [
    "localforward 0.0.0.0:19000 127.0.0.1:5432\n",
    "remoteforward 0.0.0.0:19000 127.0.0.1:5432\n",
    "dynamicforward *:19000\n", "localforward 127.0.0.1:19000 socks\n",
    "LocalForward 0.0.0.0:19000 127.0.0.1:5432\nlocalforward none\n",
    "hostname evil\nhostname 172.27.0.38\n", "user seadee\n",
    "proxyjump jump-local\n", "port 22\n", "clearallforwardings yes\n",
])
def test_additional_or_ambiguous_effective_ssh_configuration_blocks_connection(config, monkeypatch, extra):
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        return remote.subprocess.CompletedProcess(arguments, 0,
            "hostname 172.27.0.38\nuser seadee\nproxyjump jump-local\n"
            "port 22\nclearallforwardings no\n" + extra, "")

    monkeypatch.setattr(remote.subprocess, "run", run)
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.remote_inventory(config)
    assert len(calls) == 1 and "-G" in calls[0]


def test_approved_effective_ssh_config_is_accepted(config, monkeypatch):
    monkeypatch.setattr(remote.subprocess, "run", lambda arguments, **kwargs:
        remote.subprocess.CompletedProcess(arguments, 0,
            "hostname 172.27.0.38\nuser seadee\nproxyjump jump-local\n"
            "port 22\nclearallforwardings no\n", ""))
    remote.verify_ssh_config(config)


def test_cli_refuses_to_emit_tunnel_command_with_extra_ssh_forward(config, monkeypatch, capsys):
    monkeypatch.setattr(remote.sys, "argv", ["remote_environment.py", "tunnel-command"])
    monkeypatch.setattr(remote.subprocess, "run", lambda arguments, **kwargs:
        remote.subprocess.CompletedProcess(arguments, 0,
            "hostname 172.27.0.38\nuser seadee\nproxyjump jump-local\n"
            "port 22\nclearallforwardings no\nremoteforward *:19000 127.0.0.1:5432\n", ""))
    with pytest.raises(remote.RemoteEnvironmentError, match="forwarding configuration"):
        remote.main()
    assert not capsys.readouterr().out


def test_remote_probe_rejects_wrong_server_before_docker_calls(config, monkeypatch):
    monkeypatch.setattr(remote.subprocess, "run", lambda *args, **kwargs: pytest.fail("Docker called"))
    with pytest.raises(remote.RemoteEnvironmentError, match="connection address"):
        remote.collect_remote_state(config, "127.0.0.1 4567 172.27.0.39 22")


@pytest.fixture
def production_case(production_io, monkeypatch):
    monkeypatch.setattr(guard, "environment_state_directory", lambda *args: production_io.directory)
    return production_io


@pytest.mark.parametrize("user", ["0", "root", "00:1000", "", "other-user"])
def test_generated_manifest_and_consumer_reject_worker_user_drift(production_case, user):
    fixture = production_case
    manifest = record_generated_manifest(fixture)
    path = fixture.directory / "runtime-images.json"
    original = path.read_bytes()
    runtime = operations.captured_runtime()
    assert runtime.manifest == manifest
    container = fixture.host.containers["worker-id"]
    assert fixture.host.images[container["Image"]]["Config"]["User"] == "eid"
    container["Config"]["User"] = user
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime user|runtime configuration"):
        remote.runtime_images(fixture.config)
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime user|runtime configuration"):
        operations.captured_runtime()
    with pytest.raises(operations.RemoteOperationError):
        runtime.run("postgres", "start")
    assert path.read_bytes() == original and not fixture.commands


def test_empty_image_user_is_root_default_and_bound_to_generated_manifest(production_case):
    fixture = production_case
    manifest = record_generated_manifest(fixture)
    container = fixture.host.containers["postgres-id"]
    image = fixture.host.images[container["Image"]]
    assert image["Config"]["User"] == container["Config"]["User"] == ""
    # A valid changed image/default user is still a different runtime binding.
    image["Config"]["User"] = container["Config"]["User"] = "postgres"
    updated = remote.runtime_images(fixture.config)
    assert updated["services"]["postgres"]["runtime_config_sha256"] != (
        manifest["services"]["postgres"]["runtime_config_sha256"])
    with pytest.raises(remote.RemoteEnvironmentError, match="candidate binding"):
        operations.RemoteRuntime(fixture.config, manifest)
    assert operations.RemoteRuntime(fixture.config, updated).manifest == updated
    assert not fixture.commands


@pytest.mark.parametrize("user", ["2000:3000", "eid:staff", "", "0", "root:1000", "+0", "-0"])
def test_generated_user_override_retains_python_non_root_boundary(production_case, user):
    fixture = production_case
    original = remote.runtime_images(fixture.config)
    path = fixture.root / "deployment/compose.yaml"
    compose = remote.yaml.safe_load(path.read_bytes())
    compose["services"]["worker"]["user"] = user
    path.write_text(remote.yaml.safe_dump(compose), encoding="utf-8")
    fixture.host.containers["worker-id"]["Config"]["User"] = user or "eid"
    if user in {"0", "root:1000", "+0", "-0"}:
        with pytest.raises(remote.RemoteEnvironmentError, match="non-root runtime user"):
            remote.runtime_images(fixture.config)
    else:
        manifest = remote.runtime_images(fixture.config)
        assert operations.RemoteRuntime(fixture.config, manifest).manifest == manifest
        original_digest = original["services"]["worker"]["runtime_config_sha256"]
        current_digest = manifest["services"]["worker"]["runtime_config_sha256"]
        assert (original_digest == current_digest) == (user == "")
    assert not fixture.commands


@pytest.mark.parametrize("source,overlaps", [
    ("/opt/docker/another-project/deleted-source", False),
    ("/opt/docker/eid/deleted-source", True),
    ("/opt/eid/deleted-source", True),
    ("/opt/docker", True),
    ("/var/lib/docker/volumes/eid-remote-dev-postgres/_data/deleted-source", True),
    ("/var/lib/docker/volumes", True),
    ("/link-to-eid-volume/deleted-source", True),
])
def test_actual_recovery_ignores_only_unrelated_missing_bind(production_case, source, overlaps):
    fixture = production_case
    record_generated_manifest(fixture)
    runtime = operations.captured_runtime()
    runtime.run("postgres", "stop")
    identifier = runtime.container_ids["postgres"]
    fixture.host.aliases["/link-to-eid-volume/deleted-source"] = (
        "/var/lib/docker/volumes/eid-remote-dev-postgres/_data/deleted-source")
    fixture.host.containers["foreign"] = {"Id": "foreign", "Name": "/another-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "exited"},
        "Mounts": [{"Type": "bind", "Source": source, "Destination": "/shared"}]}
    if overlaps:
        with pytest.raises(operations.RemoteOperationError):
            runtime.run("postgres", "start")
        assert [command[3:] for command in fixture.commands] == [["stop", identifier]]
        assert fixture.host.containers["postgres-id"]["State"]["Status"] == "exited"
    else:
        result = runtime.run("postgres", "start")
        assert result["attempted"] and result["returncode"] == 0
        assert [command[3:] for command in fixture.commands] == [["stop", identifier], ["start", identifier]]
        assert fixture.host.containers["postgres-id"]["State"]["Status"] == "running"
