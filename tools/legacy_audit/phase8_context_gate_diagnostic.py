"""Phase 8.8 — Context Gate & Explainability Diagnostic.

DIAGNOSTIC ONLY. This script does not modify the production Brooks engine or any
database/Telegram/PAPER/order path.

Source-grounded concepts used:
- market can be trend or trading range (reviewed PDF p5)
- context / bars to the left matter (p27, pp116-123)
- HH/HL vs LH/LL structure (p127)
- context and momentum matter (pp128-130)
- EMA(20) is secondary context, not a primary decision rule (p20, pp133-135)

Engineering-only measurements (NOT Brooks-authored thresholds):
- 20-bar close-path efficiency ratio
- direction-adjusted displacement within the 20-bar high/low range
- fraction of close-to-close steps aligned with resolved structure
- adjacent-bar overlap frequency (reported for explainability, not used as a hard gate)
- normalized EMA20 slope
- three deliberately labeled diagnostic profiles: LOOSE / MEDIUM / STRICT

The profiles are hypotheses for A/B analysis only. They are not production rules and
must not be presented as Brooks thresholds.
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
from typing import Literal

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

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
CONTEXT_BARS = 20

GuardClassification = Literal["H2", "L2", "BLOCKED", "NO_SETUP"]


# Phase 8.7 visual audit labels. These are review labels, not ground truth.
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
class ContextProfile:
    name: str
    min_efficiency: Decimal
    min_directional_displacement: Decimal
    min_aligned_step_fraction: Decimal


# Explicit engineering hypotheses. No claim is made that these values come from Brooks.
CONTEXT_PROFILES = (
    ContextProfile(
        name="ENG_LOOSE",
        min_efficiency=Decimal("0.20"),
        min_directional_displacement=Decimal("0.20"),
        min_aligned_step_fraction=Decimal("0.50"),
    ),
    ContextProfile(
        name="ENG_MEDIUM",
        min_efficiency=Decimal("0.30"),
        min_directional_displacement=Decimal("0.30"),
        min_aligned_step_fraction=Decimal("0.55"),
    ),
    ContextProfile(
        name="ENG_STRICT",
        min_efficiency=Decimal("0.40"),
        min_directional_displacement=Decimal("0.40"),
        min_aligned_step_fraction=Decimal("0.60"),
    ),
)


@dataclass(frozen=True, slots=True)
class ContextMetrics:
    efficiency_ratio: Decimal
    signed_displacement_ratio: Decimal
    direction_adjusted_displacement: Decimal
    aligned_step_fraction: Decimal
    overlap_frequency: Decimal
    ema20_normalized_slope_5: Decimal
    range_position: Decimal


@dataclass(frozen=True, slots=True)
class GateAssessment:
    profile: str
    classification: str
    aligned_with_structure: bool
    passed_efficiency: bool
    passed_displacement: bool
    passed_aligned_steps: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticDetection:
    classification: GuardClassification
    direction: str | None
    setup_type: str | None
    countertrend_legs: int
    start_index: int
    signal_index: int | None
    blocked_indices: tuple[int, ...]
    leg_start_indices: tuple[int, ...]
    resume_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CandidateRow:
    candidate_id: str
    captured_at: str
    structure: str
    direction: str
    setup_type: str
    visual_review: str
    variants: tuple[str, ...]
    countertrend_legs: int
    pullback_start_index: int
    signal_index: int
    current_full_guard_blocked_indices: tuple[int, ...]
    current_full_guard_nearest_distance: int | None
    context_metrics: ContextMetrics
    gate_assessments: tuple[GateAssessment, ...]
    explainability_chart: str


def d(value: float | int | Decimal) -> Decimal:
    return Decimal(str(value))


def q(value: Decimal, places: str = "0.000001") -> Decimal:
    return value.quantize(Decimal(places))


def ema(values: tuple[Decimal, ...], length: int) -> tuple[Decimal, ...]:
    if length < 1:
        raise ValueError("EMA length must be positive")
    if not values:
        return ()
    alpha = Decimal("2") / Decimal(length + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (Decimal("1") - alpha) * out[-1])
    return tuple(out)


def context_metrics(
    candles: tuple[Candle, ...],
    *,
    structure_direction: str,
) -> ContextMetrics:
    if len(candles) < CONTEXT_BARS:
        raise ValueError("context requires at least 20 bars")

    ctx = candles[-CONTEXT_BARS:]
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
    signed_displacement = (
        Decimal("0") if total_range == 0 else net / total_range
    )

    if structure_direction == "BULL_TREND":
        adjusted = signed_displacement
    elif structure_direction == "BEAR_TREND":
        adjusted = -signed_displacement
    else:
        adjusted = Decimal("0")

    aligned_steps = 0
    overlap_count = 0
    for i in range(1, len(ctx)):
        previous_close = ctx[i - 1].close
        current_close = ctx[i].close

        if structure_direction == "BULL_TREND" and current_close > previous_close:
            aligned_steps += 1
        elif structure_direction == "BEAR_TREND" and current_close < previous_close:
            aligned_steps += 1

        a = ctx[i - 1]
        b = ctx[i]
        if min(a.high, b.high) >= max(a.low, b.low):
            overlap_count += 1

    aligned_step_fraction = Decimal(aligned_steps) / Decimal(len(ctx) - 1)
    overlap_frequency = Decimal(overlap_count) / Decimal(len(ctx) - 1)

    ema20 = ema(closes, 20)
    slope_5 = ema20[-1] - ema20[-6]
    ema_slope_normalized = (
        Decimal("0") if total_range == 0 else slope_5 / total_range
    )

    range_position = (
        Decimal("0.5")
        if total_range == 0
        else (closes[-1] - lowest) / total_range
    )

    return ContextMetrics(
        efficiency_ratio=q(efficiency),
        signed_displacement_ratio=q(signed_displacement),
        direction_adjusted_displacement=q(adjusted),
        aligned_step_fraction=q(aligned_step_fraction),
        overlap_frequency=q(overlap_frequency),
        ema20_normalized_slope_5=q(ema_slope_normalized),
        range_position=q(range_position),
    )


def assess_context_gate(
    *,
    metrics: ContextMetrics,
    structure_direction: str,
    profile: ContextProfile,
) -> GateAssessment:
    aligned = metrics.direction_adjusted_displacement > 0
    pass_efficiency = metrics.efficiency_ratio >= profile.min_efficiency
    pass_displacement = (
        metrics.direction_adjusted_displacement
        >= profile.min_directional_displacement
    )
    pass_aligned_steps = (
        metrics.aligned_step_fraction >= profile.min_aligned_step_fraction
    )

    reasons = []
    if not aligned:
        reasons.append("20-bar net displacement opposes resolved HH/HL or LH/LL structure")
    if not pass_efficiency:
        reasons.append(
            f"close-path efficiency<{profile.min_efficiency} engineering threshold"
        )
    if not pass_displacement:
        reasons.append(
            "direction-adjusted displacement below engineering threshold "
            f"{profile.min_directional_displacement}"
        )
    if not pass_aligned_steps:
        reasons.append(
            "aligned close-step fraction below engineering threshold "
            f"{profile.min_aligned_step_fraction}"
        )

    if aligned and pass_efficiency and pass_displacement and pass_aligned_steps:
        classification = "ENGINEERING_TREND_LIKE"
    elif (not aligned) or (
        not pass_efficiency and not pass_displacement
    ):
        classification = "ENGINEERING_RANGE_OR_REVERSAL_LIKE"
    else:
        classification = "ENGINEERING_AMBIGUOUS"

    return GateAssessment(
        profile=profile.name,
        classification=classification,
        aligned_with_structure=aligned,
        passed_efficiency=pass_efficiency,
        passed_displacement=pass_displacement,
        passed_aligned_steps=pass_aligned_steps,
        reasons=tuple(reasons),
    )


def detect_with_scope(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
    guard_scope_bars: int | None,
) -> DiagnosticDetection:
    if trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        raise ValueError("resolved trend required")

    full_window = candles[start_index:]
    if guard_scope_bars is None:
        guard_window = full_window
        guard_offset = start_index
    else:
        relative = max(0, len(full_window) - guard_scope_bars)
        guard_window = full_window[relative:]
        guard_offset = start_index + relative

    guard = assess_h1_h2_l1_l2_counting_window(guard_window)
    blocked = tuple(guard_offset + i for i in guard.blocked_indices)
    if not guard.allowed:
        return DiagnosticDetection(
            classification="BLOCKED",
            direction=None,
            setup_type=None,
            countertrend_legs=0,
            start_index=start_index,
            signal_index=None,
            blocked_indices=blocked,
            leg_start_indices=(),
            resume_indices=(),
        )

    legs = 0
    in_leg = False
    leg_starts = []
    resumes = []
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
            leg_starts.append(i)

        if resume and in_leg:
            resumes.append(i)
            if i == last_index and legs >= 2:
                direction = "LONG" if trend_direction == "BULL_TREND" else "SHORT"
                return DiagnosticDetection(
                    classification="H2" if direction == "LONG" else "L2",
                    direction=direction,
                    setup_type="H2_CONFIRMED" if direction == "LONG" else "L2_CONFIRMED",
                    countertrend_legs=legs,
                    start_index=start_index,
                    signal_index=i,
                    blocked_indices=(),
                    leg_start_indices=tuple(leg_starts),
                    resume_indices=tuple(resumes),
                )
            in_leg = False

    return DiagnosticDetection(
        classification="NO_SETUP",
        direction=None,
        setup_type=None,
        countertrend_legs=legs,
        start_index=start_index,
        signal_index=None,
        blocked_indices=(),
        leg_start_indices=tuple(leg_starts),
        resume_indices=tuple(resumes),
    )


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


def render_explainability_chart(
    *,
    snapshot: MarketSnapshot,
    scan,
    structure,
    detection: DiagnosticDetection,
    current_blocked_indices: tuple[int, ...],
    gates: tuple[GateAssessment, ...],
    visual_review: str,
    output_path: Path,
) -> None:
    candles = snapshot.candles
    xs = [mdates.date2num(c.open_time) for c in candles]
    width = ((xs[1] - xs[0]) * 0.65) if len(xs) > 1 else 0.004

    fig, ax = plt.subplots(figsize=(13, 7), dpi=140)

    for x, candle in zip(xs, candles):
        bullish = candle.close >= candle.open
        ax.vlines(x, float(candle.low), float(candle.high), linewidth=0.8)
        lower = min(float(candle.open), float(candle.close))
        height = abs(float(candle.close) - float(candle.open))
        if height == 0:
            height = max(float(candle.high - candle.low) * 0.02, 1e-12)
        ax.add_patch(
            Rectangle(
                (x - width / 2, lower),
                width,
                height,
                facecolor="white" if bullish else "black",
                edgecolor="black",
                linewidth=0.7,
            )
        )

    highs = [s for s in scan.swings if s.kind == "HIGH"]
    lows = [s for s in scan.swings if s.kind == "LOW"]

    if highs:
        ax.scatter(
            [xs[s.candle_index] for s in highs],
            [float(s.price) for s in highs],
            marker="v",
            s=28,
            label="confirmed swing high",
        )
    if lows:
        ax.scatter(
            [xs[s.candle_index] for s in lows],
            [float(s.price) for s in lows],
            marker="^",
            s=28,
            label="confirmed swing low",
        )

    ax.axvline(
        xs[detection.start_index],
        linestyle="--",
        linewidth=1.0,
        label="pullback anchor/start",
    )

    for i, index in enumerate(detection.leg_start_indices):
        ax.scatter(
            [xs[index]],
            [float(candles[index].low if detection.direction == "LONG" else candles[index].high)],
            marker="o",
            s=45,
            label="countertrend leg start" if i == 0 else None,
        )

    for i, index in enumerate(current_blocked_indices):
        ax.scatter(
            [xs[index]],
            [float(candles[index].high)],
            marker="x",
            s=40,
            label="CURRENT EH-006 blocked relation" if i == 0 else None,
        )

    if detection.signal_index is not None:
        ax.axvline(
            xs[detection.signal_index],
            linestyle="-.",
            linewidth=1.2,
            label="candidate signal bar",
        )

    gate_text = " | ".join(
        f"{g.profile}:{g.classification.replace('ENGINEERING_', '')}"
        for g in gates
    )
    title = (
        f"{SYMBOL} {TIMEFRAME} {detection.setup_type} | "
        f"structure={structure.direction} | visual={visual_review}\n"
        f"{gate_text}"
    )
    ax.set_title(title)
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax.grid(True, alpha=0.2)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


async def main() -> None:
    output_dir = Path("/out")
    charts_dir = output_dir / "context_explainability_charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.8 refuses enabled autonomous trade decisions")

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

    profile_window_counts = {
        profile.name: Counter() for profile in CONTEXT_PROFILES
    }

    # Union of LAST_2 diagnostic candidates, which was exactly the 7 reviewed candidates.
    candidates: dict[str, CandidateRow] = {}
    candidate_internal: dict[str, tuple] = {}

    for end_index in range(SNAPSHOT_WINDOW - 1, len(candles)):
        window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]
        snapshot = MarketSnapshot(
            exchange=EXCHANGE,
            market_type=MARKET_TYPE,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            candles=window,
            captured_at=window[-1].close_time,
            source="PHASE8_CONTEXT_GATE_DIAGNOSTIC",
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
            for profile in CONTEXT_PROFILES:
                profile_window_counts[profile.name]["SOURCE_STRUCTURE_AMBIGUOUS"] += 1
            continue

        metrics = context_metrics(
            snapshot.candles,
            structure_direction=structure.direction,
        )
        gates = tuple(
            assess_context_gate(
                metrics=metrics,
                structure_direction=structure.direction,
                profile=profile,
            )
            for profile in CONTEXT_PROFILES
        )
        for gate in gates:
            profile_window_counts[gate.profile][gate.classification] += 1

        wanted_kind = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        anchors = [s for s in scan.swings if s.kind == wanted_kind]
        if not anchors:
            continue

        start_index = anchors[-1].candle_index
        if len(snapshot.candles) - start_index > policy.pullback_window_bars:
            start_index = len(snapshot.candles) - policy.pullback_window_bars

        current = detect_with_scope(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=None,
        )
        last2 = detect_with_scope(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=2,
        )
        last3 = detect_with_scope(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=3,
        )
        last5 = detect_with_scope(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=5,
        )

        if last2.classification not in {"H2", "L2"}:
            continue

        assert last2.signal_index == SNAPSHOT_WINDOW - 1
        cid = make_candidate_id(
            captured_at=snapshot.captured_at.isoformat(),
            direction=last2.direction or "",
            setup_type=last2.setup_type or "",
            snapshot_hash=snapshot.snapshot_hash,
        )

        variants = ["LAST_2_BARS"]
        if last3.classification in {"H2", "L2"}:
            variants.append("LAST_3_BARS")
        if last5.classification in {"H2", "L2"}:
            variants.append("LAST_5_BARS")

        nearest = None
        if current.blocked_indices:
            nearest = min(
                len(snapshot.candles) - 1 - idx
                for idx in current.blocked_indices
            )

        chart_name = (
            f"{snapshot.captured_at.strftime('%Y%m%dT%H%M%S')}_"
            f"{last2.setup_type}_{cid}_context.png"
        )

        review = VISUAL_REVIEW_LABELS.get(cid, "UNREVIEWED")

        row = CandidateRow(
            candidate_id=cid,
            captured_at=snapshot.captured_at.isoformat(),
            structure=structure.direction,
            direction=last2.direction or "",
            setup_type=last2.setup_type or "",
            visual_review=review,
            variants=tuple(variants),
            countertrend_legs=last2.countertrend_legs,
            pullback_start_index=start_index,
            signal_index=last2.signal_index or 0,
            current_full_guard_blocked_indices=current.blocked_indices,
            current_full_guard_nearest_distance=nearest,
            context_metrics=metrics,
            gate_assessments=gates,
            explainability_chart=f"context_explainability_charts/{chart_name}",
        )
        candidates[cid] = row
        candidate_internal[cid] = (
            snapshot, scan, structure, last2, current.blocked_indices, gates, review, chart_name
        )

    # Render after deterministic collection/order.
    for cid in sorted(candidates, key=lambda x: candidates[x].captured_at):
        (
            snapshot,
            scan,
            structure,
            detection,
            blocked,
            gates,
            review,
            chart_name,
        ) = candidate_internal[cid]
        render_explainability_chart(
            snapshot=snapshot,
            scan=scan,
            structure=structure,
            detection=detection,
            current_blocked_indices=blocked,
            gates=gates,
            visual_review=review,
            output_path=charts_dir / chart_name,
        )

    rows = tuple(
        candidates[cid]
        for cid in sorted(candidates, key=lambda x: candidates[x].captured_at)
    )

    if set(candidates) != set(VISUAL_REVIEW_LABELS):
        missing = sorted(set(VISUAL_REVIEW_LABELS) - set(candidates))
        extra = sorted(set(candidates) - set(VISUAL_REVIEW_LABELS))
        raise RuntimeError(
            f"candidate drift against Phase 8.7 review: missing={missing} extra={extra}"
        )

    candidate_gate_summary = {}
    for profile in CONTEXT_PROFILES:
        key = profile.name
        summary = Counter()
        for row in rows:
            gate = next(g for g in row.gate_assessments if g.profile == key)
            summary[f"{row.visual_review}|{gate.classification}"] += 1
        candidate_gate_summary[key] = dict(sorted(summary.items()))

    manifest = {
        "phase": "8.8",
        "mode": "CONTEXT_GATE_DIAGNOSTIC_ONLY",
        "source_grounded_concepts": {
            "p5": "market can be trend or trading range",
            "p20": "default EMA 20",
            "p27": "context / bars to the left",
            "p116_123": "pattern alone is insufficient; context matters",
            "p127": "HH/HL bull structure and LH/LL bear structure",
            "p128_130": "context and momentum are controlling considerations",
            "p133_135": "indicators are secondary to price bars",
        },
        "engineering_metrics_not_brooks_rules": {
            "context_bars": CONTEXT_BARS,
            "efficiency_ratio": "abs(net close displacement) / total close path",
            "direction_adjusted_displacement": (
                "20-bar net close displacement divided by high-low range, "
                "signed to agree/disagree with resolved structure"
            ),
            "aligned_step_fraction": (
                "fraction of the 19 close-to-close steps that move in the same "
                "direction as resolved HH/HL or LH/LL structure"
            ),
            "overlap_frequency": (
                "fraction of adjacent 20-bar ranges that overlap; explainability "
                "metric only, not a hard diagnostic gate"
            ),
            "ema20_normalized_slope_5": "5-bar EMA20 change / 20-bar high-low range",
        },
        "engineering_profiles_not_brooks_thresholds": [
            {
                "name": p.name,
                "min_efficiency": str(p.min_efficiency),
                "min_directional_displacement": str(p.min_directional_displacement),
                "min_aligned_step_fraction": str(p.min_aligned_step_fraction),
            }
            for p in CONTEXT_PROFILES
        ],
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "end_at": END_AT.isoformat(),
        "source_candles": SOURCE_CANDLES,
        "snapshot_window": SNAPSHOT_WINDOW,
        "policy_configuration_version": policy.configuration_version,
        "autonomous_trade_decisions": False,
        "window_regime_counts": {
            name: dict(sorted(counter.items()))
            for name, counter in profile_window_counts.items()
        },
        "candidate_gate_summary": candidate_gate_summary,
        "candidate_count": len(rows),
        "candidates": [asdict(row) for row in rows],
    }

    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=str,
    ) + "\n"
    manifest_path = output_dir / "phase8_context_gate_diagnostic.json"
    manifest_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    print("===== PHASE8.8 CONTEXT GATE DIAGNOSTIC =====")
    print(f"EVALUATED_WINDOWS={SOURCE_CANDLES - SNAPSHOT_WINDOW + 1}")
    print(f"CANDIDATES={len(rows)}")
    print()

    print("WINDOW_REGIME_COUNTS")
    for profile in CONTEXT_PROFILES:
        print(profile.name, dict(sorted(profile_window_counts[profile.name].items())))

    print()
    print("CANDIDATE_MATRIX")
    for row in rows:
        gate_text = " ".join(
            f"{gate.profile}={gate.classification}"
            for gate in row.gate_assessments
        )
        m = row.context_metrics
        print(
            f"{row.candidate_id} "
            f"{row.setup_type} "
            f"visual={row.visual_review} "
            f"ER={m.efficiency_ratio} "
            f"ADJ_DISP={m.direction_adjusted_displacement} "
            f"ALIGNED_STEPS={m.aligned_step_fraction} "
            f"OVERLAP={m.overlap_frequency} "
            f"EMA20SLOPE5={m.ema20_normalized_slope_5} "
            f"EH006_NEAREST={row.current_full_guard_nearest_distance} "
            f"{gate_text}"
        )

    print()
    print("CANDIDATE_GATE_SUMMARY")
    for profile in CONTEXT_PROFILES:
        print(profile.name, candidate_gate_summary[profile.name])

    print()
    print(f"MANIFEST={manifest_path}")
    print(f"MANIFEST_SHA256={digest}")
    print(f"CHARTS_DIR={charts_dir}")
    print(f"CHART_COUNT={len(rows)}")
    print("CURRENT_PRODUCTION_CONTEXT_GATE_MODIFIED=NO")
    print("CURRENT_PRODUCTION_EH006_GUARD_MODIFIED=NO")
    print("AUTONOMOUS_TRADE_DECISIONS=FALSE")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("ENGINEERING_THRESHOLDS_ARE_NOT_BROOKS_RULES=TRUE")
    print("PHASE8_CONTEXT_GATE_DIAGNOSTIC=PASS")


if __name__ == "__main__":
    asyncio.run(main())
