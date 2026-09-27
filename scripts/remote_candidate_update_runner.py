"""Root-side single-use candidate stage/application update; supplied over stdin.

Only API, Worker and Web may be replaced. Existing transition helpers are loaded
as libraries; none of their one-time entrypoints are invoked.
"""

import copy
import hashlib
import io
import json
import os
from pathlib import PurePosixPath
import re
import signal
import stat
import tarfile
import time
import types

APPS = ("api", "worker", "web")
PROTECTED = ("postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx")
QUEUES = ("generation", "retrieval", "review", "parse_ocr", "render", "integration")
SUBSCRIBED_QUEUES = ("generation", "retrieval", "review", "integration")
COMPLETE_SHA = "9a46d6206a63b1e6a99cb08c3c70571b7df9792cf59496fb06b3d5de3131c702"
SHUTDOWN_SECONDS = 60
FORWARD_MODE = "web-forward-fix-v1"
FORWARD_RELEASE = "/opt/eid/release-20260918-001"
FORWARD_BASELINE_SHA = "8c4a3105adc8334b9b0daca6fa1c5b40e7aa7b1d3ba9b325b84085e518171799"
FORWARD_CHAIN_HASHES = {
    "update-bundle-001/bundle.json": "a4fd5881187503973d8d8fa616c74bf26a01c17c94eda077725b40d05ece9656",
    "update-bundle-001/candidate.json": "4e53d8b5db508f386d8859b1f8147e53bc10cd01e1ce9aa197895496e4e44875",
    "source.tar.gz": "b6adf5ce65e45c868e0cfdf170efd7cc80077076c53d4226e664d49a639c2138",
    "source-evidence.json": "b0d46d97401645a084238fe9c5d6e8ad8bfb35726c19e9f8133c5ceded5a6cc0",
    "stage-001.json": "287a303f96265e44ad091eaf8d6480e0a94caf65d04f6d16c63f57baa9d91d9e",
    "apply-001.json": "bcb5c930db2cf96854baea574633f99d5fa7fc83f419e75ec9b27bc39139f81c",
    "images-bundle-001/bundle.json": "79f93f54483fdc78430cc08baec14220f75fce5596aff37dee9ab0312f3dc65f",
    "images-bundle-001/import.json": "d4b3cd57f46e22c733d03339ec954773e59c30655323b8f047a21b4b317369e7",
    "images-import-001.json": "7b76d93746f29d2fa16057cd9e1641db557f7ac33b8819edf11d03397d652277",
    "migration-receipt-001.json": "2113c58ac20cb5224814e64e2e0f34f34a6fc1454f40002d0e607366134bfafc",
}
FORWARD_IDENTITY = {"device": 64768, "inode": 29497156, "uid": 0, "gid": 0,
                    "mode": 0o700, "is_dir": True, "is_regular": False}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def summary(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def forward_mode(candidate):
    require(candidate.get("update_mode", "expand") in {"expand", FORWARD_MODE}, "Unknown update mode")
    return candidate.get("update_mode") == FORWARD_MODE


def replacements(candidate):
    return ("web",) if forward_mode(candidate) else APPS


def service_release(candidate, name):
    return FORWARD_RELEASE if forward_mode(candidate) and name in APPS else candidate["old_release"]


def forward_chain(payload, baseline_raw):
    """Fixed successful 002 evidence, read as data; no historical code is executed."""
    require(digest(baseline_raw) == FORWARD_BASELINE_SHA, "Forward baseline anchor differs")
    raw = {name: payload["forward/" + name] for name in FORWARD_CHAIN_HASHES}
    require(all(digest(raw[name]) == sha for name, sha in FORWARD_CHAIN_HASHES.items()),
            "Forward successful-chain anchor differs")
    current = json.loads(raw["update-bundle-001/candidate.json"])
    baseline = json.loads(baseline_raw)
    stage = json.loads(raw["stage-001.json"])
    applied = json.loads(raw["apply-001.json"])
    bundle_sha = FORWARD_CHAIN_HASHES["update-bundle-001/bundle.json"]
    require(current["release"] == FORWARD_RELEASE and current["to_revision"] == "0007_workspace_discovery"
            and stage["exit_code"] == applied["exit_code"] == 0
            and stage["bundle_sha256"] == applied["bundle_sha256"] == bundle_sha
            and stage["events"][-1]["release_identity"] == FORWARD_IDENTITY
            and applied["events"][-1]["app_ids"] == {
                name: baseline["services"][name]["container_id"] for name in APPS}
            and applied["events"][-1]["protected_ids"] == {
                name: baseline["services"][name]["container_id"] for name in PROTECTED},
            "Forward source/stage/apply lineage differs")
    files = archive_files(raw["source.tar.gz"], current["files"])
    require(digest(files["deployment/remote.compose.yaml"]) == baseline["provenance"]["compose_sha256"],
            "Forward current Compose differs")
    for name in APPS:
        require(current["images"][name] == {key: baseline["services"][name][key]
                for key in ("image_id", "source_fingerprint")}, "Forward baseline image differs")
    return {"current": current, "files": files, "stage": stage, "apply": applied,
            "images": json.loads(raw["images-bundle-001/import.json"])["images"]}


def forward_identity(r, retained, chain):
    require(staged_identity(r, chain["current"]) == FORWARD_IDENTITY, "Current release inode/content changed")
    sha = FORWARD_CHAIN_HASHES["update-bundle-001/bundle.json"]
    for phase, evidence in (("stage", chain["stage"]), ("apply", chain["apply"])):
        raw = retained.read_owned(r, r.ROOT_PATH + "/.candidate-" + sha + "-" + phase + ".jsonl", maximum=65536)
        require(same_json([json.loads(line) for line in raw.splitlines()], evidence["events"]),
                "Current successful journal changed")


def baseline_hashes(r, candidate):
    if forward_mode(candidate):
        return (compose_hashes(r, candidate["old_release"], PROTECTED)
                | compose_hashes(r, FORWARD_RELEASE, APPS))
    return compose_hashes(r, candidate["old_release"], APPS + PROTECTED)


def schema_receipt(data, candidate, sha):
    """A no-migration proof has a separate, closed schema on both ends."""
    required = {"schema_version": 1, "kind": "eid-remote-candidate-schema-verified",
        "environment": "seadee-develop", "host": "172.27.0.38", "root": "/opt/eid",
        "compose_project": "eid-remote-dev", "database": "eid_local_dev", "marker": "eid-local-dev-v1",
        "owner_nonce": "05a8f0d646f040d5a8bdcf097864d155", "bundle_sha256": sha,
        "artifact_sha256": candidate["artifact_sha256"], "baseline_sha256": candidate["baseline_sha256"],
        "from_revision": "0007_workspace_discovery", "revision": "0007_workspace_discovery",
        "migration_executed": False, "live_revision_exit_code": 0, "database_identity_verified": True}
    require(isinstance(data, dict) and set(data) == set(required) | {"live_revision_evidence_sha256", "verified_at"}
            and all(type(data.get(key)) is type(value) and data[key] == value for key, value in required.items())
            and isinstance(data.get("live_revision_evidence_sha256"), str)
            and re.fullmatch("[a-f0-9]{64}", data["live_revision_evidence_sha256"])
            and type(data.get("verified_at")) in {int, float}
            and 0 <= time.time() - data["verified_at"] <= 900, "Recent no-migration schema receipt required")
    return data


def recent_receipt(data, candidate, sha):
    if forward_mode(candidate):
        return schema_receipt(data, candidate, sha)
    require(isinstance(data, dict) and data.get("bundle_sha256") == sha
            and data.get("revision") == candidate["to_revision"]
            and data.get("baseline_sha256") == candidate["baseline_sha256"]
            and data.get("artifact_sha256") == candidate["artifact_sha256"]
            and data.get("database_identity_verified") is True
            and data.get("expand_only_reviewed") is True
            and type(data.get("verified_at")) in {int, float}
            and 0 <= time.time() - data["verified_at"] <= 900, "Recent migration receipt missing")
    return data


def recent_check(checked, sha, phase):
    require(isinstance(checked, dict) and checked.get("kind") == "candidate_check_passed"
            and checked.get("bundle_sha256") == sha and checked.get("phase") == phase
            and checked.get("remote_writes") is False and isinstance(checked.get("snapshot"), dict)
            and type(checked.get("checked_at")) in {int, float}
            and 0 <= time.time() - checked["checked_at"] <= 300,
            "A recent exact successful phase CHECK is required")


def load_module(name, raw):
    module = types.ModuleType(name)
    exec(compile(raw, "<" + name + ">", "exec"), module.__dict__)
    return module


def helpers(payload, connection):
    frozen = {name.removeprefix("completion/"): raw for name, raw in payload.items()
              if name.startswith("completion/")}
    require(digest(frozen["complete-bundle.json"]) == COMPLETE_SHA, "Completion anchor differs")
    manifest = json.loads(frozen["complete-bundle.json"])
    require(all(digest(frozen[name]) == sha for name, sha in manifest["files"].items()),
            "Completion helper changed")
    completion = load_module("eid_completion_readonly_library", frozen["complete_runner.py"])
    r, retained = completion.load_frozen(frozen, connection, False)
    historical = load_module("eid_app_start_readonly_library", payload["app_start_runner.py"])
    normal = load_module("eid_candidate_normal_guard", payload["normal_support.py"])
    return r, retained, historical, normal


def archive_files(raw, hashes):
    require(len(raw) <= 32 * 1024 * 1024, "Oversized artifact")
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            name = member.name
            path = PurePosixPath(name)
            total += member.size
            require(name and not path.is_absolute() and "\\" not in name and ":" not in name
                    and "\0" not in name and all(part not in {"", ".", ".."} for part in name.split("/"))
                    and member.isfile() and not member.issparse() and not member.linkname
                    and not member.pax_headers and name not in files
                    and 0 <= member.size <= 16 * 1024 * 1024
                    and total <= 128 * 1024 * 1024 and len(files) < 4096, "Unsafe archive")
            raw_file = archive.extractfile(member).read()
            require(digest(raw_file) == hashes.get(name), "Artifact member changed")
            files[name] = raw_file
    require(set(files) == set(hashes), "Artifact inventory differs")
    return files


def compose_command(r, candidate, service):
    require(service in replacements(candidate), "Service is outside the fixed replacement set")
    return r.DOCKER + ["compose", "--project-name", r.PROJECT, "--file",
        candidate["release"] + "/deployment/remote.compose.yaml", "up", "--detach",
        "--no-deps", "--no-build", "--pull", "never", "--force-recreate",
        "--timeout", str(SHUTDOWN_SECONDS), "--wait", "--wait-timeout", "120", service]


def compose_hashes(r, release, services):
    prefix = r.DOCKER + ["compose", "--project-name", r.PROJECT, "--file",
                        release + "/deployment/remote.compose.yaml"]
    r.run(prefix + ["config", "--quiet"])
    result = {}
    for name in services:
        fields = r.run(prefix + ["config", "--hash", name]).split()
        require(len(fields) == 2 and fields[0] == name and re.fullmatch("[a-f0-9]{64}", fields[1]),
                "Missing or ambiguous Compose hash")
        result[name] = fields[1]
    return result


def same_json(before, after):
    """JSON types are part of the contract: in particular False must not equal 0."""
    return json.dumps(before, sort_keys=True, allow_nan=False) == json.dumps(after, sort_keys=True, allow_nan=False)


def remove_legacy_build_labels(before, after, service):
    """One-way Compose 5.0.1 build metadata removal, only on comparison copies.

    Kept identical in the standalone importer, which bundles this updater as data.
    Fingerprints must be verified separately before calling this helper.
    """
    legacy = {"com.docker.compose.project": "eid-local", "com.docker.compose.service": service,
              "com.docker.compose.version": "5.0.1"}
    require(not any(key in before for key in legacy)
            or all(before.get(key) == value for key, value in legacy.items()),
            "Candidate image runtime defaults changed")
    if all(before.get(key) == value for key, value in legacy.items()) and all(key not in after for key in legacy):
        for key in legacy:
            del before[key]


def pinned_images(r, candidate, baseline):
    result = {}
    for name in APPS:
        reference = candidate["compose"]["services"][name]["image"]
        rows = json.loads(r.docker(["image", "inspect", reference]))
        require(len(rows) == 1, "Candidate image absent or ambiguous")
        item = rows[0]
        expected = candidate["images"][name]
        require(item["Id"] == expected["image_id"] and item["Os"] == "linux"
                and item["Architecture"] == "amd64"
                and (item.get("Config", {}).get("Labels") or {}).get("io.eid.source-fingerprint")
                == expected["source_fingerprint"], "Candidate image ID/full fingerprint differs")
        old = baseline["services"][name]
        old_rows = json.loads(r.docker(["image", "inspect", old["image_id"]]))
        require(len(old_rows) == 1 and old_rows[0]["Id"] == old["image_id"]
                and old_rows[0]["Os"] == "linux" and old_rows[0]["Architecture"] == "amd64",
                "Pinned old image absent or ambiguous")
        old_config = copy.deepcopy(old_rows[0].get("Config"))
        new_config = copy.deepcopy(item.get("Config"))
        require(isinstance(old_config, dict) and isinstance(new_config, dict)
                and isinstance(old_config.get("Labels"), dict) and isinstance(new_config.get("Labels"), dict),
                "Image configuration missing")
        require(old_config["Labels"].pop("io.eid.source-fingerprint", None) == old["source_fingerprint"]
                and new_config["Labels"].pop("io.eid.source-fingerprint", None) == expected["source_fingerprint"],
                "Candidate image runtime defaults changed")
        remove_legacy_build_labels(old_config["Labels"], new_config["Labels"], name)
        require(same_json(old_config, new_config), "Candidate image runtime defaults changed")
        if name in {"api", "worker"}:
            require(isinstance(new_config.get("User"), str), "Candidate Python image is root or has invalid user")
            user = new_config["User"].partition(":")[0]
            require(user and user != "root" and not (re.fullmatch("[+-]?[0-9]+", user) and int(user) == 0),
                    "Candidate Python image is root")
        result[name] = summary(item)
    return result


def canonical_record(record):
    result = dict(record)
    result["mounts"] = sorted(record["mounts"], key=lambda value: json.dumps(value, sort_keys=True))
    return result


def require_service(normal, candidate, baseline, record, name, expected_id, hashes, replaced, phase):
    require(record["id"] == expected_id and re.fullmatch("[a-f0-9]{64}", expected_id),
            "Unexpected container replacement: " + name)
    old = baseline["services"][name]
    image = candidate["images"][name] if replaced else old
    reference = candidate["compose"]["services"][name]["image"] if replaced else old["image_ref"]
    require(record["image_id"] == record["referenced_image_id"] == image["image_id"]
            and record["image_ref"] == reference and record["state"] == "running", "Image/state drift: " + name)
    if name in APPS:
        require(record["image_labels"].get("io.eid.source-fingerprint") == image["source_fingerprint"],
                "Full runtime source fingerprint differs")
        require(not record["mounts"], "Application gained a mount")
    if replaced:
        expected_runtime = normal.candidate_runtime_config(candidate["compose"]["services"][name],
                                                           record["image_runtime_config"])
        require(record["runtime_config"] == expected_runtime, "Candidate process/environment differs")
    else:
        require(summary({"process": record["runtime_config"], "isolation": record["isolation_config"]})
                == old["runtime_config_sha256"], "Baseline runtime configuration changed")
    if name in {"api", "worker"}:
        user = record["runtime_config"]["user"].partition(":")[0]
        require(user and user != "root" and not (re.fullmatch("[+-]?[0-9]+", user) and int(user) == 0),
                "Python runtime is root")
    # Old API/Worker readiness may reject the newly expanded schema. Every other
    # service, and each replaced service, must remain healthy.
    if forward_mode(candidate) or replaced or phase == "stage" or name not in {"api", "worker"}:
        if name in APPS:
            healthcheck = record["runtime_config"]["healthcheck"]
            # The ordinary collector hashes the exact effective Test argv.
            require(isinstance(healthcheck, dict) and isinstance(healthcheck.get("Test"), str)
                    and re.fullmatch("[a-f0-9]{64}", healthcheck["Test"]), "Application health check missing")
        require(record["health"] == ("healthy" if record["runtime_config"]["healthcheck"] else None),
                "Service unhealthy: " + name)
    labels = record["labels"]
    release = candidate["release"] if replaced else service_release(candidate, name)
    require(labels.get("com.docker.compose.config-hash") == hashes[name]
            and labels.get("com.docker.compose.project.config_files") == release + "/deployment/remote.compose.yaml"
            and labels.get("com.docker.compose.project.working_dir") == release + "/deployment"
            and labels.get("com.docker.compose.container-number") == "1"
            and labels.get("com.docker.compose.oneoff") == "False", "Compose provenance differs")


def protected_snapshot(r, retained, historical, normal, candidate, baseline, replaced, hashes, phase,
                       *, importing=False):
    historical.protected_identity(r, retained)
    config = candidate["config"]
    state = normal.collect_remote_state(config, r.CONNECTION)
    normal.validate_remote_state(config, state, r.OWNER, require_running=True)
    require(state["server"] == baseline["provenance"]["docker_server"], "Docker server changed")
    found = {record["labels"]["com.docker.compose.service"]: record for record in state["containers"]
             if record["labels"].get("com.docker.compose.project") == r.PROJECT}
    require(set(found) == set(APPS + PROTECTED), "Service inventory differs")
    expected = {name: item["container_id"] for name, item in baseline["services"].items()} | replaced
    require(len(set(expected.values())) == 9, "Duplicate container identity")
    protected = {}
    namespaces = set()
    host_namespace = os.readlink("/proc/1/ns/cgroup")
    require(host_namespace == r.H["host_cgroup_namespace"], "Host cgroup namespace changed")
    for name, record in found.items():
        require_service(normal, candidate, baseline, record, name, expected[name], hashes,
                        name in replaced, phase)
        raw = json.loads(r.docker(["inspect", record["id"]]))[0]
        require(raw["Id"] == record["id"] and raw["State"]["Running"] is True
                and type(raw["State"]["Pid"]) is int and raw["State"]["Pid"] > 1, "Container process missing")
        namespace = os.readlink("/proc/" + str(raw["State"]["Pid"]) + "/ns/cgroup")
        require(namespace != host_namespace and namespace not in namespaces, "Cgroup namespace is not private")
        namespaces.add(namespace)
        if forward_mode(candidate):
            binds = [mount for mount in record["mounts"] if mount["Type"] == "bind"]
            wanted = historical.BINDS.get(name, {})
            require(len(binds) == len(wanted) and {mount["Destination"] for mount in binds} == set(wanted),
                    "Forward bind inventory differs")
            for mount in binds:
                relative = wanted[mount["Destination"]]
                require(mount["Source"] == service_release(candidate, name) + "/" + relative
                        and mount["RW"] is False and mount["sha256"] == candidate["files"][relative],
                        "Forward bind source/content differs")
            volumes = [mount for mount in record["mounts"] if mount["Type"] == "volume"]
            require(len(record["mounts"]) == len(binds) + len(volumes)
                    and len(volumes) == int(name in historical.VOLUMES), "Forward mount inventory differs")
            if volumes:
                require(volumes[0]["Name"] == r.PROJECT + "-" + name
                        and volumes[0]["Destination"] == historical.VOLUMES[name] and volumes[0]["RW"] is True,
                        "Forward persistent mount differs")
        if importing or name not in replacements(candidate):
            protected[name] = {"record": canonical_record(record), "namespace": namespace}
    for name in historical.VOLUMES:
        volume = json.loads(r.docker(["volume", "inspect", r.PROJECT + "-" + name]))[0]
        require(volume == r.H["volumes"][name]["inspect"], "Original volume changed")
        descriptor = r.secure_fd(volume["Mountpoint"], directory=True)
        try:
            actual = r.metadata(os.fstat(descriptor))
            require(actual == {key: r.H["volumes"][name]["path"][key] for key in actual},
                    "Original volume inode changed")
        finally:
            os.close(descriptor)
    network = json.loads(r.docker(["network", "inspect", r.PROJECT + "_default"]))[0]
    require({key: value for key, value in network.items() if key != "Containers"} == r.H["network"]
            and set(network["Containers"]) == set(expected.values()), "Network identity/attachment differs")
    # Candidate image imports must finish before CHECK: all images and foreign
    # containers/resources stay invariant through staging and replacement.
    foreign = historical.foreign_inventory(r, state)
    if importing:
        foreign.pop("images")
    return {"protected": summary(protected), "foreign": summary(foreign),
            "images": pinned_images(r, candidate, baseline), "network_id": network["Id"]}, found


def root_listing(r):
    result = {}
    for name in os.listdir(r.ROOT_FD):
        value = os.stat(name, dir_fd=r.ROOT_FD, follow_symlinks=False)
        require(not stat.S_ISLNK(value.st_mode), "Linked root entry")
        result[name] = r.metadata(value)
    return result


def staged_identity(r, candidate):
    """Verify the complete exclusively-created candidate tree, including its inode receipt."""
    release = candidate["release"]
    descriptor = r.secure_fd(release, directory=True)
    try:
        identity = r.metadata(os.fstat(descriptor))
        require(identity["uid"] == identity["gid"] == 0 and identity["mode"] == 0o700,
                "Candidate release is not root controlled")
        seen = set()
        directories = {str(parent) for name in candidate["files"]
                       for parent in PurePosixPath(name).parents if str(parent) != "."}
        seen_dirs = set()

        def walk(fd, prefix=""):
            for name in os.listdir(fd):
                relative = prefix + name
                value = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(value.st_mode):
                    require(relative in directories and value.st_uid == value.st_gid == 0
                            and stat.S_IMODE(value.st_mode) == 0o700, "Unexpected candidate directory")
                    seen_dirs.add(relative)
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, relative + "/")
                    finally:
                        os.close(child)
                else:
                    require(relative in candidate["files"] and stat.S_ISREG(value.st_mode)
                            and value.st_uid == value.st_gid == 0 and value.st_nlink == 1
                            and stat.S_IMODE(value.st_mode) == 0o600, "Unexpected/unsafe candidate file")
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                    with os.fdopen(child, "rb") as stream:
                        require(os.fstat(stream.fileno()) == value, "Candidate file replaced during inspection")
                        require(digest(stream.read(16 * 1024 * 1024 + 1)) == candidate["files"][relative],
                                "Staged candidate content changed")
                    seen.add(relative)
        walk(descriptor)
        require(seen == set(candidate["files"]) and seen_dirs == directories, "Candidate release incomplete")
        return identity
    finally:
        os.close(descriptor)


