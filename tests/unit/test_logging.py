"""Tests for central logging configuration."""

from __future__ import annotations

import json
import logging

from app.core.logging import configure_logging


def test_json_logging_contains_structured_context(capsys) -> None:
    configure_logging(level="INFO", output_format="json")
    logging.getLogger("test.logger").info(
        "bootstrap ready",
        extra={"event": "bootstrap_ready", "phase": 1},
    )

    payload = json.loads(capsys.readouterr().err)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["message"] == "bootstrap ready"
    assert payload["event"] == "bootstrap_ready"
    assert payload["phase"] == 1
    assert payload["timestamp"].endswith("+00:00")


def test_reconfiguration_does_not_duplicate_handlers() -> None:
    configure_logging(level="INFO", output_format="console")
    configure_logging(level="DEBUG", output_format="json")

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1
    assert root_logger.level == logging.DEBUG


def test_telegram_tokens_are_redacted_from_json_logs(capsys) -> None:
    configure_logging(level="INFO", output_format="json")
    token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef_1234"

    logging.getLogger("test.logger").error(
        "Telegram request failed: https://api.telegram.org/bot%s/getMe",
        token,
    )

    output = capsys.readouterr().err
    assert token not in output
    assert "<redacted-telegram-token>" in output


def test_telegram_tokens_are_redacted_from_console_logs(capsys) -> None:
    configure_logging(level="INFO", output_format="console")
    token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef_1234"

    logging.getLogger("test.logger").error("token=%s", token)

    output = capsys.readouterr().err
    assert token not in output
    assert "<redacted-telegram-token>" in output


def test_http_transport_info_logs_are_suppressed(capsys) -> None:
    configure_logging(level="INFO", output_format="json")

    logging.getLogger("httpx").info("request URL should not be logged")

    assert capsys.readouterr().err == ""
