"""Payment business rules independent from gateways and SQLAlchemy."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.modules.payments.entities import (
    PaymentPage,
    PaymentRecord,
    PaymentTransition,
)
from app.modules.payments.errors import (
    InvalidPaymentError,
    PaymentNotFoundError,
    PaymentPlanNotFoundError,
    PaymentStateError,
    PaymentUserNotFoundError,
)
from app.modules.payments.models import PaymentStatus
from app.modules.payments.repository import PaymentRepository

PaymentClock = Callable[[], datetime]
PaymentReferenceFactory = Callable[[], str]
PAYMENT_HISTORY_PAGE_SIZE = 10
_PAYMENT_REFERENCE_PATTERN = re.compile(r"^[A-Z0-9_-]{12,64}$")
_PROVIDER_PATTERN = re.compile(r"^[A-Z0-9_-]{2,32}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_payment_reference() -> str:
    return f"PAY_{uuid4().hex.upper()}"


class PaymentService:
    """Own payment creation, immutable snapshots, and terminal transitions."""

    def __init__(
        self,
        repository: PaymentRepository,
        *,
        clock: PaymentClock = utc_now,
        reference_factory: PaymentReferenceFactory = generate_payment_reference,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.reference_factory = reference_factory

    async def create_payment(
        self,
        user_id: int,
        plan_id: int,
        *,
        provider: str | None = None,
    ) -> PaymentRecord:
        self._validate_id(user_id, "User")
        self._validate_id(plan_id, "Plan")
        normalized_provider = self._normalize_provider(provider)
        user = await self.repository.get_user(user_id, for_update=True)
        if user is None:
            raise PaymentUserNotFoundError("Payment user was not found")
        plan = await self.repository.get_plan(plan_id, for_update=True)
        if plan is None:
            raise PaymentPlanNotFoundError("Payment plan was not found")
        if not plan.is_active:
            raise InvalidPaymentError("Inactive plans cannot create payments")
        if plan.price <= 0:
            raise InvalidPaymentError("Free plans do not require a payment record")
        payment_reference = self.reference_factory()
        if (
            not isinstance(payment_reference, str)
            or _PAYMENT_REFERENCE_PATTERN.fullmatch(payment_reference) is None
        ):
            raise RuntimeError("Payment reference factory returned an invalid value")
        return await self.repository.create_payment(
            payment_reference=payment_reference,
            user=user,
            plan=plan,
            provider=normalized_provider,
            created_at=self._now(),
        )

    async def get_payment(self, payment_id: int) -> PaymentRecord:
        self._validate_id(payment_id, "Payment")
        payment = await self.repository.get_payment(payment_id)
        if payment is None:
            raise PaymentNotFoundError("Payment was not found")
        return payment

    async def mark_success(
        self,
        payment_id: int,
        *,
        provider: str | None = None,
        provider_reference: str | None = None,
    ) -> PaymentTransition:
        return await self._transition(
            payment_id,
            target_status=PaymentStatus.SUCCESS.value,
            provider=provider,
            provider_reference=provider_reference,
            failure_reason=None,
        )

    async def mark_failed(
        self,
        payment_id: int,
        *,
        failure_reason: str,
        provider: str | None = None,
        provider_reference: str | None = None,
    ) -> PaymentTransition:
        normalized_reason = self._normalize_failure_reason(failure_reason)
        return await self._transition(
            payment_id,
            target_status=PaymentStatus.FAILED.value,
            provider=provider,
            provider_reference=provider_reference,
            failure_reason=normalized_reason,
        )

    async def cancel(self, payment_id: int) -> PaymentTransition:
        return await self._transition(
            payment_id,
            target_status=PaymentStatus.CANCELLED.value,
            provider=None,
            provider_reference=None,
            failure_reason=None,
        )

    async def get_history_page(
        self,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = PAYMENT_HISTORY_PAGE_SIZE,
    ) -> PaymentPage:
        self._validate_id(user_id, "User")
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidPaymentError("Payment page must be a positive integer")
        if page_size != PAYMENT_HISTORY_PAGE_SIZE:
            raise InvalidPaymentError("Payment page size must be 10")
        total_items = await self.repository.count_for_user(user_id)
        if total_items < 0:
            raise RuntimeError("Payment repository returned a negative count")
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        payments = await self.repository.list_for_user(
            user_id,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return PaymentPage(
            payments=payments,
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    async def _transition(
        self,
        payment_id: int,
        *,
        target_status: str,
        provider: str | None,
        provider_reference: str | None,
        failure_reason: str | None,
    ) -> PaymentTransition:
        self._validate_id(payment_id, "Payment")
        normalized_provider = self._normalize_provider(provider)
        normalized_provider_reference = self._normalize_provider_reference(
            provider_reference
        )
        payment = await self.repository.get_payment(payment_id, for_update=True)
        if payment is None:
            raise PaymentNotFoundError("Payment was not found")
        resolved_provider = normalized_provider or payment.provider
        if (
            normalized_provider is not None
            and payment.provider is not None
            and normalized_provider != payment.provider
        ):
            raise PaymentStateError("Payment provider cannot be changed")
        if normalized_provider_reference is not None and resolved_provider is None:
            raise InvalidPaymentError(
                "Provider reference requires a payment provider"
            )
        if payment.status == target_status:
            if (
                normalized_provider_reference is not None
                and payment.provider_reference != normalized_provider_reference
            ):
                raise PaymentStateError(
                    "Terminal payment provider reference cannot be changed"
                )
            return PaymentTransition(payment=payment, changed=False)
        if payment.status != PaymentStatus.PENDING.value:
            raise PaymentStateError(
                f"Payment cannot transition from {payment.status} to {target_status}"
            )
        finalized_at = self._now()
        updated = await self.repository.transition_payment(
            payment_id,
            status=target_status,
            provider=resolved_provider,
            provider_reference=normalized_provider_reference,
            failure_reason=failure_reason,
            finalized_at=finalized_at,
        )
        if updated is None:
            raise PaymentStateError("Payment state changed concurrently")
        return PaymentTransition(payment=updated, changed=True)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("PaymentService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_id(value: int, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise InvalidPaymentError(
                f"{label} identifier must be a positive integer"
            )

    @staticmethod
    def _normalize_provider(provider: str | None) -> str | None:
        if provider is None:
            return None
        if not isinstance(provider, str):
            raise InvalidPaymentError("Payment provider must be text")
        normalized = provider.strip().upper()
        if _PROVIDER_PATTERN.fullmatch(normalized) is None:
            raise InvalidPaymentError(
                "Payment provider must contain 2 to 32 letters, digits, _ or -"
            )
        return normalized

    @staticmethod
    def _normalize_provider_reference(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidPaymentError("Provider reference must be text")
        normalized = value.strip()
        if not 1 <= len(normalized) <= 128:
            raise InvalidPaymentError(
                "Provider reference must contain 1 to 128 characters"
            )
        return normalized

    @staticmethod
    def _normalize_failure_reason(value: str) -> str:
        if not isinstance(value, str):
            raise InvalidPaymentError("Failure reason must be text")
        normalized = value.strip()
        if not 1 <= len(normalized) <= 1000:
            raise InvalidPaymentError(
                "Failure reason must contain 1 to 1000 characters"
            )
        return normalized
