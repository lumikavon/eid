"""Single-use, root-controlled Docker archive import; no build or container mutation.

The archive parser is also used locally. Layers are hashed as opaque bytes, never
unpacked. Only the existing authenticated stdin launcher invokes ``run``.
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
import sys
import tarfile
import time

APPS = ("api", "worker", "web")
MAX_ARCHIVE = 4 * 1024 ** 3
CHUNK = 1024 * 1024
MAX_JSON = 4 * 1024 * 1024
LABEL = "io.eid.source-fingerprint"
BASELINE_SHA = "599b5b0287def39e9ff52a78194df9c27ec1922bf16aca8c8b8aecc9d2eb623a"
UPDATE_RUNNER_SHA = "39b57d642df842894acb05d5f46d0cc25f7e4779d6e8d640b20c219cf6c13022"
INSPECT_DEFAULTS = {"Hostname": "", "Domainname": "", "Image": "", "User": "",
    "AttachStdin": False, "AttachStdout": False, "AttachStderr": False,
    "Tty": False, "OpenStdin": False, "StdinOnce": False,
    "OnBuild": None, "Volumes": None, "Entrypoint": None}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name
            and "\0" not in name and not PurePosixPath(name).is_absolute()
            and all(part not in {"", ".", ".."} for part in name.split("/")), "Unsafe archive path")
    return name


def consume(stream, size, output=None):
    require(type(size) is int and 0 <= size <= MAX_ARCHIVE, "Invalid stream size")
    result = hashlib.sha256()
    remaining = size
    while remaining:
        raw = stream.read(min(CHUNK, remaining))
        require(raw and len(raw) <= remaining, "Truncated or oversized stream")
        result.update(raw)
        if output is not None:
            output.write(raw)
        remaining -= len(raw)
    return result.hexdigest()


def file_identity(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def tar_header(raw):
    """Decode a single fixed-size block without following extension payloads."""
    try:
        return tarfile.TarInfo.frombuf(raw, "utf-8", "strict")
    except (tarfile.HeaderError, UnicodeError) as exc:
        raise ValueError("Invalid tar header") from exc


def archive_info(stream, expected_sha, expected_size, tag, fingerprint):
    """Accept one Docker-exported image, with an optional verified OCI wrapper."""
    require(re.fullmatch("[a-f0-9]{64}", expected_sha)
            and type(expected_size) is int and 0 < expected_size <= MAX_ARCHIVE, "Invalid archive pin")
    stream.seek(0)
    require(consume(stream, expected_size) == expected_sha and not stream.read(1), "Archive hash/size differs")
    stream.seek(0)
    members = {}
    retained_size = 0
    end = 0
    # TarFile iteration automatically expands GNU/PAX headers before returning a
    # member. Inspect raw types first; frombuf only decodes this fixed 512-byte block.
    while end + 512 <= expected_size:
        stream.seek(end)
        header = stream.read(512)
        require(len(header) == 512, "Truncated tar header")
        if header == b"\0" * 512:
            break
        require(header[156:157] in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}, "Unsafe archive member")
        member = tar_header(header)
        name = safe_name(member.name.rstrip("/") if member.isdir() else member.name)
        require(name not in members and not member.linkname and not member.issparse()
                and 0 <= member.size <= MAX_ARCHIVE and len(members) < 1024, "Unsafe archive member")
        offset = end + 512
        end = offset + (member.size + 511) // 512 * 512
        require(end <= expected_size, "Archive member outside stream")
        if member.isdir():
            require(member.size == 0, "Nonempty archive directory")
            members[name] = {"directory": True}
            continue
        # Keep small blobs, since config/manifest paths need not have .json suffixes.
        # Every read is bounded even while accumulating the separately capped metadata.
        if member.size <= MAX_JSON:
            retained_size += member.size
            require(retained_size <= 32 * 1024 * 1024, "Too much archive metadata")
            with io.BytesIO() as output:
                sha = consume(stream, member.size, output)
                raw = output.getvalue()
            prefix = raw[:512]
        else:
            raw = None
            sha = consume(stream, member.size)
            stream.seek(offset)
            prefix = stream.read(512)
        members[name] = {"size": member.size, "sha256": sha, "raw": raw, "prefix": prefix}
    require(1024 <= expected_size - end <= CHUNK, "Invalid tar termination")
    stream.seek(end)
    require(not any(stream.read(expected_size - end)), "Nonzero data after archive end")
    require("manifest.json" in members, "Docker manifest missing")

    def document(name):
        require(name in members and members[name].get("raw") is not None, "Missing/oversized image metadata")
        return unique_json(members[name]["raw"])

    manifest = document("manifest.json")
    require(isinstance(manifest, list) and len(manifest) == 1 and isinstance(manifest[0], dict),
            "Exactly one Docker image required")
    entry = manifest[0]
    require(set(entry) == {"Config", "RepoTags", "Layers"} and entry["RepoTags"] == [tag],
            "Exactly the declared candidate tag required")
    config_name = safe_name(entry["Config"])
    layers = entry["Layers"]
    require(isinstance(layers, list) and 0 < len(layers) <= 128
            and all(isinstance(name, str) for name in layers)
            and len(set(layers)) == len(layers), "Invalid layer inventory")
    for name in layers:
        safe_name(name)
        require(name in members and not members[name].get("directory"), "Missing layer")
    config = document(config_name)
    require(config.get("os") == "linux" and config.get("architecture") == "amd64"
            and config.get("variant", "") == "", "Image platform differs")
    runtime = config.get("config")
    require(isinstance(runtime, dict) and isinstance(runtime.get("Labels"), dict)
            and runtime["Labels"].get(LABEL) == fingerprint, "Full image fingerprint differs")
    rootfs = config.get("rootfs", {})
    require(rootfs.get("type") == "layers" and isinstance(rootfs.get("diff_ids"), list)
            and len(rootfs["diff_ids"]) == len(layers)
            and all(isinstance(value, str) and re.fullmatch("sha256:[a-f0-9]{64}", value)
                    for value in rootfs["diff_ids"]), "Invalid image rootfs")
    for name, diff_id in zip(layers, rootfs["diff_ids"], strict=True):
        layer = members[name]
        # type=docker supports uncompressed tar layers only. Never decompress or
        # extract layer entries; a fixed first header rejects compressed encodings.
        require(layer["size"] >= 1024 and layer["size"] % 512 == 0, "Expected an uncompressed tar layer")
        try:
            if any(layer["prefix"]):
                tar_header(layer["prefix"])
        except ValueError as exc:
            raise ValueError("Expected an uncompressed tar layer") from exc
        require("sha256:" + layer["sha256"] == diff_id, "Layer content digest differs from rootfs diff_id")
        if name.startswith("blobs/"):
            require(name == "blobs/sha256/" + layer["sha256"], "Layer blob filename digest differs")
    config_sha = members[config_name]["sha256"]
    require(config_name in {config_sha + ".json", "blobs/sha256/" + config_sha}, "Config filename digest differs")
    allowed = {"manifest.json", config_name, *layers}
    if "index.json" in members or "oci-layout" in members:
        require(document("oci-layout") == {"imageLayoutVersion": "1.0.0"}, "Invalid OCI layout")
        index = document("index.json")
        descriptors = index.get("manifests")
        require(index.get("schemaVersion") == 2 and isinstance(descriptors, list)
                and len(descriptors) == 1, "Exactly one OCI image required")
        descriptor = descriptors[0]
        require(isinstance(descriptor, dict) and descriptor.get("mediaType") in {
            "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"},
            "OCI descriptor is not an image manifest")
        platform = descriptor.get("platform")
        require(platform is None or platform == {"os": "linux", "architecture": "amd64"}, "OCI platform differs")
        for value in (index, descriptor):
            annotations = value.get("annotations", {})
            require(isinstance(annotations, dict), "Invalid OCI annotations")
            for key in ("io.containerd.image.name", "org.opencontainers.image.ref.name"):
                if key in annotations:
                    names = {tag, "docker.io/library/" + tag}
                    if key == "org.opencontainers.image.ref.name":
                        # BuildKit's OCI ref annotation may contain only the exact tag component.
                        # Docker RepoTags and containerd's image name still bind the repository.
                        names.add(tag.rsplit(":", 1)[-1])
                    require(annotations[key] in names, "OCI extra image tag")

        def descriptor_path(value):
            sha = value.get("digest", "")
            require(re.fullmatch("sha256:[a-f0-9]{64}", sha), "Invalid OCI digest")
            name = "blobs/sha256/" + sha[7:]
            require(name in members and members[name].get("sha256") == sha[7:]
                    and type(value.get("size")) is int and members[name]["size"] == value["size"],
                    "OCI content hash/size differs")
            return name

        image_path = descriptor_path(descriptor)
        image = document(image_path)
        require(image.get("schemaVersion") == 2 and descriptor_path(image.get("config", {})) == config_name
                and isinstance(image.get("layers"), list)
                and [descriptor_path(layer) for layer in image["layers"]] == layers,
                "OCI/Docker image manifests differ")
        require(all(layer.get("mediaType") in {"application/vnd.oci.image.layer.v1.tar",
            "application/vnd.oci.image.layer.nondistributable.v1.tar",
            "application/vnd.docker.image.rootfs.diff.tar"} for layer in image["layers"]),
            "Expected an uncompressed tar layer media type")
        allowed |= {"index.json", "oci-layout", image_path}
    directories = {str(parent) for name in allowed for parent in PurePosixPath(name).parents if str(parent) != "."}
    require(set(members) - allowed <= directories
            and all(members[name].get("directory") for name in set(members) - allowed)
            and not (set(layers) & {"manifest.json", config_name}), "Undeclared image/archive payload")
    return {"image_id": "sha256:" + config_sha, "source_fingerprint": fingerprint,
            "tag": tag, "config": runtime, "archive_sha256": expected_sha, "archive_size": expected_size}


def same_json(before, after):
    """JSON types are part of the contract: in particular False must not equal 0."""
    return json.dumps(before, sort_keys=True, allow_nan=False) == json.dumps(after, sort_keys=True, allow_nan=False)


def archive_inspect_config(config):
    """Add only absent Docker 25 inspect defaults; never rewrite archive bytes/values."""
    result = copy.deepcopy(config)
    for key, value in INSPECT_DEFAULTS.items():
        result.setdefault(key, value)
    return result


def remove_legacy_build_labels(before, after, service):
    """One-way Compose 5.0.1 build metadata removal, only on comparison copies.

    Kept identical in the standalone updater, which has no importer dependency.
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


