"""SQLAlchemy AsyncEngine construction."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Create a PostgreSQL-only async engine from validated settings."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        connect_args={
            "timeout": float(settings.db_connect_timeout_seconds),
            "server_settings": {"application_name": settings.app_name},
        },
    )