def stage_files(r, candidate, files):
    name = candidate["release"].removeprefix(r.ROOT_PATH + "/")
    require(re.fullmatch(r"release-[0-9]{8}-[a-z0-9][a-z0-9-]{0,40}", name), "Unsafe release path")
    os.mkdir(name, 0o700, dir_fd=r.ROOT_FD)
    os.fsync(r.ROOT_FD)
    release_fd = r.secure_fd(candidate["release"], directory=True)
    try:
        for name, raw in files.items():
            parts = PurePosixPath(name).parts
            directory = os.dup(release_fd)
            try:
                for part in parts[:-1]:
                    try:
                        os.mkdir(part, 0o700, dir_fd=directory)
                    except FileExistsError:
                        pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    value = os.fstat(child)
                    require(value.st_uid == value.st_gid == 0 and stat.S_IMODE(value.st_mode) == 0o700,
                            "Unsafe staged directory")
                    os.fsync(directory)
                    os.close(directory)
                    directory = child
                r.write_new_at(directory, parts[-1], raw)
            finally:
                os.close(directory)
    finally:
        os.close(release_fd)
    return staged_identity(r, candidate)


def broker_idle(r, rabbit_id, compose):
    """Read-only inventory; no declarations, subscriptions, consumption or control RPC.

    The pinned worker subscribes to four of its six declared task queues. The
    two unsubscribed queues may be absent, but if present must also be empty.
    There are no ready-message exceptions in this vhost: retained proofs in a
    different vhost do not justify allowing unknown or native-delayed work here.
    """
    command = compose["services"]["worker"]["command"]
    require(isinstance(command, list) and all(isinstance(part, str) for part in command)
            and [part for part in command if part.startswith("--queues")]
            == ["--queues=" + ",".join(SUBSCRIBED_QUEUES)], "Pinned Worker subscription differs")
    queues = json.loads(r.docker(["exec", rabbit_id, "rabbitmqctl", "list_queues", "--vhost", "eid-local",
        "name", "type", "messages_ready", "messages_unacknowledged", "--formatter", "json"], timeout=45))
    require(isinstance(queues, list) and all(isinstance(item, dict) for item in queues), "Invalid queue inventory")
    names = [item.get("name") for item in queues]
    require(all(isinstance(name, str) and name for name in names)
            and len(set(names)) == len(names) and set(SUBSCRIBED_QUEUES) <= set(names),
            "Subscribed task queue inventory incomplete")
    stable = {}
    for item in queues:
        ready, unacked = item.get("messages_ready"), item.get("messages_unacknowledged")
        require(type(ready) is int and ready == 0 and type(unacked) is int and unacked == 0,
                "Queued/in-flight work exists")
        name, kind = item["name"], item.get("type")
        require(kind in {"quorum", "classic", "stream"}, "Unknown queue type")
        if name in QUEUES or re.fullmatch(r"celery_delayed_[0-9]+", name):
            require(kind == "quorum", "Task queue type changed")
        # Only empty, identified ephemeral control queues can appear/disappear
        # across Celery inspect/restart. Their counters above remain mandatory.
        control = kind == "classic" and (name == "eid-worker@worker.celery.pidbox"
            or re.fullmatch(r"celeryev\.[a-f0-9-]{36}", name)
            or re.fullmatch(r"[a-f0-9-]{36}\.reply\.celery\.pidbox", name))
        if not control:
            stable[name] = kind
    return {"subscribed": list(SUBSCRIBED_QUEUES), "queues": stable,
            "absent_unsubscribed": sorted(set(QUEUES) - set(SUBSCRIBED_QUEUES) - set(names))}


