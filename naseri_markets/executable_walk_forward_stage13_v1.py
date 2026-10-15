"""Stage 13: executable, deliberately bounded offline forward-chaining BACKTEST.

Runs the actual reviewed internal contract fixture via Stage-5/Universal Core
API over DATA-A1-validated archive candles. No strategy fitting, production
engine, real provider evidence, external order router, or profitability claim.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from ._contract_acceptance_fixture_v1 import OfflineContractFixture
from .contracts import Direction
from .core_api_v1 import (
    CoreBinding, CoreEventType, DataOrigin, DecisionKind, OfflineCoreHarness,
    _TIMEFRAME_MINUTES,
)
from .historical_data_loader_a1 import HistoricalFileSpec, validate_historical_file
from .historical_pit_quality_stage12_v1 import inspect_historical_pit_archive
from .market_data_engine_v1 import (
    OfflineMarketDataEngine, PriceBasis, VolumeSemantics,
)

ZERO = Decimal("0")
ONE = Decimal("1")
MAX_BARS = 5000


class ExecutableWalkForwardRefused(ValueError):
    """Fixed, non-disclosing refusal; no operator orders or private data."""


def _utc(value: datetime) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ExecutableWalkForwardRefused("STAGE13_EXPLICIT_UTC_BOUNDARY_REQUIRED")
    return value.astimezone(UTC)


def _fraction(value: Decimal, *, max_value: Decimal, label: str) -> None:
    if type(value) is not Decimal or not value.is_finite() or not ZERO <= value <= max_value:
        raise ExecutableWalkForwardRefused("STAGE13_INVALID_" + label)


def _wire(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class FrozenExecutionPlan:
    """One frozen, fixed-rule candidate. NOT a parameter optimizer."""

    training_end: datetime
    validation_end: datetime
    study_end: datetime
    validation_folds: int
    embargo_bars: int
    fee_bps_per_side: Decimal
    slippage_bps_per_side: Decimal
    initial_capital: Decimal
    notional_fraction: Decimal
    min_closed_per_segment: int

    def __post_init__(self) -> None:
        starts = tuple(_utc(t) for t in (
            self.training_end, self.validation_end, self.study_end,
        ))
        if (not starts[0] < starts[1] < starts[2]
                or starts[2] - starts[0] > timedelta(days=400)
                or type(self.validation_folds) is not int
                or not 2 <= self.validation_folds <= 8
                or type(self.embargo_bars) is not int
                or not 1 <= self.embargo_bars <= 100
                or type(self.min_closed_per_segment) is not int
                or not 1 <= self.min_closed_per_segment <= 1000):
            raise ExecutableWalkForwardRefused("STAGE13_INVALID_FROZEN_FOLDS")
        _fraction(self.fee_bps_per_side, max_value=Decimal("100"), label="FEE_BPS")
        _fraction(self.slippage_bps_per_side, max_value=Decimal("100"), label="SLIPPAGE_BPS")
        _fraction(self.notional_fraction, max_value=ONE, label="NOTIONAL_FRACTION")
        if (self.notional_fraction == ZERO or type(self.initial_capital) is not Decimal
                or not self.initial_capital.is_finite() or self.initial_capital <= ZERO):
            raise ExecutableWalkForwardRefused("STAGE13_INVALID_CAPITAL_OR_NOTIONAL")


def _slice_outcomes(packets: tuple, start: int, end: int, spec: HistoricalFileSpec,
                    plan: FrozenExecutionPlan) -> dict:
    """Fresh core evaluation per segment; previous bars are history only.

    Signals generated at close(t) can enter no sooner than OPEN(t+1).
    A fill's stop/target is evaluated on its entry bar; intrabar ambiguity
    assumes stop-before-target, with adverse fill slippage and gap handling.
    No position is silently liquidated at a segment boundary.
    """
    fixture = OfflineContractFixture()
    if spec.feed.instrument.market not in fixture.manifest.supported_markets:
        raise ExecutableWalkForwardRefused("STAGE13_CORE_UNSUPPORTED_MARKET")
    market = OfflineMarketDataEngine(enabled=True)
    market.register_feed(spec.feed)
    binding = CoreBinding("stage13_fixture", "stage13_binding",
                          spec.feed.instrument, spec.feed.timeframe)
    market.subscribe(spec.feed.feed_id, fixture.manifest, binding)
    harness = OfflineCoreHarness(fixture, enabled=True)
    if start < 0 or not start < end <= len(packets):
        raise ExecutableWalkForwardRefused("STAGE13_INVALID_SEGMENT_INDEX")
    fee = plan.fee_bps_per_side / Decimal("10000")
    slip = plan.slippage_bps_per_side / Decimal("10000")
    pending = None
    position = None
    evaluations = entries = filled = closed = busy = invalid = stops_first = 0
    costs = gross = ZERO
    realized_rs: list[Decimal] = []
    trade_evidence: list[tuple] = []
    # The engine sees each market packet at most once and has no access to
    # next-bar OHLC when it evaluates the current closed candle.
    for index, packet in enumerate(packets[:end]):
        dispatched = market.ingest(packet)
        if index >= start:
            candle = packet.candle
            if pending is not None:
                decision, signal_time = pending
                pending = None
                entry = candle.open * (
                    ONE + slip if decision.direction is Direction.LONG else ONE - slip
                )
                geometry = (decision.stop < entry
                            if decision.direction is Direction.LONG
                            else decision.stop > entry)
                if not geometry:
                    invalid += 1
                else:
                    qty = plan.initial_capital * plan.notional_fraction / entry
                    initial_risk = qty * abs(entry - decision.stop)
                    position = (decision, entry, qty, initial_risk, signal_time)
                    filled += 1
            if position is not None:
                dec, entry, qty, initial_risk, signal_at = position
                if dec.direction is Direction.LONG:
                    stopped = candle.low <= dec.stop
                    targeted = candle.high >= dec.targets[0]
                    price = (min(candle.open, dec.stop) if stopped
                             else dec.targets[0] if targeted else None)
                    if price is not None:
                        price *= (ONE - slip)
                else:
                    stopped = candle.high >= dec.stop
                    targeted = candle.low <= dec.targets[0]
                    price = (max(candle.open, dec.stop) if stopped
                             else dec.targets[0] if targeted else None)
                    if price is not None:
                        price *= (ONE + slip)
                if price is not None:
                    if stopped and targeted:
                        stops_first += 1
                    pnl = qty * (price - entry) * (
                        ONE if dec.direction is Direction.LONG else -ONE
                    )
                    charge = (qty * entry + qty * price) * fee
                    gross += pnl
                    costs += charge
                    realized_rs.append((pnl - charge) / initial_risk)
                    trade_evidence.append((
                        signal_at.isoformat(), candle.close_at.isoformat(),
                        dec.decision_id, dec.direction.value,
                        str(entry), str(price), str(qty), str(pnl), str(charge),
                    ))
                    closed += 1
                    position = None
        for delivery in dispatched.deliveries:
            result = harness.evaluate(delivery.event)
            if index < start:
                continue
            evaluations += 1
            actionable = [d for d in result.decisions
                          if d.kind is DecisionKind.ENTRY_INTENT]
            if any(d.kind not in (DecisionKind.ENTRY_INTENT, DecisionKind.NO_SETUP)
                   for d in result.decisions) or len(actionable) > 1:
                raise ExecutableWalkForwardRefused("STAGE13_UNSUPPORTED_CORE_ACTION")
            if actionable:
                entries += 1
                if pending is not None or position is not None:
                    busy += 1
                else:
                    pending = (actionable[0], delivery.event.observed_at)
    pending_count = int(pending is not None)
    open_count = int(position is not None)
    blockers = []
    if pending_count or open_count:
        blockers.append("SEGMENT_END_PENDING_OR_OPEN_CENSORED")
    if invalid:
        blockers.append("NEXT_OPEN_INVALID_STOP_GEOMETRY")
    if closed < plan.min_closed_per_segment:
        blockers.append("INSUFFICIENT_CLOSED_TRADES")
    return {
        "core_evaluations": evaluations,
        "entry_intents": entries,
        "filled": filled, "closed": closed,
        "busy_entries_not_filled": busy,
        "invalid_next_open": invalid,
        "pending_unfilled_at_end": pending_count,
        "open_unresolved_at_end": open_count,
        "both_hit_stop_first": stops_first,
        "gross_pnl": str(gross), "modeled_fees": str(costs),
        "net_pnl": str(gross-costs),
        "mean_net_r": str(sum(realized_rs, ZERO)/closed) if closed else None,
        "stress_2x_fees_net_pnl": str(gross-2*costs),
        "trade_digest": hashlib.sha256(_wire(trade_evidence)).hexdigest(),
        "blockers": blockers,
    }


def execute_frozen_walk_forward(
    path: Path,
    spec: HistoricalFileSpec,
    *,
    receipt_bytes: bytes,
    trusted_receipt_sha256: str,
    plan: FrozenExecutionPlan,
    operator_ack: bool = False,
) -> dict:
    """Actual fixed Core.evaluate calls in each fold; retrospective source unverified."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise ExecutableWalkForwardRefused("STAGE13_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if type(plan) is not FrozenExecutionPlan or type(spec) is not HistoricalFileSpec:
        raise ExecutableWalkForwardRefused("STAGE13_FROZEN_PLAN_AND_SPEC_REQUIRED")
    if (spec.feed.event is not CoreEventType.CLOSED_CANDLE
            or spec.feed.origin is not DataOrigin.REPLAY
            or spec.feed.price_basis is not PriceBasis.TRADE
            or spec.feed.volume_semantics is not VolumeSemantics.TRADED):
        raise ExecutableWalkForwardRefused("STAGE13_CRYPTO_TRADE_CANDLE_ONLY")
    # Stage-12 checks archive acquisition relative to STUDY END, not any
    # historical fold entry. This NEVER upgrades historical provenance.
    pit = inspect_historical_pit_archive(
        path, spec, receipt_bytes=receipt_bytes,
        trusted_receipt_sha256=trusted_receipt_sha256,
        as_of_utc=plan.study_end, operator_ack=True,
    )
    approved = validate_historical_file(path, spec)
    if approved.report.sha256 != pit.dataset_sha256:
        raise ExecutableWalkForwardRefused("STAGE13_DATASET_DIGEST_DRIFT")
    if approved.report.rows_validated > MAX_BARS:
        raise ExecutableWalkForwardRefused("STAGE13_BAR_CAP_EXCEEDED")
    packets = tuple(approved.packets())
    if not packets or packets[-1].candle.close_at != plan.study_end:
        raise ExecutableWalkForwardRefused("STAGE13_STUDY_END_MISMATCH")
    # All segment boundaries must coincide with a closed bar to prevent
    # any mid-candle event ordering ambiguity.
    end_index = {p.candle.close_at: i + 1 for i, p in enumerate(packets)}
    if plan.training_end not in end_index or plan.validation_end not in end_index:
        raise ExecutableWalkForwardRefused("STAGE13_FOLD_BOUNDARY_NOT_CLOSED_BAR")
    cut1 = end_index[plan.training_end]
    cut2 = end_index[plan.validation_end]
    if not 3 <= cut1 < cut2 < len(packets) - 1:
        raise ExecutableWalkForwardRefused("STAGE13_SEGMENTS_TOO_SHORT")
    interval = cut2 - cut1
    if interval % plan.validation_folds:
        raise ExecutableWalkForwardRefused("STAGE13_FOLDS_REQUIRE_WHOLE_BARS")
    width = interval // plan.validation_folds
    if width < 2 or plan.embargo_bars >= cut1 - 1:
        raise ExecutableWalkForwardRefused("STAGE13_EMBARGO_OR_FOLD_TOO_SHORT")
    folds = []
    for i in range(plan.validation_folds):
        left, right = cut1+i*width, cut1+(i+1)*width
        train_end = left-plan.embargo_bars
        train = _slice_outcomes(packets, 0, train_end, spec, plan)
        test = _slice_outcomes(packets, left, right, spec, plan)
        folds.append({
            "fold_index": i,
            "train_cutoff_utc": packets[train_end-1].candle.close_at.isoformat(),
            "test_start_utc": packets[left].candle.open_at.isoformat(),
            "test_end_utc": packets[right-1].candle.close_at.isoformat(),
            "train": train, "test": test,
        })
    holdout = _slice_outcomes(packets, cut2, len(packets), spec, plan)
    blockers = sorted({
        f"FOLD_{f['fold_index']}_TRAIN_{b}" for f in folds for b in f["train"]["blockers"]
    } | {
        f"FOLD_{f['fold_index']}_TEST_{b}" for f in folds for b in f["test"]["blockers"]
    } | {f"HOLDOUT_{b}" for b in holdout["blockers"]})
    report = {
        "stage": "STAGE13_EXECUTABLE_FIXED_CORE_FORWARD_CHAINING_V1",
        "dataset_sha256": pit.dataset_sha256,
        "pit_evidence_sha256": pit.evidence_sha256,
        "core_id": OfflineContractFixture().manifest.core_id,
        "core_version": OfflineContractFixture().manifest.core_version,
        "strategy_parameters_fitted": False,
        "historical_archival_provider_verified": False,
        "independent_pit_custody_verified": False,
        "funding_mark_contract_economics_verified": False,
        "walk_forward_strategy_refit_per_fold": False,
        "sample_significance_established": False,
        "profitability_proven": False,
        "broker_order_sent": False,
        "telegram_sent": False,
        "live_authorized": False,
        "fee_bps_per_side": str(plan.fee_bps_per_side),
        "slippage_bps_per_side": str(plan.slippage_bps_per_side),
        "folds": folds, "reserved_final_holdout": holdout,
        "blockers": blockers,
        "verdict": ("EXECUTED_SYNTHETIC_CORE_DESCRIPTIVE_ONLY"
                    if not blockers else "EXECUTED_WITH_UNRESOLVED_EVIDENCE_BLOCKERS"),
    }
    report["evidence_sha256"] = hashlib.sha256(_wire(report)).hexdigest()
    return report


__all__ = [
    "ExecutableWalkForwardRefused", "FrozenExecutionPlan",
    "execute_frozen_walk_forward",
]
