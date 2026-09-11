"""显式运行的数据库查询路径验收；所有测试数据仅存在于回滚事务中。"""

from contextlib import contextmanager
import os
import uuid

import psycopg
from psycopg.rows import dict_row
import pytest

import edw_api.db as db
from edw_api.config import Settings
from scripts.verify_local_environment import verify_database


pytestmark = pytest.mark.skipif(
    os.getenv("EID_RUN_LIVE_TESTS") != "1", reason="需要显式隔离环境验收"
)
GUARDED_URL = (
    "postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev"
)
DATABASE_URL = GUARDED_URL.replace("postgresql+psycopg:", "postgresql:")


def test_current_account_rejects_unmapped_and_inactive_database_identities(monkeypatch):
    verify_database(GUARDED_URL)
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=3)
    suffix = uuid.uuid4().hex
    workspace_id = uuid.uuid4()
    unmapped_id = uuid.uuid4()
    inactive_identity_id = uuid.uuid4()
    inactive_membership_id = uuid.uuid4()
    active_membership_id = uuid.uuid4()

    @contextmanager
    def rollback_connection(_settings):
        yield conn

    try:
        conn.execute(
            "INSERT INTO workspace(id, slug, name) VALUES (%s, %s, %s)",
            (workspace_id, f"live-{suffix}", "回滚查询测试工作区"),
        )
        conn.execute(
            "INSERT INTO identity_account(id, subject, display_name, department, active) "
            "VALUES (%s, %s, %s, %s, true), (%s, %s, %s, %s, false), "
            "(%s, %s, %s, %s, true), (%s, %s, %s, %s, true)",
            (
                unmapped_id,
                f"unmapped-{suffix}",
                "未映射身份",
                "测试部",
                inactive_identity_id,
                f"inactive-identity-{suffix}",
                "停用身份",
                "测试部",
                inactive_membership_id,
                f"inactive-membership-{suffix}",
                "停用成员关系",
                "测试部",
                active_membership_id,
                f"active-membership-{suffix}",
                "活动成员关系",
                "测试部",
            ),
        )
        conn.execute(
            "INSERT INTO workspace_membership(identity_id, workspace_id, active) "
            "VALUES (%s, %s, true), (%s, %s, false), (%s, %s, true)",
            (
                inactive_identity_id,
                workspace_id,
                inactive_membership_id,
                workspace_id,
                active_membership_id,
                workspace_id,
            ),
        )
        monkeypatch.setattr(db, "connection", rollback_connection)
        settings = Settings(database_url=DATABASE_URL)

        assert db.current_account(settings, f"unmapped-{suffix}") is None
        assert db.current_account(settings, f"inactive-identity-{suffix}") is None
        assert db.current_account(settings, f"inactive-membership-{suffix}") is None
        assert db.current_account(settings, f"active-membership-{suffix}") == {
            "actor_id": active_membership_id,
            "subject": f"active-membership-{suffix}",
            "display_name": "活动成员关系",
            "department": "测试部",
            "workspace_id": workspace_id,
            "workspace_slug": f"live-{suffix}",
            "workspace_name": "回滚查询测试工作区",
        }
    finally:
        conn.rollback()
        conn.close()
