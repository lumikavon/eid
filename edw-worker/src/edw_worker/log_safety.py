import logging
import re
import traceback
from collections.abc import Iterable

from celery.signals import after_setup_logger


_BROKER_PASSWORD = re.compile(r"(amqps?://[^\s/:@]+:)[^\s/@]+(@)", re.IGNORECASE)
_FILTER_DISPATCH_UID = "edw-worker-broker-credential-filter"


def _redact_broker_credentials(value: str) -> str:
    return _BROKER_PASSWORD.sub(r"\1[REDACTED]\2", value)


class BrokerCredentialFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_broker_credentials(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = _redact_broker_credentials(
                "".join(traceback.format_exception(*record.exc_info))
            )
        return True


def install_broker_credential_filter(
    logger: logging.Logger,
    *,
    handlers: Iterable[logging.Handler] | None = None,
    **_kwargs: object,
) -> None:
    for handler in handlers if handlers is not None else logger.handlers:
        if not any(isinstance(item, BrokerCredentialFilter) for item in handler.filters):
            handler.addFilter(BrokerCredentialFilter())


def register_worker_log_safety() -> None:
    after_setup_logger.connect(
        install_broker_credential_filter,
        weak=False,
        dispatch_uid=_FILTER_DISPATCH_UID,
    )
