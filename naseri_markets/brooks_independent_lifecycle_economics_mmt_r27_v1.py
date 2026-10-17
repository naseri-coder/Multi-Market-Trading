"""MMT-R27 independent, offline cross-check of Brooks V5 hypothetical trade.

The frozen Brooks worker is executed by Stage21A and AGAIN here against the
same original closed-bar input. Exit path, tick rounding, declared funding and
cash-flow arithmetic are independently reconstructed from original candle
values; the Stage21A model's receipt is then compared byte/number-wise.

This checks reproducible *research-model parity* only. It is NOT independent
exchange/Binance market-data custody, actual Brooks order semantics, a broker
fill, an independently attested UTC clock or a profitable OOS result.
No HTTP, account, database, scheduler, PAPER broker or Telegram.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

from .brooks_causal_execution_parity_audit_mmt_r26_v1 import (
    audit_original_stage21a_receipt,
)
from .brooks_causal_lifecycle_stage21_preflight_v1 import (
    _source,
    _validated_continuation,
    run_stage21_brooks_lifecycle_preflight,
)
from .futures_economic_scenario_stage16_v1 import (
    FundingMarkScenario,
    model_linear_usdm_research_scenario,
)

_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,20})(?:\.[0-9]{1,16})?\Z")
_MAX_REPORT = 131072
_REPORT_VERSION = "MMT_R27_INDEPENDENT_BROOKS_MODEL_EXIT_COST_PARITY_V1"


class R27IndependentParityRefused(ValueError):
    """Stable privacy-safe invalid-evidence categories."""


def _canon(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _amount(value: object) -> Decimal:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise R27IndependentParityRefused("R27_STRICT_DECIMAL_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise R27IndependentParityRefused("R27_FINITE_DECIMAL_REQUIRED") from exc
    if not number.is_finite():
        raise R27IndependentParityRefused("R27_FINITE_DECIMAL_REQUIRED")
    return number


def _unique(pairs: list[tuple[str, object]]) -> dict:
    found = {}
    for key, val in pairs:
        if key in found:
            raise R27IndependentParityRefused("R27_DUPLICATE_METADATA_FIELD")
        found[key] = val
    return found


def _contract(raw: bytes, expected_digest: str) -> dict[str, Decimal]:
    if (type(raw) is not bytes or not 2 <= len(raw) <= 4096
            or type(expected_digest) is not str
            or _sha(raw) != expected_digest):
        raise R27IndependentParityRefused("R27_PINNED_METADATA_REQUIRED")
    try:
        body = json.loads(
            raw, object_pairs_hook=_unique,
            parse_float=lambda _v: (_ for _ in ()).throw(ValueError()),
            parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()),
        )
    except R27IndependentParityRefused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise R27IndependentParityRefused("R27_METADATA_JSON_INVALID") from exc
    if (type(body) is not dict
            or body.get("schema_version") != 1
            or type(body.get("schema_version")) is not int
            or body.get("provider_claim") != "binance_usdm_operator_claim"
            or body.get("symbol") != "BTCUSDT"
            or body.get("contract_kind") != "linear_perpetual"
            or body.get("settle_currency") != "USDT"):
        raise R27IndependentParityRefused("R27_CONTRACT_IDENTITY_DRIFT")
    result = {}
    for field in (
        "base_units_per_contract", "price_tick", "quantity_step",
        "taker_fee_fraction", "worst_slippage_fraction",
    ):
        result[field] = _amount(body.get(field))
    if (any(result[k] <= 0 for k in (
            "base_units_per_contract", "price_tick", "quantity_step"))
            or not Decimal("0") <= result["taker_fee_fraction"] <= Decimal("0.01")
            or not Decimal("0") <= result["worst_slippage_fraction"] <= Decimal("0.01")):
        raise R27IndependentParityRefused("R27_CONTRACT_NUMERIC_BOUNDS")
    return result


def _ticks(price: Decimal, tick: Decimal, *, ceil: bool) -> Decimal:
    return (price / tick).to_integral_value(
        rounding=ROUND_CEILING if ceil else ROUND_FLOOR,
    ) * tick


def _independent_lifecycle(geometry, future, tick: Decimal) -> dict:
    if geometry.decision == "NO_SIGNAL":
        if geometry.entry is not None or geometry.stop is not None or geometry.targets:
            raise R27IndependentParityRefused("R27_NO_SIGNAL_WITH_ENTRY_GEOMETRY")
        return {"state": "NO_SIGNAL"}
    if (geometry.decision not in ("LONG", "SHORT")
            or geometry.entry is None or geometry.stop is None
            or not 1 <= len(geometry.targets) <= 10):
        raise R27IndependentParityRefused("R27_INCOMPLETE_FROZEN_GEOMETRY")
    long = geometry.decision == "LONG"
    anchor = _amount(geometry.entry)
    stop = _amount(geometry.stop)
    targets = tuple(_amount(t) for t in geometry.targets)
    if anchor <= 0 or stop <= 0 or any(x <= 0 for x in targets):
        raise R27IndependentParityRefused("R27_NONPOSITIVE_FROZEN_GEOMETRY")
    tp1 = min(targets) if long else max(targets)
    first = future[0]
    entry = _ticks(first["open"], tick, ceil=long)
    if (abs(entry-anchor)/anchor > Decimal("0.02")
            or (not stop < entry < tp1 if long
                else not tp1 < entry < stop)):
        return {"state": "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY"}
    reason = "MAX_HORIZON_UNOBSERVED_STOP_OR_TARGET"
    exit_bar = future[-1]
    exit_raw = exit_bar["close"]
    both = False
    for bar in future:
        stop_hit = bar["low"] <= stop if long else bar["high"] >= stop
        tp_hit = bar["high"] >= tp1 if long else bar["low"] <= tp1
        if stop_hit:
            both = tp_hit
            adverse_gap = bar["open"] < stop if long else bar["open"] > stop
            exit_raw = bar["open"] if adverse_gap else stop
            if adverse_gap:
                reason = "ADVERSE_OPEN_GAP_TO_STOP"
            elif both:
                reason = "STOP_PRIORITY_AMBIGUOUS_BAR"
            else:
                reason = "STOP_TOUCHED"
            exit_bar = bar
            break
        if tp_hit:
            exit_raw = tp1
            exit_bar = bar
            reason = "FIRST_TARGET_CAPPED"
            break
    exit_value = _ticks(exit_raw, tick, ceil=not long)
    if exit_value <= 0:
        raise R27IndependentParityRefused("R27_NONPOSITIVE_MODELED_EXIT")
    return {
        "state": "HYPOTHETICAL_CLOSED_POSITION",
        "side": "long" if long else "short",
        "entry": entry,
        "exit": exit_value,
        "entry_time": first["open_time"],
        "exit_time": exit_bar["close_time"],
        "exit_reason": reason,
        "intrabar_ambiguous": both,
    }


def _independent_economics(
    model: dict, *, metadata: dict[str, Decimal], quantity: str,
    expected_funding_instants: tuple, funding_events: tuple,
    all_future: tuple,
) -> dict:
    qty = _amount(quantity)
    if qty <= 0 or qty / metadata["quantity_step"] != (
            qty / metadata["quantity_step"]).to_integral_value():
        raise R27IndependentParityRefused("R27_MODELED_QUANTITY_GRID_DRIFT")
    if (type(expected_funding_instants) is not tuple
            or type(funding_events) is not tuple
            or len(expected_funding_instants) > 16
            or len(funding_events) > 16
            or len(expected_funding_instants) != len(funding_events)
            or tuple(sorted(set(expected_funding_instants))) != expected_funding_instants):
        raise R27IndependentParityRefused("R27_FUNDING_TAPE_INCOMPLETE")
    entry_time = model["entry_time"]
    horizon_end = all_future[-1]["close_time"]
    signed = Decimal(1) if model["side"] == "long" else Decimal(-1)
    funding = Decimal(0)
    settled = 0
    for timestamp, event in zip(
        expected_funding_instants, funding_events, strict=True,
    ):
        if (type(event) is not FundingMarkScenario
                or type(timestamp) is not type(entry_time)
                or timestamp.tzinfo is None
                or timestamp.utcoffset() != timedelta(0)
                or not entry_time < timestamp <= horizon_end
                or event.at != timestamp):
            raise R27IndependentParityRefused("R27_FUNDING_SOURCE_TIMESTAMP_DRIFT")
        rate = _amount(event.funding_rate)
        mark = _amount(event.referenced_mark_price)
        if abs(rate) > Decimal("0.01") or mark <= 0:
            raise R27IndependentParityRefused("R27_FUNDING_RATE_MARK_BOUNDS")
        if timestamp <= model["exit_time"]:
            funding -= signed*qty*metadata["base_units_per_contract"]*mark*rate
            settled += 1
    gross = signed*qty*metadata["base_units_per_contract"]*(
        model["exit"] - model["entry"]
    )
    total_notional = qty*metadata["base_units_per_contract"]*(
        model["entry"] + model["exit"]
    )
    fees = total_notional*metadata["taker_fee_fraction"]
    adverse_slip = total_notional*metadata["worst_slippage_fraction"]
    return {
        "gross_quote": gross,
        "taker_fees_quote": fees,
        "adverse_slippage_quote": adverse_slip,
        "funding_cashflow_quote": funding,
        "net_scenario_quote": gross-fees-adverse_slip+funding,
        "settled_funding_events": settled,
    }


def review_r27_independent_geometry_cost_parity(
    *, original_stage21a_report_bytes: bytes,
    original_closed_bar_replay_bytes: bytes, frozen_source: Path,
    later_closed_candles: tuple[dict, ...],
    contract_metadata_bytes: bytes, contract_metadata_sha256: str,
    quantity_contracts: str,
    expected_funding_instants: tuple,
    funding_mark_events: tuple,
    operator_ack: bool = False,
) -> dict:
    """Rerun genuine frozen worker and independently verify hypothetical model."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R27IndependentParityRefused("R27_NONPRODUCTION_OPERATOR_APPROVAL_REQUIRED")
    if (type(original_stage21a_report_bytes) is not bytes
            or not 2 <= len(original_stage21a_report_bytes) <= _MAX_REPORT):
        raise R27IndependentParityRefused("R27_ORIGINAL_STAGE21A_RECEIPT_REQUIRED")
    try:
        original_audit = audit_original_stage21a_receipt(
            original_report_bytes=original_stage21a_report_bytes,
            operator_ack=True,
        )
        report = json.loads(original_stage21a_report_bytes)
        geometry = _source(original_closed_bar_replay_bytes, frozen_source)
        future = _validated_continuation(
            original_closed_bar_replay_bytes, later_closed_candles,
            geometry.signal_close_at,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise R27IndependentParityRefused("R27_ORIGINAL_FROZEN_EVIDENCE_REFUSED") from exc
    if (report.get("source_manifest_sha256") != geometry.source_manifest_sha256
            or report.get("historical_snapshot_sha256") != geometry.snapshot_sha256
            or report.get("decision_evidence_sha256") != geometry.decision_evidence_sha256
            or report.get("decision_input_sha256") != _sha(original_closed_bar_replay_bytes)
            or report.get("future_input_sha256") != _sha(_canon(later_closed_candles))
            or report.get("decision_cutoff_utc") != geometry.signal_close_at.isoformat()
            or report.get("actual_frozen_brooks_decision") != geometry.decision):
        raise R27IndependentParityRefused("R27_INDEPENDENT_FROZEN_DECISION_DIFFERENCE")
    metadata = _contract(contract_metadata_bytes, contract_metadata_sha256)
    recomputed = _independent_lifecycle(geometry, future, metadata["price_tick"])
    reported = report["hypothetical_trade"]
    if recomputed["state"] != reported.get("state"):
        raise R27IndependentParityRefused("R27_MODELED_ORDER_STATE_MISMATCH")
    if recomputed["state"] != "HYPOTHETICAL_CLOSED_POSITION":
        if reported.get("hypothetical_order") is not False:
            raise R27IndependentParityRefused("R27_NONTRADE_WITH_ORDER_FLAG")
        return _summary(
            original_audit, recomputed, independent_economics=None,
        )
    expected_fields = {
        "entry_reference_price": recomputed["entry"],
        "exit_reference_price": recomputed["exit"],
        "quantity_contracts": _amount(quantity_contracts),
    }
    for key, expected in expected_fields.items():
        if _amount(reported.get(key)) != expected:
            raise R27IndependentParityRefused("R27_MODELED_PRICE_OR_QUANTITY_MISMATCH")
    if (reported.get("entry_time") != recomputed["entry_time"].isoformat()
            or reported.get("exit_assumed_bar_close_time") !=
            recomputed["exit_time"].isoformat()
            or reported.get("exit_reason") != recomputed["exit_reason"]
            or reported.get("intrabar_stop_target_ambiguity") is not
            recomputed["intrabar_ambiguous"]):
        raise R27IndependentParityRefused("R27_MODELED_STOP_TARGET_TIME_MISMATCH")
    independent = _independent_economics(
        recomputed, metadata=metadata, quantity=quantity_contracts,
        expected_funding_instants=expected_funding_instants,
        funding_events=funding_mark_events, all_future=future,
    )
    if (reported.get("funding_event_count") != independent["settled_funding_events"]
            or _amount(reported.get("net_scenario_quote")) !=
            independent["net_scenario_quote"]):
        raise R27IndependentParityRefused("R27_INDEPENDENT_CASHFLOW_MISMATCH")
    # Verify that the original reported Stage16 economics receipt genuinely
    # came from the same independent trade dimensions and full funding tape;
    # this still does NOT authenticate inputs or broker cash settlement.
    try:
        expected_economics = model_linear_usdm_research_scenario(
            contract_metadata_bytes,
            expected_metadata_sha256=contract_metadata_sha256,
            side=recomputed["side"],
            quantity_contracts=quantity_contracts,
            entry_price=str(recomputed["entry"]),
            exit_price=str(recomputed["exit"]),
            entry_at=recomputed["entry_time"],
            exit_at=recomputed["exit_time"],
            funding_mark_events=tuple(
                event for event in funding_mark_events
                if event.at <= recomputed["exit_time"]
            ),
            operator_ack=True,
        )
    except ValueError as exc:
        raise R27IndependentParityRefused("R27_STAGE16_CASHFLOW_VALIDATOR_REFUSED") from exc
    if (reported.get("economic_receipt_sha256") !=
            expected_economics["evidence_sha256"]
            or _amount(expected_economics["net_scenario_quote"]) !=
            independent["net_scenario_quote"]):
        raise R27IndependentParityRefused("R27_MODELED_ECONOMIC_RECEIPT_MISMATCH")
    return _summary(
        original_audit, recomputed, independent_economics=independent,
    )


def _summary(original_audit: dict, model: dict, *, independent_economics: dict | None) -> dict:
    economics = (
        {k: str(v) if isinstance(v, Decimal) else v
         for k, v in independent_economics.items()}
        if independent_economics is not None else None
    )
    result = {
        "protocol": _REPORT_VERSION,
        "original_stage21a_report_sha256": original_audit["original_stage21a_report_sha256"],
        "frozen_brooks_source_manifest_sha256":
            original_audit["frozen_brooks_source_manifest_sha256"],
        "actual_frozen_worker_rerun_and_decision_hash_equal": True,
        "verified_causal_later_input_against_original_cutoff": True,
        "hypothetical_order_path_recomputed_separately": True,
        "hypothetical_state": model["state"],
        "hypothetical_exit_reason": model.get("exit_reason"),
        "independently_recalculated_modeled_cashflows": economics,
        "market_data_independently_issuer_authenticated": False,
        "broker_actual_order_type_and_fill_verified": False,
        "actual_account_fee_tier_and_funding_settlement_verified": False,
        "original_brooks_real_exit_execution_parity_verified": False,
        "intrabar_execution_sequence_observed": False,
        "realized_pnl_evidenced": False,
        "prospective_oos_edge_established": False,
        "paper_connected_or_live_enabled": False,
        "production_modified": False,
        "research_disposition": "REPRODUCIBLE_MODELED_PARITY_ONLY_NOT_REAL_EXECUTION",
    }
    result["report_sha256"] = _sha(_canon(result))
    return result


def run_r27_brooks_two_pass_model_crosscheck(
    *, original_closed_bar_replay_bytes: bytes, frozen_source: Path,
    later_closed_candles: tuple[dict, ...],
    contract_metadata_bytes: bytes, contract_metadata_sha256: str,
    quantity_contracts: str, expected_funding_instants: tuple,
    funding_mark_events: tuple, operator_ack: bool = False,
) -> dict:
    """Execute original Stage21A then a separate original-worker shadow audit."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R27IndependentParityRefused("R27_NONPRODUCTION_OPERATOR_APPROVAL_REQUIRED")
    params = dict(
        original_replay_bytes=original_closed_bar_replay_bytes,
        legacy_source=frozen_source,
        post_signal_closed_candles=later_closed_candles,
        metadata_bytes=contract_metadata_bytes,
        metadata_sha256=contract_metadata_sha256,
        quantity_contracts=quantity_contracts,
        expected_funding_instants=expected_funding_instants,
        funding_mark_events=funding_mark_events,
    )
    try:
        original = run_stage21_brooks_lifecycle_preflight(
            **params, operator_ack=True,
        )
    except ValueError as exc:
        raise R27IndependentParityRefused("R27_ORIGINAL_STAGE21A_MODEL_REFUSED") from exc
    review = review_r27_independent_geometry_cost_parity(
        original_stage21a_report_bytes=_canon(original),
        original_closed_bar_replay_bytes=original_closed_bar_replay_bytes,
        frozen_source=frozen_source, later_closed_candles=later_closed_candles,
        contract_metadata_bytes=contract_metadata_bytes,
        contract_metadata_sha256=contract_metadata_sha256,
        quantity_contracts=quantity_contracts,
        expected_funding_instants=expected_funding_instants,
        funding_mark_events=funding_mark_events,
        operator_ack=True,
    )
    return {"stage21a_original_report": original, "r27_independent_review": review}


__all__ = [
    "R27IndependentParityRefused",
    "review_r27_independent_geometry_cost_parity",
    "run_r27_brooks_two_pass_model_crosscheck",
]
