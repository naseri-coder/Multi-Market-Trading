"""Stage16: conservative *scenario-only* USD-M cash-flow accounting.

This is not an exchange-certified fee schedule, funding history, mark tape,
liquidation model, real order fill or a Brooks V5 trading performance engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_DEC = re.compile(r"-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,12})?\Z")
_KEYS = frozenset({
    "schema_version", "provider_claim", "symbol", "contract_kind",
    "settle_currency", "base_units_per_contract", "price_tick",
    "quantity_step", "taker_fee_fraction", "worst_slippage_fraction",
    "maintenance_margin_fraction", "source_metadata_sha256",
})


class FuturesScenarioRefused(ValueError):
    """No raw, untrusted financial text is reflected in errors."""


def _pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise FuturesScenarioRefused("ST16_DUPLICATE_ECONOMIC_PARAMETER")
        result[key] = value
    return result


def _reject_float(_value: str) -> None:
    raise FuturesScenarioRefused("ST16_NONCANONICAL_ECONOMIC_NUMBER")


def _amount(value: object, *, allow_negative: bool = False,
            allow_zero: bool = False) -> Decimal:
    if type(value) is not str or not _DEC.fullmatch(value):
        raise FuturesScenarioRefused("ST16_EXACT_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise FuturesScenarioRefused("ST16_INVALID_DECIMAL") from exc
    if (not number.is_finite() or (number < 0 and not allow_negative)
            or (number == 0 and not allow_zero)):
        raise FuturesScenarioRefused("ST16_OUT_OF_RANGE_DECIMAL")
    return number


def _time(value: datetime) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != __import__("datetime").timedelta(0)):
        raise FuturesScenarioRefused("ST16_EXPLICIT_UTC_EVENT_TIME_REQUIRED")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class FundingMarkScenario:
    at: datetime
    funding_rate: str
    referenced_mark_price: str


def model_linear_usdm_research_scenario(
    metadata_bytes: bytes,
    *, expected_metadata_sha256: str,
    side: str,
    quantity_contracts: str,
    entry_price: str,
    exit_price: str,
    entry_at: datetime,
    exit_at: datetime,
    funding_mark_events: tuple[FundingMarkScenario, ...],
    operator_ack: bool = False,
) -> dict:
    """Calculate explicit gross, two taker fees, adverse slip and funding.

    No entry/exit are taken from real Brooks; caller's modeled assumptions
    are not independently attested. The future event inventory is unverified.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise FuturesScenarioRefused("ST16_EXPLICIT_RESEARCH_ACK_REQUIRED")
    if (type(metadata_bytes) is not bytes
            or not 1 <= len(metadata_bytes) <= 4096
            or type(expected_metadata_sha256) is not str
            or not _HEX.fullmatch(expected_metadata_sha256)):
        raise FuturesScenarioRefused("ST16_PINNED_ECONOMIC_METADATA_REQUIRED")
    metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    if metadata_sha != expected_metadata_sha256:
        raise FuturesScenarioRefused("ST16_ECONOMIC_METADATA_DIGEST_DRIFT")
    try:
        body = json.loads(
            metadata_bytes, object_pairs_hook=_pairs,
            parse_float=_reject_float, parse_constant=_reject_float,
        )
    except FuturesScenarioRefused:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise FuturesScenarioRefused("ST16_INVALID_ECONOMIC_METADATA_JSON") from exc
    if (type(body) is not dict or set(body) != _KEYS
            or type(body["schema_version"]) is not int
            or body["schema_version"] != 1
            or body["provider_claim"] != "binance_usdm_operator_claim"
            or body["symbol"] != "BTCUSDT"
            or body["contract_kind"] != "linear_perpetual"
            or body["settle_currency"] != "USDT"
            or type(body["source_metadata_sha256"]) is not str
            or not _HEX.fullmatch(body["source_metadata_sha256"])):
        raise FuturesScenarioRefused("ST16_EXACT_LINEAR_SETTLED_CONTRACT_REQUIRED")
    mult = _amount(body["base_units_per_contract"])
    tick = _amount(body["price_tick"])
    step = _amount(body["quantity_step"])
    fee = _amount(body["taker_fee_fraction"], allow_zero=True)
    slip = _amount(body["worst_slippage_fraction"], allow_zero=True)
    maint = _amount(body["maintenance_margin_fraction"])
    if (mult > 1000 or tick > 10000 or step > 1000
            or fee > Decimal("0.01") or slip > Decimal("0.01")
            or maint >= Decimal("1")):
        raise FuturesScenarioRefused("ST16_ECONOMIC_PARAMETER_BOUNDS")
    if side not in ("long", "short"):
        raise FuturesScenarioRefused("ST16_EXACT_DIRECTION_REQUIRED")
    qty, entry, exit_price_dec = (
        _amount(quantity_contracts), _amount(entry_price), _amount(exit_price)
    )
    if (qty / step != (qty / step).to_integral_value()
            or entry / tick != (entry / tick).to_integral_value()
            or exit_price_dec / tick != (exit_price_dec / tick).to_integral_value()):
        raise FuturesScenarioRefused("ST16_PRICE_OR_LOT_GRID_VIOLATION")
    start, end = _time(entry_at), _time(exit_at)
    if not start < end:
        raise FuturesScenarioRefused("ST16_NONCAUSAL_SCENARIO_TIMES")
    if (type(funding_mark_events) is not tuple
            or len(funding_mark_events) > 128):
        raise FuturesScenarioRefused("ST16_BOUNDED_FUNDING_MARK_REQUIRED")
    sign = Decimal(1) if side == "long" else Decimal(-1)
    funding_quote = Decimal(0)
    last = start
    rows = []
    for event in funding_mark_events:
        if type(event) is not FundingMarkScenario:
            raise FuturesScenarioRefused("ST16_EXACT_FUNDING_MARK_EVENT_REQUIRED")
        when = _time(event.at)
        rate = _amount(event.funding_rate, allow_negative=True, allow_zero=True)
        mark = _amount(event.referenced_mark_price)
        if not last < when <= end or abs(rate) > Decimal("0.01"):
            raise FuturesScenarioRefused("ST16_FUNDING_ORDER_OR_RATE_INVALID")
        last = when
        # Positive rate: longs pay; shorts receive. Reference notional is
        # explicitly the observed *claimed* mark at each funding instant.
        amount = -sign * qty * mult * mark * rate
        funding_quote += amount
        rows.append([when.isoformat(), str(rate), str(mark), str(amount)])
    gross = sign * qty * mult * (exit_price_dec - entry)
    fees = qty * mult * (entry + exit_price_dec) * fee
    # Conservative stress estimate, separate from actual fills and fees.
    adverse_slippage = qty * mult * (entry + exit_price_dec) * slip
    net = gross - fees - adverse_slippage + funding_quote
    receipt = {
        "source_metadata_sha256": metadata_sha,
        "funding_event_count": len(rows),
        "funding_events_sha256": hashlib.sha256(json.dumps(
            rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "side": side, "contracts": str(qty), "multiplier": str(mult),
        "entry": str(entry), "exit": str(exit_price_dec),
        "gross_quote": str(gross), "taker_fees_quote": str(fees),
        "adverse_slippage_quote": str(adverse_slippage),
        "funding_cashflow_quote": str(funding_quote),
        "net_scenario_quote": str(net),
        "funding_history_completeness_attested": False,
        "historical_mark_prices_authenticated": False,
        "contract_metadata_authenticated": False,
        "liquidation_margin_model_complete": False,
        "maker_taker_account_tier_verified": False,
        "actual_execution_fills_verified": False,
        "connected_to_real_brooks_trades": False,
        "backtest_profitability_proven": False,
        "live_trading_authorized": False,
        "status": "MODELED_CASHFLOWS_ONLY_ECONOMIC_EVIDENCE_INCOMPLETE",
    }
    receipt["evidence_sha256"] = hashlib.sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return receipt


__all__ = ["FundingMarkScenario", "FuturesScenarioRefused",
           "model_linear_usdm_research_scenario"]