def compatible(old, new, service, baseline):
    require(old["Id"] == baseline["image_id"] and old["Os"] == "linux" and old["Architecture"] == "amd64",
            "Old image identity/platform differs")
    before, after = copy.deepcopy(old.get("Config")), copy.deepcopy(new["config"])
    require(isinstance(before, dict) and isinstance(after, dict)
            and isinstance(before.get("Labels"), dict) and isinstance(after.get("Labels"), dict),
            "Image configuration missing")
    after = archive_inspect_config(after)
    require(before["Labels"].pop(LABEL, None) == baseline["source_fingerprint"]
            and after["Labels"].pop(LABEL, None) == new["source_fingerprint"],
            "Candidate image runtime defaults changed")
    remove_legacy_build_labels(before["Labels"], after["Labels"], service)
    require(same_json(before, after),
            "Candidate image runtime defaults changed")
    if service in {"api", "worker"}:
        require(isinstance(after.get("User"), str), "Python image is root or has invalid user")
        user = after["User"].partition(":")[0]
        require(user and user != "root" and not (re.fullmatch("[+-]?[0-9]+", user) and int(user) == 0),
                "Python image is root")


def image_inventory(r):
    identifiers = r.docker(["image", "ls", "--all", "--quiet", "--no-trunc"]).splitlines()
    require(all(re.fullmatch("sha256:[a-f0-9]{64}", value) for value in identifiers), "Invalid Docker image ID")
    result = {}
    for identifier in sorted(set(identifiers)):
        rows = unique_json(r.docker(["image", "inspect", identifier]))
        require(isinstance(rows, list) and len(rows) == 1 and rows[0]["Id"] == identifier, "Image inspect differs")
        result[identifier] = rows[0]
    return result


