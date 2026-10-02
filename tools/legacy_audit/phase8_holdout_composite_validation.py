"""Phase 8.10 — Unseen Holdout Composite-Filter Validation.

DIAGNOSTIC ONLY. No production rule changes.

This script tests a hypothesis suggested by Phases 8.7-8.9 on earlier, non-overlapping
historical data:

COMPOSITE_V1_DIAGNOSTIC =
    LAST_2 H2/L2 candidate
    AND candidate also survives LAST_3 EH-006 scope
    AND multi-horizon context transition is MULTIHORIZON_CONTINUATION_LIKE

Why this hypothesis exists:
- Phase 8.7 manual review labeled 2 candidates KEEP, 2 REJECT, 3 UNCERTAIN.
- Phase 8.9 classified both KEEP candidates as MULTIHORIZON_CONTINUATION_LIKE.
- The one reviewed UNCERTAIN candidate that was also multi-horizon-continuation-like
  survived only LAST_2, not LAST_3.
- Therefore LAST_3 robustness + multi-horizon continuation is worth testing.

IMPORTANT:
This is a post-review engineering hypothesis and is highly vulnerable to overfitting.
It is NOT a Brooks-authored rule and must NOT be promoted to production based on the
7 reviewed candidates. Phase 8.10 only measures behavior on unseen historical windows.

Holdout:
- Binance Spot
- BTCUSDT and ETHUSDT
- 15m and 1h
- 2000 closed candles per dataset
- fixed end_at 2026-08-20T00:00:00Z
This ends before the Phase 8.7 reviewed BTCUSDT 15m period around Aug 29-Sep 2.

No outcome/P&L/win-rate is computed here. That belongs to later historical outcome
validation/backtesting.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.brooks_core.fundamentals_policy import FundamentalsExecutionPolicy
from app.modules.brooks_core.pullback_guard import (
    assess_h1_h2_l1_l2_counting_window,
)
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.shadow_replay.historical import BinanceHistoricalCandleSource


END_AT = datetime.fromisoformat("2026-08-20T00:00:00+00:00")
EXCHANGE = "binance"
MARKET_TYPE = "spot"
SOURCE_CANDLES = 2000
SNAPSHOT_WINDOW = 100
HORIZONS = (20, 40, 80)

DATASETS = (
    ("BTCUSDT", "15m"),
    ("ETHUSDT", "15m"),
    ("BTCUSDT", "1h"),
    ("ETHUSDT", "1h"),
)


@dataclass(frozen=True, slots=True)
class HorizonEvidence:
    horizon: int
    local_structure: str
    direction_adjusted_displacement: Decimal
    structure_aligned: bool
    displacement_aligned: bool


@dataclass(frozen=True, slots=True)
class Candidate:
    captured_at: str
    snapshot_id: str
    snapshot_hash: str
    direction: str
    setup_type: str
    countertrend_legs: int
    survives_last3: bool
    transition: str
    composite_v1_pass: bool
    pre_context: tuple[HorizonEvidence, ...]
    signal_context: tuple[HorizonEvidence, ...]


@dataclass(frozen=True, slots=True)
class DatasetReport:
    symbol: str
    timeframe: str
    end_at: str
    source_candle_count: int
    evaluated_windows: int
    source_structure_ambiguous: int
    resolved_windows: int
    last2_candidates: int
    last3_candidates: int
    h2_last2: int
    l2_last2: int
    multihorizon_continuation_like: int
    composite_v1_pass: int
    composite_v1_per_1000_windows: float
    transition_counts: dict[str, int]
    candidates: tuple[Candidate, ...]


def q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def evaluate_horizon(
    candles: tuple[Candle, ...],
    *,
    horizon: int,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> HorizonEvidence:
    ctx = candles[-horizon:]
    if len(ctx) != horizon:
        raise ValueError(f"expected {horizon} bars, got {len(ctx)}")

    closes = tuple(c.close for c in ctx)
    highest = max(c.high for c in ctx)
    lowest = min(c.low for c in ctx)
    total_range = highest - lowest
    net = closes[-1] - closes[0]

    signed = Decimal("0") if total_range == 0 else net / total_range
    adjusted = signed if candidate_structure == "BULL_TREND" else -signed

    scan = confirm_swings_causally(
        ctx,
        left_bars=policy.swing_left_bars,
        right_bars=policy.swing_right_bars,
    )
    local_structure = evaluate_br031_structure(scan).direction

    return HorizonEvidence(
        horizon=horizon,
        local_structure=local_structure,
        direction_adjusted_displacement=q(adjusted),
        structure_aligned=local_structure == candidate_structure,
        displacement_aligned=adjusted > 0,
    )


def detect_candidate(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
    guard_scope_bars: int,
):
    full_window = candles[start_index:]
    relative_start = max(0, len(full_window) - guard_scope_bars)
    guard_window = full_window[relative_start:]

    guard = assess_h1_h2_l1_l2_counting_window(guard_window)
    if not guard.allowed:
        return None

    countertrend_legs = 0
    in_countertrend_leg = False
    last_index = len(candles) - 1

    for i in range(start_index + 1, len(candles)):
        previous = candles[i - 1]
        current = candles[i]

        if trend_direction == "BULL_TREND":
            moved_against_trend = current.low < previous.low
            resume_attempt = current.high > previous.high
        else:
            moved_against_trend = current.high > previous.high
            resume_attempt = current.low < previous.low

        if moved_against_trend and not in_countertrend_leg:
            countertrend_legs += 1
            in_countertrend_leg = True

        if resume_attempt and in_countertrend_leg:
            if i == last_index and countertrend_legs >= 2:
                direction = "LONG" if trend_direction == "BULL_TREND" else "SHORT"
                setup_type = "H2_CONFIRMED" if direction == "LONG" else "L2_CONFIRMED"
                return direction, setup_type, countertrend_legs
            in_countertrend_leg = False

    return None


def transition_label(
    pre: tuple[HorizonEvidence, ...],
    signal: tuple[HorizonEvidence, ...],
) -> str:
    pre_pos = sum(item.displacement_aligned for item in pre)
    sig_pos = sum(item.displacement_aligned for item in signal)
    pre_struct = sum(item.structure_aligned for item in pre)
    sig_struct = sum(item.structure_aligned for item in signal)

    if pre_pos == len(HORIZONS) and sig_pos == len(HORIZONS):
        return "MULTIHORIZON_CONTINUATION_LIKE"
    if pre_pos <= 1 and sig_pos >= 2:
        return "LOCAL_REVERSAL_OR_LATE_FLIP_LIKE"
    if pre_struct <= 1 and sig_struct >= 2:
        return "STRUCTURE_FLIP_LIKE"
    if pre_pos >= 2 and sig_pos <= 1:
        return "CONTINUATION_FAILURE_OR_RANGE_LIKE"
    return "MIXED_CONTEXT"


async def evaluate_dataset(
    *,
    source: BinanceHistoricalCandleSource,
    symbol: str,
    timeframe: str,
    policy: FundamentalsExecutionPolicy,
) -> DatasetReport:
    candles = await source.get_closed_candles(
        symbol=symbol,
        timeframe=timeframe,
        limit=SOURCE_CANDLES,
        market_type=MARKET_TYPE,
        end_at=END_AT,
    )

    evaluated = 0
    ambiguous = 0
    resolved = 0
    last3_count = 0
    h2 = 0
    l2 = 0
    transition_counts = Counter()
    candidates: list[Candidate] = []

    for end_index in range(SNAPSHOT_WINDOW - 1, len(candles)):
        window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

        snapshot = MarketSnapshot(
            exchange=EXCHANGE,
            market_type=MARKET_TYPE,
            symbol=symbol,
            timeframe=timeframe,
            candles=window,
            captured_at=window[-1].close_time,
            source="PHASE8_HOLDOUT_COMPOSITE",
        )

        evaluated += 1

        # Hard causality invariants.
        assert snapshot.captured_at == snapshot.candles[-1].close_time
        assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)

        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        structure = evaluate_br031_structure(scan)

        if structure.direction == "AMBIGUOUS":
            ambiguous += 1
            continue

        resolved += 1

        wanted_kind = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        anchors = [s for s in scan.swings if s.kind == wanted_kind]
        if not anchors:
            continue

        start_index = anchors[-1].candle_index
        if len(snapshot.candles) - start_index > policy.pullback_window_bars:
            start_index = len(snapshot.candles) - policy.pullback_window_bars

        last2 = detect_candidate(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=2,
        )
        if last2 is None:
            continue

        last3 = detect_candidate(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=3,
        )

        direction, setup_type, legs = last2
        if direction == "LONG":
            h2 += 1
        else:
            l2 += 1
        survives_last3 = last3 is not None
        if survives_last3:
            last3_count += 1

        pre_prefix = snapshot.candles[: start_index + 1]
        if len(pre_prefix) < max(HORIZONS):
            raise RuntimeError("unexpected insufficient pre-pullback context")

        pre = tuple(
            evaluate_horizon(
                pre_prefix,
                horizon=horizon,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for horizon in HORIZONS
        )
        signal = tuple(
            evaluate_horizon(
                snapshot.candles,
                horizon=horizon,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for horizon in HORIZONS
        )

        transition = transition_label(pre, signal)
        transition_counts[transition] += 1

        composite_pass = (
            survives_last3
            and transition == "MULTIHORIZON_CONTINUATION_LIKE"
        )

        candidates.append(
            Candidate(
                captured_at=snapshot.captured_at.isoformat(),
                snapshot_id=snapshot.snapshot_id,
                snapshot_hash=snapshot.snapshot_hash,
                direction=direction,
                setup_type=setup_type,
                countertrend_legs=legs,
                survives_last3=survives_last3,
                transition=transition,
                composite_v1_pass=composite_pass,
                pre_context=pre,
                signal_context=signal,
            )
        )

    composite_count = sum(c.composite_v1_pass for c in candidates)
    expected_windows = SOURCE_CANDLES - SNAPSHOT_WINDOW + 1
    assert evaluated == expected_windows
    assert ambiguous + resolved == evaluated
    assert h2 + l2 == len(candidates)
    assert last3_count == sum(c.survives_last3 for c in candidates)

    return DatasetReport(
        symbol=symbol,
        timeframe=timeframe,
        end_at=END_AT.isoformat(),
        source_candle_count=len(candles),
        evaluated_windows=evaluated,
        source_structure_ambiguous=ambiguous,
        resolved_windows=resolved,
        last2_candidates=len(candidates),
        last3_candidates=last3_count,
        h2_last2=h2,
        l2_last2=l2,
        multihorizon_continuation_like=sum(
            c.transition == "MULTIHORIZON_CONTINUATION_LIKE"
            for c in candidates
        ),
        composite_v1_pass=composite_count,
        composite_v1_per_1000_windows=round(
            composite_count * 1000.0 / evaluated,
            6,
        ),
        transition_counts=dict(sorted(transition_counts.items())),
        candidates=tuple(candidates),
    )


async def main() -> None:
    output_dir = Path("/out")
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.10 refuses enabled autonomous trade decisions")

    source = BinanceHistoricalCandleSource()
    try:
        reports = []
        for symbol, timeframe in DATASETS:
            reports.append(
                await evaluate_dataset(
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    policy=policy,
                )
            )
    finally:
        await source.aclose()

    total_windows = sum(r.evaluated_windows for r in reports)
    total_last2 = sum(r.last2_candidates for r in reports)
    total_last3 = sum(r.last3_candidates for r in reports)
    total_composite = sum(r.composite_v1_pass for r in reports)

    manifest = {
        "phase": "8.10",
        "mode": "UNSEEN_HOLDOUT_COMPOSITE_VALIDATION_DIAGNOSTIC_ONLY",
        "hypothesis": {
            "name": "COMPOSITE_V1_DIAGNOSTIC",
            "definition": (
                "LAST_2 candidate AND survives LAST_3 AND "
                "MULTIHORIZON_CONTINUATION_LIKE"
            ),
            "warning": (
                "Post-review engineering hypothesis; susceptible to overfitting; "
                "not a Brooks rule and not production-approved."
            ),
        },
        "holdout": {
            "exchange": EXCHANGE,
            "market_type": MARKET_TYPE,
            "end_at": END_AT.isoformat(),
            "source_candles_per_dataset": SOURCE_CANDLES,
            "snapshot_window": SNAPSHOT_WINDOW,
            "horizons": list(HORIZONS),
            "datasets": [
                {"symbol": symbol, "timeframe": timeframe}
                for symbol, timeframe in DATASETS
            ],
            "does_not_overlap_review_period": True,
        },
        "policy_configuration_version": policy.configuration_version,
        "aggregate": {
            "evaluated_windows": total_windows,
            "last2_candidates": total_last2,
            "last3_candidates": total_last3,
            "composite_v1_pass": total_composite,
            "composite_v1_per_1000_windows": round(
                0.0 if total_windows == 0
                else total_composite * 1000.0 / total_windows,
                6,
            ),
        },
        "datasets": [asdict(report) for report in reports],
        "safety": {
            "production_context_gate_modified": False,
            "production_eh006_guard_modified": False,
            "autonomous_trade_decisions": False,
            "database_writes": False,
            "telegram_publish": False,
            "paper_runtime_used": False,
            "outcome_or_pnl_computed": False,
        },
    }

    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=str,
    ) + "\n"

    output = output_dir / "phase8_holdout_composite_validation.json"
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    print("===== PHASE8.10 UNSEEN HOLDOUT COMPOSITE VALIDATION =====")
    print(f"END_AT={END_AT.isoformat()}")
    print(f"DATASETS={len(reports)}")
    print(f"TOTAL_EVALUATED_WINDOWS={total_windows}")
    print()

    for report in reports:
        print(f"--- {report.symbol} {report.timeframe} ---")
        print(f"EVALUATED={report.evaluated_windows}")
        print(f"STRUCTURE_AMBIGUOUS={report.source_structure_ambiguous}")
        print(f"RESOLVED={report.resolved_windows}")
        print(f"LAST2_CANDIDATES={report.last2_candidates}")
        print(f"LAST3_CANDIDATES={report.last3_candidates}")
        print(f"H2_LAST2={report.h2_last2}")
        print(f"L2_LAST2={report.l2_last2}")
        print(
            "MULTIHORIZON_CONTINUATION_LIKE="
            f"{report.multihorizon_continuation_like}"
        )
        print(f"COMPOSITE_V1_PASS={report.composite_v1_pass}")
        print(
            "COMPOSITE_V1_PER_1000_WINDOWS="
            f"{report.composite_v1_per_1000_windows}"
        )
        print(f"TRANSITIONS={report.transition_counts}")

        examples = [c for c in report.candidates if c.composite_v1_pass][:5]
        for c in examples:
            print(
                f"  PASS {c.captured_at} {c.setup_type} "
                f"legs={c.countertrend_legs}"
            )
        print()

    print("--- AGGREGATE ---")
    print(f"LAST2_CANDIDATES={total_last2}")
    print(f"LAST3_CANDIDATES={total_last3}")
    print(f"COMPOSITE_V1_PASS={total_composite}")
    print(
        "COMPOSITE_V1_PER_1000_WINDOWS="
        f"{manifest['aggregate']['composite_v1_per_1000_windows']}"
    )
    print(f"MANIFEST={output}")
    print(f"MANIFEST_SHA256={digest}")
    print("HOLDOUT_DOES_NOT_OVERLAP_PHASE8_REVIEW_PERIOD=TRUE")
    print("OUTCOME_OR_PNL_COMPUTED=NO")
    print("COMPOSITE_V1_IS_NOT_A_BROOKS_RULE=TRUE")
    print("COMPOSITE_V1_PRODUCTION_APPROVED=NO")
    print("CURRENT_PRODUCTION_CONTEXT_GATE_MODIFIED=NO")
    print("CURRENT_PRODUCTION_EH006_GUARD_MODIFIED=NO")
    print("AUTONOMOUS_TRADE_DECISIONS=FALSE")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_HOLDOUT_COMPOSITE_VALIDATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