def worker_idle(r, identifier, rabbit_id, compose, queue_contract):
    """Apply-only RPC plus the same read-only broker contract bound before migration."""
    script = (
        "import json,os\nfrom edw_worker.app import app\n"
        "node=os.environ.get('EID_WORKER_NODE_NAME','eid-worker@worker')\n"
        "inspector=app.control.inspect(destination=[node],timeout=5)\n"
        "print(json.dumps({'node':node,**{name:getattr(inspector,name)() "
        "for name in ('active','reserved','scheduled')}}))\n"
    )
    response = json.loads(r.docker(["exec", identifier, "python", "-c", script], timeout=25))
    require(response.get("node") == "eid-worker@worker" and all(
        response.get(name) == {"eid-worker@worker": []} for name in ("active", "reserved", "scheduled")),
        "Worker in-flight state is nonempty, missing or ambiguous")
    require(broker_idle(r, rabbit_id, compose) == queue_contract, "Queue contract changed after stage CHECK")


def verify_live_revision(r, candidate, guard, api_id):
    """Reuse the existing connection identity guard; perform only a read-only revision query.

    The orchestrator has already run verify_migration_target + online Alembic.
    Here full host/container/volume guards run under the held deployment lock.
    No SQL migration or database mutation exists in this updater.
    """
    script = ("import json\nfrom sqlalchemy import create_engine\n"
        "from alembic.runtime.migration import MigrationContext\n" + guard.decode()
        + "engine=create_engine('postgresql+psycopg://eid_migrator:local-migrate-only@postgres:5432/eid_local_dev',"
        "connect_args={'connect_timeout':3,'options':'-c statement_timeout=5000 -c lock_timeout=2000'})\n"
        "with engine.connect().execution_options(postgresql_readonly=True) as connection:\n"
        " with connection.begin():\n"
        "  verify_migration_connection(connection)\n"
        "  heads=MigrationContext.configure(connection).get_current_heads()\n"
        "  print(json.dumps({'identity_verified':True,'heads':list(heads)}))\n")
    response = json.loads(r.docker(["exec", api_id, "python", "-c", script], timeout=20))
    require(response == {"identity_verified": True, "heads": [candidate["to_revision"]]},
            "Live guarded database revision differs")


