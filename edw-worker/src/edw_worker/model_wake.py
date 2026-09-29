"""Identifier-only generation wake; the API alone reads policy and performs generation."""
import hashlib
import hmac
import logging
import os
import time
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


def register(app):
    @app.task(name='eid.model.wake.v1', queue='generation', ignore_result=True, max_retries=2)
    def wake(workspace_id, document_id, run_id):
        key = os.getenv('EID_MODEL_WAKE_KEY', '')
        if len(key) < 32:
            return
        try:
            workspace, document, run = (UUID(value) for value in (workspace_id, document_id, run_id))
            timestamp = str(int(time.time()))
            mac = hmac.new(key.encode(), f'{workspace}:{document}:{run}:{timestamp}'.encode('ascii'),
                           hashlib.sha256).hexdigest()
            url = f'http://api:8000/api/v1/workspaces/{workspace}/model-governance/documents/{document}/runs/{run}/wake'
            with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
                response = client.post(url, headers={'X-Model-Time': timestamp, 'X-Model-Mac': mac})
                response.raise_for_status()
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning('model_wake_unavailable error_type=%s', type(exc).__name__)
            raise wake.retry(countdown=10) from None
