"""Stage21 PREPARATION ONLY: authentic frozen Brooks decision -> modeled lifecycle.

Research-only, not a prospective feed, not live PAPER deployment or real
broker fills. The *existing* Stage15 frozen worker and safety reviewer certify
decision geometry before a separately named next-open hypothetical model runs.
No state, strategy mutation, HTTP, database, broker, Telegram or background job.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path

from .brooks_replay import (
    LEGACY_MANIFEST_SHA256,
    parse_candle_replay,
    verify_legacy_source,
)
from .futures_economic_scenario_stage16_v1 import (
    FundingMarkScenario,
    model_linear_usdm_research_scenario,
)
from .real_brooks_historical_stage15_v1 import _review, _worker


class Stage21StudyRefused(ValueError):
    """Constant refusal strings to avoid leaking source or account details."""


@dataclass(frozen=True, slots=True)
class FrozenGeometry:
    """Actual source-pinned V5 worker result; not exchange order evidence."""
    decision: str
    input_sha256: str
    source_manifest_sha256: str
    snapshot_sha256: str
    decision_evidence_sha256: str
    signal_close_at: datetime
    entry: str | None
    stop: str | None
    targets: tuple[str, ...]


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(v: object) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _decimal(v: object, *, positive: bool = True) -> Decimal:
    if type(v) is not str or not 1 <= len(v) <= 40:
        raise Stage21StudyRefused("ST21_DECIMAL_STRING_REQUIRED")
    try:
        n = Decimal(v)
    except InvalidOperation as exc:
        raise Stage21StudyRefused("ST21_BAD_DECIMAL") from exc
    if not n.is_finite() or (n <= 0 if positive else n < 0):
        raise Stage21StudyRefused("ST21_NONPOSITIVE_DECIMAL")
    return n


def _source(payload: bytes, root: Path) -> FrozenGeometry:
    if (not isinstance(root, Path) or not root.is_absolute() or root.is_symlink()
            or not root.is_dir()):
        raise Stage21StudyRefused("ST21_ABSOLUTE_FROZEN_SOURCE_REQUIRED")
    if type(payload) is not bytes or not 1 <= len(payload) <= 524288:
        raise Stage21StudyRefused("ST21_BOUNDED_ORIGINAL_REPLAY_REQUIRED")
    raw, _, bars = parse_candle_replay(payload)
    if len(bars) > 224:
        raise Stage21StudyRefused("ST21_FUTURE_CONTEXT_CAPACITY_REQUIRED")
    manifest = verify_legacy_source(root)
    if manifest != LEGACY_MANIFEST_SHA256:
        raise Stage21StudyRefused("ST21_FROZEN_MANIFEST_MISMATCH")
    output = _worker(root, payload, 30)
    approved = _review(raw, output, manifest)
    return FrozenGeometry(
        decision=approved["decision"],
        input_sha256=_hash(payload),
        source_manifest_sha256=manifest,
        snapshot_sha256=approved["snapshot_sha256"],
        decision_evidence_sha256=approved["decision_evidence_sha256"],
        signal_close_at=bars[-1]["close_time"],
        entry=output.get("entry"),
        stop=output.get("stop"),
        targets=tuple(output.get("targets", ())),
    )


def _round_price(price: Decimal, tick: Decimal, *, upward: bool) -> Decimal:
    return (price / tick).to_integral_value(
        rounding=ROUND_CEILING if upward else ROUND_FLOOR
    ) * tick


def _validated_continuation(
    replay: bytes, future_bars: tuple[dict, ...], cutoff: datetime,
) -> tuple[dict, ...]:
    if (type(future_bars) is not tuple
            or not 1 <= len(future_bars) <= 32
            or any(type(x) is not dict for x in future_bars)):
        raise Stage21StudyRefused("ST21_BOUNDED_EXPLICIT_FUTURE_BARS_REQUIRED")
    raw, _, original = parse_candle_replay(replay)
    if original[-1]["close_time"] != cutoff or len(original) + len(future_bars) > 256:
        raise Stage21StudyRefused("ST21_EXACT_DECISION_CUTOFF_REQUIRED")
    combined = dict(raw)
    combined["candles"] = raw["candles"] + list(future_bars)
    try:
        _, _, checked = parse_candle_replay(_canon(combined))
    except ValueError as exc:
        raise Stage21StudyRefused("ST21_NONCAUSAL_OR_UNVERIFIED_FUTURE_BARS") from exc
    future = tuple(checked[len(original):])
    if len(future) != len(future_bars) or future[0]["open_time"] != cutoff:
        raise Stage21StudyRefused("ST21_CANDLE_CONTINUATION_DRIFT")
    return future


def _model_next_open(
    geometry: FrozenGeometry, *,
    future: tuple[dict, ...],
    quantity: str,
    metadata: bytes,
    metadata_sha256: str,
    expected_funding_instants: tuple[datetime, ...],
    funding_events: tuple[FundingMarkScenario, ...],
) -> dict:
    """Transparent hypothetical next-open market/TP1 model; no fill assertion."""
    if (type(metadata) is not bytes or not 1 <= len(metadata) <= 4096
            or type(metadata_sha256) is not str or _hash(metadata) != metadata_sha256):
        raise Stage21StudyRefused("ST21_PINNED_CONTRACT_ASSUMPTIONS_REQUIRED")
    try:
        body = json.loads(metadata)
        tick = _decimal(body["price_tick"])
    except (TypeError, KeyError, ValueError, UnicodeError) as exc:
        raise Stage21StudyRefused("ST21_BAD_CONTRACT_TICK") from exc
    if type(geometry) is not FrozenGeometry:
        raise Stage21StudyRefused("ST21_FROZEN_GEOMETRY_REQUIRED")
    if geometry.decision == "NO_SIGNAL":
        if any([geometry.entry is not None, geometry.stop is not None, geometry.targets]):
            raise Stage21StudyRefused("ST21_NO_SIGNAL_GEOMETRY_INVALID")
        return {
            "state": "NO_SIGNAL", "hypothetical_order": False,
            "broker_fill_verified": False, "net_scenario_quote": None,
        }
    if (geometry.decision not in ("LONG", "SHORT")
            or not geometry.targets or len(geometry.targets) > 10):
        raise Stage21StudyRefused("ST21_COMPLETE_VALIDATED_GEOMETRY_REQUIRED")
    side = "long" if geometry.decision == "LONG" else "short"
    is_long = side == "long"
    intent_entry = _decimal(geometry.entry)
    stop = _decimal(geometry.stop)
    target = (min(_decimal(x) for x in geometry.targets) if is_long
              else max(_decimal(x) for x in geometry.targets))
    first = future[0]
    opening = first["open"]
    entry = _round_price(opening, tick, upward=is_long)
    if (abs(entry - intent_entry) / intent_entry > Decimal("0.02")
            or (not stop < entry < target if is_long else not target < entry < stop)):
        return {
            "state": "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY",
            "hypothetical_order": False,
            "broker_fill_verified": False, "net_scenario_quote": None,
        }
    exit_reason = "MAX_HORIZON_UNOBSERVED_STOP_OR_TARGET"
    exit_bar = future[-1]
    unrounded_exit = exit_bar["close"]
    intrabar_ambiguity = False
    for bar in future:
        hit_stop = (bar["low"] <= stop if is_long else bar["high"] >= stop)
        hit_target = (bar["high"] >= target if is_long else bar["low"] <= target)
        if hit_stop:
            intrabar_ambiguity = hit_target
            gap_through = (bar["open"] < stop if is_long else bar["open"] > stop)
            unrounded_exit = bar["open"] if gap_through else stop
            exit_reason = ("ADVERSE_OPEN_GAP_TO_STOP" if gap_through
                           else "STOP_PRIORITY_AMBIGUOUS_BAR" if hit_target
                           else "STOP_TOUCHED")
            exit_bar = bar
            break
        if hit_target:
            # Never award a more favourable exit for opening through target.
            unrounded_exit = target
            exit_reason = "FIRST_TARGET_CAPPED"
            exit_bar = bar
            break
    exit_price = _round_price(unrounded_exit, tick, upward=not is_long)
    if exit_price <= 0:
        raise Stage21StudyRefused("ST21_UNUSABLE_EXIT_TICK")
    entry_time = first["open_time"]
    exit_time = exit_bar["close_time"]
    if (type(expected_funding_instants) is not tuple
            or type(funding_events) is not tuple
            or len(expected_funding_instants) > 16
            or len(funding_events) > 16):
        raise Stage21StudyRefused("ST21_PINNED_FUNDING_INVENTORY_REQUIRED")
    if (any(type(t) is not datetime or t.tzinfo is None
            or t.utcoffset() != timedelta(0) for t in expected_funding_instants)
            or tuple(sorted(set(expected_funding_instants))) != expected_funding_instants):
        raise Stage21StudyRefused("ST21_FUNDING_SCHEDULE_ORDER_DRIFT")
    # Require a complete, ordered, predeclared funding tape over the WHOLE
    # supplied future horizon. Events after an early stop/TP are verified but
    # must not be charged to an already-closed hypothetical position.
    horizon_end = future[-1]["close_time"]
    if (any(not entry_time < t <= horizon_end for t in expected_funding_instants)
            or any(type(e) is not FundingMarkScenario for e in funding_events)
            or tuple(e.at for e in funding_events) != expected_funding_instants):
        raise Stage21StudyRefused("ST21_MISSING_EXTRA_OR_UNORDERED_FUNDING")
    actual = tuple(e for e in funding_events if e.at <= exit_time)
    try:
        costs = model_linear_usdm_research_scenario(
            metadata, expected_metadata_sha256=metadata_sha256,
            side=side, quantity_contracts=quantity,
            entry_price=str(entry), exit_price=str(exit_price),
            entry_at=entry_time, exit_at=exit_time,
            funding_mark_events=actual, operator_ack=True,
        )
    except ValueError as exc:
        raise Stage21StudyRefused("ST21_STAGE16_ECONOMIC_MODEL_REFUSED") from exc
    return {
        "state": "HYPOTHETICAL_CLOSED_POSITION",
        "hypothetical_order": True,
        "entry_model": "NEXT_CANDLE_OPEN_MARKET_ASSUMPTION",
        "exit_model": "NEAREST_TP_OR_STOP_FIRST_ADVERSE_GAP_PRIORITY",
        "exit_reason": exit_reason,
        "intrabar_stop_target_ambiguity": intrabar_ambiguity,
        "entry_time": entry_time.isoformat(),
        "exit_assumed_bar_close_time": exit_time.isoformat(),
        "entry_reference_price": str(entry),
        "exit_reference_price": str(exit_price),
        "quantity_contracts": quantity,
        "economic_receipt_sha256": costs["evidence_sha256"],
        "net_scenario_quote": costs["net_scenario_quote"],
        "funding_event_count": len(actual),
        "broker_fill_verified": False,
        "actual_signal_execution_parity_verified": False,
        "settlement_mark_is_exact": False,
        "account_fee_tier_verified": False,
        "market_impact_verified": False,
    }


def run_stage21_brooks_lifecycle_preflight(
    *, original_replay_bytes: bytes, legacy_source: Path,
    post_signal_closed_candles: tuple[dict, ...],
    metadata_bytes: bytes, metadata_sha256: str,
    quantity_contracts: str,
    expected_funding_instants: tuple[datetime, ...],
    funding_mark_events: tuple[FundingMarkScenario, ...],
    operator_ack: bool = False,
) -> dict:
    """Run genuine engine before exposing later candles, then model one trade."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise Stage21StudyRefused("ST21_EXPLICIT_OFFLINE_RESEARCH_ONLY")
    sealed = _source(original_replay_bytes, legacy_source)
    future = _validated_continuation(
        original_replay_bytes, post_signal_closed_candles, sealed.signal_close_at,
    )
    receipt = _model_next_open(
        sealed, future=future, quantity=quantity_contracts,
        metadata=metadata_bytes, metadata_sha256=metadata_sha256,
        expected_funding_instants=expected_funding_instants,
        funding_events=funding_mark_events,
    )
    result = {
        "stage": "STAGE21_BROOKS_CAUSAL_LIFECYCLE_PREPARATION_V1",
        "status": "ACTUAL_FROZEN_DECISION_HYPOTHETICAL_TRADE_MODEL_ONLY",
        "source_manifest_sha256": sealed.source_manifest_sha256,
        "historical_snapshot_sha256": sealed.snapshot_sha256,
        "decision_evidence_sha256": sealed.decision_evidence_sha256,
        "decision_input_sha256": sealed.input_sha256,
        "future_input_sha256": _hash(_canon(post_signal_closed_candles)),
        "decision_cutoff_utc": sealed.signal_close_at.isoformat(),
        "actual_frozen_brooks_decision": sealed.decision,
        "hypothetical_trade": receipt,
        "independent_dataset_archive_authentication": False,
        "exact_contract_fee_and_mark_verified": False,
        "prospective_holdout_untouched_attested": False,
        "real_brooks_strategy_execution_parity": False,
        "actual_realized_pnl": False,
        "paper_trading_enabled": False,
        "live_trading_authorized": False,
        "network_or_telegram_used": False,
        "production_modified": False,
    }
    result["report_sha256"] = _hash(_canon(result))
    return result


__all__ = ["Stage21StudyRefused", "run_stage21_brooks_lifecycle_preflight"]
