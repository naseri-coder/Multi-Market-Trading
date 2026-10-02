"""Real PostgreSQL tests for Phase 19 referral architecture."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.referrals.errors import SelfReferralError
from app.modules.referrals.models import Referral
from app.modules.referrals.repository import SQLAlchemyReferralRepository
from app.modules.referrals.service import ReferralService
from app.modules.users.models import User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real referrals integration test",
)


async def test_referral_codes_attribution_isolation_pagination_and_cascade(
    valid_token: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    now = datetime(2099, 9, 2, 4, 30, tzinfo=UTC)
    base_id = 780_000_000_000_000_000 + uuid4().int % 100_000_000_000_000
    codes = iter(
        (
            "RABCDEFGHJKL",
            "RMNPQRSTUVW2",
        )
    )

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                user_ids = (
                    await session.execute(
                        insert(User)
                        .values(
                            [
                                {
                                    "telegram_user_id": base_id + index,
                                    "first_name": f"P19-{index}",
                                    "last_activity": now,
                                    "status": "BLOCKED" if index == 2 else "ACTIVE",
                                }
                                for index in range(14)
                            ]
                        )
                        .returning(User.id)
                    )
                ).scalars().all()
                repository = SQLAlchemyReferralRepository(session)
                service = ReferralService(
                    repository,
                    clock=lambda: now,
                    code_factory=lambda: next(codes),
                )

                referrer_code = await service.get_or_create_code(user_ids[0])
                repeated_code = await service.get_or_create_code(user_ids[0])
                other_code = await service.get_or_create_code(user_ids[1])
                assert referrer_code == repeated_code
                assert other_code != referrer_code

                for index, referred_id in enumerate(user_ids[2:], start=1):
                    service.clock = lambda index=index: now + timedelta(
                        minutes=index
                    )
                    result = await service.register_referral(
                        referred_id,
                        referrer_code,
                    )
                    assert result.changed is True

                duplicate = await service.register_referral(
                    user_ids[2],
                    other_code,
                )
                assert duplicate.changed is False
                with pytest.raises(SelfReferralError):
                    await service.register_referral(user_ids[0], referrer_code)

                dashboard = await service.get_dashboard(user_ids[0])
                first = await service.get_invited_page(user_ids[0], page=1)
                second = await service.get_invited_page(user_ids[0], page=2)
                isolated = await service.get_invited_page(user_ids[1], page=1)
                assert dashboard.statistics.total_invited == 12
                assert dashboard.statistics.active_invited == 11
                assert dashboard.statistics.inactive_invited == 1
                assert dashboard.statistics.rewarded_invited == 0
                assert len(first.users) == 10
                assert len(second.users) == 2
                assert isolated.total_items == 0

                await session.execute(
                    delete(User).where(User.id == user_ids[2])
                )
                await session.flush()
                remaining = await session.scalar(
                    select(func.count(Referral.id)).where(
                        Referral.referrer_user_id == user_ids[0]
                    )
                )
                assert remaining == 11
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            assert (
                await verification.scalar(
                    select(func.count(Referral.id)).join(
                        User,
                        User.id == Referral.referrer_user_id,
                    ).where(User.telegram_user_id == base_id)
                )
                == 0
            )
    finally:
        await database.dispose()
