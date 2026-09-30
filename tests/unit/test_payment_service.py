"""Gateway-independent payment service tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.payments.entities import PaymentRecord, PaymentUserSnapshot
from app.modules.payments.errors import (
    InvalidPaymentError,
    PaymentNotFoundError,
    PaymentPlanNotFoundError,
    PaymentStateError,
    PaymentUserNotFoundError,
)
from app.modules.payments.models import PaymentStatus
from app.modules.payments.service import PaymentService
from app.modules.subscriptions.entities import SubscriptionPlanRecord

NOW = datetime(2026, 9, 2, 3, tzinfo=UTC)
REFERENCE = "PAY_1234567890ABCDEF1234567890ABCDEF"


def plan(
    plan_id: int = 3,
    *,
    active: bool = True,
    price: Decimal = Decimal("25.00"),
) -> SubscriptionPlanRecord:
    return SubscriptionPlanRecord(
        id=plan_id,
        name="VIP Monthly",
        duration_days=30,
        price=price,
        currency="USDT",
        description=None,
        is_active=active,
        created_at=NOW,
        updated_at=NOW,
    )


class FakePaymentRepository:
    def __init__(self) -> None:
        self.users = {7: PaymentUserSnapshot(id=7, telegram_user_id=7007)}
        self.plans = {3: plan()}
        self.payments: dict[int, PaymentRecord] = {}
        self.next_id = 1

    async def get_user(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> PaymentUserSnapshot | None:
        return self.users.get(user_id)

    async def get_plan(
        self,
        plan_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionPlanRecord | None:
        return self.plans.get(plan_id)

    async def create_payment(
        self,
        *,
        payment_reference: str,
        user: PaymentUserSnapshot,
        plan: SubscriptionPlanRecord,
        provider: str | None,
        created_at: datetime,
    ) -> PaymentRecord:
        record = PaymentRecord(
            id=self.next_id,
            payment_reference=payment_reference,
            user_id=user.id,
            telegram_user_id=user.telegram_user_id,
            plan_id=plan.id,
            subscription_id=None,
            plan_name=plan.name,
            duration_days=plan.duration_days,
            amount=plan.price,
            currency=plan.currency,
            status=PaymentStatus.PENDING.value,
            provider=provider,
            provider_reference=None,
            failure_reason=None,
            finalized_at=None,
            created_at=created_at,
            updated_at=created_at,
        )
        self.payments[record.id] = record
        self.next_id += 1
        return record

    async def get_payment(
        self,
        payment_id: int,
        *,
        for_update: bool = False,
    ) -> PaymentRecord | None:
        return self.payments.get(payment_id)

    async def transition_payment(
        self,
        payment_id: int,
        *,
        status: str,
        provider: str | None,
        provider_reference: str | None,
        failure_reason: str | None,
        finalized_at: datetime,
    ) -> PaymentRecord | None:
        current = self.payments.get(payment_id)
        if current is None or current.status != PaymentStatus.PENDING.value:
            return None
        updated = replace(
            current,
            status=status,
            provider=provider,
            provider_reference=provider_reference,
            failure_reason=failure_reason,
            finalized_at=finalized_at,
            updated_at=finalized_at,
        )
        self.payments[payment_id] = updated
        return updated

    async def count_for_user(self, user_id: int) -> int:
        return len([item for item in self.payments.values() if item.user_id == user_id])

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[PaymentRecord, ...]:
        items = sorted(
            (item for item in self.payments.values() if item.user_id == user_id),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return tuple(items[offset : offset + limit])


def service(repository: FakePaymentRepository) -> PaymentService:
    return PaymentService(
        repository,
        clock=lambda: NOW,
        reference_factory=lambda: REFERENCE,
    )


async def test_create_payment_snapshots_user_plan_amount_and_provider() -> None:
    repository = FakePaymentRepository()

    created = await service(repository).create_payment(
        7,
        3,
        provider="test_gateway",
    )

    assert created.payment_reference == REFERENCE
    assert created.telegram_user_id == 7007
    assert created.plan_name == "VIP Monthly"
    assert created.duration_days == 30
    assert created.amount == Decimal("25.00")
    assert created.currency == "USDT"
    assert created.provider == "TEST_GATEWAY"
    assert created.status == PaymentStatus.PENDING.value
    assert created.finalized_at is None


async def test_missing_user_plan_inactive_and_free_plan_are_rejected() -> None:
    repository = FakePaymentRepository()
    current_service = service(repository)

    with pytest.raises(PaymentUserNotFoundError):
        await current_service.create_payment(999, 3)
    with pytest.raises(PaymentPlanNotFoundError):
        await current_service.create_payment(7, 999)

    repository.plans[3] = plan(active=False)
    with pytest.raises(InvalidPaymentError, match="Inactive"):
        await current_service.create_payment(7, 3)

    repository.plans[3] = plan(price=Decimal("0"))
    with pytest.raises(InvalidPaymentError, match="Free"):
        await current_service.create_payment(7, 3)


async def test_success_transition_is_terminal_and_idempotent() -> None:
    repository = FakePaymentRepository()
    current_service = service(repository)
    created = await current_service.create_payment(7, 3, provider="gateway")

    first = await current_service.mark_success(
        created.id,
        provider="gateway",
        provider_reference="provider-123",
    )
    repeated = await current_service.mark_success(
        created.id,
        provider="gateway",
        provider_reference="provider-123",
    )

    assert first.changed is True
    assert first.payment.status == PaymentStatus.SUCCESS.value
    assert first.payment.finalized_at == NOW
    assert repeated.changed is False
    assert repeated.payment == first.payment
    with pytest.raises(PaymentStateError):
        await current_service.cancel(created.id)


async def test_failed_transition_requires_reason_and_is_idempotent() -> None:
    repository = FakePaymentRepository()
    current_service = service(repository)
    created = await current_service.create_payment(7, 3)

    with pytest.raises(InvalidPaymentError, match="Failure reason"):
        await current_service.mark_failed(created.id, failure_reason=" ")

    failed = await current_service.mark_failed(
        created.id,
        failure_reason="  declined  ",
    )
    repeated = await current_service.mark_failed(
        created.id,
        failure_reason="declined",
    )

    assert failed.changed is True
    assert failed.payment.failure_reason == "declined"
    assert failed.payment.status == PaymentStatus.FAILED.value
    assert repeated.changed is False


async def test_cancel_transition_sets_terminal_timestamp() -> None:
    repository = FakePaymentRepository()
    current_service = service(repository)
    created = await current_service.create_payment(7, 3)

    cancelled = await current_service.cancel(created.id)

    assert cancelled.changed is True
    assert cancelled.payment.status == PaymentStatus.CANCELLED.value
    assert cancelled.payment.finalized_at == NOW
    assert cancelled.payment.failure_reason is None


async def test_provider_reference_rules_and_provider_immutability() -> None:
    repository = FakePaymentRepository()
    current_service = service(repository)
    no_provider = await current_service.create_payment(7, 3)

    with pytest.raises(InvalidPaymentError, match="requires"):
        await current_service.mark_success(
            no_provider.id,
            provider_reference="reference",
        )

    with_provider = await current_service.create_payment(7, 3, provider="first")
    with pytest.raises(PaymentStateError, match="cannot be changed"):
        await current_service.mark_success(
            with_provider.id,
            provider="second",
            provider_reference="reference",
        )


async def test_terminal_provider_reference_cannot_change_on_retry() -> None:
    repository = FakePaymentRepository()
    current_service = service(repository)
    created = await current_service.create_payment(7, 3, provider="gateway")
    await current_service.mark_success(
        created.id,
        provider_reference="first-reference",
    )

    with pytest.raises(PaymentStateError, match="cannot be changed"):
        await current_service.mark_success(
            created.id,
            provider_reference="different-reference",
        )


async def test_history_is_isolated_paginated_and_clamped() -> None:
    repository = FakePaymentRepository()
    repository.users[8] = PaymentUserSnapshot(id=8, telegram_user_id=8008)
    current_service = service(repository)
    for index in range(12):
        current_service.clock = lambda index=index: NOW + timedelta(seconds=index)
        current_service.reference_factory = (
            lambda index=index: f"PAY_{index:032d}"
        )
        await current_service.create_payment(7, 3)
    current_service.reference_factory = lambda: "PAY_99999999999999999999999999999999"
    await current_service.create_payment(8, 3)

    first = await current_service.get_history_page(7, page=1)
    second = await current_service.get_history_page(7, page=2)
    clamped = await current_service.get_history_page(7, page=99)
    other = await current_service.get_history_page(8)

    assert (len(first.payments), len(second.payments)) == (10, 2)
    assert first.total_items == 12
    assert clamped == second
    assert other.total_items == 1


@pytest.mark.parametrize("value", (0, -1, True, "7"))
async def test_identifiers_must_be_positive_integers(value: object) -> None:
    with pytest.raises(InvalidPaymentError):
        await service(FakePaymentRepository()).get_payment(value)  # type: ignore[arg-type]


async def test_missing_payment_invalid_reference_and_naive_clock_are_rejected() -> None:
    repository = FakePaymentRepository()
    with pytest.raises(PaymentNotFoundError):
        await service(repository).get_payment(999)

    invalid_reference = PaymentService(
        repository,
        clock=lambda: NOW,
        reference_factory=lambda: "short",
    )
    with pytest.raises(RuntimeError, match="reference factory"):
        await invalid_reference.create_payment(7, 3)

    naive_clock = PaymentService(
        repository,
        clock=lambda: datetime(2026, 9, 2, 3),
        reference_factory=lambda: REFERENCE,
    )
    with pytest.raises(RuntimeError, match="aware datetime"):
        await naive_clock.create_payment(7, 3)
