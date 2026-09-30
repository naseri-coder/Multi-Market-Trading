"""Referral service anti-abuse, idempotency, and pagination tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.referrals.entities import (
    InvitedUserRecord,
    ReferralStatistics,
    ReferralUserRecord,
)
from app.modules.referrals.errors import (
    InvalidReferralError,
    ReferralCodeGenerationError,
    ReferralCodeNotFoundError,
    SelfReferralError,
)
from app.modules.referrals.service import ReferralService

NOW = datetime(2026, 9, 2, 4, 30, tzinfo=UTC)
REFERRER_CODE = "RABCDEFGHJKL"
SECOND_CODE = "RMNPQRSTUVW2"


def user(
    user_id: int,
    *,
    code: str | None = None,
    status: str = "ACTIVE",
) -> ReferralUserRecord:
    return ReferralUserRecord(
        id=user_id,
        telegram_user_id=1_000_000 + user_id,
        username=f"user{user_id}",
        first_name=f"User {user_id}",
        last_name=None,
        status=status,
        referral_code=code,
    )


class FakeReferralRepository:
    def __init__(self) -> None:
        self.users = {
            1: user(1, code=REFERRER_CODE),
            2: user(2),
            3: user(3),
        }
        self.referrals: dict[int, tuple[int, datetime]] = {}
        self.colliding_codes: set[str] = set()

    async def get_user(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> ReferralUserRecord | None:
        return self.users.get(user_id)

    async def find_user_by_code(
        self,
        referral_code: str,
    ) -> ReferralUserRecord | None:
        return next(
            (
                item
                for item in self.users.values()
                if item.referral_code == referral_code
            ),
            None,
        )

    async def assign_code_if_missing(
        self,
        user_id: int,
        referral_code: str,
    ) -> bool:
        if referral_code in self.colliding_codes:
            return False
        current = self.users[user_id]
        if current.referral_code is not None:
            return False
        self.users[user_id] = ReferralUserRecord(
            id=current.id,
            telegram_user_id=current.telegram_user_id,
            username=current.username,
            first_name=current.first_name,
            last_name=current.last_name,
            status=current.status,
            referral_code=referral_code,
        )
        return True

    async def create_referral(
        self,
        *,
        referrer_user_id: int,
        referred_user_id: int,
        referral_code: str,
        created_at: datetime,
    ) -> bool:
        if referred_user_id in self.referrals:
            return False
        self.referrals[referred_user_id] = (referrer_user_id, created_at)
        return True

    async def statistics_for_user(
        self,
        referrer_user_id: int,
    ) -> ReferralStatistics:
        invited = [
            self.users[referred_id]
            for referred_id, (owner, _) in self.referrals.items()
            if owner == referrer_user_id
        ]
        active = sum(item.status == "ACTIVE" for item in invited)
        return ReferralStatistics(
            total_invited=len(invited),
            active_invited=active,
            inactive_invited=len(invited) - active,
        )

    async def list_invited_users(
        self,
        referrer_user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[InvitedUserRecord, ...]:
        invited = sorted(
            (
                (referred_id, created_at)
                for referred_id, (owner, created_at) in self.referrals.items()
                if owner == referrer_user_id
            ),
            key=lambda row: (row[1], row[0]),
            reverse=True,
        )[offset : offset + limit]
        return tuple(
            InvitedUserRecord(
                user_id=item.id,
                username=item.username,
                first_name=item.first_name,
                last_name=item.last_name,
                status=item.status,
                invited_at=created_at,
            )
            for referred_id, created_at in invited
            for item in (self.users[referred_id],)
        )


async def test_code_is_stable_and_collision_retry_is_bounded() -> None:
    repository = FakeReferralRepository()
    repository.colliding_codes.add(REFERRER_CODE)
    candidates = iter((REFERRER_CODE, SECOND_CODE))
    service = ReferralService(repository, code_factory=lambda: next(candidates))

    assigned = await service.get_or_create_code(2)
    repeated = await service.get_or_create_code(2)

    assert assigned == SECOND_CODE
    assert repeated == SECOND_CODE


async def test_code_collision_exhaustion_is_explicit() -> None:
    repository = FakeReferralRepository()
    repository.colliding_codes.add(SECOND_CODE)
    service = ReferralService(repository, code_factory=lambda: SECOND_CODE)

    with pytest.raises(ReferralCodeGenerationError):
        await service.get_or_create_code(2)


async def test_referral_registration_is_idempotent_and_cannot_switch_referrer() -> None:
    repository = FakeReferralRepository()
    repository.users[3] = user(3, code=SECOND_CODE)
    service = ReferralService(repository, clock=lambda: NOW)

    first = await service.register_referral(2, REFERRER_CODE)
    duplicate = await service.register_referral(2, REFERRER_CODE)
    switched = await service.register_referral(2, SECOND_CODE)

    assert first.changed is True
    assert duplicate.changed is False
    assert switched.changed is False
    assert repository.referrals[2] == (1, NOW)


async def test_self_referral_invalid_and_missing_codes_are_rejected() -> None:
    service = ReferralService(FakeReferralRepository(), clock=lambda: NOW)

    with pytest.raises(SelfReferralError):
        await service.register_referral(1, REFERRER_CODE)
    with pytest.raises(ReferralCodeNotFoundError):
        await service.register_referral(2, SECOND_CODE)
    with pytest.raises(InvalidReferralError):
        await service.register_referral(2, "bad-code")


async def test_statistics_and_invited_users_are_paginated_ten_per_page() -> None:
    repository = FakeReferralRepository()
    for user_id in range(2, 14):
        repository.users[user_id] = user(
            user_id,
            status="BLOCKED" if user_id in (2, 3) else "ACTIVE",
        )
        repository.referrals[user_id] = (
            1,
            NOW + timedelta(minutes=user_id),
        )
    service = ReferralService(repository)

    dashboard = await service.get_dashboard(1)
    first = await service.get_invited_page(1, page=1)
    second = await service.get_invited_page(1, page=2)
    clamped = await service.get_invited_page(1, page=99)

    assert dashboard.referral_code == REFERRER_CODE
    assert dashboard.statistics.total_invited == 12
    assert dashboard.statistics.active_invited == 10
    assert dashboard.statistics.inactive_invited == 2
    assert dashboard.statistics.rewarded_invited == 0
    assert dashboard.statistics.rewards_enabled is False
    assert len(first.users) == 10
    assert len(second.users) == 2
    assert clamped == second


async def test_page_size_identifier_and_clock_are_validated() -> None:
    service = ReferralService(FakeReferralRepository())
    with pytest.raises(InvalidReferralError):
        await service.get_invited_page(1, page=1, page_size=20)
    with pytest.raises(InvalidReferralError):
        await service.get_dashboard(0)

    naive = ReferralService(
        FakeReferralRepository(),
        clock=lambda: datetime(2026, 9, 2),
    )
    with pytest.raises(RuntimeError, match="aware datetime"):
        await naive.register_referral(2, REFERRER_CODE)
