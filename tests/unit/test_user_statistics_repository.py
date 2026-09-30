"""Unit tests for the SQLAlchemy user statistics aggregate query."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.modules.users.entities import UserStatisticsBoundaries
from app.modules.users.errors import UserStatisticsRepositoryError
from app.modules.users.statistics_repository import SQLAlchemyUserStatisticsRepository


class FakeResult:
    def __init__(self, row: SimpleNamespace) -> None:
        self.row = row

    def one(self) -> SimpleNamespace:
        return self.row


class FakeSession:
    def __init__(
        self,
        row: SimpleNamespace | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.row = row
        self.error = error
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error
        assert self.row is not None
        return FakeResult(self.row)


def boundaries() -> UserStatisticsBoundaries:
    return UserStatisticsBoundaries(
        as_of=datetime(2026, 9, 16, 8, 30, tzinfo=UTC),
        active_since=datetime(2026, 8, 17, 8, 30, tzinfo=UTC),
        today_start=datetime(2026, 9, 15, 20, 30, tzinfo=UTC),
        week_start=datetime(2026, 9, 13, 20, 30, tzinfo=UTC),
        month_start=datetime(2026, 8, 31, 20, 30, tzinfo=UTC),
    )


async def test_repository_maps_all_counts_in_one_query() -> None:
    session = FakeSession(
        SimpleNamespace(
            total_users=20,
            active_users=8,
            new_users_today=2,
            new_users_this_week=5,
            new_users_this_month=11,
        )
    )
    repository = SQLAlchemyUserStatisticsRepository(session)  # type: ignore[arg-type]

    result = await repository.fetch_counts(boundaries())

    assert result.total_users == 20
    assert result.active_users == 8
    assert result.new_users_today == 2
    assert result.new_users_this_week == 5
    assert result.new_users_this_month == 11
    assert len(session.statements) == 1


async def test_repository_query_uses_status_activity_and_calendar_filters() -> None:
    session = FakeSession(
        SimpleNamespace(
            total_users=0,
            active_users=0,
            new_users_today=0,
            new_users_this_week=0,
            new_users_this_month=0,
        )
    )
    repository = SQLAlchemyUserStatisticsRepository(session)  # type: ignore[arg-type]

    await repository.fetch_counts(boundaries())

    sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert sql.count("FILTER (WHERE") == 4
    assert "users.status = 'ACTIVE'" in sql
    assert "users.last_activity >=" in sql
    assert sql.count("users.created_at >=") == 3
    assert sql.count("users.created_at <=") == 3


async def test_repository_maps_database_errors() -> None:
    session = FakeSession(error=SQLAlchemyError("database failed"))
    repository = SQLAlchemyUserStatisticsRepository(session)  # type: ignore[arg-type]

    with pytest.raises(UserStatisticsRepositoryError) as exc_info:
        await repository.fetch_counts(boundaries())

    assert isinstance(exc_info.value.__cause__, SQLAlchemyError)
