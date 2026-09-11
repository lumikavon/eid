from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import Settings


CURRENT_ACCOUNT_SQL = """
SELECT i.id AS actor_id, i.subject, i.display_name, i.department,
       w.id AS workspace_id, w.slug AS workspace_slug, w.name AS workspace_name
FROM identity_account i
JOIN workspace_membership m ON m.identity_id = i.id
JOIN workspace w ON w.id = m.workspace_id
WHERE i.subject = %s AND i.active AND m.active
ORDER BY w.id LIMIT 1
"""


@contextmanager
def connection(settings: Settings) -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        connect_timeout=3,
        options="-c statement_timeout=2000",
    ) as conn:
        identity_row = conn.execute("SELECT current_user").fetchone()
        if identity_row is None or identity_row.get("current_user") != "eid_api":
            raise psycopg.OperationalError("API database identity mismatch")
        yield conn


def current_account(settings: Settings, subject: str) -> dict | None:
    with connection(settings) as conn, conn.cursor() as cur:
        cur.execute(CURRENT_ACCOUNT_SQL, (subject,))
        return cur.fetchone()
