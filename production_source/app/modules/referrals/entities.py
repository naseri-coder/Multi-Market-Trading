"""Framework-independent referral read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReferralUserRecord:
    """Minimal user snapshot used by the referral domain."""

    id: int
    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    status: str
    referral_code: str | None

    @property
    def full_name(self) -> str:
        return " ".join(
            part for part in (self.first_name, self.last_name) if part
        )


@dataclass(frozen=True, slots=True)
class InvitedUserRecord:
    """One invited user shown in the referrer's paginated list."""

    user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    status: str
    invited_at: datetime

    @property
    def full_name(self) -> str:
        return " ".join(
            part for part in (self.first_name, self.last_name) if part
        )


@dataclass(frozen=True, slots=True)
class ReferralRegistration:
    """Idempotent result of applying one start payload."""

    changed: bool
    referrer_user_id: int | None


@dataclass(frozen=True, slots=True)
class ReferralStatistics:
    """Aggregated referral counts without any reward calculation."""

    total_invited: int
    active_invited: int
    inactive_invited: int
    rewarded_invited: int = 0
    rewards_enabled: bool = False


@dataclass(frozen=True, slots=True)
class ReferralDashboard:
    """Referral code and statistics shown on the main screen."""

    referral_code: str
    statistics: ReferralStatistics


@dataclass(frozen=True, slots=True)
class InvitedUsersPage:
    """One fixed-size page of invited users."""

    users: tuple[InvitedUserRecord, ...]
    page: int
    page_size: int
    total_items: int
    total_pages: int
