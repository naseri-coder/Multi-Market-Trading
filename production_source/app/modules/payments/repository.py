"""Payment repository port and async PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.payments.entities import PaymentRecord, PaymentUserSnapshot
from app.modules.payments.errors import (
    DuplicatePaymentReferenceError,
    PaymentRepositoryError,
)
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.subscriptions.entities import SubscriptionPlanRecord
from app.modules.subscriptions.models import SubscriptionPlan
from app.modules.users.models import User


class PaymentRepository(Protocol):
    async def get_user(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> PaymentUserSnapshot | None: ...

    async def get_plan(
        self,
        plan_id: int,
        *,
        for_update: bool = False,
    ) -> SubscriptionPlanRecord | None: ...

    async def create_payment(
        self,
        *,
        payment_reference: str,
        user: PaymentUserSnapshot,
        plan: SubscriptionPlanRecord,
        provider: str | None,
        created_at: datetime,
    ) -> PaymentRecord: ...

    async def get_payment(
        self,
        payment_id: int,
        *,
        for_update: bool = False,
    ) -> PaymentRecord | None: ...

    async def transition_payment(
        self,
        payment_id: int,
        *,
        status: str,
        provider: str | None,
        provider_reference: str | None,
        failure_reason: str | None,
        finalized_at: datetime,
    ) -> PaymentRecord | None: ...

    async def count_for_user(self, user_id: int) -> int: ...

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[PaymentRecord, ...]: ...


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


def _to_payment(model: Payment) -> PaymentRecord:
    return PaymentRecord(
        id=model.id,
        payment_reference=model.payment_reference,
        user_id=model.user_id,
        telegram_user_id=model.telegram_user_id,
        plan_id=model.plan_id,
        subscription_id=model.subscription_id,
        plan_name=model.plan_name,
        duration_days=model.duration_days,
        amount=model.amount,
        currency=model.currency,
        status=model.status,
        provider=model.provider,
        provider_reference=model.provider_reference,
        failure_reason=model.failure_reason,
        finalized_at=model.finalized_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SQLAlchemyPaymentRepository:
    """PostgreSQL payment persistence in a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> PaymentUserSnapshot | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise PaymentRepositoryError("Unable to load payment user") from exc
        if model is None:
            return None
        return PaymentUserSnapshot(
            id=model.id,
            telegram_user_id=model.telegram_user_id,
        )

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
            raise PaymentRepositoryError("Unable to load payment plan") from exc
        return _to_plan(model) if model is not None else None

    async def create_payment(
        self,
        *,
        payment_reference: str,
        user: PaymentUserSnapshot,
        plan: SubscriptionPlanRecord,
        provider: str | None,
        created_at: datetime,
    ) -> PaymentRecord:
        model = Payment(
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
        self.session.add(model)
        try:
            await self.session.flush()
            await self.session.refresh(model)
        except IntegrityError as exc:
            raise DuplicatePaymentReferenceError(
                "Payment reference already exists"
            ) from exc
        except SQLAlchemyError as exc:
            raise PaymentRepositoryError("Unable to create payment") from exc
        return _to_payment(model)

    async def get_payment(
        self,
        payment_id: int,
        *,
        for_update: bool = False,
    ) -> PaymentRecord | None:
        statement = select(Payment).where(Payment.id == payment_id)
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise PaymentRepositoryError("Unable to load payment") from exc
        return _to_payment(model) if model is not None else None

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
        statement = (
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status == PaymentStatus.PENDING.value,
            )
            .values(
                status=status,
                provider=provider,
                provider_reference=provider_reference,
                failure_reason=failure_reason,
                finalized_at=finalized_at,
                updated_at=finalized_at,
            )
            .returning(Payment)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one_or_none()
        except IntegrityError as exc:
            raise DuplicatePaymentReferenceError(
                "Provider payment reference already exists"
            ) from exc
        except SQLAlchemyError as exc:
            raise PaymentRepositoryError("Unable to transition payment") from exc
        return _to_payment(model) if model is not None else None

    async def count_for_user(self, user_id: int) -> int:
        statement = select(func.count(Payment.id)).where(Payment.user_id == user_id)
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise PaymentRepositoryError("Unable to count payments") from exc

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[PaymentRecord, ...]:
        statement = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise PaymentRepositoryError("Unable to list payments") from exc
        return tuple(_to_payment(model) for model in models)
