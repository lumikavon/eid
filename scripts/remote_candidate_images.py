"""Prepare reviewed build argv, seal three Docker archives, CHECK and import once.

Builds are deliberately external, explicit operations. Preparation reads only an
already frozen source package. No live workspace packaging occurs here.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import threading

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import remote_candidate_images_runner as runner
from scripts import remote_candidate_update as update

ROOT = Path(__file__).resolve().parents[1]
UPDATE_SHA = "90db6be948db01237eed7b6b76a7f25561dd3deda562a8cab016ebb9e39f9423"
GENERATED = {"deployment/remote.compose.yaml", "deployment/remote-package.json",
             "deployment/environments/seadee-develop.yaml", ".eid-remote-owner.json"}
PURPOSE = "eid-three-candidate-images-v1"
APPS = runner.APPS
require = runner.require
digest = runner.digest


def plain_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink() and not part.is_junction(), "Linked local path")
    return path


def write_new(path, raw):
    path = plain_path(path)
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def new_directory(path):
    path = plain_path(path)
    require(path.parent.is_dir() and not path.exists(), "Existing parent and fresh directory required")
    path.mkdir(mode=0o700)
    return path


def pinned_helpers():
    update.checked_file(ROOT / "scripts/remote_candidate_update.py", UPDATE_SHA)
    update.checked_file(ROOT / "scripts/remote_candidate_update_runner.py", runner.UPDATE_RUNNER_SHA)
    historical = update.module("eid_image_historical_helpers", update.checked_file(
        update.HISTORY / "app_start.py", update.HISTORICAL_HASHES["app_start.py"]), update.HISTORY / "app_start.py")
    completion = historical.completion_payload()
    support = update.read_file(ROOT / "scripts/remote_environment.py")
    remote = update.module("eid_image_packaging_helpers", support, ROOT / "scripts/remote_environment.py")
    return historical, completion, support, remote


def source_contract(raw, baseline_raw, update_mode="expand"):
    historical, completion, support, remote = pinned_helpers()
    config = remote.load_config()
    require(remote.read_owner(config) == remote.owner_receipt(config, update.OWNER), "Owner differs")
    forward = update_mode == update.runner.FORWARD_MODE
    require(update_mode in {"expand", update.runner.FORWARD_MODE}
            and digest(baseline_raw) == (update.runner.FORWARD_BASELINE_SHA if forward else runner.BASELINE_SHA),
            "Only the verified stable baseline is accepted")
    baseline = runner.unique_json(baseline_raw)
    update.validate_baseline(baseline, config)
    files = update.archive_files(raw)
    source = {name: value for name, value in files.items() if name not in GENERATED}
    images = {name: {"image_id": "sha256:" + "0" * 64,
                     "source_fingerprint": remote.image_source_fingerprint(name, source)} for name in APPS}
    old_files = update.archive_files(completion["candidate.tar.gz"])
    if forward:
        _, chain = update.forward_inputs(baseline_raw)
        old_files = chain["files"]
        require(support == old_files["scripts/remote_environment.py"], "Forward packaging/guard helper changed")
        for name in ("api", "worker"):
            images[name] = {key: baseline["services"][name][key] for key in ("image_id", "source_fingerprint")}
    update.validate_candidate(files, remote, config, baseline, images,
        ("0007_workspace_discovery" if forward else "0006_api_write_only", "0007_workspace_discovery"),
        old_files, update_mode=update_mode)
    return files, images, config, baseline, old_files, historical, completion, support


def build_argv(service, fingerprint, context, output):
    require(service in APPS and re.fullmatch("sha256:[a-f0-9]{64}", fingerprint), "Invalid build identity")
    context, output = plain_path(context), plain_path(output)
    # Buildx CSV output cannot safely represent an unescaped comma in dest.
    require(not any(char in str(output) for char in (",", "\n", "\r", '"')), "Unsupported build output path")
    dockerfile = "deployment/web.Dockerfile" if service == "web" else "deployment/python.Dockerfile"
    return ["docker", "buildx", "build", "--platform", "linux/amd64", "--provenance=false", "--sbom=false",
            "--file", str(context / dockerfile), "--build-arg", "EID_SOURCE_FINGERPRINT=" + fingerprint,
            "--tag", "eid-remote-dev-" + service + ":" + fingerprint[7:23],
            "--metadata-file", str(output / (service + ".metadata.json")),
            "--output", "type=docker,compression=uncompressed,force-compression=true,dest="
            + str(output / (service + ".tar")), str(context)]


def validate_local_names(files):
    folded = set()
    for name in files:
        update.safe_name(name)
        require(name.casefold() not in folded, "Case-colliding source paths")
        folded.add(name.casefold())
        for part in name.split("/"):
            require(not part.endswith((".", " ")) and not re.fullmatch(
                r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", part)
                and not any(char in part for char in '<>"|?*'), "Unsafe portable source path")
    require(all(str(parent).replace("\\", "/").casefold() not in folded
                for name in files for parent in Path(name).parents if str(parent) != "."),
            "Source file/directory collision")


def extract_new(files, context):
    validate_local_names(files)
    context = new_directory(context)
    for name, raw in sorted(files.items()):
        target = plain_path(context / name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_new(target, raw)


def verify_context(context, hashes):
    context = plain_path(context)
    found = {}
    directories = {str(parent).replace("\\", "/") for name in hashes
                   for parent in Path(name).parents if str(parent) != "."}
    for directory, children, names in os.walk(context, followlinks=False):
        for child in children:
            path = plain_path(Path(directory) / child)
            require(path.relative_to(context).as_posix() in directories, "Undeclared build context directory")
        for name in names:
            path = plain_path(Path(directory) / name)
            relative = path.relative_to(context).as_posix()
            require(relative in hashes, "Undeclared build context file")
            found[relative] = digest(update.read_file(path))
    require(found == hashes, "Frozen build context differs")


def prepare(args):
    artifact = update.checked_file(args.artifact, args.artifact_sha256)
    baseline = update.checked_file(args.baseline, args.baseline_sha256)
    mode = getattr(args, "update_mode", "expand")
    files, images, *_ = source_contract(artifact, baseline, mode)
    validate_local_names(files)
    output = new_directory(args.output)
    context = output / "context"
    extract_new(files, context)
    archives = new_directory(output / "archives")
    services = ("web",) if mode == update.runner.FORWARD_MODE else APPS
    commands = {name: build_argv(name, images[name]["source_fingerprint"], context, archives) for name in services}
    plan = {"schema_version": 1, "purpose": PURPOSE, "artifact_sha256": args.artifact_sha256,
            "baseline_sha256": args.baseline_sha256, "files": {name: digest(raw) for name, raw in files.items()},
            "images": images, "build_argv": commands, "output": str(output),
            "launcher_sha256": digest(update.read_file(Path(__file__))),
            "runner_sha256": digest(update.read_file(ROOT / "scripts/remote_candidate_images_runner.py"))}
    if mode == update.runner.FORWARD_MODE:
        plan.update(update_mode=mode, reused_archives=reused_archives(baseline))
    write_new(output / "source.tar.gz", artifact)
    write_new(output / "baseline.json", baseline)
    raw = update.encoded(plan)
    write_new(output / "prepare.json", raw)
    return {"prepare_sha256": digest(raw), "build_argv": commands, "builds_executed": False, "remote_writes": False}


def reused_archives(baseline_raw):
    _, chain = update.forward_inputs(baseline_raw)
    return {name: {"path": str(plain_path(update.FORWARD_HISTORY / "prepared-001/archives" / (name + ".tar"))),
                   "metadata": chain["images"][name]} for name in ("api", "worker")}


def load_prepared(directory, sha):
    plan = runner.unique_json(update.checked_file(directory / "prepare.json", sha))
    require(plan.get("schema_version") == 1 and plan.get("purpose") == PURPOSE
            and plan["output"] == str(plain_path(directory))
            and plan["launcher_sha256"] == digest(update.read_file(Path(__file__)))
            and plan["runner_sha256"] == digest(update.read_file(ROOT / "scripts/remote_candidate_images_runner.py")),
            "Prepared plan/code differs")
    artifact = update.checked_file(directory / "source.tar.gz", plan["artifact_sha256"])
    baseline_raw = update.checked_file(directory / "baseline.json", plan["baseline_sha256"])
    mode = plan.get("update_mode", "expand")
    contract = source_contract(artifact, baseline_raw, mode)
    services = ("web",) if mode == update.runner.FORWARD_MODE else APPS
    if mode == update.runner.FORWARD_MODE:
        require(plan.get("reused_archives") == reused_archives(baseline_raw), "Reused archive provenance differs")
    require(plan["files"] == {name: digest(raw) for name, raw in contract[0].items()}
            and plan["images"] == contract[1]
            and plan["build_argv"] == {name: build_argv(name, contract[1][name]["source_fingerprint"],
                directory / "context", directory / "archives") for name in services}, "Prepared build contract differs")
    verify_context(directory / "context", plan["files"])
    return plan, baseline_raw, contract


def open_archive(path):
    stream = plain_path(path).open("rb")
    info = os.fstat(stream.fileno())
    if not (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= runner.MAX_ARCHIVE):
        stream.close()
        raise ValueError("Unsafe or oversized image archive")
    return stream


def seal(args):
    prepared, baseline_raw, contract = load_prepared(args.prepared, args.prepare_sha256)
    files, fingerprints, config, baseline, old_files, historical, completion, support = contract
    images, archive_paths = {}, {}
    forward = prepared.get("update_mode") == update.runner.FORWARD_MODE
    for service in APPS:
        reused = prepared["reused_archives"][service] if forward and service != "web" else None
        path = Path(reused["path"]) if reused else args.prepared / "archives" / (service + ".tar")
        fp = fingerprints[service]["source_fingerprint"]
        with open_archive(path) as stream:
            before = runner.file_identity(os.fstat(stream.fileno()))
            images[service] = runner.archive_info(stream, getattr(args, service + "_sha256"), before[2],
                                                 "eid-remote-dev-" + service + ":" + fp[7:23], fp)
            require(runner.file_identity(os.fstat(stream.fileno())) == before, "Archive changed during seal")
        if reused:
            require(images[service] == reused["metadata"], "API/Worker archives must be exact 002 originals")
        elif forward:
            require(images[service]["image_id"] != baseline["services"][service]["image_id"], "New Web image required")
        archive_paths[service] = str(plain_path(path))
    # The old immutable release supplies runtime definitions and all bind hashes.
    import yaml
    old_candidate = {"compose": yaml.safe_load(old_files["deployment/remote.compose.yaml"]),
        "source_hashes": {name: digest(raw) for name, raw in old_files.items()},
        "fingerprints": {name: baseline["services"][name]["source_fingerprint"] for name in APPS},
        "base_ids": {name: baseline["services"][name]["container_id"] for name in historical.BASE_IDS}}
    plan = {"schema_version": 1, "purpose": PURPOSE, "images": images, "config": config,
            "owner": runner.unique_json(files[".eid-remote-owner.json"]), "old_release": update.OLD_RELEASE,
            "baseline_sha256": prepared["baseline_sha256"], "artifact_sha256": prepared["artifact_sha256"],
            "old_candidate": old_candidate, "prepare_sha256": args.prepare_sha256}
    forward_payload = {}
    if forward:
        forward_payload, chain = update.forward_inputs(baseline_raw)
        plan.update(update_mode=update.runner.FORWARD_MODE,
                    old_candidate=chain["current"] | {"update_mode": update.runner.FORWARD_MODE})
    payload = {"import.json": update.encoded(plan), "baseline.json": baseline_raw,
        "normal_support.py": historical.ordinary_support(support.decode()),
        "app_start_runner.py": update.checked_file(update.HISTORY / "app_start_runner.py",
                                                   update.HISTORICAL_HASHES["app_start_runner.py"]),
        "remote_candidate_update_runner.py": update.checked_file(ROOT / "scripts/remote_candidate_update_runner.py",
                                                                  runner.UPDATE_RUNNER_SHA),
        "remote_candidate_images_runner.py": update.read_file(ROOT / "scripts/remote_candidate_images_runner.py"),
        **{"completion/" + name: raw for name, raw in completion.items()}, **forward_payload}
    manifest = {"schema_version": 1, "purpose": PURPOSE, "archives": archive_paths,
                "launcher_sha256": digest(update.read_file(Path(__file__))),
                "files": {name: digest(raw) for name, raw in payload.items()}}
    output = new_directory(args.output)
    for name, raw in payload.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_new(target, raw)
    raw = update.encoded(manifest)
    write_new(output / "bundle.json", raw)
    return {"bundle_sha256": digest(raw), "images_verified_locally": True, "remote_writes": False}


def load_bundle(directory, sha):
    manifest = runner.unique_json(update.checked_file(directory / "bundle.json", sha))
    require(manifest.get("schema_version") == 1 and manifest.get("purpose") == PURPOSE
            and manifest["launcher_sha256"] == digest(update.read_file(Path(__file__)))
            and set(manifest["archives"]) == set(APPS), "Import bundle contract differs")
    payload = {update.safe_name(name): update.checked_file(directory / update.safe_name(name), value)
               for name, value in manifest["files"].items()}
    plan = runner.unique_json(payload["import.json"])
    forward = update.runner.forward_mode(plan)
    require(payload["remote_candidate_images_runner.py"]
            == update.read_file(ROOT / "scripts/remote_candidate_images_runner.py")
            and digest(payload["remote_candidate_update_runner.py"]) == runner.UPDATE_RUNNER_SHA
            and digest(payload["app_start_runner.py"]) == update.HISTORICAL_HASHES["app_start_runner.py"]
            and digest(payload["baseline.json"]) == (update.runner.FORWARD_BASELINE_SHA if forward else runner.BASELINE_SHA),
            "Pinned import helpers/baseline changed")
    if forward:
        chain = update.runner.forward_chain(payload, payload["baseline.json"])
        require(all(plan["images"][name] == chain["images"][name] for name in ("api", "worker")),
                "Reused images changed")
    require(set(plan["images"]) == set(APPS), "Exactly three images required")
    streams = {}
    try:
        for service in APPS:
            item = plan["images"][service]
            if forward and service != "web":
                require(plain_path(manifest["archives"][service]) == plain_path(
                    update.FORWARD_HISTORY / "prepared-001/archives" / (service + ".tar")),
                    "Reused archive path differs")
            fp = item["source_fingerprint"]
            require(re.fullmatch("sha256:[a-f0-9]{64}", fp)
                    and item["tag"] == "eid-remote-dev-" + service + ":" + fp[7:23], "Candidate tag differs")
            stream = streams[service] = open_archive(manifest["archives"][service])
            before = runner.file_identity(os.fstat(stream.fileno()))
            require(runner.archive_info(stream, item["archive_sha256"], item["archive_size"], item["tag"], fp) == item
                    and runner.file_identity(os.fstat(stream.fileno())) == before, "Sealed archive changed")
            stream.seek(0)
        return payload, streams
    except BaseException:
        for stream in streams.values():
            stream.close()
        raise


def program_bytes(payload, sha, mode, checked):
    values = {name: base64.b64encode(raw).decode() for name, raw in payload.items()}
    return ("import base64,sys\nPAYLOAD={k:base64.b64decode(v) for k,v in " + repr(values)
            + ".items()}\nBUNDLE_SHA=" + repr(sha) + "\nMODE=" + repr(mode) + "\nCHECKED=" + repr(checked)
            + "\nCONNECTION=sys.argv[1]\n"
            + 'exec(compile(PAYLOAD["remote_candidate_images_runner.py"],"<eid-candidate-images>","exec"))\n').encode()


def ssh_argv(program_size):
    boot = "import sys;exec(compile(sys.stdin.buffer.read(" + str(program_size) + '),"<eid-image-import>","exec"))'
    command = "sudo -n python3 -I -u -c " + shlex.quote(boot) + ' "$SSH_CONNECTION"'
    return ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o",
        "PreferredAuthentications=publickey", "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
        "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no", "-o", "Hostname=172.27.0.38", "-o", "User=seadee",
        "-o", "Port=22", "-o", "ProxyJump=jump-local", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3", "-T", "seadee-develop", command]


def invoke(program, streams, images):
    """Stream to the authenticated root interpreter; never stage under /tmp."""
    process = subprocess.Popen(ssh_argv(len(program)), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    results = {"stdout": bytearray(), "stderr": bytearray()}
    errors = []

    def send():
        try:
            process.stdin.write(program)
            for service, stream in streams.items():
                before = runner.file_identity(os.fstat(stream.fileno()))
                stream.seek(0)
                item = images[service]
                require(runner.consume(stream, item["archive_size"], process.stdin) == item["archive_sha256"]
                        and not stream.read(1) and runner.file_identity(os.fstat(stream.fileno())) == before,
                        "Local archive changed during upload")
        except BaseException as exc:
            errors.append(type(exc).__name__)
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    def receive(name, pipe):
        try:
            while raw := pipe.read(65536):
                require(len(results[name]) + len(raw) <= 8 * 1024 * 1024, "Oversized SSH evidence")
                results[name].extend(raw)
        except BaseException as exc:
            errors.append(type(exc).__name__)
            process.kill()
        finally:
            pipe.close()

    threads = [threading.Thread(target=send, daemon=True),
               threading.Thread(target=receive, args=("stdout", process.stdout), daemon=True),
               threading.Thread(target=receive, args=("stderr", process.stderr), daemon=True)]
    for thread in threads:
        thread.start()
    try:
        code = process.wait(timeout=3660)
    except subprocess.TimeoutExpired:
        process.kill()  # Only this local SSH child; remote state is deliberately retained.
        process.wait(timeout=15)
        code = 124
    for thread in threads:
        thread.join(timeout=5)
    if errors or any(thread.is_alive() for thread in threads):
        code = code or 125
    return code, bytes(results["stdout"]), bytes(results["stderr"])


def checked_snapshot(raw, payload, sha):
    evidence = runner.unique_json(raw)
    events = [item for item in evidence.get("events", []) if item.get("kind") == "candidate_images_check_passed"]
    require(evidence.get("mode") == "check" and type(evidence.get("exit_code")) is int and evidence["exit_code"] == 0
            and evidence.get("bundle_sha256") == sha
            and evidence.get("program_sha256") == digest(program_bytes(payload, sha, "check", None))
            and len(events) == 1 and events[0].get("bundle_sha256") == sha
            and events[0].get("remote_writes") is False, "Recent exact successful CHECK required")
    runner.recent_check(events[0], sha)
    return events[0]


def launch(args):
    payload, streams = load_bundle(args.bundle, args.bundle_sha256)
    try:
        checked = None
        plan = runner.unique_json(payload["import.json"])
        if args.mode == "import":
            require(args.reviewed_sha256 == args.bundle_sha256, "Reviewed import bundle required")
            checked = checked_snapshot(update.checked_file(args.checked_output, args.checked_sha256),
                                       payload, args.bundle_sha256)
            require(not plain_path(args.images_output).exists(), "Use a new images output")
        program = program_bytes(payload, args.bundle_sha256, args.mode, checked)
        # Reserve evidence before SSH. Its existence is a local no-replay record.
        with plain_path(args.output).open("x", encoding="utf-8") as evidence:
            json.dump({"mode": args.mode, "bundle_sha256": args.bundle_sha256,
                       "outcome_unknown": True, "automatic_retry": False}, evidence)
            evidence.flush()
            os.fsync(evidence.fileno())
            try:
                code, stdout, stderr = invoke(program, streams if args.mode == "import" else {}, plan["images"])
            except OSError:
                code, stdout, stderr = 125, b"", b"local invocation failed"
            events = []
            for line in stdout.decode("utf-8", "replace").splitlines():
                try:
                    item = runner.unique_json(line)
                    if isinstance(item, dict) and isinstance(item.get("kind"), str):
                        events.append(item)
                except (ValueError, TypeError):
                    continue
            wanted = "candidate_images_check_passed" if args.mode == "check" else "candidate_images_import_complete"
            completed = [item for item in events if item["kind"] == wanted and item.get("bundle_sha256") == args.bundle_sha256]
            expected = {name: {key: plan["images"][name][key] for key in ("image_id", "source_fingerprint")} for name in APPS}
            if code == 0 and (len(completed) != 1 or (args.mode == "import" and completed[0].get("images") != expected)):
                code = 1
            evidence.seek(0)
            evidence.truncate()
            json.dump({"mode": args.mode, "bundle_sha256": args.bundle_sha256,
                       "program_sha256": digest(program), "exit_code": code, "events": events,
                       "outcome_unknown": code != 0, "automatic_retry": False,
                       "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)}, evidence, indent=2)
            evidence.write("\n")
            evidence.flush()
            os.fsync(evidence.fileno())
        if code == 0 and args.mode == "import":
            write_new(args.images_output, update.encoded(expected))
        return code
    finally:
        for stream in streams.values():
            stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = commands.add_parser("prepare", help="extract frozen package and print build argv; no Docker/SSH")
    for name in ("artifact", "baseline"):
        prepare_parser.add_argument("--" + name, type=Path, required=True)
        prepare_parser.add_argument("--" + name + "-sha256", required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--update-mode", choices=("expand", update.runner.FORWARD_MODE), default="expand")
    seal_parser = commands.add_parser("seal", help="validate completed archives and freeze import bundle; no SSH")
    seal_parser.add_argument("--prepared", type=Path, required=True)
    seal_parser.add_argument("--prepare-sha256", required=True)
    for name in APPS:
        seal_parser.add_argument("--" + name + "-sha256", required=True)
    seal_parser.add_argument("--output", type=Path, required=True)
    for name in ("check", "import"):
        action = commands.add_parser(name)
        action.add_argument("--bundle", type=Path, required=True)
        action.add_argument("--bundle-sha256", required=True)
        action.add_argument("--output", type=Path, required=True)
        if name == "import":
            action.add_argument("--reviewed-sha256", required=True)
            action.add_argument("--checked-output", type=Path, required=True)
            action.add_argument("--checked-sha256", required=True)
            action.add_argument("--images-output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode in {"prepare", "seal"}:
        print(json.dumps(prepare(args) if args.mode == "prepare" else seal(args)))
        return 0
    return launch(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"kind": "candidate_images_launcher_stopped", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
