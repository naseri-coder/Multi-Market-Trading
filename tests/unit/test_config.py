"""Tests for typed environment configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, load_settings
from app.core.errors import ConfigurationError


def test_load_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", f"  {valid_token}  ")
    monkeypatch.setenv("DATABASE_URL", f"  {valid_database_url}  ")
    monkeypatch.setenv("APP_ENV", "PRODUCTION")
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("LOG_FORMAT", "JSON")
    monkeypatch.setenv("TELEGRAM_POLL_TIMEOUT", "25")
    monkeypatch.setenv("ADMIN_IDS", "123456789, 987654321")
    monkeypatch.setenv("REPORT_TIMEZONE", "Asia/Tehran")
    monkeypatch.setenv("BROADCAST_RATE_PER_SECOND", "15.5")
    monkeypatch.setenv("BROADCAST_BATCH_SIZE", "100")
    monkeypatch.setenv("BROADCAST_MAX_RETRIES", "3")
    monkeypatch.setenv("BROADCAST_RETRY_AFTER_CAP_SECONDS", "45")

    settings = load_settings()

    assert settings.app_env == "production"
    assert settings.log_level == "WARNING"
    assert settings.log_format == "json"
    assert settings.telegram_runtime_enabled is True
    assert settings.telegram_poll_timeout == 25
    assert settings.admin_ids == frozenset({123456789, 987654321})
    assert settings.report_timezone == "Asia/Tehran"
    assert settings.broadcast_rate_per_second == 15.5
    assert settings.broadcast_batch_size == 100
    assert settings.broadcast_max_retries == 3
    assert settings.broadcast_retry_after_cap_seconds == 45
    assert settings.telegram_bot_token.get_secret_value() == valid_token
    assert settings.database_url.get_secret_value() == valid_database_url


def test_env_example_is_valid(valid_token: str) -> None:
    example_path = Path(__file__).resolve().parents[2] / ".env.example"

    settings = Settings(_env_file=example_path)

    assert settings.app_env == "development"
    assert settings.log_format == "console"
    assert settings.telegram_bot_token.get_secret_value() != valid_token


def test_missing_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", valid_database_url)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("TELEGRAM_BOT_TOKEN" in detail for detail in exc_info.value.details)


def test_offline_mode_allows_missing_token(valid_database_url: str) -> None:
    settings = Settings(
        telegram_runtime_enabled=False,
        database_url=valid_database_url,
        _env_file=None,
    )

    assert settings.telegram_runtime_enabled is False
    assert settings.telegram_bot_token is None


def test_explicit_enabled_mode_still_requires_token(valid_database_url: str) -> None:
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Settings(
            telegram_runtime_enabled=True,
            database_url=valid_database_url,
            _env_file=None,
        )


def test_offline_mode_preserves_independent_shadow_runtime_setting(
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_runtime_enabled=False,
        performance_intelligence_shadow_mode=True,
        database_url=valid_database_url,
        _env_file=None,
    )

    assert settings.performance_intelligence_shadow_mode is True


@pytest.mark.parametrize(
    "flag_name",
    [
        "performance_reports_enabled",
        "brooks_runtime_enabled",
        "brooks_operations_enabled",
    ],
)
def test_offline_mode_rejects_telegram_dependent_runtime_features(
    valid_database_url: str,
    flag_name: str,
) -> None:
    with pytest.raises(ValueError, match="TELEGRAM_RUNTIME_ENABLED=false"):
        Settings(
            telegram_runtime_enabled=False,
            database_url=valid_database_url,
            _env_file=None,
            **{flag_name: True},
        )


def test_malformed_token_is_rejected_without_leaking_input(
    monkeypatch: pytest.MonkeyPatch,
    valid_database_url: str,
) -> None:
    secret_value = "not-a-real-secret-token"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret_value)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert secret_value not in str(exc_info.value.details)


def test_poll_timeout_bounds_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv("TELEGRAM_POLL_TIMEOUT", "0")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("telegram_poll_timeout" in detail for detail in exc_info.value.details)


def test_secret_is_masked_in_settings_representation(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)

    settings_representation = repr(load_settings())
    assert valid_token not in settings_representation
    assert valid_database_url not in settings_representation


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:password@localhost/database",
        "sqlite+aiosqlite:///database.db",
        "postgresql+asyncpg:///missing-host",
    ],
)
def test_non_async_postgresql_urls_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("database_url" in detail for detail in exc_info.value.details)


def test_sql_echo_is_forbidden_in_production(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_IDS", "123456789")
    monkeypatch.setenv("DB_ECHO", "true")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("DB_ECHO" in detail for detail in exc_info.value.details)


@pytest.mark.parametrize(
    "admin_ids",
    [
        "123,,456",
        "not-a-number",
        "0",
        "-123",
        str(2**63),
    ],
)
def test_invalid_admin_ids_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
    admin_ids: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv("ADMIN_IDS", admin_ids)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("admin_ids" in detail for detail in exc_info.value.details)


def test_duplicate_admin_ids_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv("ADMIN_IDS", "123456789,123456789,987654321")

    assert load_settings().admin_ids == frozenset({123456789, 987654321})


def test_production_requires_at_least_one_admin(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("ADMIN_IDS" in detail for detail in exc_info.value.details)


@pytest.mark.parametrize("timezone_name", ["", "Invalid/Timezone", "Asia Tehran"])
def test_invalid_report_timezone_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
    timezone_name: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv("REPORT_TIMEZONE", timezone_name)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any("report_timezone" in detail for detail in exc_info.value.details)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("BROADCAST_RATE_PER_SECOND", "31"),
        ("BROADCAST_BATCH_SIZE", "0"),
        ("BROADCAST_MAX_RETRIES", "6"),
        ("BROADCAST_RETRY_AFTER_CAP_SECONDS", "301"),
    ],
)
def test_invalid_broadcast_delivery_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert any(name.lower() in detail for detail in exc_info.value.details)
