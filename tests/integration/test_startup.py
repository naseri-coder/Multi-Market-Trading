"""Bootstrap-level startup tests that never contact Telegram."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from app.bot.application import build_application
from app.core.config import Settings
from app.core.errors import StartupError
from app.db.errors import DatabaseUnavailableError
from app.db.health import DatabaseHealth
from app.main import check_database, main, run_bot, run_offline

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeDatabaseManager:
    def __init__(self, *, fail_health: bool = False) -> None:
        self.fail_health = fail_health
        self.disposed = False
        self.health_checks = 0
        self.dispose_calls = 0

    async def health_check(self) -> DatabaseHealth:
        self.health_checks += 1
        if self.fail_health:
            raise DatabaseUnavailableError("unavailable")
        return DatabaseHealth(healthy=True, latency_ms=0.5)

    async def dispose(self) -> None:
        self.dispose_calls += 1
        self.disposed = True


def test_application_factory_registers_phase_twenty_handlers(
    valid_token: str,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        admin_ids={123456789},
        _env_file=None,
    )

    application = build_application(settings)

    assert application.bot.token == valid_token
    assert application.bot_data["admin_ids"] == frozenset({123456789})
    assert application.bot_data["report_timezone"] == "Asia/Tehran"
    assert application.bot_data["broadcast_rate_per_second"] == 20.0
    assert application.bot_data["broadcast_batch_size"] == 250
    assert application.bot_data["broadcast_max_retries"] == 2
    assert application.bot_data["broadcast_retry_after_cap_seconds"] == 60
    handlers = application.handlers[0]
    assert len(handlers) == 78
    assert isinstance(handlers[0], CommandHandler)
    assert isinstance(handlers[1], CommandHandler)
    assert isinstance(handlers[2], MessageHandler)
    assert isinstance(handlers[3], CommandHandler)
    assert isinstance(handlers[4], MessageHandler)
    assert isinstance(handlers[5], CommandHandler)
    assert isinstance(handlers[6], MessageHandler)
    assert isinstance(handlers[9], CallbackQueryHandler)
    assert isinstance(handlers[10], CommandHandler)
    assert isinstance(handlers[11], MessageHandler)
    assert isinstance(handlers[12], CallbackQueryHandler)
    assert isinstance(handlers[13], CommandHandler)
    assert isinstance(handlers[14], MessageHandler)
    assert isinstance(handlers[15], CallbackQueryHandler)
    assert isinstance(handlers[16], CommandHandler)
    assert isinstance(handlers[17], MessageHandler)
    assert isinstance(handlers[18], CommandHandler)
    assert isinstance(handlers[19], MessageHandler)
    assert isinstance(handlers[20], CallbackQueryHandler)
    assert isinstance(handlers[23], CallbackQueryHandler)
    assert isinstance(handlers[30], CallbackQueryHandler)
    assert isinstance(handlers[48], CallbackQueryHandler)
    assert isinstance(handlers[52], CallbackQueryHandler)
    assert isinstance(handlers[56], CallbackQueryHandler)
    assert isinstance(handlers[57], CommandHandler)
    assert isinstance(handlers[58], MessageHandler)
    assert isinstance(handlers[64], MessageHandler)
    assert isinstance(handlers[65], CallbackQueryHandler)
    assert isinstance(handlers[77], CallbackQueryHandler)
    protected = [handler for handler in handlers if hasattr(handler.callback, "__wrapped__")]
    assert len(protected) == 46
    assert all(handler in handlers[31:77] for handler in protected)
    assert len(application.handlers[1]) == 1
    assert len(application.error_handlers) == 1


def test_run_bot_starts_polling_with_validated_settings(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    captured: dict[str, object] = {}

    class FakeApplication:
        def run_polling(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        "app.main.build_application",
        lambda settings, **kwargs: FakeApplication(),
    )
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        telegram_poll_timeout=17,
        telegram_drop_pending_updates=True,
        _env_file=None,
    )

    assert settings.telegram_runtime_enabled is True

    run_bot(settings)

    assert captured["timeout"] == 17
    assert captured["drop_pending_updates"] is True
    assert captured["poll_interval"] == 0.0


def test_run_bot_maps_telegram_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    class FailingApplication:
        def run_polling(self, **kwargs: object) -> None:
            raise TelegramError("network unavailable")

    monkeypatch.setattr(
        "app.main.build_application",
        lambda settings, **kwargs: FailingApplication(),
    )
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        _env_file=None,
    )

    with pytest.raises(StartupError, match="Application runtime startup failed"):
        run_bot(settings)


def test_main_default_mode_reaches_telegram_application_factory(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        _env_file=None,
    )
    factory_calls: list[Settings] = []

    class FakeApplication:
        def run_polling(self, **kwargs: object) -> None:
            del kwargs

    def record_factory(value: Settings, **kwargs: object) -> FakeApplication:
        del kwargs
        factory_calls.append(value)
        return FakeApplication()

    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    monkeypatch.setattr("app.main.build_application", record_factory)

    async def fail_offline(value: Settings) -> None:
        del value
        pytest.fail("offline runtime must not be selected by default")

    monkeypatch.setattr("app.main.run_offline", fail_offline)

    assert settings.telegram_runtime_enabled is True
    assert main([]) == 0
    assert factory_calls == [settings]


def test_main_explicit_enabled_mode_selects_telegram_runtime(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_runtime_enabled=True,
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        _env_file=None,
    )
    calls: list[str] = []

    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    monkeypatch.setattr("app.main.run_bot", lambda value: calls.append("telegram"))

    async def fail_offline(value: Settings) -> None:
        del value
        pytest.fail("offline runtime must not be selected")

    monkeypatch.setattr("app.main.run_offline", fail_offline)

    assert main([]) == 0
    assert calls == ["telegram"]


async def test_offline_runtime_uses_real_lifecycle_without_ptb_and_stays_alive(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    valid_database_url: str,
) -> None:
    database = FakeDatabaseManager()
    settings = Settings(
        telegram_runtime_enabled=False,
        database_url=valid_database_url,
        _env_file=None,
    )
    shutdown_event = asyncio.Event()

    monkeypatch.setattr(
        "app.main.DatabaseManager.from_settings",
        lambda value: database,
    )
    monkeypatch.setattr(
        "app.main.build_application",
        lambda *args, **kwargs: pytest.fail("PTB application must not be constructed"),
    )
    caplog.set_level("INFO")

    task = asyncio.create_task(
        run_offline(settings, shutdown_event=shutdown_event)
    )
    for _ in range(50):
        await asyncio.sleep(0)
        if "TELEGRAM_RUNTIME_DISABLED_OFFLINE_STARTUP_READY" in caplog.text:
            break

    assert "TELEGRAM_RUNTIME_DISABLED_OFFLINE_STARTUP_READY" in caplog.text
    assert task.done() is False
    assert database.health_checks == 1

    shutdown_event.set()
    await asyncio.wait_for(task, timeout=1)

    assert database.dispose_calls == 1
    assert "TELEGRAM_RUNTIME_DISABLED_OFFLINE_SHUTDOWN_COMPLETE" in caplog.text


def test_main_offline_mode_never_falls_through_to_telegram(
    monkeypatch: pytest.MonkeyPatch,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_runtime_enabled=False,
        database_url=valid_database_url,
        _env_file=None,
    )
    calls: list[str] = []

    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    monkeypatch.setattr(
        "app.main.run_bot",
        lambda value: pytest.fail("Telegram runtime must not be selected"),
    )

    async def record_offline(value: Settings) -> None:
        assert value is settings
        calls.append("offline")

    monkeypatch.setattr("app.main.run_offline", record_offline)

    assert main([]) == 0
    assert calls == ["offline"]


def test_telegram_startup_failure_does_not_fallback_offline(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        _env_file=None,
    )
    offline_calls: list[str] = []

    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    def fail_telegram(value: Settings) -> None:
        del value
        raise StartupError("telegram startup failed")

    async def record_offline(value: Settings) -> None:
        del value
        offline_calls.append("offline")

    monkeypatch.setattr("app.main.run_bot", fail_telegram)
    monkeypatch.setattr("app.main.run_offline", record_offline)

    assert main([]) == 1
    assert offline_calls == []


def test_check_config_mode_exits_successfully_without_polling(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", valid_token)
    monkeypatch.setenv("DATABASE_URL", valid_database_url)
    monkeypatch.setattr(
        "app.main.run_bot",
        lambda settings: pytest.fail("polling must not start in --check-config mode"),
    )

    assert main(["--check-config"]) == 0


def test_module_entrypoint_validates_environment(
    valid_token: str,
    valid_database_url: str,
) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "TELEGRAM_BOT_TOKEN": valid_token,
            "DATABASE_URL": valid_database_url,
            "APP_ENV": "test",
            "LOG_FORMAT": "json",
            "ADMIN_IDS": "123456789",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "app", "--check-config"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert '"event": "configuration_valid"' in result.stderr


def test_invalid_environment_returns_nonzero_without_secret_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_value = "invalid-sensitive-value"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret_value)

    assert main(["--check-config"]) == 2


async def test_database_check_disposes_resources_on_success(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    database = FakeDatabaseManager()
    monkeypatch.setattr(
        "app.main.DatabaseManager.from_settings",
        lambda *args: database,
    )
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        _env_file=None,
    )

    assert await check_database(settings) is True
    assert database.disposed is True


async def test_database_check_disposes_resources_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    valid_token: str,
    valid_database_url: str,
) -> None:
    database = FakeDatabaseManager(fail_health=True)
    monkeypatch.setattr(
        "app.main.DatabaseManager.from_settings",
        lambda *args: database,
    )
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        _env_file=None,
    )

    assert await check_database(settings) is False
    assert database.disposed is True
