import io
import logging
import sys

from celery.signals import after_setup_logger

from edw_worker.log_safety import (
    BrokerCredentialFilter,
    install_broker_credential_filter,
    register_worker_log_safety,
)


def _render(*records: tuple[str, tuple[object, ...], object]) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    install_broker_credential_filter(logging.Logger("worker-test", logging.INFO), handlers=[handler])
    logger = logging.Logger("worker-test", logging.INFO)
    logger.addHandler(handler)
    for message, arguments, exception in records:
        logger.warning(message, *arguments, exc_info=exception)
    return stream.getvalue()


def test_worker_log_filter_redacts_broker_password_from_third_party_warning():
    output = _render(
        (
            "Failed to setup delayed delivery for %r: %s",
            (
                "amqp://eid_worker:fixture-secret@rabbitmq:5672/eid-local",
                RuntimeError("Exchange.declare(403) configure refused"),
            ),
            None,
        ),
    )

    assert "fixture-secret" not in output
    assert "amqp://eid_worker:[REDACTED]@rabbitmq:5672/eid-local" in output
    assert "Exchange.declare(403) configure refused" in output


def test_worker_log_filter_redacts_exception_text_and_preserves_other_logs():
    try:
        raise RuntimeError("cannot reach amqps://worker:p%40ss@broker.example/vhost")
    except RuntimeError:
        exception = sys.exc_info()

    output = _render(
        ("ordinary worker warning for queue %s", ("generation",), None),
        ("connection failed", (), exception),
    )

    assert "ordinary worker warning for queue generation" in output
    assert "p%40ss" not in output
    assert "amqps://worker:[REDACTED]@broker.example/vhost" in output


def test_worker_log_filter_installation_is_idempotent():
    handler = logging.StreamHandler(io.StringIO())
    logger = logging.Logger("worker-test", logging.INFO)

    install_broker_credential_filter(logger, handlers=[handler])
    install_broker_credential_filter(logger, handlers=[handler])

    assert sum(isinstance(item, BrokerCredentialFilter) for item in handler.filters) == 1


def test_worker_log_filter_is_installed_after_celery_configures_logging():
    handler = logging.StreamHandler(io.StringIO())
    logger = logging.Logger("worker-test", logging.INFO)
    logger.addHandler(handler)
    register_worker_log_safety()

    after_setup_logger.send(sender=None, logger=logger)

    assert any(isinstance(item, BrokerCredentialFilter) for item in handler.filters)
