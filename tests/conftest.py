"""Shared test configuration."""

from __future__ import annotations

import pytest

from app.core.config import clear_settings_cache

ENVIRONMENT_KEYS = (
    "APP_NAME",
    "APP_ENV",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "TELEGRAM_RUNTIME_ENABLED",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_POLL_TIMEOUT",
    "TELEGRAM_DROP_PENDING_UPDATES",
    "ADMIN_IDS",
    "REPORT_TIMEZONE",
    "BROADCAST_RATE_PER_SECOND",
    "BROADCAST_BATCH_SIZE",
    "BROADCAST_MAX_RETRIES",
    "BROADCAST_RETRY_AFTER_CAP_SECONDS",
    "DATABASE_URL",
    "DB_ECHO",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_CONNECT_TIMEOUT_SECONDS",
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Prevent developer environment and local dotenv files from affecting tests."""
    clear_settings_cache()
    monkeypatch.chdir(tmp_path)
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    clear_settings_cache()


@pytest.fixture
def valid_token() -> str:
    """Return a syntactically valid, non-functional Telegram token."""
    return "123456789:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


@pytest.fixture
def valid_database_url() -> str:
    """Return a syntactically valid local PostgreSQL URL."""
    return "postgresql+asyncpg://crypto_bot:test_password@127.0.0.1:5432/crypto_bot_test"
