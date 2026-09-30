"""Unit contract tests for production win-rate isolation."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.analytics.repository import SQLAlchemyWinRateRepository


class CapturingSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement

        class Result:
            @staticmethod
            def all():
                return []

        return Result()


@pytest.mark.asyncio
async def test_winrate_query_preserves_manual_and_requires_explicit_automation_opt_in() -> None:
    session = CapturingSession()
    repo = SQLAlchemyWinRateRepository(session)
    ended = datetime(2026, 9, 2, 12, tzinfo=UTC)

    await repo.fetch_outcome_counts(
        started_at=ended - timedelta(days=7),
        ended_at=ended,
    )

    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "LEFT OUTER JOIN signal_automation_metadata" in sql
    assert "signal_automation_metadata.signal_id IS NULL" in sql
    assert "signal_automation_metadata.counts_toward_performance IS true" in sql
