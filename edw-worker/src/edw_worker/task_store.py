"""Worker identity has only narrow task functions; connection exit commits or rolls back."""
from contextlib import contextmanager
import os

import psycopg


@contextmanager
def connection():
    with psycopg.connect(os.environ["EID_DATABASE_URL"], connect_timeout=3,
                        options="-c statement_timeout=2000 -c lock_timeout=1000") as conn:
        if conn.execute("SELECT current_user,session_user").fetchone() != ("eid_worker", "eid_worker"):
            raise psycopg.OperationalError("Worker database identity mismatch")
        yield conn


def call(sql, parameters):
    with connection() as conn:
        value = conn.execute(sql, parameters).fetchone()[0]
    return value
