import base64
import copy
import hashlib
import json
import os
import shlex
import socket
import stat
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from scripts import remote_environment as remote
from scripts import verify_local_environment as guard


OWNER = "c38d0f7481a6476ebc8b0fd2fe087db3"
FIXTURE_PROCESS_RUN = remote.subprocess.run
FIXTURE_POPEN = remote.subprocess.Popen


@pytest.fixture
def config():
    return remote.load_config()


@pytest.fixture(autouse=True)
def no_implicit_remote(monkeypatch, tmp_path):
    monkeypatch.delenv("EID_ENVIRONMENT_CONFIG", raising=False)
    monkeypatch.setattr(guard, "STATE", tmp_path / ".local/ownership.json")
    monkeypatch.setattr(guard, "RUNTIME_IMAGE_MANIFEST", tmp_path / ".local/runtime-images.json")
    monkeypatch.setattr(remote, "evidence_directory",
                        lambda config: tmp_path / ".local/remote" / config["environment"])
    monkeypatch.setattr(guard, "environment_state_directory", lambda local_root=None:
        remote.evidence_directory(config) if (config := guard.remote_config())
        else tmp_path / ".local")

    def forbidden(*args, **kwargs):
        pytest.fail("Remote unit tests prohibit implicit process or network access")

    monkeypatch.setattr(remote.subprocess, "run", forbidden)
    monkeypatch.setattr(remote.subprocess, "check_output", forbidden)
    monkeypatch.setattr(remote.subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


def test_explicit_environment_selection_is_fail_closed(monkeypatch, tmp_path):
    assert guard.remote_config() is None
    for selector in ("", "production", "deployment/compose.yaml"):
        monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
        with pytest.raises(guard.IsolationError):
            guard.remote_config()
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    assert guard.remote_config()["remote"]["compose_project"] == "eid-remote-dev"
    assert guard.PROJECT == "eid-local"
    assert guard.STATE == tmp_path / ".local/ownership.json"


def test_remote_mode_rejects_local_docker_before_execution(monkeypatch):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "seadee-develop")
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: pytest.fail("local Docker executed"))
    with pytest.raises(guard.IsolationError, match="本机 Docker"):
        guard.command("docker", "ps")
    with pytest.raises(guard.IsolationError, match="prepare"):
        guard.ownership(create=True)


def test_remote_receipt_and_fixture_state_are_separate(config, tmp_path, monkeypatch):
    monkeypatch.setattr(remote, "ROOT", tmp_path)
    path = remote.evidence_directory(config) / "ownership.json"
    path.parent.mkdir(parents=True)
    (tmp_path / ".local/ownership.json").write_text(json.dumps({"nonce": OWNER}))
    with pytest.raises(remote.RemoteEnvironmentError, match="Missing"):
        remote.read_owner(config)
    path.write_text(json.dumps(remote.owner_receipt(config, OWNER)))
    assert remote.read_owner(config)["nonce"] == OWNER
    monkeypatch.setattr(guard, "remote_config", lambda: config)
    assert guard.environment_state_directory() == path.parent
    receipt = json.loads(path.read_text())
    receipt["hostname"] = "foreign"
    path.write_text(json.dumps(receipt))
    with pytest.raises(remote.RemoteEnvironmentError, match="differs"):
        remote.read_owner(config)


