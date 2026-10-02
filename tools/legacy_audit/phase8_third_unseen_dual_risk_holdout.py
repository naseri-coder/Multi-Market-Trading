"""Phase 8.18 — Third Unseen Dual-Risk Holdout.

DIAGNOSTIC / BLIND-REVIEW PACK GENERATION ONLY.
No production rule changes. No outcomes, P&L, or win rate.

Purpose
-------
Test two failure families suggested by Phase 8.17 on a THIRD, older, non-overlapping
historical holdout:

A) Shock / reversal risk
B) Weak recent continuation

Candidate universe
------------------
LAST_2 H2/L2 diagnostic candidate
AND MULTIHORIZON_CONTINUATION_LIKE

LAST_3 is descriptive only; it is NOT a hard gate.

Third holdout
-------------
Binance Spot:
    BTCUSDT 15m
    ETHUSDT 15m
    BTCUSDT 1h
    ETHUSDT 1h

2500 closed candles per dataset
fixed end_at = 2026-01-15T00:00:00Z

This period is older than the Phase 8.14 holdout. For the slowest dataset (1h),
2500 candles ending Jan 15 are earlier than the Phase 8.14 1h source period ending
May 15, so the two review windows do not overlap.

Engineering-only pre-registered descriptive axes
-------------------------------------------------

SHOCK_RISK_HIGH if:
    shock_range_ratio >= 5.0
    OR (
        post_shock_adjusted_displacement < 0
        AND shock_offset_from_signal_bars <= 12
    )

otherwise SHOCK_RISK_LOWER.

RECENT_CONTINUATION_WEAK if:
    recent20_adjusted_displacement < 0.20
    OR recent20_close_path_efficiency < 0.08

otherwise RECENT_CONTINUATION_STRONGER.

These boundaries are engineering bins chosen BEFORE looking at the third holdout.
They are NOT Brooks rules and are NOT production thresholds.

Four blind-review cells
-----------------------
LOWER_SHOCK__STRONGER_CONT
LOWER_SHOCK__WEAK_CONT
HIGH_SHOCK__STRONGER_CONT
HIGH_SHOCK__WEAK_CONT

Sampling
--------
Up to 6 candidates per cell (max 24 total), with deterministic round-robin dataset
diversification and SHA256 ranking. Selection uses no outcomes.

Blind workflow
--------------
Outputs:
    /out/blind/phase8_18_blind_manifest.json
    /out/blind/charts/*.png
    /out/blind/SHA256SUMS.txt

    /out/mapping/phase8_18_mapping_manifest.json
    /out/mapping/SHA256SUMS.txt

Upload/review ONLY the blind pack first.
Do NOT reveal the mapping pack until blind labels are locked.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median

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


END_AT = datetime.fromisoformat("2026-01-15T00:00:00+00:00")
EXCHANGE = "binance"
MARKET_TYPE = "spot"
SOURCE_CANDLES = 2500
SNAPSHOT_WINDOW = 100
HORIZONS = (20, 40, 80)
MAX_PER_CELL = 6

DATASETS = (
    ("BTCUSDT", "15m"),
    ("ETHUSDT", "15m"),
    ("BTCUSDT", "1h"),
    ("ETHUSDT", "1h"),
)

OUT = Path("/out")
BLIND = OUT / "blind"
BLIND_CHARTS = BLIND / "charts"
MAPPING = OUT / "mapping"


@dataclass(frozen=True, slots=True)
class HorizonEvidence:
    horizon: int
    local_structure: str
    direction_adjusted_displacement: Decimal
    structure_aligned: bool
    displacement_aligned: bool


@dataclass(frozen=True, slots=True)
class SegmentEvidence:
    bars: int
    adjusted_displacement: Decimal
    close_path_efficiency: Decimal


@dataclass(frozen=True, slots=True)
class ShockEvidence:
    largest_range_ratio_vs_median40: Decimal
    shock_offset_from_signal_bars: int
    shock_body_relation: str
    post_shock_adjusted_displacement: Decimal
    post_shock_direction_class: str


@dataclass(frozen=True, slots=True)
class MaturityEvidence:
    r40_alignment_last20: Decimal
    r40_current_run_bars: int
    r40_flip_count_last40: int


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    symbol: str
    timeframe: str
    captured_at: str
    snapshot_id: str
    snapshot_hash: str
    direction: str
    setup_type: str
    countertrend_legs: int
    survives_last3: bool
    candidate_structure: str
    pullback_start_index: int
    signal_index: int
    transition: str
    recent20: SegmentEvidence
    shock: ShockEvidence
    maturity: MaturityEvidence
    shock_risk_axis: str
    continuation_axis: str
    dual_risk_cell: str


@dataclass(frozen=True, slots=True)
class BlindItem:
    blind_id: str
    symbol: str
    timeframe: str
    setup_type: str
    chart_file: str
    reviewer_label: str = "UNREVIEWED"
    reviewer_notes: str = ""


@dataclass(frozen=True, slots=True)
class MappingItem:
    blind_id: str
    deterministic_rank: str
    symbol: str
    timeframe: str
    captured_at: str
    snapshot_hash: str
    direction: str
    setup_type: str
    countertrend_legs: int
    survives_last3: bool
    candidate_structure: str
    pullback_start_index: int
    signal_index: int
    transition: str
    recent20: SegmentEvidence
    shock: ShockEvidence
    maturity: MaturityEvidence
    shock_risk_axis: str
    continuation_axis: str
    dual_risk_cell: str


def q(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def med(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        return Decimal("0")
    return q(median(values))


def detect_candidate(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
    guard_scope_bars: int,
):
    full_window = candles[start_index:]
    relative_start = max(0, len(full_window) - guard_scope_bars)
    guard = assess_h1_h2_l1_l2_counting_window(full_window[relative_start:])
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


def horizon_evidence(
    candles: tuple[Candle, ...],
    *,
    horizon: int,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> HorizonEvidence:
    ctx = candles[-horizon:]
    if len(ctx) != horizon:
        raise ValueError(f"expected {horizon} bars, got {len(ctx)}")

    high = max(c.high for c in ctx)
    low = min(c.low for c in ctx)
    total_range = high - low
    net = ctx[-1].close - ctx[0].close
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


def segment_evidence(
    candles: tuple[Candle, ...],
    *,
    candidate_structure: str,
) -> SegmentEvidence:
    if len(candles) < 2:
        raise ValueError("segment requires >=2 candles")

    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    total_range = high - low
    net = candles[-1].close - candles[0].close

    signed = Decimal("0") if total_range == 0 else net / total_range
    adjusted = signed if candidate_structure == "BULL_TREND" else -signed

    path = sum(
        abs(current.close - previous.close)
        for previous, current in zip(candles, candles[1:])
    )
    efficiency = Decimal("0") if path == 0 else abs(net) / path

    return SegmentEvidence(
        bars=len(candles),
        adjusted_displacement=q(adjusted),
        close_path_efficiency=q(efficiency),
    )


def body_relation(candle: Candle, candidate_structure: str) -> str:
    if candle.close == candle.open:
        return "DOJI"
    bullish = candle.close > candle.open
    aligned = (
        (candidate_structure == "BULL_TREND" and bullish)
        or (candidate_structure == "BEAR_TREND" and not bullish)
    )
    return "ALIGNED" if aligned else "OPPOSITE"


def shock_evidence(
    last40: tuple[Candle, ...],
    *,
    candidate_structure: str,
) -> ShockEvidence:
    ranges = tuple(c.high - c.low for c in last40)
    median40 = med(ranges)
    if median40 <= 0:
        median40 = Decimal("1")

    shock_index = max(range(len(last40)), key=lambda i: ranges[i])
    shock = last40[shock_index]
    ratio = ranges[shock_index] / median40
    offset = len(last40) - 1 - shock_index

    post = last40[shock_index:]
    if len(post) >= 2:
        post_ev = segment_evidence(
            post,
            candidate_structure=candidate_structure,
        )
        post_disp = post_ev.adjusted_displacement
    else:
        post_disp = Decimal("0")

    if post_disp > 0:
        post_class = "ALIGNED"
    elif post_disp < 0:
        post_class = "OPPOSITE"
    else:
        post_class = "NEUTRAL"

    return ShockEvidence(
        largest_range_ratio_vs_median40=q(ratio),
        shock_offset_from_signal_bars=offset,
        shock_body_relation=body_relation(shock, candidate_structure),
        post_shock_adjusted_displacement=q(post_disp),
        post_shock_direction_class=post_class,
    )


def rolling40_states(
    candles: tuple[Candle, ...],
    *,
    policy: FundamentalsExecutionPolicy,
) -> tuple[str, ...]:
    states = []
    for end_index in range(39, len(candles)):
        window = candles[end_index - 39 : end_index + 1]
        scan = confirm_swings_causally(
            window,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        states.append(evaluate_br031_structure(scan).direction)
    return tuple(states)


def maturity_evidence(
    candles: tuple[Candle, ...],
    *,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> MaturityEvidence:
    states = rolling40_states(candles, policy=policy)
    last20 = states[-20:]
    last40 = states[-40:]

    alignment = Decimal(
        sum(state == candidate_structure for state in last20)
    ) / Decimal(len(last20))

    run = 0
    for state in reversed(states):
        if state != candidate_structure:
            break
        run += 1

    resolved = [s for s in last40 if s in {"BULL_TREND", "BEAR_TREND"}]
    flips = sum(1 for a, b in zip(resolved, resolved[1:]) if a != b)

    return MaturityEvidence(
        r40_alignment_last20=q(alignment),
        r40_current_run_bars=run,
        r40_flip_count_last40=flips,
    )


def classify_shock_risk(shock: ShockEvidence) -> str:
    high = (
        shock.largest_range_ratio_vs_median40 >= Decimal("5.0")
        or (
            shock.post_shock_adjusted_displacement < 0
            and shock.shock_offset_from_signal_bars <= 12
        )
    )
    return "SHOCK_RISK_HIGH" if high else "SHOCK_RISK_LOWER"


def classify_continuation(recent20: SegmentEvidence) -> str:
    weak = (
        recent20.adjusted_displacement < Decimal("0.20")
        or recent20.close_path_efficiency < Decimal("0.08")
    )
    return (
        "RECENT_CONTINUATION_WEAK"
        if weak
        else "RECENT_CONTINUATION_STRONGER"
    )


def cell_name(shock_axis: str, continuation_axis: str) -> str:
    shock_part = "HIGH_SHOCK" if shock_axis == "SHOCK_RISK_HIGH" else "LOWER_SHOCK"
    cont_part = (
        "WEAK_CONT"
        if continuation_axis == "RECENT_CONTINUATION_WEAK"
        else "STRONGER_CONT"
    )
    return f"{shock_part}__{cont_part}"


def deterministic_rank(candidate: CandidateRecord) -> str:
    raw = (
        "PHASE8.18|"
        + candidate.symbol
        + "|"
        + candidate.timeframe
        + "|"
        + candidate.snapshot_hash
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def blind_id(candidate: CandidateRecord) -> str:
    raw = (
        "PHASE8.18.BLIND|"
        + candidate.symbol
        + "|"
        + candidate.timeframe
        + "|"
        + candidate.snapshot_hash
    )
    return "T" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:11].upper()


def diversified_cell_sample(
    candidates: list[CandidateRecord],
    *,
    max_items: int,
) -> list[CandidateRecord]:
    """Deterministic round-robin across datasets inside one cell."""
    buckets = defaultdict(list)
    for candidate in candidates:
        buckets[(candidate.symbol, candidate.timeframe)].append(candidate)

    for key in buckets:
        buckets[key] = sorted(buckets[key], key=deterministic_rank)

    keys = sorted(buckets)
    queues = {key: deque(buckets[key]) for key in keys}

    chosen: list[CandidateRecord] = []
    while len(chosen) < max_items:
        progress = False
        for key in keys:
            if queues[key] and len(chosen) < max_items:
                chosen.append(queues[key].popleft())
                progress = True
        if not progress:
            break

    return chosen


def render_blind_chart(
    *,
    snapshot: MarketSnapshot,
    scan,
    start_index: int,
    signal_index: int,
    setup_type: str,
    blind_code: str,
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
            s=25,
            label="confirmed swing high",
        )
    if lows:
        ax.scatter(
            [xs[s.candle_index] for s in lows],
            [float(s.price) for s in lows],
            marker="^",
            s=25,
            label="confirmed swing low",
        )

    ax.axvline(
        xs[len(candles) - 40],
        linestyle=":",
        linewidth=0.9,
        label="40-bar context start",
    )
    ax.axvline(
        xs[start_index],
        linestyle="--",
        linewidth=1.1,
        label="pullback anchor/start",
    )
    ax.axvline(
        xs[signal_index],
        linestyle="-",
        linewidth=1.3,
        label="candidate signal bar",
    )

    # Deliberately hide dual-risk cell, metrics, LAST3, legs, R40.
    ax.set_title(
        f"{blind_code} | {snapshot.symbol} {snapshot.timeframe} | {setup_type}"
    )
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax.grid(True, alpha=0.2)
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("blind chart output missing")


async def evaluate_dataset(
    *,
    source: BinanceHistoricalCandleSource,
    symbol: str,
    timeframe: str,
    policy: FundamentalsExecutionPolicy,
) -> tuple[list[CandidateRecord], dict]:
    candles = await source.get_closed_candles(
        symbol=symbol,
        timeframe=timeframe,
        limit=SOURCE_CANDLES,
        market_type=MARKET_TYPE,
        end_at=END_AT,
    )

    candidates: list[CandidateRecord] = []
    counts = Counter()

    for end_index in range(SNAPSHOT_WINDOW - 1, len(candles)):
        window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

        snapshot = MarketSnapshot(
            exchange=EXCHANGE,
            market_type=MARKET_TYPE,
            symbol=symbol,
            timeframe=timeframe,
            candles=window,
            captured_at=window[-1].close_time,
            source="PHASE8_THIRD_UNSEEN_DUAL_RISK_HOLDOUT",
        )

        counts["evaluated_windows"] += 1

        assert snapshot.captured_at == snapshot.candles[-1].close_time
        assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)

        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        structure = evaluate_br031_structure(scan)

        if structure.direction == "AMBIGUOUS":
            counts["source_structure_ambiguous"] += 1
            continue

        counts["resolved_windows"] += 1

        wanted = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        anchors = [s for s in scan.swings if s.kind == wanted]
        if not anchors:
            counts["no_anchor"] += 1
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

        counts["last2_candidates"] += 1
        direction, setup_type, legs, signal_index = last2

        last3 = detect_candidate(
            snapshot.candles,
            trend_direction=structure.direction,
            start_index=start_index,
            guard_scope_bars=3,
        )
        if last3 is not None:
            counts["last3_survives"] += 1

        pre_prefix = snapshot.candles[: start_index + 1]
        if len(pre_prefix) < max(HORIZONS):
            raise RuntimeError("unexpected insufficient pre-pullback context")

        pre = tuple(
            horizon_evidence(
                pre_prefix,
                horizon=h,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for h in HORIZONS
        )
        signal = tuple(
            horizon_evidence(
                snapshot.candles,
                horizon=h,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for h in HORIZONS
        )

        transition = transition_label(pre, signal)
        counts[f"transition:{transition}"] += 1

        if transition != "MULTIHORIZON_CONTINUATION_LIKE":
            continue

        counts["mh_continuation_candidates"] += 1

        last40 = snapshot.candles[-40:]
        recent20 = segment_evidence(
            snapshot.candles[-20:],
            candidate_structure=structure.direction,
        )
        shock = shock_evidence(
            last40,
            candidate_structure=structure.direction,
        )
        maturity = maturity_evidence(
            snapshot.candles,
            candidate_structure=structure.direction,
            policy=policy,
        )

        shock_axis = classify_shock_risk(shock)
        cont_axis = classify_continuation(recent20)
        cell = cell_name(shock_axis, cont_axis)

        counts[f"cell:{cell}"] += 1

        candidates.append(
            CandidateRecord(
                symbol=symbol,
                timeframe=timeframe,
                captured_at=snapshot.captured_at.isoformat(),
                snapshot_id=snapshot.snapshot_id,
                snapshot_hash=snapshot.snapshot_hash,
                direction=direction,
                setup_type=setup_type,
                countertrend_legs=legs,
                survives_last3=last3 is not None,
                candidate_structure=structure.direction,
                pullback_start_index=start_index,
                signal_index=signal_index,
                transition=transition,
                recent20=recent20,
                shock=shock,
                maturity=maturity,
                shock_risk_axis=shock_axis,
                continuation_axis=cont_axis,
                dual_risk_cell=cell,
            )
        )

    expected = len(candles) - SNAPSHOT_WINDOW + 1
    if counts["evaluated_windows"] != expected:
        raise RuntimeError("evaluated-window count mismatch")

    return candidates, dict(sorted(counts.items()))


async def main() -> None:
    BLIND_CHARTS.mkdir(parents=True, exist_ok=True)
    MAPPING.mkdir(parents=True, exist_ok=True)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.18 refuses enabled autonomous trade decisions")

    all_candidates: list[CandidateRecord] = []
    dataset_counts = {}

    source = BinanceHistoricalCandleSource()
    try:
        for symbol, timeframe in DATASETS:
            candidates, counts = await evaluate_dataset(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                policy=policy,
            )
            all_candidates.extend(candidates)
            dataset_counts[f"{symbol}|{timeframe}"] = counts
    finally:
        await source.aclose()

    grouped_by_cell = defaultdict(list)
    for candidate in all_candidates:
        grouped_by_cell[candidate.dual_risk_cell].append(candidate)

    selected: list[CandidateRecord] = []
    selection_counts = Counter()

    for cell in (
        "LOWER_SHOCK__STRONGER_CONT",
        "LOWER_SHOCK__WEAK_CONT",
        "HIGH_SHOCK__STRONGER_CONT",
        "HIGH_SHOCK__WEAK_CONT",
    ):
        chosen = diversified_cell_sample(
            grouped_by_cell.get(cell, []),
            max_items=MAX_PER_CELL,
        )
        selected.extend(chosen)
        selection_counts[cell] = len(chosen)

    # Unique invariant.
    unique_keys = {
        (c.symbol, c.timeframe, c.snapshot_hash)
        for c in selected
    }
    if len(unique_keys) != len(selected):
        raise RuntimeError("duplicate selected candidate")

    selected = sorted(
        selected,
        key=lambda c: (
            c.dual_risk_cell,
            deterministic_rank(c),
        ),
    )

    selected_grouped = defaultdict(list)
    for candidate in selected:
        selected_grouped[(candidate.symbol, candidate.timeframe)].append(candidate)

    blind_items: list[BlindItem] = []
    mapping_items: list[MappingItem] = []

    source = BinanceHistoricalCandleSource()
    try:
        for symbol, timeframe in sorted(selected_grouped):
            candles = await source.get_closed_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=SOURCE_CANDLES,
                market_type=MARKET_TYPE,
                end_at=END_AT,
            )
            by_close = {c.close_time.isoformat(): i for i, c in enumerate(candles)}

            for candidate in selected_grouped[(symbol, timeframe)]:
                if candidate.captured_at not in by_close:
                    raise RuntimeError("selected candidate cannot be relocated")

                end_index = by_close[candidate.captured_at]
                window = candles[
                    end_index - SNAPSHOT_WINDOW + 1 : end_index + 1
                ]

                snapshot = MarketSnapshot(
                    exchange=EXCHANGE,
                    market_type=MARKET_TYPE,
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=window,
                    captured_at=window[-1].close_time,
                    source="PHASE8_THIRD_UNSEEN_DUAL_RISK_RENDER",
                )

                if snapshot.snapshot_hash != candidate.snapshot_hash:
                    raise RuntimeError("selected snapshot hash drift")

                scan = confirm_swings_causally(
                    snapshot.candles,
                    left_bars=policy.swing_left_bars,
                    right_bars=policy.swing_right_bars,
                )
                structure = evaluate_br031_structure(scan).direction
                if structure != candidate.candidate_structure:
                    raise RuntimeError("selected structure drift")

                code = blind_id(candidate)
                chart_name = f"{code}.png"

                render_blind_chart(
                    snapshot=snapshot,
                    scan=scan,
                    start_index=candidate.pullback_start_index,
                    signal_index=candidate.signal_index,
                    setup_type=candidate.setup_type,
                    blind_code=code,
                    output_path=BLIND_CHARTS / chart_name,
                )

                blind_items.append(
                    BlindItem(
                        blind_id=code,
                        symbol=symbol,
                        timeframe=timeframe,
                        setup_type=candidate.setup_type,
                        chart_file=f"charts/{chart_name}",
                    )
                )

                mapping_items.append(
                    MappingItem(
                        blind_id=code,
                        deterministic_rank=deterministic_rank(candidate),
                        symbol=symbol,
                        timeframe=timeframe,
                        captured_at=candidate.captured_at,
                        snapshot_hash=candidate.snapshot_hash,
                        direction=candidate.direction,
                        setup_type=candidate.setup_type,
                        countertrend_legs=candidate.countertrend_legs,
                        survives_last3=candidate.survives_last3,
                        candidate_structure=candidate.candidate_structure,
                        pullback_start_index=candidate.pullback_start_index,
                        signal_index=candidate.signal_index,
                        transition=candidate.transition,
                        recent20=candidate.recent20,
                        shock=candidate.shock,
                        maturity=candidate.maturity,
                        shock_risk_axis=candidate.shock_risk_axis,
                        continuation_axis=candidate.continuation_axis,
                        dual_risk_cell=candidate.dual_risk_cell,
                    )
                )
    finally:
        await source.aclose()

    blind_items = sorted(blind_items, key=lambda item: item.blind_id)
    mapping_items = sorted(mapping_items, key=lambda item: item.blind_id)

    blind_manifest = {
        "phase": "8.18",
        "mode": "BLIND_THIRD_UNSEEN_DUAL_RISK_HOLDOUT_REVIEW",
        "holdout_end_at": END_AT.isoformat(),
        "review_item_count": len(blind_items),
        "review_labels_allowed": ["KEEP", "REJECT", "UNCERTAIN"],
        "items": [asdict(item) for item in blind_items],
        "hidden_from_blind_review": [
            "dual risk cell",
            "shock risk axis",
            "continuation strength axis",
            "shock metrics",
            "recent20 displacement/efficiency",
            "R40 maturity",
            "LAST3 survival",
            "countertrend leg count",
            "deterministic rank",
        ],
        "outcomes_used_for_selection": False,
        "outcome_or_pnl_computed": False,
    }

    blind_payload = json.dumps(
        blind_manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    blind_manifest_path = BLIND / "phase8_18_blind_manifest.json"
    blind_manifest_path.write_text(blind_payload, encoding="utf-8")

    mapping_manifest = {
        "phase": "8.18",
        "mode": "HIDDEN_MAPPING_FOR_POST_BLIND_DUAL_RISK_ANALYSIS",
        "warning": (
            "Do not reveal this mapping until Phase 8.18 blind visual labels are locked."
        ),
        "candidate_universe": (
            "LAST2 candidate AND MULTIHORIZON_CONTINUATION_LIKE; LAST3 descriptive only"
        ),
        "third_holdout": {
            "end_at": END_AT.isoformat(),
            "source_candles_per_dataset": SOURCE_CANDLES,
            "snapshot_window": SNAPSHOT_WINDOW,
            "datasets": [
                {"symbol": symbol, "timeframe": timeframe}
                for symbol, timeframe in DATASETS
            ],
            "older_than_phase8_14_holdout": True,
            "nonoverlap_intent": True,
        },
        "pre_registered_engineering_bins": {
            "shock_risk_high": (
                "shock_range_ratio >= 5.0 OR "
                "(post_shock_adjusted_displacement < 0 AND shock_offset <= 12)"
            ),
            "recent_continuation_weak": (
                "recent20_adjusted_displacement < 0.20 OR "
                "recent20_close_path_efficiency < 0.08"
            ),
            "boundaries_are_not_brooks_rules": True,
            "production_threshold_selected": False,
        },
        "dataset_counts": dataset_counts,
        "candidate_universe_count": len(all_candidates),
        "universe_by_cell": dict(
            sorted(Counter(c.dual_risk_cell for c in all_candidates).items())
        ),
        "selection_counts_by_cell": dict(sorted(selection_counts.items())),
        "selected_count": len(mapping_items),
        "items": [asdict(item) for item in mapping_items],
        "safety": {
            "production_rules_modified": False,
            "outcomes_used_for_selection": False,
            "outcome_or_pnl_computed": False,
            "database_writes": False,
            "telegram_publish": False,
            "paper_runtime_used": False,
        },
    }

    mapping_payload = json.dumps(
        mapping_manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=str,
    ) + "\n"
    mapping_manifest_path = MAPPING / "phase8_18_mapping_manifest.json"
    mapping_manifest_path.write_text(mapping_payload, encoding="utf-8")

    blind_sums = []
    for file_path in [blind_manifest_path, *sorted(BLIND_CHARTS.glob("*.png"))]:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        blind_sums.append(f"{digest}  {file_path.relative_to(BLIND)}")
    (BLIND / "SHA256SUMS.txt").write_text(
        "\n".join(blind_sums) + "\n",
        encoding="utf-8",
    )

    mapping_sums = []
    for file_path in [mapping_manifest_path]:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        mapping_sums.append(f"{digest}  {file_path.relative_to(MAPPING)}")
    (MAPPING / "SHA256SUMS.txt").write_text(
        "\n".join(mapping_sums) + "\n",
        encoding="utf-8",
    )

    universe_by_cell = Counter(c.dual_risk_cell for c in all_candidates)
    universe_by_dataset = Counter(
        f"{c.symbol}|{c.timeframe}" for c in all_candidates
    )
    selected_by_dataset = Counter(
        f"{c.symbol}|{c.timeframe}" for c in selected
    )

    print("===== PHASE8.18 THIRD UNSEEN DUAL-RISK HOLDOUT =====")
    print(f"END_AT={END_AT.isoformat()}")
    print(f"SOURCE_CANDLES_PER_DATASET={SOURCE_CANDLES}")
    print(f"DATASETS={len(DATASETS)}")
    print()

    print("DATASET_COUNTS")
    for key in sorted(dataset_counts):
        print(key, dataset_counts[key])

    print()
    print(f"CANDIDATE_UNIVERSE={len(all_candidates)}")
    print(f"UNIVERSE_BY_CELL={dict(sorted(universe_by_cell.items()))}")
    print(f"UNIVERSE_BY_DATASET={dict(sorted(universe_by_dataset.items()))}")
    print(f"SELECTED_FOR_BLIND_REVIEW={len(blind_items)}")
    print(f"SELECTION_BY_CELL={dict(sorted(selection_counts.items()))}")
    print(f"SELECTION_BY_DATASET={dict(sorted(selected_by_dataset.items()))}")
    print(f"BLIND_CHART_COUNT={len(list(BLIND_CHARTS.glob('*.png')))}")
    print(f"BLIND_MANIFEST={blind_manifest_path}")
    print(f"MAPPING_MANIFEST={mapping_manifest_path}")
    print()

    print("BLIND_ITEMS")
    for item in blind_items:
        print(
            f"{item.blind_id} "
            f"{item.symbol} {item.timeframe} "
            f"{item.setup_type} "
            f"chart={item.chart_file}"
        )

    print()
    print("THIRD_HOLDOUT_OLDER_THAN_PHASE8_14=TRUE")
    print("LAST3_USED_AS_HARD_GATE=NO")
    print("OUTCOMES_USED_FOR_SELECTION=NO")
    print("OUTCOME_OR_PNL_COMPUTED=NO")
    print("DUAL_RISK_BINS_ARE_NOT_BROOKS_RULES=TRUE")
    print("PRODUCTION_THRESHOLD_SELECTED=NO")
    print("CURRENT_PRODUCTION_RULES_MODIFIED=NO")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_THIRD_UNSEEN_DUAL_RISK_HOLDOUT=PASS")
    print("IMPORTANT=UPLOAD_BLIND_PACK_FIRST_DO_NOT_UPLOAD_MAPPING_YET")


if __name__ == "__main__":
    asyncio.run(main())
