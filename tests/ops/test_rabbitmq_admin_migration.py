"""一次性 RabbitMQ legacy Worker 管理身份迁移的无服务单元测试。"""

from pathlib import Path

import pytest

from scripts import migrate_rabbitmq_bootstrap_admin as migration
from scripts.verify_local_environment import IsolationError


class Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _legacy_client(*, worker_tags=None, calls=None):
    calls = calls if calls is not None else []
    worker_tags = ["administrator"] if worker_tags is None else worker_tags

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): return None

        def get(self, path):
            payloads = {
                "/api/whoami": {"name": "eid_worker", "tags": worker_tags},
                "/api/vhosts/eid-local": {"name": "eid-local"},
                "/api/users": [
                    {"name": "eid_worker", "tags": worker_tags},
                    {"name": "eid_api", "tags": []},
                ],
                "/api/users/eid_worker": {"name": "eid_worker", "tags": worker_tags},
                "/api/users/eid_worker/permissions": [
                    {"vhost": "eid-local", **migration.RABBITMQ_ADMIN_PERMISSIONS}
                ],
                "/api/users/eid_api": {"name": "eid_api", "tags": []},
                "/api/users/eid_api/permissions": [
                    {"vhost": "eid-local", **migration.RABBITMQ_API_PERMISSIONS}
                ],
                "/api/users/eid_broker_admin": None,
            }
            return Response(404 if path == "/api/users/eid_broker_admin" else 200, payloads[path])

        def put(self, path, json):
            calls.append(("put", path, json))
            return Response(201)

        def delete(self, *_args, **_kwargs):
            pytest.fail("迁移不得删除用户、权限、vhost 或数据")

    return Client()


class Connection:
    def __enter__(self): return self
    def __exit__(self, *_args): return None
    def connect(self): return None


def test_apply_creates_admin_before_stripping_only_legacy_worker(monkeypatch):
    calls = []
    monkeypatch.setattr(migration, "ownership", lambda create=False: {"nonce": "owned"})
    monkeypatch.setattr(migration, "service_container", lambda *args: calls.append(("container", args)))
    monkeypatch.setattr(migration, "BrokerConnection", lambda *_args, **_kwargs: Connection())
    monkeypatch.setattr(migration.httpx, "Client", lambda **_kwargs: _legacy_client(calls=calls))
    monkeypatch.setattr(migration, "verify_rabbitmq", lambda: calls.append(("final-guard",)))

    migration.migrate()

    assert calls == [
        ("container", ("rabbitmq", 15672, 55673)),
        ("put", "/api/users/eid_broker_admin", {
            "password": "local-rabbitmq-bootstrap-admin-only", "tags": "administrator"
        }),
        ("put", "/api/permissions/eid-local/eid_broker_admin", migration.RABBITMQ_ADMIN_PERMISSIONS),
        ("put", "/api/permissions/eid-local/eid_worker", migration.RABBITMQ_WORKER_PERMISSIONS),
        ("put", "/api/users/eid_worker", {"tags": "", "password": "local-worker-only"}),
        ("final-guard",),
    ]


def test_preflight_rejects_nonlegacy_worker_without_writes(monkeypatch):
    calls = []
    monkeypatch.setattr(migration, "ownership", lambda create=False: {"nonce": "owned"})
    monkeypatch.setattr(migration, "service_container", lambda *_args: None)
    monkeypatch.setattr(migration.httpx, "Client", lambda **_kwargs: _legacy_client(worker_tags=[], calls=calls))

    with pytest.raises(IsolationError, match="legacy Worker 管理标签"):
        migration.preflight()
    assert calls == []


def test_migration_source_has_no_delete_or_cleanup_operation():
    source = (Path(__file__).parents[2] / "scripts" / "migrate_rabbitmq_bootstrap_admin.py").read_text(
        encoding="utf-8"
    )
    assert ".delete(" not in source
    assert "docker compose down" not in source
    assert "volume rm" not in source
