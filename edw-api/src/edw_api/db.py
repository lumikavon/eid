from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import Settings


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
    from .access.repository import first_workspace
    with connection(settings) as conn:
        item = first_workspace(conn, subject)
        if item is None:
            return None
        return {"actor_id": item["actor_id"], "subject": subject,
                "display_name": item["display_name"], "department": item["department"],
                "workspace_id": item["workspace_id"], "workspace_slug": item["slug"],
                "workspace_name": item["name"]}
