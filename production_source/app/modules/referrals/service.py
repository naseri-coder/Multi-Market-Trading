"""Referral business rules independent from Telegram and SQLAlchemy."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.referrals.entities import (
    InvitedUsersPage,
    ReferralDashboard,
    ReferralRegistration,
)
from app.modules.referrals.errors import (
    InvalidReferralError,
    ReferralCodeGenerationError,
    ReferralCodeNotFoundError,
    ReferralUserNotFoundError,
    SelfReferralError,
)
from app.modules.referrals.repository import ReferralRepository

REFERRAL_PAGE_SIZE = 10
REFERRAL_CODE_PATTERN = re.compile(
    r"^R[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{11}$"
)
_REFERRAL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_RETRY_LIMIT = 5

ReferralClock = Callable[[], datetime]
ReferralCodeFactory = Callable[[], str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_referral_code() -> str:
    """Generate a URL-safe, non-sequential code with cryptographic randomness."""
    return "R" + "".join(secrets.choice(_REFERRAL_ALPHABET) for _ in range(11))


class ReferralService:
    """Own referral attribution, anti-abuse, statistics, and pagination rules."""

    def __init__(
        self,
        repository: ReferralRepository,
        *,
        clock: ReferralClock = utc_now,
        code_factory: ReferralCodeFactory = generate_referral_code,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.code_factory = code_factory

    async def get_dashboard(self, user_id: int) -> ReferralDashboard:
        referral_code = await self.get_or_create_code(user_id)
        statistics = await self.repository.statistics_for_user(user_id)
        self._validate_statistics(statistics)
        return ReferralDashboard(
            referral_code=referral_code,
            statistics=statistics,
        )

    async def get_or_create_code(self, user_id: int) -> str:
        self._validate_id(user_id)
        user = await self.repository.get_user(user_id, for_update=True)
        if user is None:
            raise ReferralUserNotFoundError("Referral user does not exist")
        if user.referral_code is not None:
            self._validate_code(user.referral_code)
            return user.referral_code

        for _ in range(_CODE_RETRY_LIMIT):
            candidate = self.code_factory()
            self._validate_code(candidate)
            if await self.repository.assign_code_if_missing(user_id, candidate):
                return candidate
        raise ReferralCodeGenerationError(
            "Unable to allocate a unique referral code"
        )

    async def register_referral(
        self,
        referred_user_id: int,
        referral_code: str,
    ) -> ReferralRegistration:
        self._validate_id(referred_user_id)
        normalized_code = referral_code.strip().upper()
        self._validate_code(normalized_code)

        referred_user = await self.repository.get_user(
            referred_user_id,
            for_update=True,
        )
        if referred_user is None:
            raise ReferralUserNotFoundError("Referred user does not exist")
        referrer = await self.repository.find_user_by_code(normalized_code)
        if referrer is None:
            raise ReferralCodeNotFoundError("Referral code does not exist")
        if referrer.id == referred_user_id:
            raise SelfReferralError("Users cannot refer themselves")

        changed = await self.repository.create_referral(
            referrer_user_id=referrer.id,
            referred_user_id=referred_user_id,
            referral_code=normalized_code,
            created_at=self._now(),
        )
        return ReferralRegistration(
            changed=changed,
            referrer_user_id=referrer.id if changed else None,
        )

    async def get_invited_page(
        self,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = REFERRAL_PAGE_SIZE,
    ) -> InvitedUsersPage:
        self._validate_id(user_id)
        self._validate_page(page, page_size)
        statistics = await self.repository.statistics_for_user(user_id)
        self._validate_statistics(statistics)
        total_pages = max(
            1,
            (statistics.total_invited + page_size - 1) // page_size,
        )
        current_page = min(page, total_pages)
        users = await self.repository.list_invited_users(
            user_id,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return InvitedUsersPage(
            users=users,
            page=current_page,
            page_size=page_size,
            total_items=statistics.total_invited,
            total_pages=total_pages,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("ReferralService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_id(user_id: int) -> None:
        if (
            not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            raise InvalidReferralError(
                "User identifier must be a positive integer"
            )

    @staticmethod
    def _validate_code(referral_code: str) -> None:
        is_valid = isinstance(
            referral_code,
            str,
        ) and REFERRAL_CODE_PATTERN.fullmatch(referral_code)
        if not is_valid:
            raise InvalidReferralError("Referral code format is invalid")

    @staticmethod
    def _validate_page(page: int, page_size: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidReferralError("Referral page must be a positive integer")
        if page_size != REFERRAL_PAGE_SIZE:
            raise InvalidReferralError("Referral page size must be 10")

    @staticmethod
    def _validate_statistics(statistics: object) -> None:
        total = getattr(statistics, "total_invited", -1)
        active = getattr(statistics, "active_invited", -1)
        inactive = getattr(statistics, "inactive_invited", -1)
        rewarded = getattr(statistics, "rewarded_invited", -1)
        rewards_enabled = getattr(statistics, "rewards_enabled", True)
        if (
            min(total, active, inactive, rewarded) < 0
            or active + inactive != total
            or rewarded != 0
            or rewards_enabled is not False
        ):
            raise RuntimeError("Referral repository returned invalid statistics")