def test_old_local_receipt_is_rejected_without_adoption_or_mutation(config):
    path = remote.evidence_directory(config) / "ownership.json"
    path.parent.mkdir(parents=True)
    previous = {**remote.owner_receipt(config, OWNER), "root": "/opt/docker/eid"}
    path.write_text(json.dumps(previous), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(remote.RemoteEnvironmentError, match="differs from selected target"):
        remote.read_owner(config)
    assert path.read_bytes() == before


def test_new_root_rejects_old_remote_receipt(config):
    state = guard_state(config)
    state["receipt"]["root"] = "/opt/docker/eid"
    with pytest.raises(remote.RemoteEnvironmentError, match="receipt mismatch"):
        remote.validate_remote_state(config, state, OWNER)


@pytest.mark.parametrize("final", [False, True])
def test_new_receipt_cannot_authorize_old_eid_bind(config, monkeypatch, final):
    state = guard_state(config)
    mount = next(mount for item in state["containers"] for mount in item["mounts"]
                 if mount["Type"] == "bind")
    mount["Source"] = mount["Source"].replace("/opt/eid/", "/opt/docker/eid/", 1)
    with pytest.raises(remote.RemoteEnvironmentError, match="escapes EID root"):
        remote.validate_guard_state(config, state, OWNER, require_running=final)
    mount["OriginalSource"] = mount["Source"]
    mount["Source"] = mount["Source"].replace("/opt/docker/eid/", "/opt/eid/", 1)
    with pytest.raises(remote.RemoteEnvironmentError, match="escapes EID root"):
        remote.validate_guard_state(config, state, OWNER, require_running=final)
    fixture = collector_fixture(config, monkeypatch)
    raw = next(item for item in fixture.containers["postgres-id"]["Mounts"] if item["Type"] == "bind")
    raw["Source"] = raw["Source"].replace("/opt/eid/", "/opt/docker/eid/", 1)
    with pytest.raises(remote.RemoteEnvironmentError, match="escapes EID root"):
        fixture.probe()


def tunnel_snapshot(config):
    return {"listeners": [{"LocalPort": port, "LocalAddress": "127.0.0.1", "OwningProcess": 10}
                           for port in config["tunnels"]["ports"].values()],
            "processes": [{"ProcessId": 10, "ExecutablePath": str(Path("ssh.exe").resolve()),
                           "argv": remote.tunnel_command(config), "CreationDate": "started-now"}]}


@pytest.mark.parametrize("mutation", ["none", "missing", "ipv6", "wildcard", "foreign_pid",
    "foreign_executable", "redirect", "proxy_option", "extra_loopback", "extra_wildcard"])
def test_actual_tunnel_process_and_ports_are_bound(config, mutation):
    snapshot = tunnel_snapshot(config)
    if mutation == "missing":
        snapshot["listeners"].pop()
    elif mutation == "ipv6":
        snapshot["listeners"].append({**snapshot["listeners"][0], "LocalAddress": "::1"})
    elif mutation == "wildcard":
        snapshot["listeners"][0]["LocalAddress"] = "0.0.0.0"
    elif mutation == "foreign_pid":
        snapshot["listeners"][0]["OwningProcess"] = 11
    elif mutation == "foreign_executable":
        snapshot["processes"][0]["ExecutablePath"] = "unrelated.exe"
    elif mutation == "redirect":
        argv = snapshot["processes"][0]["argv"]
        argv[argv.index("-L") + 1] = "127.0.0.1:55432:enterprise:5432"
    elif mutation == "proxy_option":
        snapshot["processes"][0]["argv"][1:1] = ["-o", "ProxyCommand=unapproved"]
    elif mutation.startswith("extra_"):
        snapshot["listeners"].append({"LocalPort": 19000, "OwningProcess": 10,
            "LocalAddress": "0.0.0.0" if mutation == "extra_wildcard" else "127.0.0.1"})
    if mutation == "none":
        assert remote.validate_tunnels(config, snapshot, "ssh.exe")["pid"] == 10
    else:
        with pytest.raises(remote.RemoteEnvironmentError):
            remote.validate_tunnels(config, snapshot, "ssh.exe")


@pytest.mark.skipif(os.name != "nt", reason="Runs the Windows inventory script against fake OS records")
@pytest.mark.parametrize("extra_address", ["127.0.0.1", "0.0.0.0", "::"])
def test_tunnel_inventory_collects_every_listener_owned_by_target_pid(config, monkeypatch, extra_address):
    records = tunnel_snapshot(config)
    extra = {"LocalPort": 19000, "LocalAddress": extra_address, "OwningProcess": 10}
    records["listeners"].append(extra)
    unrelated = {"LocalPort": 19001, "LocalAddress": "0.0.0.0", "OwningProcess": 99}
    records["listeners"].append(unrelated)
    records["processes"][0]["CommandLine"] = "fixture"
    original_run = FIXTURE_PROCESS_RUN

    def run(arguments, **kwargs):
        # Execute the real generated selection logic. Only OS query commands are replaced.
        assert arguments[:3] == ["powershell.exe", "-NoProfile", "-NonInteractive"]
        program = base64.b64decode(arguments[-1]).decode("utf-16le")
        fixture = base64.b64encode(json.dumps(records).encode()).decode()
        setup = ("$eidFixture=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
                 + fixture + "')) | ConvertFrom-Json; "
                 "function Get-NetTCPConnection { $eidFixture.listeners }; "
                 "function Get-CimInstance { $eidFixture.processes }; ")
        actual_arguments = arguments[:-1] + [base64.b64encode((setup + program).encode("utf-16le")).decode()]
        with monkeypatch.context() as patch:
            patch.setattr(remote.subprocess, "Popen", FIXTURE_POPEN)
            return original_run(actual_arguments, **kwargs)

    monkeypatch.setattr(remote.subprocess, "run", run)
    monkeypatch.setattr(remote, "windows_command_line", lambda command: remote.tunnel_command(config))
    actual = remote.tunnel_inventory(config)
    assert extra in actual["listeners"]
    assert unrelated not in actual["listeners"]
    with pytest.raises(remote.RemoteEnvironmentError, match="additional process listeners"):
        remote.validate_tunnels(config, actual, "ssh.exe")


def isolation_config():
    return {"Privileged": False, "PidMode": "", "IpcMode": "private", "UTSMode": "",
            "UsernsMode": "", "CgroupnsMode": "private", "CapAdd": [], "Devices": [],
            "DeviceRequests": [], "DeviceCgroupRules": [], "SecurityOpt": [], "VolumesFrom": []}


def docker_healthcheck(definition):
    """Raw Docker fixture, independently converting the repository's seconds-only probes."""
    check = definition.get("healthcheck")
    if check is None:
        return None
    return {"Test": [part.replace("$$", "$") for part in check["test"]],
            "Interval": int(check["interval"].removesuffix("s")) * 1_000_000_000,
            "Timeout": int(check["timeout"].removesuffix("s")) * 1_000_000_000,
            "Retries": check["retries"],
            "StartPeriod": int(check.get("start_period", "0s").removesuffix("s")) * 1_000_000_000}


def guard_state(config):
    project = config["remote"]["compose_project"]
    labels = {"io.eid.owner": OWNER, "io.eid.environment": config["environment"],
              "com.docker.compose.project": project}
    compose = remote.yaml.safe_load(remote.render_compose(config, OWNER, remote.source_files(remote.ROOT)))
    state = {"root_exists": True, "receipt": remote.owner_receipt(config, OWNER),
             "containers": [], "volumes": [{"name": project + "-" + service,
                 "labels": dict(labels), "driver": "local", "options": {},
                 "mountpoint": "/var/lib/docker/volumes/" + project + "-" + service + "/_data"}
                 for service in remote.VOLUME_SERVICES],
             "networks": [{"name": project + "_default", "labels": dict(labels),
                           "driver": "bridge", "options": {}}], "listeners": [],
             "server": {"Os": "linux", "Arch": "amd64", "Version": "25.0.3"},
             "compose": "2.32.4", "compose_wait": True, "buildx": ""}
    for service, definition in compose["services"].items():
        mounts = []
        for volume in definition.get("volumes", []):
            source, destination, *flags = volume.split(":")
            if source.startswith("eid-"):
                mounts.append({"Type": "volume", "Name": compose["volumes"][source]["name"],
                               "Destination": destination})
            else:
                relative = "deployment/" + source.removeprefix("./")
                mounts.append({"Type": "bind", "Source": "/opt/eid/releases/current/" + relative,
                               "Destination": destination, "RW": flags != ["ro"],
                               "sha256": hashlib.sha256((remote.ROOT / relative).read_bytes()).hexdigest()})
        state["containers"].append({"id": service + "-id", "name": project + "-" + service + "-1",
            "labels": {**labels, "com.docker.compose.service": service}, "mounts": mounts,
            "ports": {f"{port}/tcp": [{"HostIp": "127.0.0.1",
                "HostPort": str(config["remote"]["ports"][name])}]
                for name, (target, port) in remote.PORTS.items() if target == service},
            "networks": [project + "_default"], "network_mode": project + "_default",
            "state": "running", "health": "healthy", "isolation_config": isolation_config(),
            "image_id": "sha256:" + "a" * 64,
            "referenced_image_id": "sha256:" + "a" * 64, "image_ref": definition["image"],
            "hostname": definition.get("hostname"),
            "rabbitmq_identity_env": [key + "=" + value
                for key, value in definition.get("environment", {}).items()
                if key in {"RABBITMQ_NODENAME", "RABBITMQ_MNESIA_DIR"}],
            "image_labels": {"io.eid.source-fingerprint": guard.source_fingerprint(service)}
                            if service in {"api", "worker", "web"} else {}})
        image_config = {"command": remote.configuration_digest(["image-default"]),
                        "entrypoint": remote.configuration_digest(["/entrypoint"]),
                        "environment": {"PATH": remote.configuration_digest("/usr/bin")},
                        "user": "eid" if service in {"api", "worker"} else "",
                        "healthcheck": None}
        state["containers"][-1]["image_runtime_config"] = image_config
        state["containers"][-1]["runtime_config"] = remote.candidate_runtime_config(definition, image_config)
    return state


@pytest.mark.parametrize("mutation", ["none", "owner", "wrong_image", "image_retag",
    "source", "config", "writable_config", "data_path", "incomplete", "wrong_port"])
def test_remote_candidate_guard_rejects_stale_or_foreign_resources(config, mutation):
    state = guard_state(config)
    containers = {item["labels"]["com.docker.compose.service"]: item for item in state["containers"]}
    if mutation == "owner":
        containers["postgres"]["labels"]["io.eid.owner"] = "b" * 32
    elif mutation == "wrong_image":
        containers["postgres"]["image_ref"] = "postgres:latest"
    elif mutation == "image_retag":
        containers["api"]["referenced_image_id"] = "sha256:" + "b" * 64
    elif mutation == "source":
        containers["api"]["image_labels"]["io.eid.source-fingerprint"] = "sha256:" + "b" * 64
    elif mutation in {"config", "writable_config"}:
        mount = next(item for item in containers["seaweedfs"]["mounts"] if item["Type"] == "bind")
        mount["sha256" if mutation == "config" else "RW"] = "wrong" if mutation == "config" else True
    elif mutation == "data_path":
        containers["postgres"]["mounts"][0]["Destination"] = "/wrong-data"
    elif mutation == "incomplete":
        state["containers"].remove(containers["redis"])
    elif mutation == "wrong_port":
        containers["postgres"]["ports"]["5432/tcp"][0]["HostPort"] = "5432"
    if mutation == "none":
        assert set(remote.validate_guard_state(config, state, OWNER, require_running=True)) == remote.SERVICES
    else:
        with pytest.raises(remote.RemoteEnvironmentError):
            remote.validate_guard_state(config, state, OWNER, require_running=True)


@pytest.mark.parametrize("service", ["api", "worker", "web", "nginx"])
@pytest.mark.parametrize("running", [True, False])
def test_migration_accepts_owned_old_or_stopped_apps_but_final_candidate_rejects(config, service, running):
    state = guard_state(config)
    container = next(item for item in state["containers"]
                     if item["labels"]["com.docker.compose.service"] == service)
    container.update(state="running" if running else "exited", image_ref="previous-candidate",
                     referenced_image_id=None, image_labels={"io.eid.source-fingerprint": "old"})
    if service == "nginx":
        container["mounts"][0]["sha256"] = "previous-config"
    assert service in remote.validate_guard_state(config, state, OWNER)
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_guard_state(config, state, OWNER, require_running=True)


@pytest.mark.parametrize("mutation", ["owner", "network", "writable_config", "extra_mount", "data_path"])
def test_migration_still_rejects_unsafe_stopped_apps(config, mutation):
    state = guard_state(config)
    container = next(item for item in state["containers"]
                     if item["labels"]["com.docker.compose.service"] == "nginx")
    container["state"] = "exited"
    if mutation == "owner":
        container["labels"]["io.eid.owner"] = "b" * 32
    elif mutation == "network":
        container["networks"] = ["foreign_default"]
    elif mutation == "writable_config":
        container["mounts"][0]["RW"] = True
    elif mutation == "extra_mount":
        container["mounts"].append(dict(container["mounts"][0]))
    else:
        container["mounts"][0]["Source"] = "/opt/docker/foreign/config"
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_guard_state(config, state, OWNER)


@pytest.mark.parametrize("mutation", ["stopped", "image", "config"])
def test_migration_still_requires_current_running_infrastructure(config, mutation):
    state = guard_state(config)
    container = next(item for item in state["containers"]
                     if item["labels"]["com.docker.compose.service"] == "postgres")
    if mutation == "stopped":
        container["state"] = "exited"
    elif mutation == "image":
        container["referenced_image_id"] = None
    else:
        next(mount for mount in container["mounts"] if mount["Type"] == "bind")["sha256"] = "old"
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_guard_state(config, state, OWNER)


@pytest.mark.parametrize("mutation", ["hostname", "node", "directory", "duplicate", "longname"])
def test_broker_identity_drift_is_rejected_before_migration(config, mutation):
    state = guard_state(config)
    broker = next(item for item in state["containers"]
                  if item["labels"]["com.docker.compose.service"] == "rabbitmq")
    if mutation == "hostname":
        broker["hostname"] = "new-container"
    elif mutation == "node":
        broker["rabbitmq_identity_env"][0] = "RABBITMQ_NODENAME=rabbit@other"
    elif mutation == "directory":
        broker["rabbitmq_identity_env"][1] = "RABBITMQ_MNESIA_DIR=/var/lib/rabbitmq/new"
    elif mutation == "duplicate":
        broker["rabbitmq_identity_env"].append(broker["rabbitmq_identity_env"][0])
    else:
        broker["rabbitmq_identity_env"].append("RABBITMQ_USE_LONGNAME=true")
    with pytest.raises(remote.RemoteEnvironmentError):
        remote.validate_guard_state(config, state, OWNER)


def test_observed_implicit_broker_identity_allows_ownership_but_requires_explicit_final_pin(config):
    state = guard_state(config)
    broker = next(item for item in state["containers"]
                  if item["labels"]["com.docker.compose.service"] == "rabbitmq")
    broker["rabbitmq_identity_env"] = []
    remote.validate_guard_state(config, state, OWNER)
    with pytest.raises(remote.RemoteEnvironmentError, match="explicitly preserve"):
        remote.validate_guard_state(config, state, OWNER, require_running=True)


def test_infrastructure_initialization_does_not_require_apps_but_runtime_does(config):
    state = guard_state(config)
    state["containers"] = [item for item in state["containers"]
        if item["labels"]["com.docker.compose.service"] in remote.VOLUME_SERVICES]
    assert set(remote.validate_guard_state(config, state, OWNER)) == remote.VOLUME_SERVICES
    with pytest.raises(remote.RemoteEnvironmentError, match="nine-service"):
        remote.validate_guard_state(config, state, OWNER, require_running=True)


def test_database_identity_check_is_preserved_for_remote(config, monkeypatch):
    import psycopg

    calls = []
    monkeypatch.setattr(guard, "remote_config", lambda: config)
    monkeypatch.setattr(guard, "ownership", lambda: {"nonce": OWNER})
    monkeypatch.setattr(remote, "guarded_service", lambda *args: calls.append(args))
    monkeypatch.setattr(guard, "command", lambda *a: pytest.fail("local Docker used"))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query):
            assert "current_database()" in query and "current_user" in query
            return SimpleNamespace(fetchone=lambda: ("enterprise", "eid_migrator", "eid-local-dev-v1"))

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: Connection())
    with pytest.raises(guard.IsolationError, match="数据库名称"):
        guard.verify_database("postgresql+psycopg://eid_migrator:local-migrate-only@localhost:15432/eid_local_dev")
    assert calls == [(config, "postgres", 5432, 15432)]


