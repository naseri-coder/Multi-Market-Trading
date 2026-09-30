"""Application bootstrap and process entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence
from typing import NoReturn

from telegram.error import TelegramError

from app.bot.application import build_application
from app.core.config import Settings, load_settings
from app.core.errors import ConfigurationError, StartupError
from app.core.logging import configure_logging
from app.db.errors import DatabaseUnavailableError
from app.db.session import DatabaseManager
from app.lifecycle import ApplicationLifecycle
from app.modules.brooks_runtime.coordinator import BrooksFullCoreCoordinator
from app.modules.operations.coordinator import BrooksProductionOperationsCoordinator

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser without reading environment state."""
    parser = argparse.ArgumentParser(description="Crypto signal Telegram bot")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate environment configuration and exit without contacting Telegram",
    )
    parser.add_argument(
        "--check-db",
        action="store_true",
        help="validate configuration, verify PostgreSQL connectivity, and exit",
    )
    return parser


async def run_offline(
    settings: Settings,
    *,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run the real non-Telegram lifecycle until controlled shutdown."""
    database = DatabaseManager.from_settings(settings)
    lifecycle = ApplicationLifecycle(database, settings)
    runtime_state: dict[str, object] = {}
    stop_event = shutdown_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    registered_signals: list[signal.Signals] = []

    if shutdown_event is None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, stop_event.set)
            except (NotImplementedError, RuntimeError):
                continue
            registered_signals.append(signum)

    try:
        try:
            await lifecycle.startup_core(runtime_state)
        except DatabaseUnavailableError as exc:
            raise StartupError("Application runtime startup failed") from exc

        logger.info(
            "TELEGRAM_RUNTIME_DISABLED_OFFLINE_STARTUP_READY",
            extra={"event": "telegram_runtime_disabled_offline_startup_ready"},
        )
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            logger.info(
                "Offline runtime cancellation received",
                extra={"event": "telegram_runtime_disabled_offline_cancelled"},
            )
    finally:
        if "database" in runtime_state:
            await lifecycle.shutdown_core(runtime_state)
            logger.info(
                "TELEGRAM_RUNTIME_DISABLED_OFFLINE_SHUTDOWN_COMPLETE",
                extra={"event": "telegram_runtime_disabled_offline_shutdown_complete"},
            )
        for signum in registered_signals:
            loop.remove_signal_handler(signum)


def run_bot(settings: Settings) -> None:
    """Build the Telegram application and run long polling."""
    database = DatabaseManager.from_settings(settings)
    lifecycle = ApplicationLifecycle(database, settings)
    brooks_runtime = BrooksFullCoreCoordinator(
        settings=settings,
        database=database,
    )
    production_operations = BrooksProductionOperationsCoordinator(
        settings=settings,
        database=database,
    )

    async def post_init(application) -> None:
        await lifecycle.startup(application)
        await brooks_runtime.start(application)
        await production_operations.start(application)

    async def post_shutdown(application) -> None:
        await production_operations.shutdown(application)
        await brooks_runtime.shutdown(application)
        await lifecycle.shutdown(application)

    application = build_application(
        settings,
        post_init=post_init,
        post_shutdown=post_shutdown,
    )
    logger.info(
        "Telegram bot is starting",
        extra={"event": "bot_starting", "environment": settings.app_env},
    )

    try:
        application.run_polling(
            allowed_updates=None,
            drop_pending_updates=settings.telegram_drop_pending_updates,
            poll_interval=0.0,
            timeout=settings.telegram_poll_timeout,
        )
    except (DatabaseUnavailableError, TelegramError) as exc:
        raise StartupError("Application runtime startup failed") from exc


async def check_database(settings: Settings) -> bool:
    """Run a one-shot PostgreSQL health check and close all resources."""
    database = DatabaseManager.from_settings(settings)
    try:
        health = await database.health_check()
    except DatabaseUnavailableError:
        logger.error(
            "PostgreSQL health check failed",
            extra={"event": "database_health_failed"},
        )
        return False
    finally:
        await database.dispose()

    logger.info(
        "PostgreSQL health check passed",
        extra={"event": "database_health_passed", "latency_ms": health.latency_ms},
    )
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Validate configuration and run the application."""
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        configure_logging(level="ERROR", output_format="console")
        logger.error(
            "Application configuration is invalid",
            extra={"event": "configuration_invalid", "details": list(exc.details)},
        )
        return 2

    configure_logging(level=settings.log_level, output_format=settings.log_format)

    if args.check_config:
        logger.info(
            "Application configuration is valid",
            extra={"event": "configuration_valid", "environment": settings.app_env},
        )
        return 0

    if args.check_db:
        return 0 if asyncio.run(check_database(settings)) else 1

    try:
        if settings.telegram_runtime_enabled:
            run_bot(settings)
        else:
            asyncio.run(run_offline(settings))
    except StartupError:
        logger.exception(
            "Application startup failed",
            extra={"event": "startup_failed"},
        )
        return 1
    except KeyboardInterrupt:
        logger.info("Application interrupted", extra={"event": "application_interrupted"})

    return 0


def cli() -> NoReturn:
    """Console-script wrapper that propagates the process exit status."""
    raise SystemExit(main())
