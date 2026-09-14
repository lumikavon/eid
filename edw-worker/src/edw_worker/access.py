"""Trusted supervisor authorization at each stage and again before protected output.

Only a stored API-issued delegation identifier enters this boundary, never user tokens
or supplied actor/scope claims. No task engine or result commit is implemented here.
"""
import os
import re
from dataclasses import replace
from uuid import UUID

import psycopg

from edw_api.access.policy import AccessDenied, authorize


def current_access(delegation_id: str, operation: str, purpose: str):
    try:
        identifier = UUID(delegation_id)
        with psycopg.connect(os.environ["EID_DATABASE_URL"], connect_timeout=3,
                            options="-c statement_timeout=2000 -c lock_timeout=1000") as conn:
            if conn.execute("SELECT current_user").fetchone() != ("eid_worker",):
                raise AccessDenied()
            row = conn.execute("SELECT eid_worker_access(%s)", (identifier,)).fetchone()
            if not row or not row[0]:
                raise AccessDenied()
            payload = row[0]
            delegation = payload["delegation"]
            if (not isinstance(delegation.get("request_id"), str) or not delegation["request_id"]
                    or not isinstance(delegation.get("trace_id"), str)
                    or not re.fullmatch(r"[0-9a-f]{32}", delegation["trace_id"])):
                raise AccessDenied()
            context = authorize(payload["facts"], operation, payload["resource"],
                             service_id="eid-worker", purpose=purpose,
                             delegation=delegation)
            return replace(context, request_id=delegation["request_id"], trace_id=delegation["trace_id"])
    except (ValueError, KeyError, psycopg.Error) as exc:
        raise AccessDenied() from exc
