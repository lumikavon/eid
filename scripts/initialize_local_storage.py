"""仅在全部既有边界核实后初始化专用 broker 身份与 bucket。"""

import os
import time

from botocore.exceptions import BotoCoreError, ClientError

from scripts.verify_local_environment import (
    EXPECTED,
    ownership,
    create_rabbitmq_runtime_users,
    provision_keycloak_readiness_monitor,
    s3_client,
    service_container,
    verify_database,
    verify_keycloak,
    verify_migration_target,
    verify_rabbitmq,
    verify_s3_configuration,
)


def storage_boundary():
    owner = ownership()["nonce"]
    return (owner, service_container("rabbitmq", 15672, 55673),
            service_container("keycloak", 8080, 58080),
            service_container("seaweedfs", 8333, 58333))


def main():
    verify_database(os.environ.get("EID_MIGRATION_DATABASE_URL", ""))
    initial_boundary = storage_boundary()
    # 在首次 S3 请求前证明全部既有资源边界，避免后续 guard 失败时已经写入 bucket。
    service_container("seaweedfs", 8333, 58333)
    rabbitmq_runtime_state = verify_rabbitmq(allow_missing_runtime=True)
    keycloak_monitor_state = verify_keycloak(allow_incomplete_monitor=True)
    verify_s3_configuration()
    client = s3_client("bootstrap")
    deadline = time.monotonic() + 90
    while True:
        try:
            buckets = {bucket["Name"] for bucket in client.list_buckets().get("Buckets", [])}
            break
        except (BotoCoreError, ClientError):
            if time.monotonic() >= deadline:
                raise RuntimeError("对象存储在 90 秒内未就绪，拒绝继续写入")
            time.sleep(2)
    allowed_inventory = {EXPECTED["bucket"]}
    if buckets not in (set(), allowed_inventory):
        raise RuntimeError("对象存储 bucket 清单必须为空或仅包含本项目 bucket")
    # 到此为止均为只读守卫；运行用户必须同时缺失或同时完全匹配。
    def verify_write_boundary():
        if storage_boundary() != initial_boundary:
            raise RuntimeError("存储初始化期间容器归属或实例已变化，拒绝写入")

    if rabbitmq_runtime_state == "missing":
        verify_write_boundary()
        create_rabbitmq_runtime_users()
    if keycloak_monitor_state != "ready":
        verify_write_boundary()
        provision_keycloak_readiness_monitor()
    if not buckets:
        verify_write_boundary()
        client.create_bucket(Bucket=EXPECTED["bucket"])
    client.head_bucket(Bucket=EXPECTED["bucket"])
    # 创建后重新运行完整守卫，只有最终状态全部匹配时才报告初始化成功。
    verify_migration_target(os.environ.get("EID_MIGRATION_DATABASE_URL", ""))
    print("所选隔离开发环境的对象存储已就绪")


if __name__ == "__main__":
    main()
