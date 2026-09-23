"""离线验证迁移链和新增授权声明，不执行迁移或连接数据库。"""
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest


ROOT = Path(__file__).parents[2]


def migration():
    spec = importlib.util.spec_from_file_location(
        "discovery_migration", ROOT / "migrations/versions/0007_workspace_discovery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_extends_existing_head_and_has_no_data_cleanup(monkeypatch):
    module = migration()
    commands = []
    monkeypatch.setattr(module, "op", SimpleNamespace(execute=commands.append))
    module.upgrade()
    statements = [statement.strip() for sql in commands for statement in sql.split(";") if statement.strip()]
    assert module.down_revision == "0006_api_write_only"
    assert all(statement.startswith(("CREATE TABLE ", "CREATE INDEX ", "GRANT ", "REVOKE "))
               for statement in statements)
    assert {re.match(r"CREATE TABLE (\w+)", statement).group(1)
            for statement in statements if statement.startswith("CREATE TABLE")} == {
                "discovery_record", "discovery_participant", "discovery_favorite",
                "discovery_restore_policy", "discovery_receipt"}
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_revision("0008_durable_submission").down_revision == module.revision
    with pytest.raises(RuntimeError):
        module.downgrade()


def test_only_collection_state_columns_are_updateable_and_worker_has_no_grants(monkeypatch):
    commands = []
    module = migration()
    monkeypatch.setattr(module, "op", SimpleNamespace(execute=commands.append))
    module.upgrade()
    statements = [statement.strip() for sql in commands for statement in sql.split(";") if statement.strip()]
    grants = [statement for statement in statements if statement.startswith("GRANT")]
    assert all(statement.endswith("TO eid_api") for statement in grants)
    assert not any("access_audit" in statement or "access_resource" in statement for statement in grants)
    updates = {}
    for statement in grants:
        if statement.startswith("GRANT UPDATE"):
            match = re.fullmatch(r"GRANT UPDATE \(([^)]+)\) ON (\w+) TO eid_api", statement)
            assert match is not None
            updates[match[2]] = set(match[1].split(","))
    assert updates == {"discovery_record": {"visibility", "revision", "updated_at"},
                       "discovery_favorite": {"active", "revision", "updated_at"}}
    revocation = next(statement for statement in statements if statement.startswith("REVOKE"))
    assert revocation.endswith("FROM PUBLIC,eid_worker")
    assert all(table in revocation for table in ("discovery_record", "discovery_participant",
                                                "discovery_favorite", "discovery_restore_policy",
                                                "discovery_receipt"))
