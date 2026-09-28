"""Restricted evidence wake consumer: identifiers only, API owns authorization and excerpts."""
import hashlib
import hmac
import logging
import os
import time
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


def register(app):
    @app.task(name='eid.evidence.wake.v1', queue='retrieval', ignore_result=True, max_retries=2)
    def wake(workspace_id, document_id, job_id):
        key = os.getenv('EID_EVIDENCE_WAKE_KEY', '')
        if len(key) < 32:
            return  # Fail closed; persisted job can be reconciled on authorized observation.
        try:
            workspace, document, job = (UUID(value) for value in (workspace_id, document_id, job_id))
            timestamp = str(int(time.time()))
            mac = hmac.new(key.encode(), f'{workspace}:{document}:{job}:{timestamp}'.encode('ascii'), hashlib.sha256).hexdigest()
            url = (f'http://api:8000/api/v1/workspaces/{workspace}/documents/{document}/evidence/jobs/{job}/wake')
            with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
                response = client.post(url, headers={'X-Evidence-Time': timestamp, 'X-Evidence-Mac': mac})
                response.raise_for_status()
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning('evidence_wake_unavailable error_type=%s', type(exc).__name__)
            raise wake.retry(countdown=10) from None
