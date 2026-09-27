"""Freeze, check, stage and apply a reviewed EID application candidate.

Freeze reads an already frozen source artifact, never the changing application tree.
Build/import and guarded online Alembic remain separate, explicit operations.
"""

from __future__ import annotations

import argparse
import ast
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import time
import types

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import remote_candidate_update_runner as runner

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / ".local/remote/app-start-20260917"
HISTORICAL_HASHES = {
    "app_start.py": "7c8e35e36303d31c0bd81f3179c68c31708a5c4e5886217eae231bf9945b040d",
    "app_start_runner.py": "59a4ec13903a1b088e2a692fdd4205cc9dc9f5b8b898ac832a545fb1e453374f",
}
APPS = ("api", "worker", "web")
PROTECTED = ("postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx")
OWNER = "05a8f0d646f040d5a8bdcf097864d155"
OLD_RELEASE = "/opt/eid/release-20260917-002"
PURPOSE = "eid-reviewed-application-update-v1"
FORWARD_HISTORY = ROOT / ".local/story-1-3-candidate-20260918-002"
FORWARD_SOURCES = {"edw-web/src/app/App.tsx", "edw-web/src/features/workspace/discovery.css"}
REVIEWED_OPS = {"scripts/remote_candidate_images.py", "scripts/remote_candidate_images_runner.py",
                "scripts/remote_candidate_update.py", "scripts/remote_candidate_update_runner.py"}


def forward_inputs(baseline_raw):
    payload = {"forward/" + name: checked_file(FORWARD_HISTORY / name, sha)
               for name, sha in runner.FORWARD_CHAIN_HASHES.items()}
    return payload, runner.forward_chain(payload, baseline_raw)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name
            and "\0" not in name and not PurePosixPath(name).is_absolute()
            and all(part not in {"", ".", ".."} for part in name.split("/")),
            "Unsafe artifact member")
    return name


def read_file(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        require(not item.is_symlink() and not item.is_junction(), "Linked local input")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_size <= 64 * 1024 * 1024, "Unsafe local input")
        raw = stream.read(64 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
        require((before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_ino, after.st_size, after.st_mtime_ns)
                and len(raw) == before.st_size, "Input changed during read")
    return raw


def checked_file(path, sha):
    require(isinstance(sha, str) and re.fullmatch("[a-f0-9]{64}", sha), "Invalid SHA256")
    raw = read_file(path)
    require(digest(raw) == sha, "Input hash differs")
    return raw


def module(name, raw, path="<frozen-helper>"):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value


def archive_files(raw):
    require(len(raw) <= 32 * 1024 * 1024, "Oversized artifact")
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        total = 0
        for member in archive:
            name = safe_name(member.name)
            total += member.size
            require(member.isfile() and not member.issparse() and not member.linkname
                    and not member.pax_headers and name not in result
                    and 0 <= member.size <= 16 * 1024 * 1024
                    and total <= 128 * 1024 * 1024 and len(result) < 4096,
                    "Unsafe, duplicate or oversized archive member")
            result[name] = archive.extractfile(member).read()
    require(result, "Empty artifact")
    return result


def migration_guard(source):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name == "verify_migration_connection"]
    require(len(nodes) == 1, "Existing migration connection guard missing")
    return (ast.get_source_segment(source, nodes[0]) + "\n").encode()


def validate_baseline(data, config):
    require(data.get("schema_version") == 3
            and data.get("source_fingerprint_algorithm") == "sha256"
            and set(data.get("services", {})) == set(APPS + PROTECTED), "Schema3 baseline required")
    provenance = data.get("provenance", {})
    require(provenance.get("environment") == "seadee-develop"
            and provenance.get("ssh") == config["ssh"]
            and provenance.get("remote_root") == "/opt/eid"
            and provenance.get("compose_project") == "eid-remote-dev"
            and provenance.get("owner") == OWNER, "Foreign baseline")
    require(len({item["container_id"] for item in data["services"].values()}) == 9,
            "Duplicate baseline container")
    for name, item in data["services"].items():
        require(re.fullmatch("[a-f0-9]{64}", item["container_id"])
                and re.fullmatch("sha256:[a-f0-9]{64}", item["image_id"])
                and re.fullmatch("[a-f0-9]{64}", item["runtime_config_sha256"]), "Invalid baseline ID")
        if name in APPS:
            require(re.fullmatch("sha256:[a-f0-9]{64}", item["source_fingerprint"]),
                    "Full baseline fingerprint required")


