"""Integration test against a real PostgreSQL server."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import DatabaseManager

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real PostgreSQL integration test",
)


async def test_real_postgresql_connection_and_session(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)

    try:
        health = await database.health_check()
        assert health.healthy is True

        async with database.session() as session:
            result = await session.execute(text("SELECT current_database()"))
            assert result.scalar_one()
    finally:
        await database.dispose()
