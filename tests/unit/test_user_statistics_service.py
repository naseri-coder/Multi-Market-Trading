"""Unit tests for user statistics business boundaries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.users.entities import UserStatisticsBoundaries, UserStatisticsCounts
from app.modules.users.statistics_service import UserStatisticsService


class FakeStatisticsRepository:
    def __init__(self, counts: UserStatisticsCounts) -> None:
        self.counts = counts
        self.boundaries: UserStatisticsBoundaries | None = None

    async def fetch_counts(
        self,
        boundaries: UserStatisticsBoundaries,
    ) -> UserStatisticsCounts:
        self.boundaries = boundaries
        return self.counts


def counts(*, total: int = 10, active: int = 4) -> UserStatisticsCounts:
    return UserStatisticsCounts(
        total_users=total,
        active_users=active,
        new_users_today=1,
        new_users_this_week=3,
        new_users_this_month=7,
    )


async def test_service_builds_tehran_calendar_boundaries_in_utc() -> None:
    now = datetime(2026, 9, 16, 8, 30, tzinfo=UTC)
    repository = FakeStatisticsRepository(counts())
    service = UserStatisticsService(repository, clock=lambda: now)

    statistics = await service.get_dashboard_statistics()

    assert repository.boundaries == UserStatisticsBoundaries(
        as_of=now,
        active_since=datetime(2026, 8, 17, 8, 30, tzinfo=UTC),
        today_start=datetime(2026, 9, 15, 20, 30, tzinfo=UTC),
        week_start=datetime(2026, 9, 13, 20, 30, tzinfo=UTC),
        month_start=datetime(2026, 8, 31, 20, 30, tzinfo=UTC),
    )
    assert statistics.active_window_days == 30
    assert statistics.report_timezone == "Asia/Tehran"
    assert statistics.generated_at == now


async def test_service_calculates_inactive_as_total_minus_active() -> None:
    repository = FakeStatisticsRepository(counts(total=25, active=9))
    service = UserStatisticsService(
        repository,
        clock=lambda: datetime(2026, 9, 16, tzinfo=UTC),
    )

    statistics = await service.get_dashboard_statistics()

    assert statistics.total_users == 25
    assert statistics.active_users == 9
    assert statistics.inactive_users == 16
    assert statistics.total_users == statistics.active_users + statistics.inactive_users


async def test_service_rejects_naive_clock() -> None:
    repository = FakeStatisticsRepository(counts())
    service = UserStatisticsService(
        repository,
        clock=lambda: datetime(2026, 9, 16),
    )

    with pytest.raises(RuntimeError, match="aware datetime"):
        await service.get_dashboard_statistics()

    assert repository.boundaries is None


async def test_service_rejects_inconsistent_repository_counts() -> None:
    repository = FakeStatisticsRepository(counts(total=2, active=3))
    service = UserStatisticsService(
        repository,
        clock=lambda: datetime(2026, 9, 16, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="inconsistent counts"):
        await service.get_dashboard_statistics()
