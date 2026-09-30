"""Framework-neutral database dependency helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import DatabaseManager


@asynccontextmanager
async def get_database_session(database: DatabaseManager) -> AsyncIterator[AsyncSession]:
    """Provide a session to services without exposing factory internals."""
    async with database.session() as session:
        yield session
