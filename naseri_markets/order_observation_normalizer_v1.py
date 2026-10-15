"""Pure, nonproduction order-observation normalization with conservative reconciliation.

No network, persistence, execution, retry, exchange credentials or auto-repair.
This module never turns an observed quantity into a booked trade/fill.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from .execution_contract_v1 import OrderStatus


class ObservationRefused(ValueError):
    """Malformed evidence or checkpoint; no untrusted payload in the exception."""


class ObservationVerdict(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    QUARANTINED = "quarantined"


class ObservationReason(StrEnum):
    ACCEPTED = "accepted"
    REPLAY = "replay"
    EVENT_ID_CONFLICT = "event_id_conflict"
    UNKNOWN_NATIVE_STATUS = "unknown_native_status"
    WRONG_ORDER = "wrong_order"
    OUT_OF_ORDER = "out_of_order"
    FILLED_REGRESSION = "filled_regression"
    FILLED_EXCEEDS_ORDER = "filled_exceeds_order"
    STATUS_QUANTITY_CONFLICT = "status_quantity_conflict"
    TERMINAL_REOPEN = "terminal_reopen"
    STATUS_REGRESSION = "status_regression"
    RECEIPT_CAPACITY = "receipt_capacity"


_VENUES = frozenset({"binance", "okx", "bybit", "bitget"})
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_RECEIPTS = 256
_TERMINAL = frozenset({
    OrderStatus.FILLED, OrderStatus.CANCELED,
    OrderStatus.REJECTED, OrderStatus.CLOSED,
})
_PENDING = frozenset({
    OrderStatus.CREATED, OrderStatus.SENT_UNCONFIRMED,
    OrderStatus.SUBMISSION_UNKNOWN, OrderStatus.ACKNOWLEDGED,
})
_NATIVE: dict[str, dict[str, OrderStatus]] = {
    "binance": {
        "new": OrderStatus.ACKNOWLEDGED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELED,
        "expired": OrderStatus.CANCELED,
        "expired_in_match": OrderStatus.CANCELED,
        "rejected": OrderStatus.REJECTED,
    },
    "okx": {
        "live": OrderStatus.ACKNOWLEDGED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELED,
        "mmp_canceled": OrderStatus.CANCELED,
    },
    "bybit": {
        "new": OrderStatus.ACKNOWLEDGED,
        "partiallyfilled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "cancelled": OrderStatus.CANCELED,
        "partiallyfilledcanceled": OrderStatus.CANCELED,
        "rejected": OrderStatus.REJECTED,
    },
    "bitget": {
        "live": OrderStatus.ACKNOWLEDGED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELED,
    },
}


def _venue(value: object) -> str:
    if type(value) is not str or value not in _VENUES:
        raise ObservationRefused("UNSUPPORTED_VENUE")
    return value


def _identifier(value: object) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ObservationRefused("INVALID_OBSERVATION_ID")
    return value


def _decimal(value: object, *, allow_zero: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ObservationRefused("INVALID_OBSERVED_QUANTITY")
    if value < 0 or (not allow_zero and value == 0):
        raise ObservationRefused("INVALID_OBSERVED_QUANTITY")
    return value


def _timestamp(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ObservationRefused("UTC_EVENT_TIMESTAMP_REQUIRED")
    try:
        result = value.astimezone(UTC)
    except (ValueError, OverflowError, TypeError) as exc:
        raise ObservationRefused("UTC_EVENT_TIMESTAMP_REQUIRED") from exc
    if not 2000 <= result.year <= 2100:
        raise ObservationRefused("EVENT_TIMESTAMP_OUT_OF_BOUNDS")
    return result


def _coherent(status: OrderStatus, filled: Decimal, requested: Decimal) -> bool:
    if filled > requested:
        return False
    if status in _PENDING or status is OrderStatus.REJECTED:
        return filled == 0
    if status is OrderStatus.PARTIALLY_FILLED:
        return 0 < filled < requested
    if status is OrderStatus.FILLED:
        return filled == requested
    if status is OrderStatus.CANCELED:
        return filled < requested
    return status is OrderStatus.CLOSED


def normalize_native_order_status(venue: str, native_status: str) -> OrderStatus | None:
    """Allowlisted exact status mapping. None means quarantine, not cancellation."""
    v = _venue(venue)
    if type(native_status) is not str or len(native_status) > 48:
        raise ObservationRefused("INVALID_NATIVE_STATUS")
    return _NATIVE[v].get(native_status.strip().lower())


@dataclass(frozen=True, slots=True)
class OrderProgress:
    """Trusted checkpoint supplied by the caller, never a broker ledger itself."""

    venue: str
    order_id: str
    requested_quantity: Decimal
    status: OrderStatus = OrderStatus.CREATED
    cumulative_filled: Decimal = Decimal("0")
    last_event_at: datetime | None = None
    receipts: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _venue(self.venue)
        _identifier(self.order_id)
        requested = _decimal(self.requested_quantity, allow_zero=False)
        filled = _decimal(self.cumulative_filled, allow_zero=True)
        if type(self.status) is not OrderStatus or not _coherent(self.status, filled, requested):
            raise ObservationRefused("INVALID_ORDER_CHECKPOINT")
        if self.last_event_at is not None:
            _timestamp(self.last_event_at)
        if type(self.receipts) is not tuple or len(self.receipts) > _MAX_RECEIPTS:
            raise ObservationRefused("INVALID_RECEIPT_CHECKPOINT")
        ids: set[str] = set()
        for item in self.receipts:
            if (type(item) is not tuple or len(item) != 2
                    or type(item[1]) is not str or not _HEX.fullmatch(item[1])):
                raise ObservationRefused("INVALID_RECEIPT_CHECKPOINT")
            event_id = _identifier(item[0])
            if event_id in ids:
                raise ObservationRefused("DUPLICATE_RECEIPT_CHECKPOINT")
            ids.add(event_id)
        if self.receipts and self.last_event_at is None:
            raise ObservationRefused("MISSING_CHECKPOINT_TIMESTAMP")


@dataclass(frozen=True, slots=True)
class OrderObservation:
    venue: str
    order_id: str
    event_id: str
    native_status: str
    cumulative_filled: Decimal
    occurred_at: datetime

    def __post_init__(self) -> None:
        _venue(self.venue)
        _identifier(self.order_id)
        _identifier(self.event_id)
        _decimal(self.cumulative_filled, allow_zero=True)
        _timestamp(self.occurred_at)
        if type(self.native_status) is not str or len(self.native_status) > 48:
            raise ObservationRefused("INVALID_NATIVE_STATUS")


@dataclass(frozen=True, slots=True)
class ObservationDecision:
    verdict: ObservationVerdict
    reason: ObservationReason
    progress: OrderProgress


def _fingerprint(event: OrderObservation, status: OrderStatus | None) -> str:
    body = json.dumps({
        "venue": event.venue,
        "order_id": event.order_id,
        "status": status.value if status is not None else None,
        "quantity": str(event.cumulative_filled.normalize()),
        "at": _timestamp(event.occurred_at).isoformat(),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def assess_order_observation(
    progress: OrderProgress, event: OrderObservation,
) -> ObservationDecision:
    """Validate an external *observation*, never post the resulting delta.

    The caller owns atomic checkpoint persistence and actual venue reconciliation.
    Duplicate detection covers only the caller-provided bounded receipt history.
    """
    if type(progress) is not OrderProgress or type(event) is not OrderObservation:
        raise ObservationRefused("TYPED_OBSERVATION_REQUIRED")

    def decide(verdict: ObservationVerdict, reason: ObservationReason) -> ObservationDecision:
        return ObservationDecision(verdict, reason, progress)

    if progress.venue != event.venue or progress.order_id != event.order_id:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.WRONG_ORDER)
    status = normalize_native_order_status(event.venue, event.native_status)
    if status is None:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.UNKNOWN_NATIVE_STATUS)
    digest = _fingerprint(event, status)
    for event_id, prior_digest in progress.receipts:
        if event_id == event.event_id:
            if prior_digest == digest:
                return decide(ObservationVerdict.DUPLICATE, ObservationReason.REPLAY)
            return decide(ObservationVerdict.QUARANTINED, ObservationReason.EVENT_ID_CONFLICT)
    if len(progress.receipts) >= _MAX_RECEIPTS:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.RECEIPT_CAPACITY)
    at = _timestamp(event.occurred_at)
    if progress.last_event_at is not None and at <= _timestamp(progress.last_event_at):
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.OUT_OF_ORDER)
    if progress.status is OrderStatus.PARTIALLY_FILLED and status is OrderStatus.ACKNOWLEDGED:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.STATUS_REGRESSION)
    filled = event.cumulative_filled
    if filled < progress.cumulative_filled:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.FILLED_REGRESSION)
    if filled > progress.requested_quantity:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.FILLED_EXCEEDS_ORDER)
    if progress.status in _TERMINAL:
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.TERMINAL_REOPEN)
    if not _coherent(status, filled, progress.requested_quantity):
        return decide(ObservationVerdict.QUARANTINED, ObservationReason.STATUS_QUANTITY_CONFLICT)
    updated = replace(
        progress, status=status, cumulative_filled=filled, last_event_at=at,
        receipts=progress.receipts + ((event.event_id, digest),),
    )
    return ObservationDecision(ObservationVerdict.APPLIED, ObservationReason.ACCEPTED, updated)
