"""将本项目旧 Worker 管理 fixture 一次性迁移为独立 bootstrap 管理员。"""

import argparse

import httpx
from kombu import Connection as BrokerConnection

from scripts.verify_local_environment import (
    EXPECTED,
    IsolationError,
    RABBITMQ_ADMIN_PASSWORD,
    RABBITMQ_ADMIN_PERMISSIONS,
    RABBITMQ_ADMIN_USER,
    RABBITMQ_API_PASSWORD,
    RABBITMQ_API_PERMISSIONS,
    RABBITMQ_API_USER,
    RABBITMQ_WORKER_PASSWORD,
    RABBITMQ_WORKER_PERMISSIONS,
    RABBITMQ_WORKER_USER,
    _rabbitmq_tags,
    ownership,
    require,
    service_container,
    verify_rabbitmq,
)


def _exact_grant(client, user_name: str, expected: dict[str, str], label: str) -> None:
    response = client.get(f"/api/users/{user_name}/permissions")
    require(response.status_code == 200, f"无法核验 RabbitMQ {label}权限")
    grants = response.json()
    require(
        len(grants) == 1
        and grants[0].get("vhost") == EXPECTED["rabbitmq_vhost"]
        and all(grants[0].get(key) == value for key, value in expected.items()),
        f"RabbitMQ {label}不是预期的 legacy fixture，拒绝迁移",
    )


def _fixture_credential(user_name: str, password: str, label: str) -> None:
    try:
        with BrokerConnection(
            f"amqp://{user_name}:{password}@localhost:55672/eid-local",
            connect_timeout=3,
        ) as broker:
            broker.connect()
    except Exception as exc:
        raise IsolationError(f"RabbitMQ {label} fixture 凭据不匹配，拒绝迁移") from exc


def preflight():
    ownership(create=False)
    service_container("rabbitmq", 15672, 55673)
    auth = httpx.BasicAuth(RABBITMQ_WORKER_USER, RABBITMQ_WORKER_PASSWORD)
    client = httpx.Client(base_url="http://localhost:55673", auth=auth, timeout=5)
    with client:
        whoami = client.get("/api/whoami")
        require(
            whoami.status_code == 200
            and whoami.json().get("name") == RABBITMQ_WORKER_USER
            and _rabbitmq_tags(whoami.json()) == {"administrator"},
            "RabbitMQ legacy Worker 管理标签或当前 fixture 凭据不匹配，拒绝迁移",
        )
        vhost = client.get(f"/api/vhosts/{EXPECTED['rabbitmq_vhost']}")
        require(
            vhost.status_code == 200 and vhost.json().get("name") == EXPECTED["rabbitmq_vhost"],
            "RabbitMQ legacy vhost 不匹配，拒绝迁移",
        )
        users = client.get("/api/users")
        require(users.status_code == 200, "无法核验 RabbitMQ legacy 用户清单")
        require(
            {user.get("name") for user in users.json()} == {RABBITMQ_WORKER_USER, RABBITMQ_API_USER},
            "RabbitMQ legacy 用户清单不匹配，拒绝迁移",
        )
        worker = client.get(f"/api/users/{RABBITMQ_WORKER_USER}")
        require(
            worker.status_code == 200
            and worker.json().get("name") == RABBITMQ_WORKER_USER
            and _rabbitmq_tags(worker.json()) == {"administrator"},
            "RabbitMQ legacy Worker 管理标签不匹配，拒绝迁移",
        )
        _exact_grant(client, RABBITMQ_WORKER_USER, RABBITMQ_ADMIN_PERMISSIONS, "legacy Worker")
        api = client.get(f"/api/users/{RABBITMQ_API_USER}")
        require(
            api.status_code == 200
            and api.json().get("name") == RABBITMQ_API_USER
            and not _rabbitmq_tags(api.json()),
            "RabbitMQ API 用户不是预期 fixture，拒绝迁移",
        )
        _exact_grant(client, RABBITMQ_API_USER, RABBITMQ_API_PERMISSIONS, "API 用户")
        new_admin = client.get(f"/api/users/{RABBITMQ_ADMIN_USER}")
        require(new_admin.status_code == 404, "RabbitMQ bootstrap 管理员已存在，拒绝重复迁移")
        _fixture_credential(RABBITMQ_WORKER_USER, RABBITMQ_WORKER_PASSWORD, "legacy Worker")
        _fixture_credential(RABBITMQ_API_USER, RABBITMQ_API_PASSWORD, "API 用户")
    return None


def migrate() -> None:
    preflight()
    auth = httpx.BasicAuth(RABBITMQ_WORKER_USER, RABBITMQ_WORKER_PASSWORD)
    with httpx.Client(base_url="http://localhost:55673", auth=auth, timeout=5) as client:
        created = client.put(
            f"/api/users/{RABBITMQ_ADMIN_USER}",
            json={"password": RABBITMQ_ADMIN_PASSWORD, "tags": "administrator"},
        )
        require(created.status_code in (201, 204), "创建 RabbitMQ bootstrap 管理员失败")
        granted = client.put(
            f"/api/permissions/{EXPECTED['rabbitmq_vhost']}/{RABBITMQ_ADMIN_USER}",
            json=RABBITMQ_ADMIN_PERMISSIONS,
        )
        require(granted.status_code in (201, 204), "设置 RabbitMQ bootstrap 管理员权限失败")
        restricted = client.put(
            f"/api/permissions/{EXPECTED['rabbitmq_vhost']}/{RABBITMQ_WORKER_USER}",
            json=RABBITMQ_WORKER_PERMISSIONS,
        )
        require(restricted.status_code in (201, 204), "收紧 RabbitMQ Worker 权限失败")
        stripped = client.put(
            f"/api/users/{RABBITMQ_WORKER_USER}",
            json={"tags": "", "password": RABBITMQ_WORKER_PASSWORD},
        )
        require(stripped.status_code in (201, 204), "移除 RabbitMQ legacy Worker 管理标签失败")
    verify_rabbitmq()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="执行已授权的一次性 fixture 迁移")
    args = parser.parse_args()
    if args.apply:
        migrate()
        print("RabbitMQ bootstrap 管理身份迁移完成")
    else:
        preflight()
        print("RabbitMQ legacy fixture 只读预检通过；使用 --apply 执行一次性迁移")


if __name__ == "__main__":
    main()
