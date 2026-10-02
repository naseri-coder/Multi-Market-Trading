"""Phase 8.5 diagnostic-only A/B test for EH-006 guard scope.

This script DOES NOT modify the production engine, database, Telegram, PAPER runtime,
or signal persistence. It replays the same historical candles and compares:
- CURRENT: guard scans the entire pullback window (production behavior)
- LAST_2 / LAST_3 / LAST_5: guard scans only the final N bars, while the existing
  causal second-entry state machine is replayed unchanged across the same pullback.

The localized variants are engineering diagnostics only. They are NOT Brooks rules
and are NOT production recommendations.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

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


END_AT = datetime.fromisoformat("2026-09-02T10:45:00+00:00")
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
SOURCE_CANDLES = 500
SNAPSHOT_WINDOW = 100


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    classification: str
    legs: int
    blocked_indices: tuple[int, ...]


def detect_with_guard_scope(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
    guard_scope_bars: int | None,
) -> DiagnosticResult:
    """Replay current state machine while changing only guard scan scope."""
    if trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        return DiagnosticResult("UNRESOLVED", 0, ())
    if start_index < 0 or start_index >= len(candles) - 1:
        return DiagnosticResult("INVALID_START", 0, ())

    full_window = candles[start_index:]

    if guard_scope_bars is None:
        guard_window = full_window
        guard_offset = start_index
    else:
        if guard_scope_bars < 2:
            raise ValueError("guard_scope_bars must be >= 2")
        relative_start = max(0, len(full_window) - guard_scope_bars)
        guard_window = full_window[relative_start:]
        guard_offset = start_index + relative_start

    guard = assess_h1_h2_l1_l2_counting_window(guard_window)
    if not guard.allowed:
        return DiagnosticResult(
            "BLOCKED",
            0,
            tuple(guard_offset + i for i in guard.blocked_indices),
        )

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
                return DiagnosticResult(
                    "H2" if trend_direction == "BULL_TREND" else "L2",
                    countertrend_legs,
                    (),
                )
            in_countertrend_leg = False

    return DiagnosticResult("NO_SETUP", countertrend_legs, ())


async def main() -> None:
    source = BinanceHistoricalCandleSource()
    try:
        candles = await source.get_closed_candles(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            limit=SOURCE_CANDLES,
            market_type="spot",
            end_at=END_AT,
        )
    finally:
        await source.aclose()

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Diagnostic refuses enabled autonomous trade decisions")

    variants: dict[str, int | None] = {
        "CURRENT_FULL_WINDOW": None,
        "LAST_2_BARS": 2,
        "LAST_3_BARS": 3,
        "LAST_5_BARS": 5,
    }

    counts = {name: Counter() for name in variants}
    leg_counts = {name: Counter() for name in variants}
    structure_counts = Counter()
    current_nearest_edge_distance = Counter()

    evaluated = 0

    for end_index in range(SNAPSHOT_WINDOW - 1, len(candles)):
        window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="spot",
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            candles=window,
            captured_at=window[-1].close_time,
            source="PHASE8_AB_DIAGNOSTIC",
        )

        evaluated += 1

        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        structure = evaluate_br031_structure(scan)
        structure_counts[structure.direction] += 1

        if structure.direction == "AMBIGUOUS":
            for name in variants:
                counts[name]["AMBIGUOUS"] += 1
            continue

        wanted_kind = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        candidate_swings = [s for s in scan.swings if s.kind == wanted_kind]

        if not candidate_swings:
            for name in variants:
                counts[name]["NO_ANCHOR"] += 1
            continue

        start_index = candidate_swings[-1].candle_index
        if len(snapshot.candles) - start_index > policy.pullback_window_bars:
            start_index = len(snapshot.candles) - policy.pullback_window_bars

        for name, scope in variants.items():
            result = detect_with_guard_scope(
                snapshot.candles,
                trend_direction=structure.direction,
                start_index=start_index,
                guard_scope_bars=scope,
            )
            counts[name][result.classification] += 1
            leg_counts[name][result.legs] += 1

            if name == "CURRENT_FULL_WINDOW" and result.classification == "BLOCKED":
                distances = [
                    len(snapshot.candles) - 1 - index
                    for index in result.blocked_indices
                ]
                if distances:
                    current_nearest_edge_distance[min(distances)] += 1

    print("===== PHASE8.5 EH-006 A/B DIAGNOSTIC =====")
    print(f"EVALUATED={evaluated}")
    print(f"STRUCTURE_COUNTS={dict(structure_counts)}")
    print(
        "POLICY="
        f"swingL{policy.swing_left_bars}/"
        f"swingR{policy.swing_right_bars}/"
        f"pullback{policy.pullback_window_bars}/"
        f"exec={int(policy.enable_trade_decisions)}"
    )
    print()

    for name in variants:
        c = counts[name]
        resolved_reached = (
            c["BLOCKED"] + c["H2"] + c["L2"] + c["NO_SETUP"]
        )
        state_machine_reached = c["H2"] + c["L2"] + c["NO_SETUP"]
        detections = c["H2"] + c["L2"]

        print(f"--- {name} ---")
        print(f"AMBIGUOUS={c['AMBIGUOUS']}")
        print(f"NO_ANCHOR={c['NO_ANCHOR']}")
        print(f"RESOLVED_REACHED={resolved_reached}")
        print(f"BLOCKED={c['BLOCKED']}")
        print(f"STATE_MACHINE_REACHED={state_machine_reached}")
        print(f"H2={c['H2']}")
        print(f"L2={c['L2']}")
        print(f"NO_SETUP={c['NO_SETUP']}")
        print(f"DETECTIONS={detections}")
        print(
            "DETECTIONS_PER_1000_EVALUATED="
            f"{(detections * 1000.0 / evaluated):.6f}"
        )
        print(f"LEG_COUNTS_WHEN_UNBLOCKED={dict(sorted(leg_counts[name].items()))}")
        print()

    current = counts["CURRENT_FULL_WINDOW"]
    for name in ("LAST_2_BARS", "LAST_3_BARS", "LAST_5_BARS"):
        c = counts[name]
        print(
            f"DELTA_{name}: "
            f"BLOCKED={c['BLOCKED'] - current['BLOCKED']:+d} "
            f"H2={c['H2'] - current['H2']:+d} "
            f"L2={c['L2'] - current['L2']:+d} "
            f"NO_SETUP={c['NO_SETUP'] - current['NO_SETUP']:+d}"
        )

    print()
    print(
        "CURRENT_NEAREST_BLOCKING_EDGE_DISTANCE_FROM_FINAL_BAR="
        f"{dict(sorted(current_nearest_edge_distance.items()))}"
    )

    baseline_match = (
        evaluated == 401
        and current["AMBIGUOUS"] == 156
        and current["BLOCKED"] == 221
        and current["H2"] == 0
        and current["L2"] == 0
        and current["NO_SETUP"] == 24
    )
    print(f"CURRENT_BASELINE_MATCH={'PASS' if baseline_match else 'DRIFT'}")

    # Safety/causality invariants.
    assert evaluated == SOURCE_CANDLES - SNAPSHOT_WINDOW + 1
    assert sum(structure_counts.values()) == evaluated
    for name in variants:
        assert sum(counts[name].values()) == evaluated

    print("AUTONOMOUS_TRADE_DECISIONS=FALSE")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("PHASE8_AB_DIAGNOSTIC=PASS")


if __name__ == "__main__":
    asyncio.run(main())
