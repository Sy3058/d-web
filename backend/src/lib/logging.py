import logging
import re
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

_EMAIL_RE = re.compile(r"\b([a-zA-Z0-9._%+\-])[a-zA-Z0-9._%+\-]*(@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b")
_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\b")


def _mask_str(value: str) -> str:
    value = _EMAIL_RE.sub(r"\1***\2", value)
    value = _IP_RE.sub(r"\1.xxx", value)
    return value


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_str(value)
    if isinstance(value, dict):
        return {k: _mask_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_mask_value(v) for v in value)
    return value


def mask_pii(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    return {k: _mask_value(v) for k, v in event_dict.items()}


def configure_logging(debug: bool = False) -> None:
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        mask_pii,
    ]

    renderer: Any = (
        structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
