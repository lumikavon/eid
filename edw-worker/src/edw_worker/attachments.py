"""Fenced parse_ocr consumer. Parser sees bytes only, never DB/MQ/S3 credentials."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import resource
import subprocess
import tempfile
from uuid import UUID, uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.types.json import Jsonb
from edw_api.access.policy import AccessDenied

from .access import current_access
from .task_store import call
from .template_validation import SANDBOX, _sandbox_command

logger = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
MAX_REPORT = 1024 * 1024


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_REPORT, MAX_REPORT))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def inspect(kind, raw):
    if not SANDBOX.is_file() or not os.access(SANDBOX, os.X_OK):
        raise RuntimeError("Attachment sandbox unavailable")
    script = Path(__file__).with_name("attachment_parser_process.py").resolve()
    command = _sandbox_command(script)
    # A required preloaded model directory is read-only; absent models produce
    # explicit OCR_UNAVAILABLE rather than silently claiming successful OCR.
    models = Path("/opt/eid-ocr")
    if models.is_dir():
        at = command.index("--dev")
        command[at:at] = ["--ro-bind", str(models), str(models)]
    try:
        with tempfile.TemporaryFile() as output:
            completed = subprocess.run(command, input=json.dumps({"kind": kind,
                "bytes": base64.b64encode(raw).decode("ascii")}).encode("ascii"),
                stdout=output, stderr=subprocess.DEVNULL, env={}, timeout=55,
                preexec_fn=_limits, check=False)
            output.seek(0)
            data = output.read(MAX_REPORT + 1)
        if completed.returncode or len(data) > MAX_REPORT:
            return None, "RESOURCE_LIMIT"
        report = json.loads(data)
        if not isinstance(report, dict):
            return None, "PARSER_FAILED"
        if report.get("error"):
            return None, report["error"] if report["error"] in ("UNSAFE_CONTENT", "PARSER_FAILED") else "PARSER_FAILED"
        pages = report.get("pages")
        if not isinstance(pages, list) or len(pages) > 500:
            return None, "RESOURCE_LIMIT"
        return pages, None
    except subprocess.TimeoutExpired:
        return None, "RESOURCE_LIMIT"
    except (ValueError, OSError, json.JSONDecodeError):
        return None, "PARSER_FAILED"


def process(identifier):
    attachment_id = UUID(str(identifier))
    owner = uuid4()
    claim = call("SELECT eid_attachment_claim_v1(%s,%s)", (attachment_id, owner))
    if not claim:
        return
    # Access is checked at claim and again before the security-definer commit.
    try:
        current_access(str(claim["delegation"]), "resource:read", f"attachment:{attachment_id}")
        client = boto3.client("s3", endpoint_url=os.environ["EID_S3_ENDPOINT_URL"],
                              aws_access_key_id=os.environ["EID_S3_ACCESS_KEY"],
                              aws_secret_access_key=os.environ["EID_S3_SECRET_KEY"],
                              config=Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1}))
        try:
            obj = client.get_object(Bucket=os.environ["EID_S3_BUCKET"], Key=claim["key"])
            try:
                raw = obj["Body"].read(MAX_BYTES + 1)
            finally:
                obj["Body"].close()
        finally:
            client.close()
        if len(raw) != claim["length"] or sha256(raw).hexdigest() != claim["hash"]:
            pages, error = None, "INTEGRITY_FAILED"
        else:
            pages, error = inspect(claim["kind"], raw)
        current_access(str(claim["delegation"]), "resource:read", f"attachment:{attachment_id}")
        committed = call("SELECT eid_attachment_finish_v1(%s,%s,%s,%s,%s)",
                         (attachment_id, owner, claim["hash"], Jsonb(pages) if pages is not None else None, error))
        if committed is not True:
            logger.warning("attachment_finish_not_committed")
    except Exception as exc:
        # Uncertain dependency/policy failures leave a fenced lease for a bounded retry;
        # no untrusted content enters logs or messages.
        if isinstance(exc, AccessDenied):
            try:
                # Database is the final authority; this transitions revoked leases to BLOCKED.
                call("SELECT eid_attachment_finish_v1(%s,%s,%s,%s,%s)",
                     (attachment_id, owner, claim["hash"], None, "PARSER_FAILED"))
            except Exception:
                pass
        logger.warning("attachment_processing_failed error_type=%s", type(exc).__name__)


def cleanup_orphans():
    """Remove only unreferenced quarantine objects older than 24 hours.

    A persisted formal or quarantined attachment is never eligible. Database
    uncertainty aborts cleanup; a per-object storage failure leaves that key intact.
    """
    client = boto3.client("s3", endpoint_url=os.environ["EID_S3_ENDPOINT_URL"],
                          aws_access_key_id=os.environ["EID_S3_ACCESS_KEY"],
                          aws_secret_access_key=os.environ["EID_S3_SECRET_KEY"],
                          config=Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1}))
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        removed = 0
        for listing in client.get_paginator("list_objects_v2").paginate(
                Bucket=os.environ["EID_S3_BUCKET"], Prefix="attachment-quarantine/"):
            for item in listing.get("Contents", []):
                key, modified = item.get("Key"), item.get("LastModified")
                if not key or not isinstance(modified, datetime) or modified >= cutoff:
                    continue
                if call("SELECT eid_attachment_orphan_v1(%s)", (key,)) is not True:
                    continue
                try:
                    client.delete_object(Bucket=os.environ["EID_S3_BUCKET"], Key=key)
                except (BotoCoreError, ClientError) as exc:
                    logger.warning("attachment_orphan_cleanup_failed error_type=%s", type(exc).__name__)
                    continue
                removed += 1
                if removed == 20:
                    return
    finally:
        logger.info("attachment_orphan_cleanup_removed count=%d", removed)
        client.close()


def register(app):
    @app.task(name="eid.attachment.parse.v1", queue="parse_ocr", ignore_result=True)
    def parse_attachment(attachment_id):
        process(attachment_id)
