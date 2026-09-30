"""Framework-independent subscription data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateSubscriptionPlan:
    """Validated inputs required to create a plan."""

    name: str
    duration_days: int
    price: Decimal
    currency: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateSubscriptionPlan:
    """Complete editable snapshot used to update a plan safely."""

    name: str
    duration_days: int
    price: Decimal
    currency: str
    description: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class SubscriptionPlanRecord:
    """Administrator-facing plan read model."""

    id: int
    name: str
    duration_days: int
    price: Decimal
    currency: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SubscriptionRecord:
    """Immutable subscription history with a plan snapshot."""

    id: int
    user_id: int
    plan_id: int
    status: str
    starts_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    plan_name: str
    duration_days: int
    price: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime

    def remaining_days(self, *, at: datetime) -> int:
        """Return whole calendar-style days remaining, rounded upward."""
        remaining_seconds = max(0.0, (self.expires_at - at).total_seconds())
        return int((remaining_seconds + 86_399) // 86_400)
