"""Real PostgreSQL tests for Phase 17 subscriptions."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.subscriptions.entities import (
    CreateSubscriptionPlan,
    UpdateSubscriptionPlan,
)
from app.modules.subscriptions.errors import (
    ActiveSubscriptionExistsError,
    DuplicateSubscriptionPlanError,
    SubscriptionPlanInUseError,
)
from app.modules.subscriptions.models import Subscription, SubscriptionPlan
from app.modules.subscriptions.repository import SQLAlchemySubscriptionRepository
from app.modules.subscriptions.service import SubscriptionService
from app.modules.users.models import User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real subscriptions integration test",
)


async def test_plan_lifecycle_activation_snapshot_expiry_and_cascades(
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
    now = datetime(2099, 9, 2, 2, tzinfo=UTC)
    suffix = uuid4().hex[:10]
    telegram_user_id = (
        720_000_000_000_000_000
        + uuid4().int % 100_000_000_000_000
    )

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                user_id = (
                    await session.execute(
                        User.__table__.insert()
                        .values(
                            telegram_user_id=telegram_user_id,
                            first_name="Phase17",
                            last_activity=now,
                        )
                        .returning(User.id)
                    )
                ).scalar_one()
                repository = SQLAlchemySubscriptionRepository(session)
                service = SubscriptionService(repository, clock=lambda: now)
                monthly = await service.create_plan(
                    CreateSubscriptionPlan(
                        name=f"Monthly {suffix}",
                        duration_days=30,
                        price=Decimal("20.00"),
                        currency="usdt",
                        description="Original terms",
                    )
                )
                unused = await service.create_plan(
                    CreateSubscriptionPlan(
                        name=f"Unused {suffix}",
                        duration_days=7,
                        price=Decimal("0.00"),
                        currency="USDT",
                    )
                )

                with pytest.raises(DuplicateSubscriptionPlanError):
                    async with session.begin_nested():
                        await service.create_plan(
                            CreateSubscriptionPlan(
                                name=monthly.name.upper(),
                                duration_days=60,
                                price=Decimal("30.00"),
                                currency="USDT",
                            )
                        )

                activated = await service.activate_subscription(
                    user_id,
                    monthly.id,
                )
                assert activated.expires_at == now + timedelta(days=30)
                assert activated.plan_name == monthly.name
                assert activated.price == Decimal("20.00")
                with pytest.raises(ActiveSubscriptionExistsError):
                    await service.activate_subscription(user_id, monthly.id)

                edited = await service.update_plan(
                    monthly.id,
                    UpdateSubscriptionPlan(
                        name=f"Monthly Plus {suffix}",
                        duration_days=45,
                        price=Decimal("35.00"),
                        currency="USDT",
                        description="Edited terms",
                        is_active=True,
                    ),
                )
                persisted = await service.get_user_subscription(user_id)
                assert persisted is not None
                assert persisted.plan_name == monthly.name
                assert persisted.duration_days == 30
                assert persisted.price == Decimal("20.00")
                assert edited.name != persisted.plan_name

                expired = await service.expire_user_subscription(user_id)
                assert expired.status == "EXPIRED"
                assert expired.ended_at == now
                reactivated = await service.activate_subscription(user_id, edited.id)
                assert reactivated.plan_name == edited.name
                assert reactivated.duration_days == 45

                later = now + timedelta(days=46)
                later_service = SubscriptionService(repository, clock=lambda: later)
                assert await later_service.get_user_subscription(user_id) is None

                with pytest.raises(SubscriptionPlanInUseError):
                    await later_service.delete_plan(edited.id)
                await later_service.delete_plan(unused.id)
                assert await repository.get_plan(unused.id) is None

                await session.execute(delete(User).where(User.id == user_id))
                subscription_count = await session.scalar(
                    select(func.count(Subscription.id)).where(
                        Subscription.user_id == user_id
                    )
                )
                plan_count = await session.scalar(
                    select(func.count(SubscriptionPlan.id)).where(
                        SubscriptionPlan.id == edited.id
                    )
                )
                assert subscription_count == 0
                assert plan_count == 1
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            assert (
                await verification.scalar(
                    select(func.count(User.id)).where(
                        User.telegram_user_id == telegram_user_id
                    )
                )
                == 0
            )
            assert (
                await verification.scalar(
                    select(func.count(SubscriptionPlan.id)).where(
                        SubscriptionPlan.name.ilike(f"%{suffix}%")
                    )
                )
                == 0
            )
    finally:
        await database.dispose()
