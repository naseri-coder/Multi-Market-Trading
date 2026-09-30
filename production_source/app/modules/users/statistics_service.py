"""Business rules for calendar-aware user statistics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.users.entities import UserStatistics, UserStatisticsBoundaries
from app.modules.users.statistics_repository import UserStatisticsRepository

StatisticsClock = Callable[[], datetime]
ACTIVE_WINDOW_DAYS = 30


def utc_now() -> datetime:
    """Return an aware UTC timestamp for statistics generation."""
    return datetime.now(UTC)


class UserStatisticsService:
    """Calculate UTC query boundaries and produce a stable dashboard snapshot."""

    def __init__(
        self,
        repository: UserStatisticsRepository,
        *,
        timezone_name: str = "Asia/Tehran",
        clock: StatisticsClock = utc_now,
    ) -> None:
        self.repository = repository
        self.timezone = ZoneInfo(timezone_name)
        self.clock = clock

    async def get_dashboard_statistics(self) -> UserStatistics:
        """Load rolling activity and calendar-based new-user statistics."""
        generated_at = self.clock()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise RuntimeError("UserStatisticsService clock must return an aware datetime")

        generated_at = generated_at.astimezone(UTC)
        local_now = generated_at.astimezone(self.timezone)
        today_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start_local = today_start_local - timedelta(days=today_start_local.weekday())
        month_start_local = today_start_local.replace(day=1)

        boundaries = UserStatisticsBoundaries(
            as_of=generated_at,
            active_since=generated_at - timedelta(days=ACTIVE_WINDOW_DAYS),
            today_start=today_start_local.astimezone(UTC),
            week_start=week_start_local.astimezone(UTC),
            month_start=month_start_local.astimezone(UTC),
        )
        counts = await self.repository.fetch_counts(boundaries)

        if (
            min(
                counts.total_users,
                counts.active_users,
                counts.new_users_today,
                counts.new_users_this_week,
                counts.new_users_this_month,
            )
            < 0
            or counts.active_users > counts.total_users
        ):
            raise RuntimeError("User statistics repository returned inconsistent counts")

        return UserStatistics(
            total_users=counts.total_users,
            active_users=counts.active_users,
            inactive_users=counts.total_users - counts.active_users,
            new_users_today=counts.new_users_today,
            new_users_this_week=counts.new_users_this_week,
            new_users_this_month=counts.new_users_this_month,
            active_window_days=ACTIVE_WINDOW_DAYS,
            report_timezone=self.timezone.key,
            generated_at=generated_at,
        )
