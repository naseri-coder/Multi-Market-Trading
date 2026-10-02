"""Real PostgreSQL tests for Phase 18 payment architecture."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.payments.errors import (
    DuplicatePaymentReferenceError,
    PaymentStateError,
)
from app.modules.payments.models import Payment
from app.modules.payments.repository import SQLAlchemyPaymentRepository
from app.modules.payments.service import PaymentService
from app.modules.subscriptions.models import SubscriptionPlan
from app.modules.users.models import User

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real payments integration test",
)


async def test_payment_states_snapshots_uniqueness_history_and_set_null_audit(
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
    now = datetime(2099, 9, 2, 3, tzinfo=UTC)
    suffix = uuid4().hex[:10].upper()
    telegram_user_id = (
        740_000_000_000_000_000
        + uuid4().int % 100_000_000_000_000
    )
    references = iter(
        (
            f"PAY_{suffix}_000000000001",
            f"PAY_{suffix}_000000000002",
            f"PAY_{suffix}_000000000003",
            f"PAY_{suffix}_000000000004",
        )
    )

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                user_id = (
                    await session.execute(
                        insert(User)
                        .values(
                            telegram_user_id=telegram_user_id,
                            first_name="Phase18",
                            last_activity=now,
                        )
                        .returning(User.id)
                    )
                ).scalar_one()
                plan_id = (
                    await session.execute(
                        insert(SubscriptionPlan)
                        .values(
                            name=f"P18 {suffix}",
                            duration_days=30,
                            price=Decimal("49.90"),
                            currency="USDT",
                            is_active=True,
                            created_at=now,
                            updated_at=now,
                        )
                        .returning(SubscriptionPlan.id)
                    )
                ).scalar_one()
                repository = SQLAlchemyPaymentRepository(session)
                service = PaymentService(
                    repository,
                    clock=lambda: now,
                    reference_factory=lambda: next(references),
                )

                success_payment = await service.create_payment(
                    user_id,
                    plan_id,
                    provider="test_gateway",
                )
                failed_payment = await service.create_payment(
                    user_id,
                    plan_id,
                    provider="test_gateway",
                )
                cancelled_payment = await service.create_payment(user_id, plan_id)
                assert success_payment.plan_name == f"P18 {suffix}"
                assert success_payment.amount == Decimal("49.90")
                assert success_payment.telegram_user_id == telegram_user_id

                success = await service.mark_success(
                    success_payment.id,
                    provider="test_gateway",
                    provider_reference=f"SUCCESS-{suffix}",
                )
                repeated = await service.mark_success(
                    success_payment.id,
                    provider="test_gateway",
                    provider_reference=f"SUCCESS-{suffix}",
                )
                failed = await service.mark_failed(
                    failed_payment.id,
                    provider="test_gateway",
                    provider_reference=f"FAILED-{suffix}",
                    failure_reason="declined",
                )
                cancelled = await service.cancel(cancelled_payment.id)
                assert success.changed is True
                assert repeated.changed is False
                assert failed.payment.failure_reason == "declined"
                assert cancelled.payment.status == "CANCELLED"

                with pytest.raises(PaymentStateError):
                    await service.cancel(success_payment.id)

                duplicate_provider = await service.create_payment(
                    user_id,
                    plan_id,
                    provider="test_gateway",
                )
                try:
                    async with session.begin_nested():
                        await service.mark_success(
                            duplicate_provider.id,
                            provider_reference=f"SUCCESS-{suffix}",
                        )
                except DuplicatePaymentReferenceError:
                    pass
                else:
                    raise AssertionError(
                        "Duplicate provider reference was accepted"
                    )

                history = await service.get_history_page(user_id)
                assert history.total_items == 4
                assert len(history.payments) == 4

                await session.execute(
                    delete(SubscriptionPlan).where(
                        SubscriptionPlan.id == plan_id
                    )
                )
                await session.flush()
                session.expire_all()
                after_plan_delete = await service.get_payment(success_payment.id)
                assert after_plan_delete.plan_id is None
                assert after_plan_delete.plan_name == f"P18 {suffix}"
                assert after_plan_delete.amount == Decimal("49.90")

                await session.execute(delete(User).where(User.id == user_id))
                await session.flush()
                session.expire_all()
                after_user_delete = await service.get_payment(success_payment.id)
                assert after_user_delete.user_id is None
                assert after_user_delete.telegram_user_id == telegram_user_id

                payment_count = await session.scalar(
                    select(func.count(Payment.id)).where(
                        Payment.payment_reference.like(f"PAY_{suffix}%")
                    )
                )
                assert payment_count == 4
            finally:
                await transaction.rollback()

        async with database.session() as verification:
            assert (
                await verification.scalar(
                    select(func.count(Payment.id)).where(
                        Payment.payment_reference.like(f"PAY_{suffix}%")
                    )
                )
                == 0
            )
    finally:
        await database.dispose()
