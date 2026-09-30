"""PostgreSQL health checking."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.errors import DatabaseUnavailableError


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Successful database health-check result."""

    healthy: bool
    latency_ms: float


async def check_database_health(engine: AsyncEngine) -> DatabaseHealth:
    """Verify PostgreSQL connectivity with a minimal parameter-free query."""
    started_at = perf_counter()
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            if result.scalar_one() != 1:
                raise DatabaseUnavailableError("PostgreSQL returned an invalid health result")
    except DatabaseUnavailableError:
        raise
    except (OSError, SQLAlchemyError, TimeoutError) as exc:
        raise DatabaseUnavailableError("PostgreSQL health check failed") from exc

    latency_ms = round((perf_counter() - started_at) * 1000, 3)
    return DatabaseHealth(healthy=True, latency_ms=latency_ms)