def validate_candidate(files, remote, config, baseline, images, revisions, old_files, *, update_mode="expand"):
    """Accept only the existing package contract and unchanged protected configuration."""
    generated_names = {"deployment/remote.compose.yaml", "deployment/remote-package.json",
                       "deployment/environments/seadee-develop.yaml", ".eid-remote-owner.json"}
    source = {name: raw for name, raw in files.items() if name not in generated_names}
    require(all(remote.allowed_source(name) for name in source), "Unapproved source artifact file")
    require(remote.FIXED_FILES <= source.keys(), "Incomplete source artifact")
    expected = remote.generated_files(config, OWNER, source)
    require(set(files) == set(source) | set(expected)
            and all(files[name] == value for name, value in expected.items()),
            "Package manifest, owner, configuration or generated Compose differs")
    compose = yaml.safe_load(files["deployment/remote.compose.yaml"])
    old_compose = yaml.safe_load(old_files["deployment/remote.compose.yaml"])
    require(digest(old_files["deployment/remote.compose.yaml"])
            == baseline["provenance"]["compose_sha256"], "Old Compose baseline differs")
    require(set(compose) == set(old_compose)
            and set(compose["services"]) == set(old_compose["services"]) == set(APPS + PROTECTED),
            "Compose inventory changed")
    for name in PROTECTED:
        require(compose["services"][name] == old_compose["services"][name],
                "Protected service definition changed: " + name)
    for name in ("volumes", "networks", "name"):
        require(compose[name] == old_compose[name], "Protected Compose resource changed")
    for name in ("deployment/nginx/default.conf", "deployment/postgres/001-isolated-database.sql",
                 "deployment/keycloak/eid-local-realm.json", "deployment/seaweedfs/s3.json",
                 "deployment/images.lock.json", "deployment/python.Dockerfile", "deployment/web.Dockerfile"):
        require(files[name] == old_files[name], "Protected runtime input changed: " + name)
    require(set(images) == set(APPS), "Exactly three candidate images required")
    require(update_mode in {"expand", runner.FORWARD_MODE}, "Unknown update mode")
    if update_mode == runner.FORWARD_MODE:
        require(revisions == ("0007_workspace_discovery", "0007_workspace_discovery"),
                "Forward fix must not change schema")
        old_source = {name: raw for name, raw in old_files.items() if name not in generated_names}
        require(set(source) == set(old_source), "Forward source inventory changed")
        require(all(raw == old_source[name] for name, raw in source.items()
                    if name not in FORWARD_SOURCES | REVIEWED_OPS),
                "Forward source changed outside the two Web files and reviewed ops")
        require(all(source[name] == read_file(ROOT / name) for name in REVIEWED_OPS),
                "Forward ops source differs from reviewed tools")
        expected_compose = copy.deepcopy(old_compose)
        for name in APPS:
            item = images[name]
            fingerprint = remote.image_source_fingerprint(name, source)
            require(set(item) == {"image_id", "source_fingerprint"}
                    and re.fullmatch("sha256:[a-f0-9]{64}", item["image_id"])
                    and item["source_fingerprint"] == fingerprint, "Forward image/full fingerprint differs")
            if name != "web":
                require(item == {key: baseline["services"][name][key]
                                 for key in ("image_id", "source_fingerprint")}, "API/Worker must reuse exact images")
            else:
                require(fingerprint != baseline["services"][name]["source_fingerprint"], "New Web source required")
                expected_compose["services"][name]["image"] = "eid-remote-dev-web:" + fingerprint[7:23]
                expected_compose["services"][name]["build"]["args"]["EID_SOURCE_FINGERPRINT"] = fingerprint
        require(runner.same_json(compose, expected_compose), "Forward Compose may change only Web image/fingerprint")
        return compose, migration_guard(source["migrations/env.py"].decode())
    # Build the only accepted configuration from the pinned old definitions.
    # Comparing the whole object also rejects future/unknown execution options,
    # lifecycle hooks and host access before any remote Compose invocation.
    expected_compose = copy.deepcopy(old_compose)
    for name in APPS:
        item = images[name]
        fingerprint = remote.image_source_fingerprint(name, source)
        require(set(item) == {"image_id", "source_fingerprint"}
                and re.fullmatch("sha256:[a-f0-9]{64}", item["image_id"])
                and item["source_fingerprint"] == fingerprint, "Candidate image/full fingerprint differs")
        definition = expected_compose["services"][name]
        require(definition["image"] == baseline["services"][name]["image_ref"]
                and definition["build"]["args"]["EID_SOURCE_FINGERPRINT"]
                == baseline["services"][name]["source_fingerprint"], "Old application fingerprint differs")
        definition["image"] = "eid-remote-dev-" + name + ":" + fingerprint.removeprefix("sha256:")[:16]
        definition["build"]["args"]["EID_SOURCE_FINGERPRINT"] = fingerprint
    for name in ("api", "worker"):
        environment = expected_compose["services"][name]["environment"]
        require(environment.get("EID_REQUIRED_SCHEMA_REVISION") == revisions[0], "Old application revision differs")
        environment["EID_REQUIRED_SCHEMA_REVISION"] = revisions[1]
    expected_compose["services"]["api"]["environment"]["EID_DISCOVERY_POLICY_ENVIRONMENT"] = "isolated_development"
    require(expected_compose["x-runtime-environment"]["EID_REQUIRED_SCHEMA_REVISION"] == revisions[0],
            "Old shared revision differs")
    expected_compose["x-runtime-environment"]["EID_REQUIRED_SCHEMA_REVISION"] = revisions[1]
    require(compose == expected_compose, "Application Compose contract changed outside reviewed expansion")
    # This updater is deliberately bounded to the current inspect-only worker.
    # A task-engine change requires its own drain protocol, not a relaxed check.
    old_worker = {name: raw for name, raw in old_files.items() if name.startswith("edw-worker/src/")}
    new_worker = {name: raw for name, raw in source.items() if name.startswith("edw-worker/src/")}
    require(set(old_worker) == set(new_worker) and all(
        new_worker[name].replace(revisions[1].encode(), revisions[0].encode()) == raw
        for name, raw in old_worker.items()), "Worker task implementation changed; new drain review required")
    guard = migration_guard(source["migrations/env.py"].decode())
    require(guard == migration_guard(old_files["migrations/env.py"].decode()),
            "Migration identity guard changed; independent review required")
    old_versions = {name: raw for name, raw in old_files.items() if name.startswith("migrations/versions/")}
    require(all(source.get(name) == raw for name, raw in old_versions.items()),
            "Previously applied migration changed")
    new_versions = {name: raw for name, raw in source.items()
                    if name.startswith("migrations/versions/") and name not in old_versions}
    require(len(new_versions) == 1, "Exactly one reviewed expansion migration is required")
    revision_fields = {}
    for node in ast.parse(next(iter(new_versions.values()))).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    require(target.id not in revision_fields, "Duplicate migration revision declaration")
                    revision_fields[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in {"revision", "down_revision"}:
                require(node.target.id not in revision_fields, "Duplicate migration revision declaration")
                revision_fields[node.target.id] = ast.literal_eval(node.value)
    require(revision_fields == {"revision": revisions[1], "down_revision": revisions[0]},
            "Migration revision chain differs")
    return compose, guard


def freeze(args):
    artifact = checked_file(args.artifact, args.artifact_sha256)
    baseline_raw = checked_file(args.baseline, args.baseline_sha256)
    images_raw = checked_file(args.images, args.images_sha256)
    require(re.fullmatch(r"release-[0-9]{8}-[a-z0-9][a-z0-9-]{0,40}", args.release)
            and "/opt/eid/" + args.release != OLD_RELEASE, "Unsafe or old release name")
    revisions = (args.from_revision, args.to_revision)
    update_mode = getattr(args, "update_mode", "expand")
    forward = update_mode == runner.FORWARD_MODE
    require(update_mode in {"expand", runner.FORWARD_MODE} and revisions == (
        "0007_workspace_discovery" if forward else "0006_api_write_only", "0007_workspace_discovery"),
            "Only the reviewed expand-only Story 1.3 revision transition is supported")
    launcher_raw = checked_file(HISTORY / "app_start.py", HISTORICAL_HASHES["app_start.py"])
    historical = module("eid_pinned_start_helpers", launcher_raw, HISTORY / "app_start.py")
    completion = historical.completion_payload()
    old_files = archive_files(completion["candidate.tar.gz"])
    forward_payload = {}
    if forward:
        forward_payload, chain = forward_inputs(baseline_raw)
        old_files = chain["files"]
        require("/opt/eid/" + args.release != runner.FORWARD_RELEASE, "Current release cannot be reused")
    support_raw = read_file(ROOT / "scripts/remote_environment.py")
    if forward:
        require(support_raw == old_files["scripts/remote_environment.py"], "Forward packaging/guard helper changed")
    remote = module("eid_candidate_packaging", support_raw, ROOT / "scripts/remote_environment.py")
    config = remote.load_config()
    require(remote.read_owner(config) == remote.owner_receipt(config, OWNER), "Owner differs")
    baseline = json.loads(baseline_raw)
    validate_baseline(baseline, config)
    files = archive_files(artifact)
    images = json.loads(images_raw)
    compose, guard = validate_candidate(files, remote, config, baseline, images, revisions, old_files,
                                       update_mode=update_mode)
    candidate = {"config": config, "owner": remote.owner_receipt(config, OWNER),
                 "old_release": OLD_RELEASE, "release": "/opt/eid/" + args.release,
                 "from_revision": revisions[0], "to_revision": revisions[1],
                 "artifact_sha256": digest(artifact), "baseline_sha256": digest(baseline_raw),
                 "images": images, "compose": compose,
                 "files": {name: digest(raw) for name, raw in files.items()}}
    if forward:
        candidate["update_mode"] = update_mode
    payload = {"candidate.json": encoded(candidate), "baseline.json": baseline_raw,
               "candidate.tar.gz": artifact, "migration_guard.py": guard,
               "normal_support.py": historical.ordinary_support(support_raw.decode()),
               "app_start_runner.py": checked_file(HISTORY / "app_start_runner.py",
                                                     HISTORICAL_HASHES["app_start_runner.py"]),
               "remote_candidate_update_runner.py": read_file(ROOT / "scripts/remote_candidate_update_runner.py"),
               **{"completion/" + name: raw for name, raw in completion.items()}, **forward_payload}
    manifest = {"schema_version": 1, "purpose": PURPOSE,
                "launcher_sha256": digest(read_file(Path(__file__))),
                "files": {name: digest(raw) for name, raw in payload.items()}}
    output = args.output.absolute()
    require(output.parent.is_dir() and not output.exists(), "Use an existing parent and new bundle directory")
    for parent in output.parents:
        require(not parent.is_symlink() and not parent.is_junction(), "Linked bundle parent")
    output.mkdir()
    for name, raw in {**payload, "bundle.json": encoded(manifest)}.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    return digest(encoded(manifest))


def load_bundle(path, sha):
    manifest = json.loads(checked_file(path / "bundle.json", sha))
    require(manifest.get("schema_version") == 1 and manifest.get("purpose") == PURPOSE
            and manifest.get("launcher_sha256") == digest(read_file(Path(__file__))),
            "Bundle schema/purpose/launcher differs")
    payload = {safe_name(name): checked_file(path / safe_name(name), value)
               for name, value in manifest["files"].items()}
    require(digest(payload["app_start_runner.py"]) == HISTORICAL_HASHES["app_start_runner.py"],
            "Historical helper changed")
    require(payload["remote_candidate_update_runner.py"]
            == read_file(ROOT / "scripts/remote_candidate_update_runner.py"), "Runner changed after freeze")
    candidate = json.loads(payload["candidate.json"])
    require(digest(payload["candidate.tar.gz"]) == candidate["artifact_sha256"]
            and digest(payload["baseline.json"]) == candidate["baseline_sha256"], "Candidate inputs changed")
    if runner.forward_mode(candidate):
        runner.forward_chain(payload, payload["baseline.json"])
    return payload


def migration_receipt(raw, candidate, bundle_sha):
    data = json.loads(raw)
    if runner.forward_mode(candidate):
        try:
            return runner.schema_receipt(data, candidate, bundle_sha)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
    required = {"schema_version": 1, "kind": "eid-remote-candidate-migration-success",
                "environment": "seadee-develop", "host": "172.27.0.38", "root": "/opt/eid",
                "compose_project": "eid-remote-dev", "database": "eid_local_dev",
                "marker": "eid-local-dev-v1", "owner_nonce": OWNER,
                "bundle_sha256": bundle_sha, "artifact_sha256": candidate["artifact_sha256"],
                "baseline_sha256": candidate["baseline_sha256"],
                "from_revision": candidate["from_revision"], "revision": candidate["to_revision"],
                "migration_exit_code": 0, "live_revision_exit_code": 0,
                "database_identity_verified": True, "expand_only_reviewed": True}
    require(all(type(data.get(key)) is type(value) and data[key] == value
                for key, value in required.items()), "Migration receipt target/result differs")
    for key in ("migration_evidence_sha256", "live_revision_evidence_sha256"):
        require(isinstance(data.get(key), str) and re.fullmatch("[a-f0-9]{64}", data[key]),
                "Migration evidence digest missing")
    require(type(data.get("verified_at")) in {int, float}
            and 0 <= time.time() - data["verified_at"] <= 900, "Migration receipt is not recent")
    return data


def program_bytes(payload, sha, mode, phase, checked, migration):
    values = {name: base64.b64encode(raw).decode() for name, raw in payload.items()}
    return ("import base64,sys\nPAYLOAD={k:base64.b64decode(v) for k,v in " + repr(values)
            + ".items()}\nBUNDLE_SHA=" + repr(sha) + "\nMODE=" + repr(mode)
            + "\nPHASE=" + repr(phase) + "\nCHECKED=" + repr(checked)
            + "\nMIGRATION=" + repr(migration) + "\nCONNECTION=sys.argv[1]\n"
            + 'exec(compile(PAYLOAD["remote_candidate_update_runner.py"],"<eid-candidate-update>","exec"))\n').encode()


def invoke(program):
    boot = "import sys;exec(compile(sys.stdin.buffer.read(" + str(len(program)) + '),"<eid-update>","exec"))'
    command = "sudo -n python3 -I -u -c " + shlex.quote(boot) + ' "$SSH_CONNECTION"'
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "PreferredAuthentications=publickey", "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no", "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no",
        "-o", "Hostname=172.27.0.38", "-o", "User=seadee", "-o", "Port=22", "-o", "ProxyJump=jump-local",
        "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
        "-T", "seadee-develop", command], input=program, capture_output=True, timeout=1260)