def validate_image_delta(before, after, imported):
    """Preserve every old ID, tag, digest and all image metadata except new tags."""
    require(set(after) == set(before) | {item["image_id"] for item in imported.values()},
            "Undeclared image addition/removal")
    for identifier, image in after.items():
        additions = {item["tag"] for item in imported.values() if item["image_id"] == identifier}
        tags = image.get("RepoTags") or []
        require(len(tags) == len(set(tags)), "Duplicate image tag")
        if identifier in before:
            old = copy.deepcopy(before[identifier])
            current = copy.deepcopy(image)
            require(set(current.pop("RepoTags", None) or []) == set(old.pop("RepoTags", None) or []) | additions
                    and same_json(current, old), "Old image/tag/digest metadata changed")
        else:
            require(set(tags) == additions and not image.get("RepoDigests"), "Unexpected new image references")
    for item in imported.values():
        image = after[item["image_id"]]
        require(image["Os"] == "linux" and image["Architecture"] == "amd64"
                and same_json(image.get("Config"), archive_inspect_config(item["config"]))
                and item["tag"] in (image.get("RepoTags") or []),
                "Imported image ID/platform/full configuration differs")


def validate_tags(images, candidates):
    tags = {tag: identifier for identifier, image in images.items() for tag in image.get("RepoTags") or []}
    for item in candidates.values():
        require(item["tag"] not in tags or tags[item["tag"]] == item["image_id"], "Candidate tag collision")
        if item["image_id"] in images:
            # Adding a tag to an old image may mutate its metadata. Only already
            # present exact tags can skip load; no retagging old images is allowed.
            require(item["tag"] in (images[item["image_id"]].get("RepoTags") or []),
                    "Candidate would retag an existing image")
            validate_image_delta(images, images, {item["tag"]: item})


