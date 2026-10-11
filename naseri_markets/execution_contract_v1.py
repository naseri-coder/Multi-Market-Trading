"""Execution Architecture V1: PAPER-only contracts and conservative linear sizing.

No exchange client, trading terminal, credentials, dispatcher or network operations.
The quantity calculator is deliberately *not* an MT5 lot or futures-contract
adapter: venue-specific contract/tick/margin metadata must be validated later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from .contracts import Direction, EvidenceMode, Instrument

_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}$")


def positive(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")


def nonnegative(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative Decimal")


def identity(value: str, name: str) -> None:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise ValueError(f"invalid {name}")


class OrderKind(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SENT_UNCONFIRMED = "SENT_UNCONFIRMED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class OrderSpec:
    """Approved PAPER intent, never an actual broker execution permission."""

    order_id: str
    signal_id: str
    account_id: str
    engine_id: str
    instrument: Instrument
    direction: Direction
    kind: OrderKind
    quantity: Decimal
    reference_entry: Decimal
    stop: Decimal
    target: Decimal
    mode: EvidenceMode = EvidenceMode.PAPER

    def __post_init__(self) -> None:
        for field in ("order_id", "signal_id", "account_id", "engine_id"):
            identity(getattr(self, field), field)
        if not isinstance(self.instrument, Instrument):
            raise ValueError("canonical Instrument required")
        if not isinstance(self.direction, Direction) or not isinstance(self.kind, OrderKind):
            raise ValueError("known order direction and kind required")
        if self.mode is not EvidenceMode.PAPER:
            raise ValueError("EXECUTION_V1_PAPER_ONLY")
        for field in ("quantity", "reference_entry", "stop", "target"):
            positive(getattr(self, field), field)
        if self.direction is Direction.LONG and not (
            self.stop < self.reference_entry < self.target
        ):
            raise ValueError("LONG_STOP_TARGET_GEOMETRY")
        if self.direction is Direction.SHORT and not (
            self.target < self.reference_entry < self.stop
        ):
            raise ValueError("SHORT_STOP_TARGET_GEOMETRY")


@dataclass(frozen=True, slots=True)
class RiskEnvelope:
    """Single-account snapshot. Caller must include existing reserved orders.

    Fractions 0..1; the daily loss limit is an absolute fraction of equity.
    Only linear quote-settled contract models are supported at this stage.
    """

    equity: Decimal
    risk_fraction: Decimal
    max_daily_loss_fraction: Decimal
    daily_realized_loss: Decimal
    reserved_risk: Decimal
    existing_notional: Decimal
    max_notional_fraction: Decimal
    max_leverage: Decimal
    contract_multiplier: Decimal
    quantity_step: Decimal
    roundtrip_fee_fraction: Decimal
    worst_slippage_fraction: Decimal

    def __post_init__(self) -> None:
        for name in (
            "equity", "risk_fraction", "max_daily_loss_fraction",
            "max_notional_fraction", "max_leverage", "contract_multiplier",
            "quantity_step",
        ):
            positive(getattr(self, name), name)
        for name in (
            "daily_realized_loss", "reserved_risk", "existing_notional",
            "roundtrip_fee_fraction", "worst_slippage_fraction",
        ):
            nonnegative(getattr(self, name), name)
        if self.risk_fraction > 1 or self.max_daily_loss_fraction > 1:
            raise ValueError("risk fractions must be <= 1")
        if self.max_notional_fraction > self.max_leverage:
            raise ValueError("notional fraction cannot exceed leverage ceiling")
        if self.roundtrip_fee_fraction >= 1 or self.worst_slippage_fraction >= 1:
            raise ValueError("invalid assumed transaction friction")


@dataclass(frozen=True, slots=True)
class RiskApproval:
    quantity: Decimal
    reserved_risk: Decimal
    notional: Decimal


def size_linear_paper_order(
    *, reference_entry: Decimal, stop: Decimal, envelope: RiskEnvelope,
) -> RiskApproval:
    """Round DOWN in venue quantity steps, or refuse instead of increasing risk.

    This calculator alone does not authorize placing or even submitting an order.
    Equity, open order reservations, realized loss, venue margin rules, contract
    multipliers and fee estimates must be trustworthy operator inputs.
    """
    positive(reference_entry, "reference_entry")
    positive(stop, "stop")
    if reference_entry == stop:
        raise ValueError("NO_STOP_DISTANCE")
    if not isinstance(envelope, RiskEnvelope):
        raise ValueError("RISK_ENVELOPE_REQUIRED")
    if envelope.daily_realized_loss >= (
        envelope.equity * envelope.max_daily_loss_fraction
    ):
        raise ValueError("DAILY_LOSS_CIRCUIT_BREAKER")
    risk_available = envelope.equity * envelope.risk_fraction - envelope.reserved_risk
    exposure_available = min(
        envelope.equity * envelope.max_notional_fraction,
        envelope.equity * envelope.max_leverage,
    ) - envelope.existing_notional
    per_unit_risk = (
        abs(reference_entry - stop)
        + reference_entry * (
            envelope.roundtrip_fee_fraction + envelope.worst_slippage_fraction
        )
    ) * envelope.contract_multiplier
    per_unit_notional = reference_entry * envelope.contract_multiplier
    if risk_available <= 0 or exposure_available <= 0:
        raise ValueError("ACCOUNT_RISK_OR_EXPOSURE_EXHAUSTED")
    raw = min(risk_available / per_unit_risk, exposure_available / per_unit_notional)
    units = (raw / envelope.quantity_step).to_integral_value(
        rounding=ROUND_DOWN
    ) * envelope.quantity_step
    if units <= 0:
        raise ValueError("QUANTITY_BELOW_MINIMUM_STEP")
    return RiskApproval(
        quantity=units,
        reserved_risk=units * per_unit_risk,
        notional=units * per_unit_notional,
    )