def test_remote_runtime_manifest_cannot_accept_local_evidence(config, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "remote_config", lambda: config)
    monkeypatch.setattr(guard, "environment_state_directory", lambda: tmp_path)
    manifest = {"schema_version": 2, "services": {}, "source_fingerprint_algorithm": "sha256"}
    (tmp_path / "runtime-images.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(remote, "runtime_images", lambda *args: {
        **manifest, "schema_version": 3, "provenance": {"environment": "seadee-develop"}})
    with pytest.raises(guard.IsolationError, match="远端运行镜像"):
        guard.verify_runtime_images()


@pytest.mark.parametrize("ancestor", ["/", "/opt"])
def test_ancestor_pin_requires_observed_root_control(config, ancestor):
    assert config["remote"]["ancestors"] == {
        "/": {"uid": 0, "gid": 0, "mode": "0555"},
        "/opt": {"uid": 0, "gid": 0, "mode": "0755"}}
    for field, value in (("uid", 197610), ("gid", 197121), ("mode", "0775")):
        changed = copy.deepcopy(config)
        changed["remote"]["ancestors"][ancestor][field] = value
        with pytest.raises(remote.RemoteEnvironmentError, match="ancestor"):
            remote.validate_config(changed)


@pytest.mark.parametrize("ancestor", ["/", "/opt"])
@pytest.mark.parametrize("mutation", ["none", "uid", "gid", "writable", "other_writable", "symlink"])
def test_live_ancestor_metadata_is_checked_before_docker(config, monkeypatch, mutation, ancestor):
    class ReachedDocker(Exception):
        pass

    class RemotePath:
        def __init__(self, name):
            self.name = name

        def lstat(self):
            if self.name not in config["remote"]["ancestors"]:
                raise FileNotFoundError(self.name)
            expected = config["remote"]["ancestors"][self.name]
            metadata = SimpleNamespace(st_uid=expected["uid"], st_gid=expected["gid"],
                                       st_mode=stat.S_IFDIR | int(expected["mode"], 8))
            if self.name == ancestor:
                if mutation == "uid":
                    metadata.st_uid = 5
                elif mutation == "gid":
                    metadata.st_gid = 5
                elif mutation == "writable":
                    metadata.st_mode = stat.S_IFDIR | 0o775
                elif mutation == "other_writable":
                    metadata.st_mode = stat.S_IFDIR | 0o757
                elif mutation == "symlink":
                    metadata.st_mode = stat.S_IFLNK | 0o755
            return metadata

        def resolve(self, strict=False):
            return self

        def exists(self):
            return False

        def is_symlink(self):
            return False

    def docker(*args, **kwargs):
        raise ReachedDocker()

    monkeypatch.setattr(remote, "Path", RemotePath)
    monkeypatch.setattr(remote.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(remote.subprocess, "run", docker)
    expected_error = ReachedDocker if mutation == "none" else remote.RemoteEnvironmentError
    with pytest.raises(expected_error):
        remote.collect_remote_state(config, "127.0.0.1 12345 172.27.0.38 22")


def collector_fixture(config, monkeypatch, filesystem_root=None):
    """Real collector with only remote filesystem and subprocess I/O replaced."""
    import posixpath

    state = guard_state(config)
    compose = remote.yaml.safe_load(remote.render_compose(config, OWNER, remote.source_files(remote.ROOT)))
    root = config["remote"]["root"]
    metadata = {name: SimpleNamespace(st_uid=value["uid"], st_gid=value["gid"],
        st_mode=stat.S_IFDIR | int(value["mode"], 8))
        for name, value in config["remote"]["ancestors"].items()}
    metadata[root] = SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFDIR | 0o700)
    receipt_path = root + "/.eid-remote-owner.json"
    contents = {receipt_path: json.dumps(remote.owner_receipt(config, OWNER)).encode()}
    containers, images, volumes = {}, {}, {}
    for index, record in enumerate(state["containers"], 1):
        service = record["labels"]["com.docker.compose.service"]
        definition = compose["services"][service]
        image_id = "sha256:" + f"{index:064x}"
        image_config = {"Cmd": ["image-default"], "Entrypoint": ["/entrypoint"],
                        "Env": ["PATH=/usr/bin"], "Labels": record["image_labels"],
                        "User": "eid" if service in {"api", "worker"} else ""}
        actual = copy.deepcopy(image_config)
        actual.update(Image=record["image_ref"], Labels=record["labels"],
                      Hostname=definition.get("hostname", "fixture-host"),
                      Healthcheck=docker_healthcheck(definition))
        if definition.get("entrypoint") is not None:
            actual["Entrypoint"] = definition["entrypoint"]
            actual["Cmd"] = []
        if definition.get("command") is not None:
            actual["Cmd"] = definition["command"]
        actual["Env"] += [key + "=" + value.replace("$$", "$")
                          for key, value in definition.get("environment", {}).items()]
        for mount in record["mounts"]:
            if mount["Type"] == "bind":
                relative = mount["Source"].split("/releases/current/", 1)[1]
                contents[mount["Source"]] = (remote.ROOT / relative).read_bytes()
        containers[record["id"]] = {
            "Id": record["id"], "Name": "/" + record["name"], "Config": actual, "Image": image_id,
            "HostConfig": {"PortBindings": record["ports"], "NetworkMode": record["network_mode"],
                           **isolation_config()},
            "NetworkSettings": {"Networks": dict.fromkeys(record["networks"], {})},
            "Mounts": record["mounts"], "State": {"Status": "running", "Health": {"Status": "healthy"}},
        }
        images[image_id] = images[record["image_ref"]] = {"Id": image_id, "Config": image_config}
    for volume in state["volumes"]:
        volumes[volume["name"]] = {"Name": volume["name"], "Labels": volume["labels"],
            "Driver": "local", "Options": {}, "Mountpoint": volume["mountpoint"]}
        for path in (PurePosixPath(volume["mountpoint"]), *PurePosixPath(volume["mountpoint"]).parents):
            metadata.setdefault(str(path), SimpleNamespace(st_uid=0, st_gid=0,
                                                           st_mode=stat.S_IFDIR | 0o755))
    for name, content in contents.items():
        metadata[name] = SimpleNamespace(st_uid=0, st_gid=0, st_nlink=1, st_size=len(content),
            st_mode=stat.S_IFREG | (0o600 if name == receipt_path else 0o644))
        for parent in PurePosixPath(name).parents:
            metadata.setdefault(str(parent), SimpleNamespace(st_uid=0, st_gid=0,
                                                               st_mode=stat.S_IFDIR | 0o755))
    aliases, calls = {}, []
    if filesystem_root is not None:
        # Real pathlib resolution, including symlinks, stays inside pytest's temp tree.
        for name, value in metadata.items():
            path = filesystem_root / name.lstrip("/")
            if stat.S_ISDIR(value.st_mode):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents[name])

    class RemotePath(PurePosixPath):
        def exists(self):
            return str(self) in metadata

        def is_symlink(self):
            return stat.S_ISLNK(self.lstat().st_mode) if self.exists() else False

        def lstat(self):
            if str(self) in metadata:
                return metadata[str(self)]
            if filesystem_root is not None:
                return (filesystem_root / str(self).lstrip("/")).lstat()
            raise FileNotFoundError(str(self))

        def resolve(self, strict=False):
            if filesystem_root is not None:
                actual = (filesystem_root / str(self).lstrip("/")).resolve(strict=strict)
                return RemotePath("/" + actual.relative_to(filesystem_root).as_posix())
            resolved = RemotePath(aliases.get(str(self), posixpath.normpath(str(self))))
            if strict:
                resolved.lstat()
            return resolved

        def read_text(self):
            return self.read_bytes().decode()

        def read_bytes(self):
            return contents[str(self)]

    def run(arguments, **kwargs):
        calls.append(arguments)
        if arguments == ["ss", "-H", "-ltn"]:
            return remote.subprocess.CompletedProcess(arguments, 0, "", "")
        assert arguments[:3] == ["docker", "--host", config["remote"]["docker_endpoint"]]
        args = arguments[3:]
        if args[0] == "version":
            output = state["server"]
        elif args[:2] == ["compose", "version"]:
            output = "2.32.4"
        elif args[:2] == ["compose", "up"]:
            output = "--wait --wait-timeout"
        elif args[0] == "buildx":
            output = "buildx fixture"
        elif args[0] == "ps":
            output = "\n".join(containers)
        elif args[0] == "inspect":
            output = [containers[args[1]]]
        elif args[:2] == ["image", "inspect"]:
            output = [images[args[2]]]
        elif args[:2] == ["volume", "ls"]:
            output = "\n".join(volumes)
        elif args[:2] == ["volume", "inspect"]:
            output = [volumes[args[2]]]
        elif args[:2] == ["network", "ls"]:
            output = "\n".join(network["name"] for network in state["networks"])
        elif args[:2] == ["network", "inspect"]:
            network = state["networks"][0]
            output = [{"Name": network["name"], "Labels": network["labels"],
                       "Driver": "bridge", "Options": {}}]
        else:
            raise AssertionError(arguments)
        return remote.subprocess.CompletedProcess(arguments, 0,
            output if isinstance(output, str) else json.dumps(output), "")

    def probe():
        with monkeypatch.context() as patch:
            patch.setattr(remote, "Path", RemotePath)
            patch.setattr(remote.os, "geteuid", lambda: 0, raising=False)
            patch.setattr(remote.subprocess, "run", run)
            return remote.collect_remote_state(config, "127.0.0.1 12345 172.27.0.38 22")

    return SimpleNamespace(probe=probe, metadata=metadata, containers=containers, images=images,
                           volumes=volumes, aliases=aliases, calls=calls, compose=compose,
                           path_type=RemotePath, run=run, networks=state["networks"])


