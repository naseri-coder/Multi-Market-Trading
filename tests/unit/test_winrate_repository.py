"""Repository error-boundary tests for win-rate aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.modules.analytics.errors import WinRateRepositoryError
from app.modules.analytics.repository import SQLAlchemyWinRateRepository


async def test_sqlalchemy_failure_is_mapped_without_raw_database_details() -> None:
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("sensitive database detail")
    repository = SQLAlchemyWinRateRepository(session)
    ended_at = datetime(2026, 9, 2, 12, tzinfo=UTC)

    with pytest.raises(WinRateRepositoryError) as raised:
        await repository.fetch_outcome_counts(
            started_at=ended_at - timedelta(hours=24),
            ended_at=ended_at,
        )

    assert "sensitive" not in str(raised.value)
