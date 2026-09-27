"""持久化模板校验队列：受限领取、独立进程解析、带租约收据提交。"""
import base64
from hashlib import sha256
from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from psycopg.types.json import Jsonb

from .task_store import call, connection

MAX_REPORT_BYTES = 12 * 1024 * 1024
SANDBOX = Path("/usr/bin/bwrap")
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def sandbox_available():
    """Fail before claiming a lease if the actual namespace/parser cannot start."""
    if os.name != "posix" or not SANDBOX.is_file() or not os.access(SANDBOX, os.X_OK):
        return False
    script = Path(__file__).with_name("template_validator_process.py").resolve()
    try:
        # An empty package is rejected by the parser, but a zero exit confirms that
        # the networkless mount namespace and its trusted Python imports started.
        probe = subprocess.run(_sandbox_command(script), input=b"", stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env={}, timeout=5, check=False)
        return probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def _sandbox_command(script):
    # Bind only Python's installed runtime and the trusted parser directory.
    # All other host paths are absent; --unshare-all includes the network namespace.
    command = [str(SANDBOX), "--die-with-parent", "--new-session", "--unshare-user",
               "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts",
               "--unshare-cgroup", "--clearenv", "--ro-bind", "/usr", "/usr"]
    for root in (Path("/lib"), Path("/lib64"), Path(sys.prefix).resolve(), script.parent):
        if root.is_dir() and not root.is_relative_to(Path("/usr")):
            command += ["--ro-bind", str(root), str(root)]
    command += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
                "--setenv", "HOME", "/tmp", "--setenv", "TMPDIR", "/tmp",
                "--chdir", "/tmp", str(Path(sys.executable).resolve()), "-I", str(script)]
    return command


def inspect_package(raw):
    """Parse only inside a fail-closed, networkless, read-only namespace."""
    if not sandbox_available():
        raise RuntimeError("Template validator isolation unavailable")
    script = Path(__file__).with_name("template_validator_process.py").resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="eid-template-") as directory:
            with tempfile.TemporaryFile() as output:
                completed = subprocess.run(
                    _sandbox_command(script), input=raw, stdout=output,
                    stderr=subprocess.DEVNULL, timeout=15, check=False, env={}, cwd=directory)
                output.seek(0)
                stdout = output.read(MAX_REPORT_BYTES + 1)
        if completed.returncode:
            raise RuntimeError("Template validator sandbox failed")
        if len(stdout) > MAX_REPORT_BYTES:
            return None, "VALIDATOR_FAILED"
        result = json.loads(stdout)
        if not isinstance(result, dict):
            return None, "VALIDATOR_FAILED"
        report = result.get("report")
        if report is not None:
            if (not isinstance(report, dict) or report.get("source_sha256") != sha256(raw).hexdigest()
                    or report.get("validator_version") != "template-archive-v1"):
                return None, "VALIDATOR_FAILED"
            return report, None
        error = result.get("error")
        if not isinstance(error, str) or not error.isascii() or not error.replace("_", "").isalpha():
            error = "VALIDATOR_FAILED"
        return None, error
    except subprocess.TimeoutExpired:
        return None, "VALIDATOR_TIMEOUT"
    except OSError as exc:
        raise RuntimeError("Template validator sandbox unavailable") from exc
    except ValueError:
        return None, "VALIDATOR_FAILED"


def validate_once():
    if not sandbox_available():
        raise RuntimeError("Template validator isolation unavailable")
    with connection() as conn:
        pending = conn.execute("SELECT eid_template_validation_pending_v1()").fetchall()
    for (candidate_id,) in pending:
        owner = uuid4()
        claim = call("SELECT eid_template_validation_claim_v1(%s,%s)", (candidate_id, owner))
        if claim is None:
            continue
        # PostgreSQL base64 uses LF folding. No untrusted paths leave the database.
        raw = base64.b64decode(claim["package_base64"].replace("\n", ""), validate=True)
        if len(raw) > 5 * 1024 * 1024 or sha256(raw).hexdigest() != claim["sha256"]:
            report, error = None, "PACKAGE_INTEGRITY"
        else:
            report, error = inspect_package(raw)
        call("SELECT eid_template_validation_finish_v1(%s,%s,%s,%s)",
             (candidate_id, owner, Jsonb(report) if report is not None else None, error))
        return True
    return False


def main(status_sender=None):
    while True:
        try:
            progressed = validate_once()
            healthy = True
        except Exception as exc:
            logger.warning("template_validation_pending error_type=%s", type(exc).__name__)
            progressed, healthy = False, False
        if status_sender is not None:
            status_sender.send((time.monotonic(), healthy))
        if not progressed:
            time.sleep(2)
