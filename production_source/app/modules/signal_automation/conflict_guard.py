from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class SignalConflictCategory(str, Enum):
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    VALID_PENDING_ENTRY_CONFLICT = "VALID_PENDING_ENTRY_CONFLICT"
    ACTIVE_POSITION_CONFLICT = "ACTIVE_POSITION_CONFLICT"
    STALE_OR_INVALID_PENDING = "STALE_OR_INVALID_PENDING"
    NO_CONFLICT = "NO_CONFLICT"


@dataclass(frozen=True, slots=True)
class SignalConflictContext:
    signal_id: int
    direction: str
    signal_status: str
    lifecycle_state: str | None
    entry_activated_at: datetime | None
    last_market_price: Decimal | None
    stop_loss: Decimal


@dataclass(frozen=True, slots=True)
class ConflictResult:
    allowed: bool
    reason: str
    category: SignalConflictCategory = SignalConflictCategory.NO_CONFLICT
    reconcile_stale: bool = False


def _pending_structurally_invalid(context: SignalConflictContext) -> bool:
    if context.lifecycle_state != "WAITING_ENTRY" or context.entry_activated_at is not None:
        return False
    if context.last_market_price is None:
        return False
    if context.direction == "LONG":
        return context.last_market_price <= context.stop_loss
    return context.last_market_price >= context.stop_loss


def check_signal_conflict(
    context: SignalConflictContext | None,
    new_direction: str,
) -> ConflictResult:
    if context is None or context.signal_status != "OPEN":
        return ConflictResult(True, "NO_CONFLICT")

    if context.lifecycle_state in {"COMPLETE", "AMBIGUOUS"}:
        return ConflictResult(True, "NO_CONFLICT")

    if _pending_structurally_invalid(context):
        return ConflictResult(
            True,
            "STALE_PENDING_STRUCTURAL_INVALIDATION",
            SignalConflictCategory.STALE_OR_INVALID_PENDING,
            reconcile_stale=True,
        )
    if context.lifecycle_state == "ACTIVE" and context.entry_activated_at is not None:
        if context.direction == new_direction:
            return ConflictResult(True, "ACTIVE_SAME_DIRECTION_ALLOWED")
        return ConflictResult(
            False,
            "ACTIVE_OPPOSITE_SIGNAL_EXISTS",
            SignalConflictCategory.ACTIVE_POSITION_CONFLICT,
        )

    if context.lifecycle_state in {None, "WAITING_ENTRY"} and context.entry_activated_at is None:
        reason = (
            "VALID_PENDING_SAME_DIRECTION_EXISTS"
            if context.direction == new_direction
            else "VALID_PENDING_OPPOSITE_SIGNAL_EXISTS"
        )
        return ConflictResult(
            False,
            reason,
            SignalConflictCategory.VALID_PENDING_ENTRY_CONFLICT,
        )

    return ConflictResult(
        False,
        "UNACTIVATED_OR_INCONSISTENT_LIFECYCLE_CONFLICT",
        SignalConflictCategory.VALID_PENDING_ENTRY_CONFLICT,
    )