def import_archives(r, plan, initial_images, snapshot, initial_state, directory, log):
    imported = {}
    for service in APPS:
        item = plan["images"][service]
        require(snapshot() == initial_state, "Protected resources changed before image load")
        current = image_inventory(r)
        validate_image_delta(initial_images, current, imported)
        existing = item["image_id"] in current and item["tag"] in (current[item["image_id"]].get("RepoTags") or [])
        if plan.get("update_mode") == "web-forward-fix-v1" and service != "web":
            require(existing, "Retained API/Worker image/tag disappeared; load is forbidden")
        if not existing:
            log("candidate_image_load_intent", service=service, image_id=item["image_id"], tag=item["tag"],
                archive_sha256=item["archive_sha256"])
            r.run(r.DOCKER + ["image", "load", "--input", directory + "/" + service + ".tar"], timeout=600)
        imported[service] = item
        validate_image_delta(initial_images, image_inventory(r), imported)
        require(snapshot() == initial_state, "Protected resources changed after image load")
        log("candidate_image_verified", service=service, image_id=item["image_id"], tag=item["tag"], loaded=not existing)
    return {service: {key: imported[service][key] for key in ("image_id", "source_fingerprint")} for service in APPS}


def helpers(payload, connection):
    require(digest(payload["remote_candidate_update_runner.py"]) == UPDATE_RUNNER_SHA, "Reviewed updater changed")
    import types
    update = types.ModuleType("eid_reviewed_update_helpers")
    exec(compile(payload["remote_candidate_update_runner.py"], "<reviewed-update>", "exec"), update.__dict__)
    r, retained, historical, normal = update.helpers(payload, connection)
    return update, r, retained, historical, normal


def recent_check(checked, sha):
    require(isinstance(checked, dict) and checked.get("kind") == "candidate_images_check_passed"
            and checked.get("bundle_sha256") == sha and checked.get("remote_writes") is False
            and isinstance(checked.get("snapshot"), dict)
            and type(checked.get("checked_at")) in {int, float}
            and 0 <= time.time() - checked["checked_at"] <= 300, "Recent exact successful CHECK required")


