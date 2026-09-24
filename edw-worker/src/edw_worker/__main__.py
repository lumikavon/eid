import sys
import os
from edw_worker.app import verify_dependencies
from edw_worker.log_safety import register_worker_log_safety
from edw_worker.relay import scheduler_main, supervise


def worker_arguments(arguments: list[str]) -> list[str]:
    result = list(arguments)
    if result and result[0] == "worker" and not any(
        value == "-n" or value == "--hostname" or value.startswith("--hostname=")
        for value in result
    ):
        result.append(f"--hostname={os.getenv('EID_WORKER_NODE_NAME', 'eid-worker@worker')}")
    return result


def main() -> int:
    register_worker_log_safety()
    arguments = worker_arguments(sys.argv[1:])
    if arguments == ["scheduler"]:
        verify_dependencies()
        scheduler_main()
        return 0
    if not arguments or arguments[0] != "worker":
        raise ValueError("The worker or scheduler sub-command must be specified")
    verify_dependencies()
    return supervise(arguments)


if __name__ == "__main__":
    sys.exit(main())
