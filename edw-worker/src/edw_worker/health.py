import os
import sys

from .app import app


def worker_is_ready() -> bool:
    node_name = os.getenv("EID_WORKER_NODE_NAME", "eid-worker@worker")
    timeout = float(os.getenv("EID_WORKER_HEALTH_TIMEOUT_SECONDS", "2"))
    if timeout < 2:
        return False
    try:
        replies = app.control.broadcast(
            "dependency_readiness",
            arguments={"timeout_seconds": timeout * 0.75},
            destination=[node_name],
            reply=True,
            timeout=timeout,
        )
    except Exception:
        return False
    return replies == [{node_name: {"status": "ready"}}]


def main() -> int:
    return 0 if worker_is_ready() else 1


if __name__ == "__main__":
    sys.exit(main())