def run(payload, connection, mode, sha, checked, source):
    require(mode in {"check", "import"}, "Invalid image operation")
    update, r, retained, historical, normal = helpers(payload, connection)
    plan = unique_json(payload["import.json"])
    baseline = unique_json(payload["baseline.json"])
    require(re.fullmatch("[a-f0-9]{64}", plan["artifact_sha256"]), "Invalid source artifact identity")
    # Identity follows frozen source, not local bundle paths. Re-sealing the same
    # archives under a fresh directory cannot turn a partial attempt into a retry.
    attempt = plan["artifact_sha256"]
    log_name, directory_name = ".candidate-images-" + attempt + ".jsonl", ".candidate-images-" + attempt
    directory = r.ROOT_PATH + "/" + directory_name
    directory_fd = None
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(RuntimeError("Image import timed out")))
    signal.alarm(3600)
    os.umask(0o077)
    os.environ.clear()
    os.environ.update(r.CLEAN_ENV)
    os.chdir("/")
    try:
        require(os.geteuid() == 0 and r.run(["/usr/bin/hostname"]) == "seadee-develop"
                and connection.split()[2:3] == ["172.27.0.38"], "Wrong authenticated host")
        require(plan.get("update_mode", "expand") in {"expand", "web-forward-fix-v1"}, "Unknown image update mode")
        forward = plan.get("update_mode") == "web-forward-fix-v1"
        anchor = update.FORWARD_BASELINE_SHA if forward else BASELINE_SHA
        require(digest(payload["baseline.json"]) == anchor == plan["baseline_sha256"]
                and plan["owner"] == r.INPUTS["receipt"] and plan["old_release"] == r.RELEASE
                and set(plan["images"]) == set(APPS), "Import target/baseline differs")
        chain = update.forward_chain(payload, payload["baseline.json"]) if forward else None
        if chain:
            require(same_json(plan["old_candidate"], chain["current"] | {"update_mode": update.FORWARD_MODE})
                    and all(same_json(plan["images"][name], chain["images"][name]) for name in ("api", "worker")),
                    "Forward retained image/source differs")
        normal.validate_config(plan["config"])
        r.ROOT_FD = r.secure_fd(r.ROOT_PATH, directory=True)
        historical.protected_identity(r, retained)
        r.acquire_lock(r.LEGACY_ROOT + "/.deploy.lock")
        r.acquire_lock(r.ROOT_PATH + "/.deploy.lock")
        historical.protected_identity(r, retained)
        root_before = update.root_listing(r)
        require(log_name not in root_before and directory_name not in root_before, "Import attempt exists; no replay")
        images = image_inventory(r)
        validate_tags(images, plan["images"])
        if chain:
            for name in ("api", "worker"):
                item = plan["images"][name]
                require(item["image_id"] in images and item["tag"] in images[item["image_id"]].get("RepoTags", []),
                        "Retained API/Worker image/tag missing before import")
        for service in APPS:
            compatible(images[baseline["services"][service]["image_id"]], plan["images"][service], service,
                       baseline["services"][service])
        old = plan["old_candidate"]
        if chain:
            update.forward_identity(r, retained, chain)
        hashes = update.baseline_hashes(r, old) if chain else historical.compose_hashes(r)
        additions = {}
        archive_identities = {}

        def snapshot():
            historical.protected_identity(r, retained)
            require(update.root_listing(r) == root_before | additions, "Protected root inventory changed")
            if chain:
                update.forward_identity(r, retained, chain)
                resources, _ = update.protected_snapshot(r, retained, historical, normal, old,
                    baseline, {}, hashes, "stage", importing=True)
                resources["queues"] = update.broker_idle(r, baseline["services"]["rabbitmq"]["container_id"], old["compose"])
            else:
                state, found, namespaces = historical.container_inventory(r, normal, old,
                    {name: baseline["services"][name]["container_id"] for name in historical.ORDER}, hashes,
                    {name: {"image_id": baseline["services"][name]["image_id"]} for name in historical.ORDER})
                require(state["server"] == baseline["provenance"]["docker_server"], "Docker server changed")
                for name, record in found.items():
                    require(update.summary({"process": record["runtime_config"], "isolation": record["isolation_config"]})
                            == baseline["services"][name]["runtime_config_sha256"], "Baseline runtime changed")
                foreign = historical.foreign_inventory(r, state)
                foreign.pop("images")
                resources = {"containers": {name: update.canonical_record(record) for name, record in found.items()},
                             "namespaces": namespaces, "foreign": foreign}
            if directory_fd is not None:
                named = r.secure_fd(directory, directory=True)
                try:
                    require(r.metadata(os.fstat(named)) == additions[directory_name]
                            == r.metadata(os.fstat(directory_fd)), "Import directory inode changed")
                finally:
                    os.close(named)
                require(set(os.listdir(directory_fd)) == set(archive_identities), "Import directory inventory changed")
                for name, identity in archive_identities.items():
                    value = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    require(file_identity(value) == identity and stat.S_ISREG(value.st_mode)
                            and value.st_uid == value.st_gid == 0 and value.st_nlink == 1
                            and stat.S_IMODE(value.st_mode) == 0o600, "Uploaded archive changed")
            return resources

        initial = snapshot()
        check_state = {"resources": initial, "images": images, "root": root_before}
        if mode == "check":
            r.event("candidate_images_check_passed", bundle_sha256=sha, checked_at=time.time(),
                    snapshot=check_state, remote_writes=False)
            return 0
        require(isinstance(checked, dict)
                and update.summary(checked.get("snapshot")) == update.summary(check_state),
                "State changed after reviewed CHECK")
        # The first remote write follows every identity/lock/resource/config guard.
        # Recheck the exact event's remote timestamp here: SSH and guards can be slow.
        recent_check(checked, sha)
        r.EVIDENCE_FD = os.open(log_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600, dir_fd=r.ROOT_FD)
        os.fsync(r.ROOT_FD)
        additions[log_name] = r.metadata(os.fstat(r.EVIDENCE_FD))

        def log(kind, **fields):
            named = r.secure_fd(r.ROOT_PATH + "/" + log_name)
            try:
                require(r.metadata(os.fstat(named)) == additions[log_name] == r.metadata(os.fstat(r.EVIDENCE_FD))
                        and os.fstat(named).st_nlink == 1, "Import journal inode changed")
            finally:
                os.close(named)
            r.event(kind, bundle_sha256=sha, **fields)

        log("candidate_images_import_intent", initial_sha256=update.summary(check_state))
        require(snapshot() == initial, "Resources changed before upload")
        os.mkdir(directory_name, 0o700, dir_fd=r.ROOT_FD)
        os.fsync(r.ROOT_FD)
        directory_fd = r.secure_fd(directory, directory=True)
        additions[directory_name] = r.metadata(os.fstat(directory_fd))
        require(additions[directory_name]["uid"] == additions[directory_name]["gid"] == 0
                and additions[directory_name]["mode"] == 0o700, "Import directory is not root controlled")
        for service in APPS:
            item = plan["images"][service]
            name = service + ".tar"
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as output:
                require(consume(source, item["archive_size"], output) == item["archive_sha256"], "Upload digest differs")
                output.flush()
                os.fsync(output.fileno())
            os.fsync(directory_fd)
            descriptor = r.secure_fd(directory + "/" + name)
            with os.fdopen(descriptor, "rb") as stream:
                identity = file_identity(os.fstat(stream.fileno()))
                require(archive_info(stream, item["archive_sha256"], item["archive_size"], item["tag"],
                                     item["source_fingerprint"]) == item, "Uploaded image metadata differs")
                require(file_identity(os.fstat(stream.fileno())) == identity, "Upload changed during validation")
                archive_identities[name] = identity
            log("candidate_archive_verified", service=service, archive_sha256=item["archive_sha256"])
        require(not source.read(1), "Unexpected trailing upload data")
        require(snapshot() == initial, "Resources changed during upload")
        result = import_archives(r, plan, images, snapshot, initial, directory, log)
        log("candidate_images_import_complete", images=result, application_acceptance=False,
            runtime_manifest_recorded=False, automatic_cleanup=False)
        return 0
    except BaseException as exc:
        r.event("candidate_images_stopped", reason=str(exc), error_type=type(exc).__name__,
                partial_state_preserved=True, automatic_retry=False, automatic_cleanup=False)
        return 1
    finally:
        signal.alarm(0)
        if directory_fd is not None:
            os.close(directory_fd)
        for descriptor, _, _ in reversed(r.LOCKS):
            r.fcntl.flock(descriptor, r.fcntl.LOCK_UN)
            os.close(descriptor)
        if r.EVIDENCE_FD is not None:
            os.close(r.EVIDENCE_FD)
        if r.ROOT_FD is not None:
            os.close(r.ROOT_FD)


if __name__ == "__main__":
    inputs = globals()
    raise SystemExit(run(*(inputs[name] for name in ("PAYLOAD", "CONNECTION", "MODE", "BUNDLE_SHA", "CHECKED")),
                         sys.stdin.buffer))
