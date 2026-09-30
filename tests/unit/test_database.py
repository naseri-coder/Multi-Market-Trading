"""Unit tests for asynchronous database infrastructure."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.base import NAMING_CONVENTION, Base
from app.db.dependencies import get_database_session
from app.db.engine import create_database_engine
from app.db.errors import DatabaseUnavailableError
from app.db.health import check_database_health
from app.db.session import DatabaseManager


class FakeResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class FakeConnection:
    async def execute(self, statement: object) -> FakeResult:
        return FakeResult(1)


class FakeConnectionContext:
    async def __aenter__(self) -> FakeConnection:
        return FakeConnection()

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext()

    async def dispose(self) -> None:
        self.disposed = True


class FailingConnectionContext:
    async def __aenter__(self) -> None:
        raise SQLAlchemyError("connection failed")

    async def __aexit__(self, *args: object) -> None:
        return None


class FailingEngine(FakeEngine):
    def connect(self) -> FailingConnectionContext:
        return FailingConnectionContext()


class FakeSession:
    def __init__(self) -> None:
        self.rollback_called = False

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def rollback(self) -> None:
        self.rollback_called = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


def test_base_has_stable_constraint_naming() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


async def test_engine_uses_asyncpg_and_validated_pool_settings(
    valid_token: str,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        db_pool_size=7,
        _env_file=None,
    )

    engine = create_database_engine(settings)
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "asyncpg"
        assert engine.pool.size() == 7
    finally:
        await engine.dispose()


async def test_health_check_returns_timing_for_valid_result() -> None:
    health = await check_database_health(FakeEngine())

    assert health.healthy is True
    assert health.latency_ms >= 0


async def test_health_check_maps_sqlalchemy_failure() -> None:
    try:
        await check_database_health(FailingEngine())
    except DatabaseUnavailableError as exc:
        assert isinstance(exc.__cause__, SQLAlchemyError)
    else:
        raise AssertionError("DatabaseUnavailableError was not raised")


async def test_session_rolls_back_on_application_error() -> None:
    fake_session = FakeSession()
    manager = DatabaseManager(FakeEngine(), FakeSessionFactory(fake_session))

    try:
        async with manager.session():
            raise RuntimeError("service failed")
    except RuntimeError:
        pass

    assert fake_session.rollback_called is True


async def test_database_dependency_yields_managed_session() -> None:
    fake_session = FakeSession()
    manager = DatabaseManager(FakeEngine(), FakeSessionFactory(fake_session))

    async with get_database_session(manager) as yielded_session:
        assert yielded_session is fake_session


async def test_dispose_closes_the_owned_engine() -> None:
    engine = FakeEngine()
    manager = DatabaseManager(engine, FakeSessionFactory(FakeSession()))

    await manager.dispose()

    assert engine.disposed is True
