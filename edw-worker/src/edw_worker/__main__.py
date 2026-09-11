import sys
import os
from edw_worker.app import app, verify_dependencies
from edw_worker.log_safety import register_worker_log_safety


def worker_arguments(arguments: list[str]) -> list[str]:
    result = list(arguments)
    if result and result[0] == "worker" and not any(
        value == "-n" or value == "--hostname" or value.startswith("--hostname=")
        for value in result
    ):
        result.append(f"--hostname={os.getenv('EID_WORKER_NODE_NAME', 'eid-worker@worker')}")
    return result


def main() -> None:
    register_worker_log_safety()
    verify_dependencies()
    app.worker_main(worker_arguments(sys.argv[1:]))


if __name__ == "__main__":
    main()
