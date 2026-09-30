"""Central logging configuration with JSON production output."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

_TELEGRAM_TOKEN_PATTERN = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")
_NOISY_HTTP_LOGGERS = ("httpx", "httpcore")

_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def redact_sensitive_data(value: str) -> str:
    """Remove Telegram bot tokens from formatted log output."""
    return _TELEGRAM_TOKEN_PATTERN.sub("<redacted-telegram-token>", value)


class RedactingFormatter(logging.Formatter):
    """Apply secret redaction after standard record formatting."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_data(super().format(record))


class JsonFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        return redact_sensitive_data(serialized)


def configure_logging(
    *,
    level: str = "INFO",
    output_format: Literal["json", "console"] = "json",
) -> None:
    """Configure the root logger exactly once per invocation."""
    handler = logging.StreamHandler()
    if output_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            RedactingFormatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in _NOISY_HTTP_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    logging.captureWarnings(True)