def install_runtime_io(config, monkeypatch, inventory):
    # Exercise runtime_images -> guarded_inventory -> validate_guard_state without SSH.
    monkeypatch.setattr(remote, "read_owner", lambda _: remote.owner_receipt(config, OWNER))
    monkeypatch.setattr(remote, "verify_tunnels", lambda _: {"pid": 10, "started": "fixture"})
    monkeypatch.setattr(remote, "remote_inventory", lambda _: inventory())


@pytest.mark.parametrize("mutation", ["none", "uid", "gid", "symlink", "mode", "resolved_elsewhere"])
def test_installed_root_metadata_is_enforced_by_actual_collector(config, monkeypatch, mutation):
    fixture = collector_fixture(config, monkeypatch)
    root = config["remote"]["root"]
    if mutation == "uid":
        fixture.metadata[root].st_uid = 1000
    elif mutation == "gid":
        fixture.metadata[root].st_gid = 1000
    elif mutation == "symlink":
        fixture.metadata[root].st_mode = stat.S_IFLNK | 0o700
    elif mutation == "mode":
        fixture.metadata[root].st_mode = stat.S_IFDIR | 0o750
    elif mutation == "resolved_elsewhere":
        fixture.aliases[root] = "/other"
    if mutation == "none":
        assert fixture.probe()["receipt"] == remote.owner_receipt(config, OWNER)
        assert fixture.calls
    else:
        with pytest.raises(remote.RemoteEnvironmentError, match="root-owned private directory"):
            fixture.probe()
        assert not fixture.calls


