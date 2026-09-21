"""当前账户验收入口在连接前沿用当前环境地址；不连接真实数据库。"""

from pathlib import Path
import runpy

import psycopg
import pytest


@pytest.mark.parametrize("selector,port", [(None, 55432), ("seadee-develop", 15432)])
def test_current_account_client_uses_same_guarded_endpoint(monkeypatch, selector, port):
    if selector is None:
        monkeypatch.delenv("EID_ENVIRONMENT_CONFIG", raising=False)
    else:
        monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
    path = Path(__file__).with_name("test_live_current_account.py")
    probe = runpy.run_path(str(path))["test_current_account_rejects_unmapped_and_inactive_database_identities"]
    expected = f"postgresql+psycopg://eid_migrator:local-migrate-only@localhost:{port}/eid_local_dev"
    events = []

    def guard(url):
        assert url == expected
        events.append("guard")

    def connect(url, **_):
        assert events == ["guard"]
        assert url == expected.replace("postgresql+psycopg:", "postgresql:")
        events.append("connect")
        raise RuntimeError("isolated probe stopped before database I/O")

    monkeypatch.setitem(probe.__globals__, "verify_database", guard)
    monkeypatch.setattr(psycopg, "connect", connect)
    with pytest.raises(RuntimeError, match="isolated probe stopped"):
        probe(monkeypatch)
    assert events == ["guard", "connect"]
