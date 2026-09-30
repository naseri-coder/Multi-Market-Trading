"""Async session factory, transaction boundary, and connection lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.engine import create_database_engine
from app.db.health import DatabaseHealth, check_database_health


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create sessions that remain usable after a successful commit."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


class DatabaseManager:
    """Own the AsyncEngine and provide transaction-safe sessions."""

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory or create_session_factory(engine)

    @classmethod
    def from_settings(cls, settings: Settings) -> DatabaseManager:
        """Construct the manager at the application composition root."""
        return cls(create_database_engine(settings))

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield one session and roll it back when application work fails."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> DatabaseHealth:
        """Check that the managed engine can reach PostgreSQL."""
        return await check_database_health(self.engine)

    async def dispose(self) -> None:
        """Close pooled connections during shutdown."""
        await self.engine.dispose()