@pytest.mark.parametrize("validator", [remote.validate_remote_state, remote.validate_guard_state])
@pytest.mark.parametrize("mutation", ["symlink", "dangling_symlink", "redirected_directory",
                                      "alias_without_metadata", "regular_file"])
def test_retained_root_redirection_is_rejected_before_validation(
        config, monkeypatch, validator, mutation):
    fixture = collector_fixture(config, monkeypatch)
    retained = "/opt/docker/eid"
    destination = retained + "-retained"
    fixture.metadata[destination] = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700)
    if mutation != "alias_without_metadata":
        mode = stat.S_IFLNK if "symlink" in mutation else stat.S_IFDIR
        if mutation == "regular_file":
            mode = stat.S_IFREG
        fixture.metadata[retained] = SimpleNamespace(st_mode=mode | 0o700)
    if mutation != "regular_file":
        fixture.aliases[retained] = destination
    if mutation == "dangling_symlink":
        del fixture.metadata[destination]
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "exited"},
        "Mounts": [{"Type": "bind", "Source": retained, "Destination": "/shared"}]}
    with pytest.raises(remote.RemoteEnvironmentError, match="Retained EID root"):
        validator(config, fixture.probe(), OWNER, require_running=True)
    assert not fixture.calls


@pytest.mark.parametrize("present", [False, True])
def test_retained_root_may_be_absent_or_a_real_directory(config, monkeypatch, present):
    fixture = collector_fixture(config, monkeypatch)
    if present:
        fixture.metadata["/opt/docker/eid"] = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700)
    state = fixture.probe()
    assert remote.validate_remote_state(config, state, OWNER, require_running=True)["isolation_verified"]
    assert set(remote.validate_guard_state(config, state, OWNER, require_running=True)) == remote.SERVICES


def test_pristine_environment_does_not_require_a_retained_root(config, monkeypatch):
    fixture = collector_fixture(config, monkeypatch)
    del fixture.metadata[config["remote"]["root"]]
    del fixture.metadata[config["remote"]["root"] + "/.eid-remote-owner.json"]
    fixture.containers.clear()
    fixture.volumes.clear()
    fixture.networks.clear()
    state = fixture.probe()
    assert state["root_exists"] is False and state["receipt"] is None
    assert remote.validate_remote_state(config, state)["root_exists"] is False
    with pytest.raises(remote.RemoteEnvironmentError, match="not installed"):
        remote.validate_guard_state(config, state, OWNER)


