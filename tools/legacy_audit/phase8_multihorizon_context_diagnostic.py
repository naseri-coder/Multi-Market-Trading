"""Phase 8.9 — Multi-horizon pre-pullback vs signal-context diagnostic.

DIAGNOSTIC ONLY.

Goal:
Determine whether visually rejected/uncertain H2/L2 candidates are local reversals or
range events rather than continuation setups by comparing context:
1) immediately BEFORE the pullback anchor, and
2) at the candidate signal bar,
across 20/40/80-bar horizons.

No production rule is modified. No DB/Telegram/PAPER/order path is used.

Source-grounded concepts:
- market can be trend or trading range (reviewed PDF p5)
- context / bars to the left matter (p27, pp116-123)
- HH/HL vs LH/LL structure (p127)
- context and momentum matter (pp128-130)
- EMA(20) is secondary context (p20, pp133-135)

Engineering-only diagnostics:
- 20/40/80-bar horizons
- close-path efficiency
- direction-adjusted net displacement
- aligned close-step fraction
- EMA20 slope sign/size
- local structure evaluated independently on each horizon

These horizons/metrics are NOT Brooks-authored thresholds.
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


END_AT = datetime.fromisoformat("2026-09-02T10:45:00+00:00")
EXCHANGE = "binance"
MARKET_TYPE = "spot"
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
SOURCE_CANDLES = 500
SNAPSHOT_WINDOW = 100
HORIZONS = (20, 40, 80)

VISUAL_REVIEW_LABELS = {
    "9844c2b4ff08035a": "REJECT",
    "38fa7ee9b56f6798": "UNCERTAIN",
    "2de58c1e5010cacf": "KEEP",
    "7fc0d43185d5e326": "UNCERTAIN",
    "516a9413fc2a97cb": "REJECT",
    "4f9a871160bde399": "KEEP",
    "b03f0f0e75fd6ac1": "UNCERTAIN",
}


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    horizon: int
    evaluated_bars: int
    structure: str
    efficiency_ratio: Decimal
    signed_displacement_ratio: Decimal
    direction_adjusted_displacement: Decimal
    aligned_step_fraction: Decimal
    ema20_normalized_slope_5: Decimal
    structure_aligned_with_candidate: bool
    displacement_aligned_with_candidate: bool
    ema_slope_aligned_with_candidate: bool


@dataclass(frozen=True, slots=True)
class CandidateRow:
    candidate_id: str
    captured_at: str
    setup_type: str
    direction: str
    candidate_structure: str
    visual_review: str
    pullback_start_index: int
    signal_index: int
    pre_pullback: tuple[HorizonMetrics, ...]
    at_signal: tuple[HorizonMetrics, ...]
    pre_pullback_positive_displacement_horizons: int
    at_signal_positive_displacement_horizons: int
    pre_pullback_structure_alignment_horizons: int
    at_signal_structure_alignment_horizons: int
    context_transition: str


def q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def ema(values: tuple[Decimal, ...], length: int) -> tuple[Decimal, ...]:
    alpha = Decimal("2") / Decimal(length + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (Decimal("1") - alpha) * result[-1])
    return tuple(result)


def evaluate_horizon(
    candles: tuple[Candle, ...],
    *,
    horizon: int,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> HorizonMetrics:
    if len(candles) < horizon:
        raise ValueError(f"insufficient candles for horizon {horizon}")

    ctx = candles[-horizon:]
    closes = tuple(c.close for c in ctx)

    path = sum(
        (abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))),
        Decimal("0"),
    )
    net = closes[-1] - closes[0]
    efficiency = Decimal("0") if path == 0 else abs(net) / path

    highest = max(c.high for c in ctx)
    lowest = min(c.low for c in ctx)
    total_range = highest - lowest

    signed_disp = Decimal("0") if total_range == 0 else net / total_range
    adjusted_disp = (
        signed_disp if candidate_structure == "BULL_TREND" else -signed_disp
    )

    aligned_steps = 0
    for i in range(1, len(ctx)):
        if candidate_structure == "BULL_TREND" and closes[i] > closes[i - 1]:
            aligned_steps += 1
        elif candidate_structure == "BEAR_TREND" and closes[i] < closes[i - 1]:
            aligned_steps += 1
    aligned_fraction = Decimal(aligned_steps) / Decimal(len(ctx) - 1)

    ema20 = ema(closes, 20)
    ema_slope_5 = ema20[-1] - ema20[-6]
    ema_slope_norm = (
        Decimal("0") if total_range == 0 else ema_slope_5 / total_range
    )

    scan = confirm_swings_causally(
        ctx,
        left_bars=policy.swing_left_bars,
        right_bars=policy.swing_right_bars,
    )
    structure = evaluate_br031_structure(scan).direction

    structure_aligned = structure == candidate_structure
    displacement_aligned = adjusted_disp > 0
    ema_aligned = (
        ema_slope_norm > 0
        if candidate_structure == "BULL_TREND"
        else ema_slope_norm < 0
    )

    return HorizonMetrics(
        horizon=horizon,
        evaluated_bars=len(ctx),
        structure=structure,
        efficiency_ratio=q(efficiency),
        signed_displacement_ratio=q(signed_disp),
        direction_adjusted_displacement=q(adjusted_disp),
        aligned_step_fraction=q(aligned_fraction),
        ema20_normalized_slope_5=q(ema_slope_norm),
        structure_aligned_with_candidate=structure_aligned,
        displacement_aligned_with_candidate=displacement_aligned,
        ema_slope_aligned_with_candidate=ema_aligned,
    )


def detect_last2_candidate(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
):
    full_window = candles[start_index:]
    relative = max(0, len(full_window) - 2)
    guard_window = full_window[relative:]
    guard = assess_h1_h2_l1_l2_counting_window(guard_window)
    if not guard.allowed:
        return None

    legs = 0
    in_leg = False
    last_index = len(candles) - 1

    for i in range(start_index + 1, len(candles)):
        previous = candles[i - 1]
        current = candles[i]

        if trend_direction == "BULL_TREND":
            moved_against = current.low < previous.low
            resume = current.high > previous.high
        else:
            moved_against = current.high > previous.high
            resume = current.low < previous.low

        if moved_against and not in_leg:
            legs += 1
            in_leg = True

        if resume and in_leg:
            if i == last_index and legs >= 2:
                direction = "LONG" if trend_direction == "BULL_TREND" else "SHORT"
                setup_type = "H2_CONFIRMED" if direction == "LONG" else "L2_CONFIRMED"
                return direction, setup_type, legs, i
            in_leg = False

    return None


def make_candidate_id(
    *,
    captured_at: str,
    direction: str,
    setup_type: str,
    snapshot_hash: str,
) -> str:
    raw = "|".join(
        ("PHASE8_CANDIDATE_AUDIT_V1", captured_at, direction, setup_type, snapshot_hash)
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def transition_label(
    pre: tuple[HorizonMetrics, ...],
    signal: tuple[HorizonMetrics, ...],
) -> str:
    pre_pos = sum(m.displacement_aligned_with_candidate for m in pre)
    sig_pos = sum(m.displacement_aligned_with_candidate for m in signal)
    pre_struct = sum(m.structure_aligned_with_candidate for m in pre)
    sig_struct = sum(m.structure_aligned_with_candidate for m in signal)

    if pre_pos == len(HORIZONS) and sig_pos == len(HORIZONS):
        return "MULTIHORIZON_CONTINUATION_LIKE"
    if pre_pos <= 1 and sig_pos >= 2:
        return "LOCAL_REVERSAL_OR_LATE_FLIP_LIKE"
    if pre_struct <= 1 and sig_struct >= 2:
        return "STRUCTURE_FLIP_LIKE"
    if pre_pos >= 2 and sig_pos <= 1:
        return "CONTINUATION_FAILURE_OR_RANGE_LIKE"
    return "MIXED_CONTEXT"


async def main() -> None:
    output_dir = Path("/out")
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.9 refuses enabled autonomous trade decisions")

    source = BinanceHistoricalCandleSource()
    try:
        candles = await source.get_closed_candles(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            limit=SOURCE_CANDLES,
            market_type=MARKET_TYPE,
            end_at=END_AT,
        )
    finally:
        await source.aclose()

    rows: dict[str, CandidateRow] = {}

    for end_index in range(SNAPSHOT_WINDOW - 1, len(candles)):
        window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

        snapshot = MarketSnapshot(
            exchange=EXCHANGE,
            market_type=MARKET_TYPE,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            candles=window,
            captured_at=window[-1].close_time,
            source="PHASE8_MULTIHORIZON_CONTEXT",
        )

        assert snapshot.captured_at == snapshot.candles[-1].close_time
        assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)

        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        structure = evaluate_br031_structure(scan)
        if structure.direction == "AMBIGUOUS":
            continue

        wanted = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        anchors = [s for s in scan.swings if s.kind == wanted]
        if not anchors:
            continue

        start_index = anchors[-1].candle_index
        if len(snapshot.candles) - start_index > policy.pullback_window_bars:
            start_index = len(snapshot.candles) - policy.pullback_window_bars

        detected = detect_last2_candidate(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
        )
        if detected is None:
            continue

        direction, setup_type, legs, signal_index = detected
        cid = make_candidate_id(
            captured_at=snapshot.captured_at.isoformat(),
            direction=direction,
            setup_type=setup_type,
            snapshot_hash=snapshot.snapshot_hash,
        )

        # Because pullback_start_index is clamped to the last 20 bars, there are
        # always at least 80 bars available before/through the anchor in a 100-bar
        # snapshot. Include the anchor in pre-pullback context.
        pre_prefix = snapshot.candles[: start_index + 1]

        pre_metrics = tuple(
            evaluate_horizon(
                pre_prefix,
                horizon=h,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for h in HORIZONS
        )
        signal_metrics = tuple(
            evaluate_horizon(
                snapshot.candles,
                horizon=h,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for h in HORIZONS
        )

        pre_pos = sum(m.displacement_aligned_with_candidate for m in pre_metrics)
        sig_pos = sum(m.displacement_aligned_with_candidate for m in signal_metrics)
        pre_struct = sum(m.structure_aligned_with_candidate for m in pre_metrics)
        sig_struct = sum(m.structure_aligned_with_candidate for m in signal_metrics)

        rows[cid] = CandidateRow(
            candidate_id=cid,
            captured_at=snapshot.captured_at.isoformat(),
            setup_type=setup_type,
            direction=direction,
            candidate_structure=structure.direction,
            visual_review=VISUAL_REVIEW_LABELS.get(cid, "UNREVIEWED"),
            pullback_start_index=start_index,
            signal_index=signal_index,
            pre_pullback=pre_metrics,
            at_signal=signal_metrics,
            pre_pullback_positive_displacement_horizons=pre_pos,
            at_signal_positive_displacement_horizons=sig_pos,
            pre_pullback_structure_alignment_horizons=pre_struct,
            at_signal_structure_alignment_horizons=sig_struct,
            context_transition=transition_label(pre_metrics, signal_metrics),
        )

    if set(rows) != set(VISUAL_REVIEW_LABELS):
        raise RuntimeError(
            "candidate drift: "
            f"missing={sorted(set(VISUAL_REVIEW_LABELS)-set(rows))} "
            f"extra={sorted(set(rows)-set(VISUAL_REVIEW_LABELS))}"
        )

    ordered = tuple(rows[cid] for cid in sorted(rows, key=lambda x: rows[x].captured_at))

    transition_summary = Counter(
        f"{row.visual_review}|{row.context_transition}" for row in ordered
    )

    manifest = {
        "phase": "8.9",
        "mode": "MULTIHORIZON_CONTEXT_DIAGNOSTIC_ONLY",
        "source_grounded_concepts": {
            "p5": "market can be trend or trading range",
            "p27": "context / bars to the left",
            "p116_123": "pattern alone insufficient; context matters",
            "p127": "HH/HL bull structure; LH/LL bear structure",
            "p128_130": "context and momentum matter",
            "p20_p133_135": "EMA20 is secondary context",
        },
        "engineering_horizons_not_brooks_thresholds": list(HORIZONS),
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "end_at": END_AT.isoformat(),
        "source_candles": SOURCE_CANDLES,
        "snapshot_window": SNAPSHOT_WINDOW,
        "candidate_count": len(ordered),
        "transition_summary": dict(sorted(transition_summary.items())),
        "candidates": [asdict(row) for row in ordered],
        "safety": {
            "production_context_gate_modified": False,
            "production_eh006_guard_modified": False,
            "autonomous_trade_decisions": False,
            "database_writes": False,
            "telegram_publish": False,
            "paper_runtime_used": False,
        },
    }

    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=str,
    ) + "\n"
    output = output_dir / "phase8_multihorizon_context_diagnostic.json"
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    print("===== PHASE8.9 MULTIHORIZON CONTEXT DIAGNOSTIC =====")
    print(f"CANDIDATES={len(ordered)}")
    print(f"HORIZONS={HORIZONS}")
    print()

    for row in ordered:
        print(
            f"{row.candidate_id} "
            f"{row.setup_type} "
            f"visual={row.visual_review} "
            f"transition={row.context_transition} "
            f"PRE_DISP_ALIGN={row.pre_pullback_positive_displacement_horizons}/3 "
            f"SIG_DISP_ALIGN={row.at_signal_positive_displacement_horizons}/3 "
            f"PRE_STRUCT_ALIGN={row.pre_pullback_structure_alignment_horizons}/3 "
            f"SIG_STRUCT_ALIGN={row.at_signal_structure_alignment_horizons}/3"
        )
        for label, metrics in (
            ("PRE", row.pre_pullback),
            ("SIG", row.at_signal),
        ):
            for m in metrics:
                print(
                    f"  {label}{m.horizon}: "
                    f"STRUCT={m.structure} "
                    f"ER={m.efficiency_ratio} "
                    f"ADJ_DISP={m.direction_adjusted_displacement} "
                    f"ALIGNED_STEPS={m.aligned_step_fraction} "
                    f"EMA20SLOPE5={m.ema20_normalized_slope_5} "
                    f"STRUCT_OK={int(m.structure_aligned_with_candidate)} "
                    f"DISP_OK={int(m.displacement_aligned_with_candidate)} "
                    f"EMA_OK={int(m.ema_slope_aligned_with_candidate)}"
                )
        print()

    print("TRANSITION_SUMMARY=", dict(sorted(transition_summary.items())))
    print(f"MANIFEST={output}")
    print(f"MANIFEST_SHA256={digest}")
    print("CURRENT_PRODUCTION_CONTEXT_GATE_MODIFIED=NO")
    print("CURRENT_PRODUCTION_EH006_GUARD_MODIFIED=NO")
    print("AUTONOMOUS_TRADE_DECISIONS=FALSE")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("ENGINEERING_HORIZONS_ARE_NOT_BROOKS_THRESHOLDS=TRUE")
    print("PHASE8_MULTIHORIZON_CONTEXT_DIAGNOSTIC=PASS")


if __name__ == "__main__":
    asyncio.run(main())
