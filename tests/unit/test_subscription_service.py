"""Subscription service business-rule tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.subscriptions.entities import (
    CreateSubscriptionPlan,
    SubscriptionPlanRecord,
    SubscriptionRecord,
    UpdateSubscriptionPlan,
)
from app.modules.subscriptions.errors import (
    ActiveSubscriptionExistsError,
    ActiveSubscriptionNotFoundError,
    InvalidSubscriptionError,
    SubscriptionPlanInUseError,
    SubscriptionPlanNotFoundError,
    SubscriptionUserNotFoundError,
)
from app.modules.subscriptions.models import SubscriptionStatus
from app.modules.subscriptions.service import SubscriptionService

NOW = datetime(2026, 9, 2, 2, tzinfo=UTC)


def plan(plan_id: int = 1, *, active: bool = True) -> SubscriptionPlanRecord:
    return SubscriptionPlanRecord(
        id=plan_id,
        name="VIP Monthly",
        duration_days=30,
        price=Decimal("19.50"),
        currency="USDT",
        description="Premium signals",
        is_active=active,
        created_at=NOW,
        updated_at=NOW,
    )


def subscription(
    subscription_id: int = 1,
    *,
    expires_at: datetime | None = None,
) -> SubscriptionRecord:
    return SubscriptionRecord(
        id=subscription_id,
        user_id=7,
        plan_id=1,
        status=SubscriptionStatus.ACTIVE.value,
        starts_at=NOW - timedelta(days=1),
        expires_at=expires_at or NOW + timedelta(days=29),
        ended_at=None,
        plan_name="VIP Monthly",
        duration_days=30,
        price=Decimal("19.50"),
        currency="USDT",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )


class FakeSubscriptionRepository:
    def __init__(self) -> None:
        self.plans: dict[int, SubscriptionPlanRecord] = {1: plan()}
        self.active: dict[int, SubscriptionRecord] = {}
        self.users = {7: 7007}
        self.used_plan_ids: set[int] = set()
        self.next_plan_id = 2
        self.next_subscription_id = 2

    async def create_plan(self, **values) -> SubscriptionPlanRecord:
        changed_at = values.pop("changed_at")
        record = SubscriptionPlanRecord(
            id=self.next_plan_id,
            is_active=True,
            created_at=changed_at,
            updated_at=changed_at,
            **values,
        )
        self.plans[record.id] = record
        self.next_plan_id += 1
        return record

    async def get_plan(
        self,
        plan_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionPlanRecord | None:
        return self.plans.get(plan_id)

    async def list_plans(self) -> tuple[SubscriptionPlanRecord, ...]:
        return tuple(self.plans.values())

    async def update_plan(self, plan_id: int, **values) -> SubscriptionPlanRecord | None:
        changed_at = values.pop("changed_at")
        current = self.plans.get(plan_id)
        if current is None:
            return None
        updated = replace(current, updated_at=changed_at, **values)
        self.plans[plan_id] = updated
        return updated

    async def delete_plan(self, plan_id: int) -> bool:
        return self.plans.pop(plan_id, None) is not None

    async def plan_has_subscriptions(self, plan_id: int) -> bool:
        return plan_id in self.used_plan_ids

    async def lock_user(self, user_id: int) -> bool:
        return user_id in self.users

    async def user_id_by_telegram_id(self, telegram_user_id: int) -> int | None:
        return next(
            (user_id for user_id, item in self.users.items() if item == telegram_user_id),
            None,
        )

    async def get_active_subscription(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionRecord | None:
        return self.active.get(user_id)

    async def create_subscription(
        self,
        *,
        user_id: int,
        plan: SubscriptionPlanRecord,
        starts_at: datetime,
        expires_at: datetime,
    ) -> SubscriptionRecord:
        record = SubscriptionRecord(
            id=self.next_subscription_id,
            user_id=user_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE.value,
            starts_at=starts_at,
            expires_at=expires_at,
            ended_at=None,
            plan_name=plan.name,
            duration_days=plan.duration_days,
            price=plan.price,
            currency=plan.currency,
            created_at=starts_at,
            updated_at=starts_at,
        )
        self.active[user_id] = record
        self.used_plan_ids.add(plan.id)
        self.next_subscription_id += 1
        return record

    async def expire_subscription(
        self,
        subscription_id: int,
        *,
        ended_at: datetime,
    ) -> SubscriptionRecord | None:
        current = next(
            (item for item in self.active.values() if item.id == subscription_id),
            None,
        )
        if current is None:
            return None
        self.active.pop(current.user_id)
        return replace(
            current,
            status=SubscriptionStatus.EXPIRED.value,
            ended_at=ended_at,
            updated_at=ended_at,
        )


async def test_create_and_update_plan_normalize_values() -> None:
    repository = FakeSubscriptionRepository()
    service = SubscriptionService(repository, clock=lambda: NOW)

    created = await service.create_plan(
        CreateSubscriptionPlan(
            name="  VIP   Yearly ",
            duration_days=365,
            price=Decimal("99.00"),
            currency="usdt",
            description="  Annual access  ",
        )
    )
    updated = await service.update_plan(
        created.id,
        UpdateSubscriptionPlan(
            name="VIP Annual",
            duration_days=366,
            price=Decimal("100.00"),
            currency="usd",
            description=" ",
            is_active=False,
        ),
    )

    assert created.name == "VIP Yearly"
    assert created.currency == "USDT"
    assert updated.description is None
    assert updated.currency == "USD"
    assert updated.is_active is False


async def test_delete_rejects_used_plan_and_missing_plan() -> None:
    repository = FakeSubscriptionRepository()
    service = SubscriptionService(repository)
    repository.used_plan_ids.add(1)

    with pytest.raises(SubscriptionPlanInUseError):
        await service.delete_plan(1)
    with pytest.raises(SubscriptionPlanNotFoundError):
        await service.delete_plan(999)


async def test_activate_snapshots_plan_and_rejects_duplicate_active() -> None:
    repository = FakeSubscriptionRepository()
    service = SubscriptionService(repository, clock=lambda: NOW)

    activated = await service.activate_subscription(7, 1)

    assert activated.plan_name == "VIP Monthly"
    assert activated.price == Decimal("19.50")
    assert activated.expires_at == NOW + timedelta(days=30)
    with pytest.raises(ActiveSubscriptionExistsError):
        await service.activate_subscription(7, 1)


async def test_expired_active_is_closed_before_reactivation() -> None:
    repository = FakeSubscriptionRepository()
    repository.active[7] = subscription(expires_at=NOW)
    service = SubscriptionService(repository, clock=lambda: NOW)

    activated = await service.activate_subscription(7, 1)

    assert activated.id == 2
    assert activated.status == SubscriptionStatus.ACTIVE.value


async def test_status_check_auto_expires_due_subscription() -> None:
    repository = FakeSubscriptionRepository()
    repository.active[7] = subscription(expires_at=NOW - timedelta(seconds=1))
    service = SubscriptionService(repository, clock=lambda: NOW)

    assert await service.get_user_subscription(7) is None
    assert repository.active == {}


async def test_manual_expiration_and_missing_active_rejection() -> None:
    repository = FakeSubscriptionRepository()
    repository.active[7] = subscription()
    service = SubscriptionService(repository, clock=lambda: NOW)

    expired = await service.expire_user_subscription(7)

    assert expired.status == SubscriptionStatus.EXPIRED.value
    assert expired.ended_at == NOW
    with pytest.raises(ActiveSubscriptionNotFoundError):
        await service.expire_user_subscription(7)


async def test_inactive_plan_and_missing_user_are_rejected() -> None:
    repository = FakeSubscriptionRepository()
    repository.plans[1] = plan(active=False)
    service = SubscriptionService(repository, clock=lambda: NOW)

    with pytest.raises(InvalidSubscriptionError, match="Inactive"):
        await service.activate_subscription(7, 1)
    with pytest.raises(SubscriptionUserNotFoundError):
        await service.activate_subscription(999, 1)
    with pytest.raises(SubscriptionUserNotFoundError):
        await service.resolve_user_id(9999)


@pytest.mark.parametrize(
    ("plan_request", "message"),
    (
        (
            CreateSubscriptionPlan("", 30, Decimal("1"), "USDT"),
            "name",
        ),
        (
            CreateSubscriptionPlan("VIP", 0, Decimal("1"), "USDT"),
            "duration",
        ),
        (
            CreateSubscriptionPlan("VIP", 30, Decimal("-1"), "USDT"),
            "price",
        ),
        (
            CreateSubscriptionPlan("VIP", 30, Decimal("1.001"), "USDT"),
            "precision",
        ),
        (
            CreateSubscriptionPlan("VIP", 30, Decimal("1"), "US DT"),
            "currency",
        ),
    ),
)
async def test_invalid_plan_values_are_rejected(
    plan_request: CreateSubscriptionPlan,
    message: str,
) -> None:
    with pytest.raises(InvalidSubscriptionError, match=message):
        await SubscriptionService(FakeSubscriptionRepository()).create_plan(
            plan_request
        )


async def test_clock_must_be_timezone_aware() -> None:
    service = SubscriptionService(
        FakeSubscriptionRepository(),
        clock=lambda: datetime(2026, 9, 2, 2),
    )

    with pytest.raises(RuntimeError, match="aware datetime"):
        await service.activate_subscription(7, 1)