@pytest.mark.parametrize("validator", [remote.validate_remote_state, remote.validate_guard_state])
def test_original_retained_bind_still_overlaps_when_child_resolves_elsewhere(
        config, monkeypatch, validator):
    fixture = collector_fixture(config, monkeypatch)
    source = "/opt/docker/eid/linked-config"
    canonical = "/foreign-config"
    fixture.metadata["/opt/docker/eid"] = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700)
    fixture.metadata[canonical] = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)
    fixture.aliases[source] = canonical
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "exited"},
        "Mounts": [{"Type": "bind", "Source": source, "Destination": "/shared"}]}
    state = json.loads(json.dumps(fixture.probe()))
    mount = state["containers"][-1]["mounts"][0]
    assert mount["Source"] == canonical
    assert mount["OriginalSource"] == source
    with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
        validator(config, state, OWNER, require_running=True)


@pytest.mark.parametrize("transport", ["inventory", "operation"])
@pytest.mark.parametrize("case", ["retained-root", "retained-child", "external-eid-alias",
                                 "external-unrelated-alias"])
def test_serialized_collectors_preserve_retained_root_and_original_bind_checks(
        config, monkeypatch, transport, case):
    from scripts import remote_service_operations as operations

    fixture = collector_fixture(config, monkeypatch)
    sources = {"retained-root": "/opt/docker/eid", "retained-child": "/opt/docker/eid/config",
               "external-eid-alias": "/foreign-link", "external-unrelated-alias": "/unrelated-link"}
    source = sources[case]
    canonical = ("/var/lib/docker/volumes/eid-remote-dev-postgres/_data"
                 if case == "external-eid-alias" else "/unrelated-data")
    fixture.aliases[source] = canonical
    fixture.metadata[canonical] = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "exited"},
        "Mounts": [{"Type": "bind", "Source": source, "Destination": "/shared"}]}
    if transport == "inventory":
        programs = []

        def capture(arguments, **kwargs):
            assert arguments[0] == "ssh"
            boot = shlex.split(arguments[-1])[4]
            programs.append(base64.b64decode(boot.split("'")[1]).decode())
            return remote.subprocess.CompletedProcess(arguments, 0, "{}", "")

        with monkeypatch.context() as patch:
            patch.setattr(remote, "verify_ssh_config", lambda _: None)
            patch.setattr(remote.subprocess, "run", capture)
            remote.remote_inventory(config)
        definitions = programs[0].split("\ntry:\n", 1)[0]
    else:
        definitions = operations._remote_program().split("try:\n payload = json.load(sys.stdin)", 1)[0]
    namespace = {}
    exec(definitions, namespace)
    namespace.update(Path=fixture.path_type, os=SimpleNamespace(geteuid=lambda: 0),
                     subprocess=SimpleNamespace(run=fixture.run))
    if case == "retained-root":
        with pytest.raises(namespace["RemoteEnvironmentError"], match="Retained EID root"):
            namespace["collect_remote_state"](config, "127.0.0.1 12345 172.27.0.38 22")
        assert not fixture.calls
        return
    state = json.loads(json.dumps(namespace["collect_remote_state"](
        config, "127.0.0.1 12345 172.27.0.38 22")))
    mount = state["containers"][-1]["mounts"][0]
    assert mount["Source"] == canonical and mount["OriginalSource"] == source
    overlaps = case != "external-unrelated-alias"
    if transport == "operation":
        assert namespace["bind_mount_overlaps"](config, state, mount) is overlaps
        attached_ids = {item["id"] for item in namespace["runtime_binding"](config, state)["containers"]}
        assert ("foreign" in attached_ids) is overlaps
    for validator in (remote.validate_remote_state, remote.validate_guard_state):
        if overlaps:
            with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
                validator(config, state, OWNER, require_running=True)
        else:
            assert validator(config, state, OWNER, require_running=True)


@pytest.mark.parametrize("source", ["/var/lib/docker/volumes/eid-remote-dev-postgres/_data",
    "/var/lib/docker/volumes/eid-remote-dev-postgres/_data/pg_wal", "/var/lib/docker/volumes",
    "/opt/docker/eid", "/opt/docker/eid/releases/current", "/opt/docker", "/",
    "/opt/eid", "/opt/eid/releases/current", "/opt",
    "/var/lib/docker/volumes/other/../eid-remote-dev-postgres/_data", "/alias-to-eid-volume"])
def test_collector_and_guard_reject_foreign_bind_path_overlap(config, monkeypatch, source):
    fixture = collector_fixture(config, monkeypatch)
    fixture.aliases["/alias-to-eid-volume"] = "/var/lib/docker/volumes/eid-remote-dev-postgres/_data"
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "running"},
        "Mounts": [{"Type": "bind", "Source": source, "Destination": "/shared"}]}
    state = fixture.probe()
    assert {volume["mountpoint"] for volume in state["volumes"]} == {
        value["Mountpoint"] for value in fixture.volumes.values()}
    with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
        remote.validate_remote_state(config, state, OWNER, require_running=True)
    with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
        remote.validate_guard_state(config, state, OWNER, require_running=True)


def test_unrelated_bind_sibling_is_not_an_eid_attachment(config, monkeypatch):
    fixture = collector_fixture(config, monkeypatch)
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "running"},
        "Mounts": [{"Type": "bind", "Source": "/opt/docker/eid-other", "Destination": "/shared"}]}
    assert remote.validate_remote_state(config, fixture.probe(), OWNER,
                                        require_running=True)["isolation_verified"]


@pytest.mark.parametrize("service", ["api", "worker", "web"])
def test_runtime_path_rejects_stable_old_source_candidate(config, monkeypatch, service):
    fixture = collector_fixture(config, monkeypatch)
    record = fixture.containers[service + "-id"]
    # Leave both snapshots and current image reference stable; only the image source is stale.
    fixture.images[record["Image"]]["Config"]["Labels"]["io.eid.source-fingerprint"] = "sha256:" + "b" * 64
    install_runtime_io(config, monkeypatch, fixture.probe)
    with pytest.raises(remote.RemoteEnvironmentError, match="source fingerprint"):
        remote.runtime_images(config)


@pytest.mark.parametrize("service", ["postgres", "keycloak", "rabbitmq", "redis", "api", "worker", "web"])
def test_runtime_path_rejects_absent_declared_health(config, monkeypatch, service):
    fixture = collector_fixture(config, monkeypatch)
    fixture.containers[service + "-id"]["State"].pop("Health")
    install_runtime_io(config, monkeypatch, fixture.probe)
    with pytest.raises(remote.RemoteEnvironmentError, match="health check failed"):
        remote.runtime_images(config)