def checked_snapshot(raw, payload, sha, phase, migration):
    evidence = json.loads(raw)
    require(isinstance(evidence, dict) and isinstance(evidence.get("events"), list),
            "A recent exact successful phase CHECK is required")
    events = [event for event in evidence["events"]
              if isinstance(event, dict) and event.get("kind") == "candidate_check_passed"]
    require(evidence.get("mode") == "check" and evidence.get("phase") == phase
            and type(evidence.get("exit_code")) is int and evidence["exit_code"] == 0
            and evidence.get("bundle_sha256") == sha
            and evidence.get("program_sha256") == digest(program_bytes(payload, sha, "check", phase, None, migration))
            and len(events) == 1,
            "A recent exact successful phase CHECK is required")
    try:
        runner.recent_check(events[0], sha, phase)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    return events[0]


def launch(args):
    payload = load_bundle(args.bundle, args.bundle_sha256)
    phase = args.phase if args.mode == "check" else args.mode
    migration = None
    if phase == "apply-apps":
        require(args.migration_receipt and args.migration_sha256, "Migration receipt required")
        migration = migration_receipt(checked_file(args.migration_receipt, args.migration_sha256),
                                      json.loads(payload["candidate.json"]), args.bundle_sha256)
    checked = None
    if args.mode != "check":
        require(args.reviewed_sha256 == args.bundle_sha256 and args.checked_output and args.checked_sha256,
                "Reviewed digest and pinned phase CHECK required")
        checked = checked_snapshot(checked_file(args.checked_output, args.checked_sha256), payload,
                                   args.bundle_sha256, phase, migration)
    program = program_bytes(payload, args.bundle_sha256, args.mode, phase, checked, migration)
    # Reserve local evidence before contacting the host. Unknown outcomes are never retried.
    with args.output.open("x", encoding="utf-8") as stream:
        try:
            result = invoke(program)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", exc.stderr or b"", 124
        except OSError:
            stdout, stderr, code = b"", b"local invocation failed", 125
        events = []
        for line in stdout.decode("utf-8", "replace").splitlines():
            try:
                event = json.loads(line)
                if isinstance(event, dict) and isinstance(event.get("kind"), str):
                    events.append(event)
            except json.JSONDecodeError:
                continue
        wanted = "candidate_check_passed" if args.mode == "check" else "candidate_" + phase + "_complete"
        if code == 0 and sum(event["kind"] == wanted for event in events) != 1:
            code = 1
        json.dump({"mode": args.mode, "phase": phase, "bundle_sha256": args.bundle_sha256,
                   "program_sha256": digest(program), "exit_code": code, "events": events,
                   "outcome_unknown": code != 0, "automatic_retry": False,
                   "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)}, stream, indent=2)
        stream.write("\n")
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    freezer = commands.add_parser("freeze", help="freeze explicit artifacts locally; no SSH")
    for name in ("artifact", "baseline", "images"):
        freezer.add_argument("--" + name, type=Path, required=True)
        freezer.add_argument("--" + name + "-sha256", required=True)
    for name in ("release", "from-revision", "to-revision"):
        freezer.add_argument("--" + name, required=True)
    freezer.add_argument("--output", type=Path, required=True)
    freezer.add_argument("--update-mode", choices=("expand", runner.FORWARD_MODE), default="expand")
    for mode in ("check", "stage", "apply-apps"):
        action = commands.add_parser(mode)
        action.add_argument("--bundle", type=Path, required=True)
        action.add_argument("--bundle-sha256", required=True)
        action.add_argument("--output", type=Path, required=True)
        action.add_argument("--migration-receipt", type=Path)
        action.add_argument("--migration-sha256")
        if mode == "check":
            action.add_argument("--phase", choices=("stage", "apply-apps"), required=True)
        else:
            action.add_argument("--reviewed-sha256", required=True)
            action.add_argument("--checked-output", type=Path, required=True)
            action.add_argument("--checked-sha256", required=True)
    args = parser.parse_args()
    if args.mode == "freeze":
        print(json.dumps({"bundle_sha256": freeze(args), "remote_writes": False}))
        return 0
    return launch(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, tarfile.TarError) as exc:
        print(json.dumps({"kind": "candidate_launcher_stopped", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