def apply_services(r, candidate, baseline, initial, snapshot, live_revision, idle, log):
    """Each mutation is journaled before invocation. A failed/unknown result stops immediately."""
    replaced = {}
    for name in replacements(candidate):
        require(snapshot(replaced) == initial, "Protected state drift before replacement")
        live_revision(replaced)
        # Check work before every replace, including the API step. Celery
        # control probes publish transient RPC messages, but never consume or
        # cancel application tasks or alter persistent broker definitions.
        idle(replaced)
        old_id = baseline["services"][name]["container_id"]
        log("candidate_service_replace_begin", service=name, old_id=old_id)
        r.run(compose_command(r, candidate, name), timeout=SHUTDOWN_SECONDS + 150)
        rows = json.loads(r.docker(["inspect", r.PROJECT + "-" + name + "-1"]))
        require(len(rows) == 1 and re.fullmatch("[a-f0-9]{64}", rows[0]["Id"])
                and rows[0]["Id"] not in {item["container_id"] for item in baseline["services"].values()}
                and rows[0]["Id"] not in set(replaced.values()), "Replacement identity ambiguous")
        replaced[name] = rows[0]["Id"]
        require(not r.docker(["ps", "--all", "--quiet", "--no-trunc", "--filter", "id=" + old_id]),
                "Original application container remains")
        require(snapshot(replaced) == initial, "Protected state drift after replacement")
        log("candidate_service_verified", service=name, container_id=replaced[name])
    live_revision(replaced)
    idle(replaced)
    require(snapshot(replaced) == initial, "Protected state drift at completion")
    return replaced


