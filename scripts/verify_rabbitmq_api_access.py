"""对已运行的本地环境执行 API broker 最小权限正反探针。"""

from amqp.exceptions import AccessRefused
from celery import Celery
from kombu import Connection as BrokerConnection

from scripts.verify_local_environment import ownership, service_container, verify_rabbitmq


BROKER_URL = "amqp://eid_api:local-api-broker-only@localhost:55672/eid-local"
WORKER_NODE = "eid-worker@worker"


def main():
    ownership(create=False)
    service_container("rabbitmq", 15672, 55673)
    verify_rabbitmq()

    probe = Celery(
        "edw_api_broker_permission_probe",
        broker=BROKER_URL,
        broker_connection_timeout=2,
        broker_transport_options={"connect_timeout": 2, "socket_timeout": 2},
    )
    try:
        replies = probe.control.broadcast(
            "dependency_readiness",
            arguments={"timeout_seconds": 1.5},
            destination=[WORKER_NODE],
            reply=True,
            timeout=2,
        )
    finally:
        probe.close()
    if replies != [{WORKER_NODE: {"status": "ready"}}]:
        raise RuntimeError("API broker 身份未能完成 dependency_readiness 控制请求/回复")

    try:
        with BrokerConnection(BROKER_URL, connect_timeout=2) as broker:
            broker.connect()
            # passive declare 不创建、不删除、不消费；业务队列必须被 broker 以权限错误拒绝。
            broker.default_channel.queue_declare(queue="generation", passive=True)
    except AccessRefused:
        print("API broker 身份控制请求/回复成功，且业务队列访问被拒绝")
        return
    raise RuntimeError("API broker 身份意外获得业务队列元数据访问；请检查 broker 安全补丁和权限")


if __name__ == "__main__":
    main()
