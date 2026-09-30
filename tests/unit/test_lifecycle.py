"""Tests for resource lifecycle coordination."""

from __future__ import annotations

from types import SimpleNamespace

from app.db.errors import DatabaseUnavailableError
from app.db.health import DatabaseHealth
from app.lifecycle import ApplicationLifecycle


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        performance_intelligence_shadow_mode=False,
        performance_reports_enabled=False,
    )


class FakeDatabase:
    def __init__(self, *, fail_health: bool = False) -> None:
        self.fail_health = fail_health
        self.disposed = False
        self.health_checks = 0
        self.dispose_calls = 0

    async def health_check(self) -> DatabaseHealth:
        self.health_checks += 1
        if self.fail_health:
            raise DatabaseUnavailableError("unavailable")
        return DatabaseHealth(healthy=True, latency_ms=1.25)

    async def dispose(self) -> None:
        self.dispose_calls += 1
        self.disposed = True


async def test_lifecycle_registers_and_disposes_database() -> None:
    database = FakeDatabase()
    application = SimpleNamespace(bot_data={}, bot=object())
    lifecycle = ApplicationLifecycle(database, settings())

    await lifecycle.startup(application)
    assert application.bot_data["database"] is database
    assert database.health_checks == 1

    await lifecycle.shutdown(application)
    assert "database" not in application.bot_data
    assert database.disposed is True
    assert database.dispose_calls == 1


async def test_core_lifecycle_runs_without_ptb_application() -> None:
    database = FakeDatabase()
    runtime_state: dict[str, object] = {}
    lifecycle = ApplicationLifecycle(database, settings())

    await lifecycle.startup_core(runtime_state)

    assert runtime_state["database"] is database
    assert database.health_checks == 1

    await lifecycle.shutdown_core(runtime_state)

    assert "database" not in runtime_state
    assert database.dispose_calls == 1


async def test_lifecycle_disposes_database_when_startup_fails() -> None:
    database = FakeDatabase(fail_health=True)
    application = SimpleNamespace(bot_data={}, bot=object())
    lifecycle = ApplicationLifecycle(database, settings())

    try:
        await lifecycle.startup(application)
    except DatabaseUnavailableError:
        pass
    else:
        raise AssertionError("DatabaseUnavailableError was not raised")

    assert "database" not in application.bot_data
    assert database.disposed is True