def read_stage_receipt(r, retained, name, sha, candidate):
    raw = retained.read_owned(r, r.ROOT_PATH + "/" + name, maximum=65536)
    events = [json.loads(line) for line in raw.splitlines()]
    require(len(events) == 2 and events[0].get("kind") == "candidate_stage_begin"
            and events[1].get("kind") == "candidate_stage_complete"
            and all(event.get("bundle_sha256") == sha for event in events)
            and events[1].get("release_identity") == staged_identity(r, candidate),
            "Stage did not complete exactly; preserve partial state, no adoption/replay")
    require(isinstance(events[1].get("queue_contract"), dict), "Stage queue contract missing")
    return digest(raw), events[1]["release_identity"], events[1]["queue_contract"]


def run(payload, connection, mode, phase, sha, checked, migration):
    require(mode in {"check", "stage", "apply-apps"} and phase in {"stage", "apply-apps"}
            and (mode == "check" or mode == phase), "Invalid phase")
    r, retained, historical, normal = helpers(payload, connection)
    candidate = json.loads(payload["candidate.json"])
    baseline = json.loads(payload["baseline.json"])
    stage_name = ".candidate-" + sha + "-stage.jsonl"
    apply_name = ".candidate-" + sha + "-apply.jsonl"
    step = "bootstrap"
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(RuntimeError("Candidate update timed out")))
    signal.alarm(1200)
    os.umask(0o077)
    os.environ.clear()
    os.environ.update(r.CLEAN_ENV)
    os.chdir("/")
    try:
        require(os.geteuid() == 0 and r.run(["/usr/bin/hostname"]) == "seadee-develop"
                and connection.split()[2:3] == ["172.27.0.38"], "Wrong host")
        require(candidate["owner"] == r.INPUTS["receipt"] and candidate["old_release"] == r.RELEASE
                and candidate["release"] != r.RELEASE
                and re.fullmatch(r"/opt/eid/release-[0-9]{8}-[a-z0-9][a-z0-9-]{0,40}", candidate["release"]),
                "Candidate ownership/path differs")
        normal.validate_config(candidate["config"])
        require(digest(payload["baseline.json"]) == candidate["baseline_sha256"]
                and digest(payload["candidate.tar.gz"]) == candidate["artifact_sha256"], "Frozen input changed")
        chain = forward_chain(payload, payload["baseline.json"]) if forward_mode(candidate) else None
        if chain:
            require(candidate["from_revision"] == candidate["to_revision"] == "0007_workspace_discovery"
                    and candidate["release"] != FORWARD_RELEASE
                    and all(candidate["images"][name] == chain["current"]["images"][name]
                            for name in ("api", "worker")), "Forward revision/reuse differs")
        files = archive_files(payload["candidate.tar.gz"], candidate["files"])
        r.ROOT_FD = r.secure_fd(r.ROOT_PATH, directory=True)
        historical.protected_identity(r, retained)
        # Open existing locks only. No O_CREAT, O_TRUNC, replacement or lock bypass.
        r.acquire_lock(r.LEGACY_ROOT + "/.deploy.lock")
        r.acquire_lock(r.ROOT_PATH + "/.deploy.lock")
        historical.protected_identity(r, retained)
        step = "locked-preflight"
        root_before = root_listing(r)
        require(apply_name not in root_before, "Application attempt exists; blind replay forbidden")
        # Image defaults (including effective Python user, command, entrypoint,
        # health and all other Config fields) are checked before ANY Compose call.
        pinned_images(r, candidate, baseline)
        if chain:
            forward_identity(r, retained, chain)
        old_hashes = baseline_hashes(r, candidate)
        stage_proof = None
        new_hashes = {}
        if phase == "stage":
            require(stage_name not in root_before
                    and candidate["release"].rsplit("/", 1)[1] not in root_before, "Stage attempt exists; no replay")
        else:
            recent_receipt(migration, candidate, sha)
            stage_proof = read_stage_receipt(r, retained, stage_name, sha, candidate)
            new_hashes = compose_hashes(r, candidate["release"], replacements(candidate))

        def snapshot(replaced):
            if chain:
                forward_identity(r, retained, chain)
            hashes = old_hashes | {name: new_hashes[name] for name in replaced}
            value, _ = protected_snapshot(r, retained, historical, normal, candidate, baseline,
                                          replaced, hashes, phase)
            queues = broker_idle(r, baseline["services"]["rabbitmq"]["container_id"], candidate["compose"])
            if phase == "apply-apps":
                require(read_stage_receipt(r, retained, stage_name, sha, candidate) == stage_proof,
                        "Stage receipt/release identity changed")
                require(queues == stage_proof[2], "Queue contract changed since pre-migration stage")
            return value | {"queue_contract": queues}

        def live_revision(replaced):
            verify_live_revision(r, candidate, payload["migration_guard.py"],
                                 replaced.get("api", baseline["services"]["api"]["container_id"]))

        def idle(replaced):
            worker_idle(r, replaced.get("worker", baseline["services"]["worker"]["container_id"]),
                        baseline["services"]["rabbitmq"]["container_id"], candidate["compose"],
                        initial["queue_contract"])

        initial = snapshot({})
        if phase == "apply-apps" or chain:
            live_revision({})
        check_state = {"snapshot": initial, "root": root_before, "stage_proof": stage_proof,
                       "old_hashes": old_hashes, "new_hashes": new_hashes}
        if mode == "check":
            r.event("candidate_check_passed", bundle_sha256=sha, phase=phase, checked_at=time.time(),
                    snapshot=check_state, remote_writes=False, application_acceptance=False)
            return 0
        # JSON converts tuples to lists between the remote/local processes.
        require(isinstance(checked, dict) and summary(checked.get("snapshot")) == summary(check_state),
                "State changed after the reviewed phase CHECK")
        step = "create-single-use-journal"
        log_name = stage_name if phase == "stage" else apply_name
        # SSH, lock acquisition and read-only guards may consume the evidence lifetime.
        # Keep the original bound event and repeat both clocks at the first-write boundary.
        recent_check(checked, sha, phase)
        if phase == "apply-apps":
            recent_receipt(migration, candidate, sha)
        r.EVIDENCE_FD = os.open(log_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600, dir_fd=r.ROOT_FD)
        os.fsync(r.ROOT_FD)
        log_identity = r.metadata(os.fstat(r.EVIDENCE_FD))

        def log(kind, **fields):
            named = r.secure_fd(r.ROOT_PATH + "/" + log_name)
            try:
                require(r.metadata(os.fstat(named)) == log_identity == r.metadata(os.fstat(r.EVIDENCE_FD))
                        and os.fstat(named).st_nlink == 1, "Journal inode changed")
            finally:
                os.close(named)
            r.event(kind, bundle_sha256=sha, **fields)

        def guarded_snapshot(replaced):
            expected = dict(root_before) | {log_name: log_identity}
            require(root_listing(r) == expected, "Protected root inventory changed")
            return snapshot(replaced)

        log("candidate_" + phase + "_begin", initial_sha256=summary(check_state),
            broker_control_probes=phase == "apply-apps")
        step = phase
        if phase == "stage":
            require(guarded_snapshot({}) == initial, "State changed before staging")
            if chain:
                live_revision({})
            identity = stage_files(r, candidate, files)
            expected_root = root_before | {log_name: log_identity,
                                          candidate["release"].rsplit("/", 1)[1]: identity}
            require(root_listing(r) == expected_root and snapshot({}) == initial,
                    "Protected state changed during staging")
            compose_hashes(r, candidate["release"], replacements(candidate))
            if chain:
                live_revision({})
            log("candidate_stage_complete", release_identity=identity,
                artifact_sha256=candidate["artifact_sha256"], queue_contract=initial["queue_contract"],
                application_acceptance=False)
        else:
            replaced = apply_services(r, candidate, baseline, initial, guarded_snapshot, live_revision, idle, log)
            log("candidate_apply-apps_complete", app_ids=replaced, protected_ids={name:
                baseline["services"][name]["container_id"] for name in APPS + PROTECTED
                if name not in replacements(candidate)},
                live_revision=candidate["to_revision"], application_acceptance=False,
                runtime_manifest_recorded=False, automatic_rollback=False)
        return 0
    except BaseException as exc:
        # Unknown command outcomes preserve containers, volumes, releases and the
        # intent journal. This tool contains no recovery, replay or cleanup mode.
        r.event("candidate_update_stopped", step=step, reason=str(exc), error_type=type(exc).__name__,
                partial_state_preserved=True, automatic_retry=False, automatic_cleanup=False)
        return 1
    finally:
        signal.alarm(0)
        for descriptor, _, _ in reversed(r.LOCKS):
            r.fcntl.flock(descriptor, r.fcntl.LOCK_UN)
            os.close(descriptor)
        if r.EVIDENCE_FD is not None:
            os.close(r.EVIDENCE_FD)
        if r.ROOT_FD is not None:
            os.close(r.ROOT_FD)


if __name__ == "__main__":
    inputs = globals()
    raise SystemExit(run(*(inputs[name] for name in (
        "PAYLOAD", "CONNECTION", "MODE", "PHASE", "BUNDLE_SHA", "CHECKED", "MIGRATION"))))
