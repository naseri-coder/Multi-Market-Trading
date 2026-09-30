"""Framework-independent user data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TelegramUserIdentity:
    """Profile fields received from a trusted Telegram update."""

    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    is_bot: bool


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Stable user read model returned by the application layer."""

    id: int
    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    is_bot: bool
    status: str
    last_activity: datetime
    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        """Return the available Telegram display name."""
        return " ".join(part for part in (self.first_name, self.last_name) if part)


@dataclass(frozen=True, slots=True)
class UserRegistrationResult:
    """Result of an idempotent registration/update operation."""

    profile: UserProfile
    created: bool


@dataclass(frozen=True, slots=True)
class UserStatisticsBoundaries:
    """UTC cutoffs used by the statistics persistence query."""

    as_of: datetime
    active_since: datetime
    today_start: datetime
    week_start: datetime
    month_start: datetime


@dataclass(frozen=True, slots=True)
class UserStatisticsCounts:
    """Aggregate counts returned by the statistics repository."""

    total_users: int
    active_users: int
    new_users_today: int
    new_users_this_week: int
    new_users_this_month: int


@dataclass(frozen=True, slots=True)
class UserStatistics:
    """Administrator-facing user statistics snapshot."""

    total_users: int
    active_users: int
    inactive_users: int
    new_users_today: int
    new_users_this_week: int
    new_users_this_month: int
    active_window_days: int
    report_timezone: str
    generated_at: datetime