def test_runtime_path_preserves_image_defaults_and_redacts_configuration(config, monkeypatch):
    fixture = collector_fixture(config, monkeypatch)
    for service in ("seaweedfs", "nginx"):
        assert "healthcheck" not in fixture.compose["services"][service]
        fixture.containers[service + "-id"]["State"].pop("Health")
    install_runtime_io(config, monkeypatch, fixture.probe)
    manifest = remote.runtime_images(config)
    assert set(manifest["services"]) == remote.SERVICES
    assert all(len(record["runtime_config_sha256"]) == 64 for record in manifest["services"].values())
    serialized = json.dumps(manifest)
    assert "local-api-only" not in serialized and "/entrypoint" not in serialized
    collected = json.dumps(fixture.probe())
    assert "local-api-only" not in collected and "/entrypoint" not in collected


@pytest.mark.parametrize("mutation", ["command", "entrypoint", "environment", "extra_env", "missing_env"])
def test_actual_collector_runtime_config_drift_rejected(config, monkeypatch, mutation):
    fixture = collector_fixture(config, monkeypatch)
    settings = fixture.containers["worker-id"]["Config"]
    if mutation == "command":
        settings["Cmd"] = ["python", "-m", "edw_worker", "--queues=other"]
    elif mutation == "entrypoint":
        settings["Entrypoint"] = ["/foreign-entrypoint"]
    elif mutation == "environment":
        settings["Env"] = [value if not value.startswith("EID_DATABASE_URL=")
                           else "EID_DATABASE_URL=postgresql://unapproved" for value in settings["Env"]]
    elif mutation == "extra_env":
        settings["Env"].append("UNREVIEWED=secret-value")
    else:
        settings["Env"] = [value for value in settings["Env"] if not value.startswith("EID_DATABASE_URL=")]
    install_runtime_io(config, monkeypatch, fixture.probe)
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime configuration differs"):
        remote.runtime_images(config)


def test_candidate_compose_queue_edit_rejects_stable_old_runtime(config, monkeypatch, tmp_path):
    fixture = collector_fixture(config, monkeypatch)
    state = fixture.probe()
    source = remote.source_files(remote.ROOT)
    compose = remote.yaml.safe_load(source["deployment/compose.yaml"])
    compose["services"]["worker"]["command"] = ["python", "-m", "edw_worker", "--queues=changed"]
    source["deployment/compose.yaml"] = remote.yaml.safe_dump(compose).encode()
    for name, data in source.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Actual source reader and renderer run against the modified candidate; images stay identical.
    monkeypatch.setattr(remote, "ROOT", tmp_path)
    install_runtime_io(config, monkeypatch, lambda: copy.deepcopy(state))
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime configuration differs"):
        remote.runtime_images(config)


def test_compose_escaped_dollars_compare_as_literal_container_values(config, monkeypatch, tmp_path):
    fixture = collector_fixture(config, monkeypatch)
    source = remote.source_files(remote.ROOT)
    compose = remote.yaml.safe_load(source["deployment/compose.yaml"])
    compose["services"]["worker"]["environment"]["EXPLICIT_LITERAL"] = "$${LITERAL}$$value"
    source["deployment/compose.yaml"] = remote.yaml.safe_dump(compose).encode()
    for name, data in source.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(remote, "ROOT", tmp_path)
    fixture.containers["worker-id"]["Config"]["Env"].append("EXPLICIT_LITERAL=${LITERAL}$value")
    install_runtime_io(config, monkeypatch, fixture.probe)
    assert remote.runtime_images(config)["services"]["worker"]["runtime_config_sha256"]


@pytest.mark.parametrize("final", [False, True])
@pytest.mark.parametrize("field,value", [
    ("Privileged", True), ("Privileged", None), ("PidMode", "host"),
    ("PidMode", "container:foreign"), ("IpcMode", "host"), ("UTSMode", "host"),
    ("UsernsMode", "host"), ("CgroupnsMode", "host"), ("CapAdd", ["SYS_ADMIN"]),
    ("Devices", [{"PathOnHost": "/dev/mem"}]), ("DeviceRequests", [{"Count": -1}]),
    ("DeviceCgroupRules", ["a *:* rwm"]), ("SecurityOpt", ["seccomp=unconfined"]),
    ("VolumesFrom", ["foreign"]),
])
def test_actual_collector_rejects_undeclared_isolation_for_migration_and_final(
        config, monkeypatch, final, field, value):
    fixture = collector_fixture(config, monkeypatch)
    fixture.containers["worker-id"]["HostConfig"][field] = value
    state = fixture.probe()
    assert next(item for item in state["containers"] if item["id"] == "worker-id")[
        "isolation_config"][field] == value
    with pytest.raises(remote.RemoteEnvironmentError, match="isolation configuration"):
        remote.validate_guard_state(config, state, OWNER, require_running=final)


@pytest.mark.parametrize("field,value", [
    ("Test", ["CMD", "true"]), ("Test", ["NONE"]), ("Test", []),
    ("Interval", 60_000_000_000), ("Timeout", 5_000_000_000),
    ("Retries", 300), ("StartPeriod", 1_000_000_000), ("StartInterval", 9_000_000_000),
])
def test_actual_healthy_probe_definition_drift_is_rejected(config, monkeypatch, field, value):
    fixture = collector_fixture(config, monkeypatch)
    fixture.containers["rabbitmq-id"]["Config"]["Healthcheck"][field] = value
    install_runtime_io(config, monkeypatch, fixture.probe)
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime configuration differs"):
        remote.runtime_images(config)


def test_missing_actual_probe_rejected_even_with_stale_healthy_status(config, monkeypatch):
    fixture = collector_fixture(config, monkeypatch)
    fixture.containers["rabbitmq-id"]["Config"].pop("Healthcheck")
    install_runtime_io(config, monkeypatch, fixture.probe)
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime configuration differs"):
        remote.runtime_images(config)


def test_probe_inherits_image_defaults_and_compose_units_match_docker(config, monkeypatch):
    fixture = collector_fixture(config, monkeypatch)
    broker = fixture.containers["rabbitmq-id"]
    image_probe = {"Test": ["CMD", "image-check"], "Interval": 17_000_000_000,
                   "Timeout": 9_000_000_000, "Retries": 4, "StartInterval": 2_000_000_000}
    fixture.images[broker["Image"]]["Config"]["Healthcheck"] = image_probe
    broker["Config"]["Healthcheck"]["StartInterval"] = 2_000_000_000
    state = fixture.probe()
    remote.validate_guard_state(config, state, OWNER, require_running=True)
    actual = next(item for item in state["containers"] if item["id"] == "rabbitmq-id")
    assert actual["runtime_config"]["healthcheck"]["StartInterval"] == 2_000_000_000
    assert actual["runtime_config"]["healthcheck"]["Timeout"] == 20_000_000_000
    definition = copy.deepcopy(fixture.compose["services"]["rabbitmq"])
    definition["healthcheck"].update(interval="3000ms", timeout="0.333333333m20ns",
                                   start_period="10000000000ns")
    expected = remote.candidate_runtime_config(definition, actual["image_runtime_config"])
    assert expected == actual["runtime_config"]


