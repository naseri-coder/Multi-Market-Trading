"""Framework-independent payment data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PaymentUserSnapshot:
    """Minimum user identity persisted for financial audit history."""

    id: int
    telegram_user_id: int


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    """Immutable read model for one payment attempt."""

    id: int
    payment_reference: str
    user_id: int | None
    telegram_user_id: int
    plan_id: int | None
    subscription_id: int | None
    plan_name: str
    duration_days: int
    amount: Decimal
    currency: str
    status: str
    provider: str | None
    provider_reference: str | None
    failure_reason: str | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PaymentTransition:
    """Idempotent result of one terminal-state request."""

    payment: PaymentRecord
    changed: bool


@dataclass(frozen=True, slots=True)
class PaymentPage:
    """A bounded page of one user's payment history."""

    payments: tuple[PaymentRecord, ...]
    page: int
    page_size: int
    total_items: int
    total_pages: int
