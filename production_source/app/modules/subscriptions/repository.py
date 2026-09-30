"""Subscription repository port and async PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.subscriptions.entities import (
    SubscriptionPlanRecord,
    SubscriptionRecord,
)
from app.modules.subscriptions.errors import (
    ActiveSubscriptionExistsError,
    DuplicateSubscriptionPlanError,
    SubscriptionPlanInUseError,
    SubscriptionRepositoryError,
)
from app.modules.subscriptions.models import (
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.modules.users.models import User


class SubscriptionRepository(Protocol):
    async def create_plan(
        self,
        *,
        name: str,
        duration_days: int,
        price: Decimal,
        currency: str,
        description: str | None,
        changed_at: datetime,
    ) -> SubscriptionPlanRecord: ...

    async def get_plan(
        self,
        plan_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionPlanRecord | None: ...

    async def list_plans(self) -> tuple[SubscriptionPlanRecord, ...]: ...

    async def update_plan(
        self,
        plan_id: int,
        *,
        name: str,
        duration_days: int,
        price: Decimal,
        currency: str,
        description: str | None,
        is_active: bool,
        changed_at: datetime,
    ) -> SubscriptionPlanRecord | None: ...

    async def delete_plan(self, plan_id: int) -> bool: ...

    async def plan_has_subscriptions(self, plan_id: int) -> bool: ...

    async def lock_user(self, user_id: int) -> bool: ...

    async def user_id_by_telegram_id(self, telegram_user_id: int) -> int | None: ...

    async def get_active_subscription(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionRecord | None: ...

    async def create_subscription(
        self,
        *,
        user_id: int,
        plan: SubscriptionPlanRecord,
        starts_at: datetime,
        expires_at: datetime,
    ) -> SubscriptionRecord: ...

    async def expire_subscription(
        self,
        subscription_id: int,
        *,
        ended_at: datetime,
    ) -> SubscriptionRecord | None: ...


def _to_plan(model: SubscriptionPlan) -> SubscriptionPlanRecord:
    return SubscriptionPlanRecord(
        id=model.id,
        name=model.name,
        duration_days=model.duration_days,
        price=model.price,
        currency=model.currency,
        description=model.description,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_subscription(model: Subscription) -> SubscriptionRecord:
    return SubscriptionRecord(
        id=model.id,
        user_id=model.user_id,
        plan_id=model.plan_id,
        status=model.status,
        starts_at=model.starts_at,
        expires_at=model.expires_at,
        ended_at=model.ended_at,
        plan_name=model.plan_name,
        duration_days=model.duration_days,
        price=model.price,
        currency=model.currency,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SQLAlchemySubscriptionRepository:
    """PostgreSQL persistence bound to a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_plan(
        self,
        *,
        name: str,
        duration_days: int,
        price: Decimal,
        currency: str,
        description: str | None,
        changed_at: datetime,
    ) -> SubscriptionPlanRecord:
        model = SubscriptionPlan(
            name=name,
            duration_days=duration_days,
            price=price,
            currency=currency,
            description=description,
            is_active=True,
            created_at=changed_at,
            updated_at=changed_at,
        )
        self.session.add(model)
        try:
            await self.session.flush()
            await self.session.refresh(model)
        except IntegrityError as exc:
            raise DuplicateSubscriptionPlanError(
                "Subscription plan name already exists"
            ) from exc
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to create subscription plan"
            ) from exc
        return _to_plan(model)

    async def get_plan(
        self,
        plan_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionPlanRecord | None:
        statement = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to load subscription plan"
            ) from exc
        return _to_plan(model) if model is not None else None

    async def list_plans(self) -> tuple[SubscriptionPlanRecord, ...]:
        statement = select(SubscriptionPlan).order_by(
            SubscriptionPlan.is_active.desc(),
            SubscriptionPlan.id.asc(),
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to list subscription plans"
            ) from exc
        return tuple(_to_plan(model) for model in models)

    async def update_plan(
        self,
        plan_id: int,
        *,
        name: str,
        duration_days: int,
        price: Decimal,
        currency: str,
        description: str | None,
        is_active: bool,
        changed_at: datetime,
    ) -> SubscriptionPlanRecord | None:
        statement = (
            update(SubscriptionPlan)
            .where(SubscriptionPlan.id == plan_id)
            .values(
                name=name,
                duration_days=duration_days,
                price=price,
                currency=currency,
                description=description,
                is_active=is_active,
                updated_at=changed_at,
            )
            .returning(SubscriptionPlan)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one_or_none()
        except IntegrityError as exc:
            raise DuplicateSubscriptionPlanError(
                "Subscription plan name already exists"
            ) from exc
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to update subscription plan"
            ) from exc
        return _to_plan(model) if model is not None else None

    async def delete_plan(self, plan_id: int) -> bool:
        statement = (
            delete(SubscriptionPlan)
            .where(SubscriptionPlan.id == plan_id)
            .returning(SubscriptionPlan.id)
        )
        try:
            return (await self.session.scalar(statement)) is not None
        except IntegrityError as exc:
            raise SubscriptionPlanInUseError(
                "Subscription plan has subscription history"
            ) from exc
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to delete subscription plan"
            ) from exc

    async def plan_has_subscriptions(self, plan_id: int) -> bool:
        statement = select(func.count(Subscription.id)).where(
            Subscription.plan_id == plan_id
        )
        try:
            return int((await self.session.scalar(statement)) or 0) > 0
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to inspect subscription plan usage"
            ) from exc

    async def lock_user(self, user_id: int) -> bool:
        statement = (
            select(User.id)
            .where(User.id == user_id)
            .with_for_update()
        )
        try:
            return await self.session.scalar(statement) is not None
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError("Unable to lock user") from exc

    async def user_id_by_telegram_id(self, telegram_user_id: int) -> int | None:
        statement = select(User.id).where(User.telegram_user_id == telegram_user_id)
        try:
            return await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError("Unable to load user") from exc

    async def get_active_subscription(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionRecord | None:
        statement = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE.value,
        )
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to load active subscription"
            ) from exc
        return _to_subscription(model) if model is not None else None

    async def create_subscription(
        self,
        *,
        user_id: int,
        plan: SubscriptionPlanRecord,
        starts_at: datetime,
        expires_at: datetime,
    ) -> SubscriptionRecord:
        model = Subscription(
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
        self.session.add(model)
        try:
            await self.session.flush()
            await self.session.refresh(model)
        except IntegrityError as exc:
            raise ActiveSubscriptionExistsError(
                "User already has an active subscription"
            ) from exc
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to activate subscription"
            ) from exc
        return _to_subscription(model)

    async def expire_subscription(
        self,
        subscription_id: int,
        *,
        ended_at: datetime,
    ) -> SubscriptionRecord | None:
        statement = (
            update(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .values(
                status=SubscriptionStatus.EXPIRED.value,
                ended_at=ended_at,
                updated_at=ended_at,
            )
            .returning(Subscription)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise SubscriptionRepositoryError(
                "Unable to expire subscription"
            ) from exc
        return _to_subscription(model) if model is not None else None