def test_engine_health_defaults_and_no_probe_services_preserved():
    probe = remote.inspected_healthcheck({"Test": ["CMD", "check"]})
    assert probe == {"Test": remote.configuration_digest(["CMD", "check"]),
                     "Interval": 30_000_000_000, "Timeout": 30_000_000_000,
                     "Retries": 3, "StartPeriod": 0, "StartInterval": 5_000_000_000}
    assert remote.candidate_healthcheck({}, None) is None
    assert remote.candidate_healthcheck({}, probe) == probe
    assert remote.inspected_healthcheck({"Test": ["NONE"]}) is None


@pytest.mark.parametrize("location", ["image", "container"])
@pytest.mark.parametrize("value", [None, 0, False, [], {}, "missing"])
def test_actual_collector_requires_explicit_string_user(config, monkeypatch, location, value):
    fixture = collector_fixture(config, monkeypatch)
    container = fixture.containers["worker-id"]
    settings = (fixture.images[container["Image"]] if location == "image" else container)["Config"]
    if value == "missing":
        settings.pop("User")
    else:
        settings["User"] = value
    install_runtime_io(config, monkeypatch, fixture.probe)
    with pytest.raises(remote.RemoteEnvironmentError, match="runtime user"):
        remote.runtime_images(config)


@pytest.mark.parametrize("override,expected", [(None, "eid"), ("", "eid"),
    ("2000:3000", "2000:3000"), ("eid:staff", "eid:staff")])
def test_compose_user_merges_with_inspected_image(config, monkeypatch, override, expected):
    fixture = collector_fixture(config, monkeypatch)
    worker = next(item for item in fixture.probe()["containers"] if item["id"] == "worker-id")
    definition = {} if override is None else {"user": override}
    result = remote.candidate_runtime_config(definition, worker["image_runtime_config"])
    assert result["user"] == expected


@pytest.mark.parametrize("user", [None, 0, True, {}, []])
def test_compose_non_string_user_is_rejected(config, monkeypatch, user):
    fixture = collector_fixture(config, monkeypatch)
    worker = next(item for item in fixture.probe()["containers"] if item["id"] == "worker-id")
    with pytest.raises(remote.RemoteEnvironmentError, match="Compose user"):
        remote.candidate_runtime_config({"user": user}, worker["image_runtime_config"])


@pytest.mark.parametrize("user", [None, 0, False, [], {}, "missing"])
def test_candidate_requires_complete_inspected_user(config, monkeypatch, user):
    fixture = collector_fixture(config, monkeypatch)
    worker = next(item for item in fixture.probe()["containers"] if item["id"] == "worker-id")
    image = worker["image_runtime_config"]
    if user == "missing":
        image.pop("user")
    else:
        image["user"] = user
    with pytest.raises(remote.RemoteEnvironmentError, match="image runtime configuration"):
        remote.candidate_runtime_config({}, image)


@pytest.mark.parametrize("source,overlaps", [
    ("/opt/docker/eid-other/removed", False),
    ("/opt/docker/eid/removed", True),
    ("/opt/eid-other/removed", False),
    ("/opt/eid/removed", True),
    ("/opt/docker", True),
    ("/var/lib/docker/volumes/eid-remote-dev-postgres/_data/removed", True),
    ("/var/lib/docker/volumes", True),
])
def test_real_path_resolution_preserves_overlap_for_missing_foreign_bind(
        config, monkeypatch, tmp_path, source, overlaps):
    fixture = collector_fixture(config, monkeypatch, filesystem_root=tmp_path)
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "exited"},
        "Mounts": [{"Type": "bind", "Source": source, "Destination": "/shared"}]}
    state = fixture.probe()
    if overlaps:
        with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
            remote.validate_remote_state(config, state, OWNER, require_running=True)
        with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
            remote.validate_guard_state(config, state, OWNER, require_running=True)
    else:
        assert remote.validate_remote_state(config, state, OWNER, require_running=True)[
            "isolation_verified"]
        assert set(remote.validate_guard_state(config, state, OWNER,
                                               require_running=True)) == remote.SERVICES


@pytest.mark.parametrize("target,tail", [("opt/docker/eid", "removed"),
    ("opt/eid", "removed"),
    ("var/lib/docker/volumes/eid-remote-dev-postgres/_data", "removed"),
    ("var/lib/docker/volumes", "eid-remote-dev-postgres/_data/removed")])
def test_real_symlink_ancestor_of_missing_foreign_bind_still_overlaps_eid(
        config, monkeypatch, tmp_path, target, tail):
    fixture = collector_fixture(config, monkeypatch, filesystem_root=tmp_path)
    (tmp_path / "foreign-link").symlink_to(tmp_path / target, target_is_directory=True)
    fixture.containers["foreign"] = {"Id": "foreign", "Name": "/other-project",
        "Config": {"Labels": {}}, "HostConfig": {}, "State": {"Status": "exited"},
        "Mounts": [{"Type": "bind", "Source": "/foreign-link/" + tail, "Destination": "/shared"}]}
    state = fixture.probe()
    assert state["containers"][-1]["mounts"][0]["Source"] == "/" + target + "/" + tail
    assert state["containers"][-1]["mounts"][0]["OriginalSource"] == "/foreign-link/" + tail
    with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
        remote.validate_remote_state(config, state, OWNER, require_running=True)
    with pytest.raises(remote.RemoteEnvironmentError, match="Foreign container"):
        remote.validate_guard_state(config, state, OWNER, require_running=True)


@pytest.mark.parametrize("linked_path", ["opt/docker", "opt/docker/eid"])
def test_real_symlink_redirecting_retained_root_is_rejected(config, monkeypatch, tmp_path, linked_path):
    fixture = collector_fixture(config, monkeypatch, filesystem_root=tmp_path)
    destination = tmp_path / "retained-elsewhere"
    destination.mkdir()
    path = tmp_path / linked_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(destination, target_is_directory=True)
    with pytest.raises(remote.RemoteEnvironmentError, match="Retained EID root"):
        fixture.probe()
    assert not fixture.calls


def test_missing_eid_owned_bind_remains_blocked(config, monkeypatch, tmp_path):
    fixture = collector_fixture(config, monkeypatch, filesystem_root=tmp_path)
    mount = next(item for item in fixture.containers["postgres-id"]["Mounts"] if item["Type"] == "bind")
    (tmp_path / mount["Source"].lstrip("/")).unlink()
    with pytest.raises(FileNotFoundError):
        fixture.probe()
