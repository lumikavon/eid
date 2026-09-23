"""Regression test SOURCE only; compilation does not execute these cases."""
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

from celery.exceptions import Reject
import pytest

from edw_worker import inventory, relay
from scripts.verify_local_environment import RABBITMQ_API_PERMISSIONS, RABBITMQ_WORKER_PERMISSIONS

os.environ.setdefault("EID_RABBITMQ_URL", "amqp://eid_worker:local-worker-only@rabbitmq/eid-local")


def test_publisher_uses_a_bound_named_exchange_with_existing_least_privilege(monkeypatch):
    envelope = json.loads((Path(__file__).parents[2] / "contracts/vectors/task-envelope-v1.json")
                          .read_text("utf8"))
    observed = {}

    class Connection:
        def __init__(self, url, **options):
            observed["connection"] = options
            self.transport = SimpleNamespace(driver_name="py-amqp")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    class Producer(Connection):
        def __init__(self, broker, **options):
            observed["on_return"] = options["on_return"]

        def publish(self, body, **options):
            observed.update(options)

    monkeypatch.setattr(relay, "Connection", Connection)
    monkeypatch.setattr(relay, "Producer", Producer)
    relay.publish(envelope)
    exchange, queue = observed["exchange"], observed["declare"][0]
    assert exchange.name == queue.exchange.name == queue.name == "integration"
    assert exchange.type == "direct" and exchange.durable and queue.durable
    assert observed["routing_key"] == queue.routing_key == "integration"
    for permissions in RABBITMQ_WORKER_PERMISSIONS.values():
        assert re.fullmatch(permissions, exchange.name)
        assert re.fullmatch(permissions, queue.name)
        assert re.fullmatch(permissions, "amq.default") is None
    assert re.fullmatch(RABBITMQ_API_PERMISSIONS["write"], exchange.name) is None
    assert observed["mandatory"] and observed["retry"] is False
    assert observed["connection"]["transport_options"]["confirm_publish"] is True
    assert observed["confirm_timeout"] == 3
    with pytest.raises(RuntimeError, match="unroutable"):
        observed["on_return"]()


def test_storage_error_rejects_without_hot_requeue_or_success_ack(monkeypatch):
    class App:
        def task(self, **options):
            assert options["acks_late"] and options["acks_on_failure_or_timeout"] is False
            return lambda handler: handler

    def unavailable(_envelope):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(inventory, "consume", unavailable)
    with pytest.raises(Reject) as error:
        inventory.register(App())({})
    assert error.value.requeue is False


class Event:
    def __init__(self):
        self.value = False

    def clear(self):
        self.value = False

    def set(self):
        self.value = True

    def is_set(self):
        return self.value

    def wait(self, timeout):
        pass


@pytest.mark.parametrize("failed_child,exitcode", [(0, 0), (0, 7), (1, 0), (1, 9)])
def test_supervisor_fails_and_stops_sibling_for_either_child_exit(monkeypatch, failed_child, exitcode):
    processes, handlers, ready = [], {}, Event()

    class Process:
        def __init__(self, **kwargs):
            self.exitcode = None
            self.terminated = False
            processes.append(self)

        def start(self):
            if len(processes) == 2:
                processes[failed_child].exitcode = exitcode

        def is_alive(self):
            return self.exitcode is None

        def terminate(self):
            self.terminated = True
            self.exitcode = -15

        def join(self, **kwargs):
            pass

    channel = SimpleNamespace(close=lambda: None, poll=lambda: False)
    context = SimpleNamespace(Event=lambda: ready, Pipe=lambda **_: (channel, channel), Process=Process)
    monkeypatch.setattr(relay.multiprocessing, "get_context", lambda mode: context)
    monkeypatch.setattr(relay.signal, "signal", lambda signum, callback: handlers.setdefault(signum, callback))
    assert relay.supervise(["worker"]) == 1
    assert processes[1 - failed_child].terminated
    assert not ready.is_set()


def test_supervisor_times_out_a_relay_that_never_reports_progress(monkeypatch):
    clock, ready, children = [0.0], Event(), []
    stopped = Event()
    stopped.wait = lambda _: clock.__setitem__(0, clock[0] + 16.0)

    class Process:
        def __init__(self, **kwargs):
            self.exitcode = None
            children.append(self)

        def start(self):
            pass

        def is_alive(self):
            return self.exitcode is None

        def terminate(self):
            self.exitcode = -15

        def join(self, **kwargs):
            pass

    channel = SimpleNamespace(close=lambda: None, poll=lambda: False)
    context = SimpleNamespace(Event=lambda: ready, Pipe=lambda **_: (channel, channel), Process=Process)
    monkeypatch.setattr(relay.multiprocessing, "get_context", lambda mode: context)
    monkeypatch.setattr(relay.threading, "Event", lambda: stopped)
    monkeypatch.setattr(relay.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(relay.signal, "signal", lambda *_: None)
    assert relay.supervise(["worker"]) == 1
    assert all(child.exitcode == -15 for child in children)
    assert not ready.is_set()


def test_readiness_requires_current_supervisor_relay_signal(monkeypatch):
    from edw_worker import app
    ready = Event()
    monkeypatch.setattr(app, "_RELAY_READY", ready)
    monkeypatch.setattr(app, "verify_dependencies", lambda **_: None)
    assert app.dependency_readiness(None) == {"status": "unavailable"}
    ready.set()
    assert app.dependency_readiness(None) == {"status": "ready"}
    ready.clear()
    assert app.dependency_readiness(None) == {"status": "unavailable"}


def test_worker_cli_propagates_supervisor_failure(monkeypatch):
    from edw_worker import __main__ as entry
    monkeypatch.setattr(entry.sys, "argv", ["edw_worker", "worker", "--concurrency=1"])
    monkeypatch.setattr(entry, "verify_dependencies", lambda: None)
    monkeypatch.setattr(entry, "register_worker_log_safety", lambda: None)
    monkeypatch.setattr(entry, "supervise", lambda arguments: 7)
    assert entry.main() == 7
