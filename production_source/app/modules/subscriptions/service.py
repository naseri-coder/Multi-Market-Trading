"""Subscription business rules independent from Telegram and SQLAlchemy."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
from app.modules.subscriptions.repository import SubscriptionRepository

SubscriptionClock = Callable[[], datetime]
_CURRENCY_PATTERN = re.compile(r"^[A-Z0-9]{2,12}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


class SubscriptionService:
    """Own plan management and deterministic entitlement transitions."""

    def __init__(
        self,
        repository: SubscriptionRepository,
        *,
        clock: SubscriptionClock = utc_now,
    ) -> None:
        self.repository = repository
        self.clock = clock

    async def create_plan(
        self,
        request: CreateSubscriptionPlan,
    ) -> SubscriptionPlanRecord:
        values = self._validated_plan_values(
            name=request.name,
            duration_days=request.duration_days,
            price=request.price,
            currency=request.currency,
            description=request.description,
        )
        return await self.repository.create_plan(
            **values,
            changed_at=self._now(),
        )

    async def update_plan(
        self,
        plan_id: int,
        request: UpdateSubscriptionPlan,
    ) -> SubscriptionPlanRecord:
        self._validate_id(plan_id, "Plan")
        if not isinstance(request.is_active, bool):
            raise InvalidSubscriptionError("Plan active state must be boolean")
        existing = await self.repository.get_plan(plan_id, for_update=True)
        if existing is None:
            raise SubscriptionPlanNotFoundError("Subscription plan was not found")
        values = self._validated_plan_values(
            name=request.name,
            duration_days=request.duration_days,
            price=request.price,
            currency=request.currency,
            description=request.description,
        )
        updated = await self.repository.update_plan(
            plan_id,
            **values,
            is_active=request.is_active,
            changed_at=self._now(),
        )
        if updated is None:
            raise SubscriptionPlanNotFoundError("Subscription plan was not found")
        return updated

    async def delete_plan(self, plan_id: int) -> None:
        self._validate_id(plan_id, "Plan")
        plan = await self.repository.get_plan(plan_id, for_update=True)
        if plan is None:
            raise SubscriptionPlanNotFoundError("Subscription plan was not found")
        if await self.repository.plan_has_subscriptions(plan_id):
            raise SubscriptionPlanInUseError(
                "Plans with subscription history cannot be deleted"
            )
        if not await self.repository.delete_plan(plan_id):
            raise SubscriptionPlanNotFoundError("Subscription plan was not found")

    async def get_plan(self, plan_id: int) -> SubscriptionPlanRecord:
        self._validate_id(plan_id, "Plan")
        plan = await self.repository.get_plan(plan_id)
        if plan is None:
            raise SubscriptionPlanNotFoundError("Subscription plan was not found")
        return plan

    async def list_plans(self) -> tuple[SubscriptionPlanRecord, ...]:
        return await self.repository.list_plans()

    async def resolve_user_id(self, telegram_user_id: int) -> int:
        self._validate_id(telegram_user_id, "Telegram user")
        user_id = await self.repository.user_id_by_telegram_id(telegram_user_id)
        if user_id is None:
            raise SubscriptionUserNotFoundError("Telegram user was not found")
        return user_id

    async def activate_subscription(
        self,
        user_id: int,
        plan_id: int,
    ) -> SubscriptionRecord:
        self._validate_id(user_id, "User")
        self._validate_id(plan_id, "Plan")
        now = self._now()
        if not await self.repository.lock_user(user_id):
            raise SubscriptionUserNotFoundError("User was not found")
        plan = await self.repository.get_plan(plan_id, for_update=True)
        if plan is None:
            raise SubscriptionPlanNotFoundError("Subscription plan was not found")
        if not plan.is_active:
            raise InvalidSubscriptionError("Inactive plans cannot be activated")
        current = await self.repository.get_active_subscription(
            user_id,
            for_update=True,
        )
        if current is not None and current.expires_at <= now:
            await self.repository.expire_subscription(current.id, ended_at=now)
            current = None
        if current is not None:
            raise ActiveSubscriptionExistsError(
                "User already has an active subscription"
            )
        return await self.repository.create_subscription(
            user_id=user_id,
            plan=plan,
            starts_at=now,
            expires_at=now + timedelta(days=plan.duration_days),
        )

    async def get_user_subscription(
        self,
        user_id: int,
    ) -> SubscriptionRecord | None:
        self._validate_id(user_id, "User")
        now = self._now()
        if not await self.repository.lock_user(user_id):
            raise SubscriptionUserNotFoundError("User was not found")
        current = await self.repository.get_active_subscription(
            user_id,
            for_update=True,
        )
        if current is not None and current.expires_at <= now:
            await self.repository.expire_subscription(current.id, ended_at=now)
            return None
        return current

    async def expire_user_subscription(self, user_id: int) -> SubscriptionRecord:
        self._validate_id(user_id, "User")
        now = self._now()
        if not await self.repository.lock_user(user_id):
            raise SubscriptionUserNotFoundError("User was not found")
        current = await self.repository.get_active_subscription(
            user_id,
            for_update=True,
        )
        if current is None:
            raise ActiveSubscriptionNotFoundError(
                "User has no active subscription"
            )
        expired = await self.repository.expire_subscription(
            current.id,
            ended_at=now,
        )
        if expired is None:
            raise ActiveSubscriptionNotFoundError(
                "User has no active subscription"
            )
        return expired

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("SubscriptionService clock must return an aware datetime")
        return value.astimezone(UTC)

    @classmethod
    def _validated_plan_values(
        cls,
        *,
        name: str,
        duration_days: int,
        price: Decimal,
        currency: str,
        description: str | None,
    ) -> dict[str, object]:
        if not isinstance(name, str):
            raise InvalidSubscriptionError("Plan name must be text")
        normalized_name = " ".join(name.split())
        if not 1 <= len(normalized_name) <= 100:
            raise InvalidSubscriptionError("Plan name must contain 1 to 100 characters")
        if (
            not isinstance(duration_days, int)
            or isinstance(duration_days, bool)
            or duration_days <= 0
            or duration_days > 36_500
        ):
            raise InvalidSubscriptionError(
                "Plan duration must be between 1 and 36500 days"
            )
        if not isinstance(price, Decimal) or not price.is_finite() or price < 0:
            raise InvalidSubscriptionError(
                "Plan price must be a finite non-negative decimal"
            )
        if price.as_tuple().exponent < -2 or price >= Decimal("10000000000000000"):
            raise InvalidSubscriptionError(
                "Plan price exceeds supported precision"
            )
        if not isinstance(currency, str):
            raise InvalidSubscriptionError("Plan currency must be text")
        normalized_currency = currency.strip().upper()
        if _CURRENCY_PATTERN.fullmatch(normalized_currency) is None:
            raise InvalidSubscriptionError(
                "Plan currency must contain 2 to 12 letters or digits"
            )
        normalized_description: str | None
        if description is None:
            normalized_description = None
        elif isinstance(description, str):
            normalized_description = description.strip() or None
            if normalized_description is not None and len(normalized_description) > 2000:
                raise InvalidSubscriptionError(
                    "Plan description must not exceed 2000 characters"
                )
        else:
            raise InvalidSubscriptionError("Plan description must be text or null")
        return {
            "name": normalized_name,
            "duration_days": duration_days,
            "price": price,
            "currency": normalized_currency,
            "description": normalized_description,
        }

    @staticmethod
    def _validate_id(value: int, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise InvalidSubscriptionError(
                f"{label} identifier must be a positive integer"
            )
