"""Aggregate position-risk calculations for multi-lot Scale-In."""
from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from .entities import AggregateRiskDecision


class RiskLot(Protocol):
    fill_price: Decimal
    open_qty: Decimal
    risk_buffer_per_unit: Decimal


def _loss_per_unit(direction: str, entry: Decimal, stop: Decimal) -> Decimal:
    if direction == "LONG":
        return max(Decimal("0"), entry - stop)
    if direction == "SHORT":
        return max(Decimal("0"), stop - entry)
    raise ValueError("direction must be LONG or SHORT")


def lot_risk(*, direction: str, entry: Decimal, stop: Decimal, qty: Decimal,
             risk_buffer_per_unit: Decimal = Decimal("0")) -> Decimal:
    if qty < 0 or entry <= 0 or stop <= 0 or risk_buffer_per_unit < 0:
        raise ValueError("invalid risk inputs")
    return (_loss_per_unit(direction, entry, stop) + risk_buffer_per_unit) * qty


def aggregate_risk(*, direction: str, lots: Iterable[RiskLot], stop: Decimal) -> Decimal:
    return sum((lot_risk(direction=direction, entry=lot.fill_price, stop=stop,
                         qty=lot.open_qty, risk_buffer_per_unit=lot.risk_buffer_per_unit)
                for lot in lots if lot.open_qty > 0), Decimal("0"))


def round_down_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value < 0 or step <= 0:
        raise ValueError("value must be non-negative and step positive")
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def max_safe_add_qty(*, remaining_risk_budget: Decimal, direction: str,
                     expected_price: Decimal, executable_stop: Decimal,
                     desired_qty: Decimal, qty_step: Decimal,
                     risk_buffer_per_unit: Decimal = Decimal("0"),
                     min_qty: Decimal = Decimal("0"),
                     min_notional: Decimal = Decimal("0")) -> Decimal:
    if remaining_risk_budget < 0 or desired_qty <= 0:
        return Decimal("0")
    per_unit = _loss_per_unit(direction, expected_price, executable_stop) + risk_buffer_per_unit
    if per_unit == 0:
        raw = desired_qty
    else:
        raw = min(desired_qty, remaining_risk_budget / per_unit)
    safe = round_down_to_step(raw, qty_step)
    if safe < min_qty:
        return Decimal("0")
    if min_notional > 0 and safe * expected_price < min_notional:
        return Decimal("0")
    return safe


def assess_scale_in(*, direction: str, lots: Iterable[RiskLot], executable_stop: Decimal,
                    initial_trade_risk_budget: Decimal, requested_qty: Decimal,
                    expected_price: Decimal, qty_step: Decimal,
                    risk_buffer_per_unit: Decimal = Decimal("0"),
                    min_qty: Decimal = Decimal("0"), min_notional: Decimal = Decimal("0"),
                    allow_clamp: bool = False) -> AggregateRiskDecision:
    lots_tuple = tuple(lots)
    current = aggregate_risk(direction=direction, lots=lots_tuple, stop=executable_stop)
    remaining = max(Decimal("0"), initial_trade_risk_budget - current)
    safe = max_safe_add_qty(
        remaining_risk_budget=remaining, direction=direction,
        expected_price=expected_price, executable_stop=executable_stop,
        desired_qty=requested_qty, qty_step=qty_step,
        risk_buffer_per_unit=risk_buffer_per_unit, min_qty=min_qty,
        min_notional=min_notional,
    )
    if safe <= 0:
        approved_qty = Decimal("0")
        approved = False
        reason = "NO_REMAINING_SAFE_QUANTITY"
    elif safe < requested_qty and not allow_clamp:
        approved_qty = Decimal("0")
        approved = False
        reason = "REQUEST_EXCEEDS_MAX_SAFE_QUANTITY"
    else:
        approved_qty = safe if allow_clamp else requested_qty
        approved = True
        reason = "WITHIN_IMMUTABLE_RISK_BUDGET"
    post = current + lot_risk(
        direction=direction, entry=expected_price, stop=executable_stop,
        qty=approved_qty, risk_buffer_per_unit=risk_buffer_per_unit,
    )
    if approved and post > initial_trade_risk_budget:
        raise AssertionError("approved Scale-In exceeds immutable risk budget")
    return AggregateRiskDecision(
        approved=approved, requested_qty=requested_qty, approved_qty=approved_qty,
        max_safe_add_qty=safe, current_aggregate_risk=current,
        post_scale_aggregate_risk=post, remaining_risk_budget=remaining,
        initial_trade_risk_budget=initial_trade_risk_budget,
        executable_stop=executable_stop, reason=reason,
    )
