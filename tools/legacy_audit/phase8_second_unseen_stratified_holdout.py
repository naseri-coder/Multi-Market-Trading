"""Phase 8.14 — Second Unseen Stratified Holdout.

DIAGNOSTIC / REVIEW-PACK GENERATION ONLY.
No production rule changes. No outcomes, P&L, or win rate.

Goal
----
Test whether the Phase 8.13 observation that 40-bar structural maturity may be useful
reappears on a second, older, non-overlapping holdout.

Candidate universe:
    LAST_2 H2/L2 diagnostic candidate
    AND MULTIHORIZON_CONTINUATION_LIKE

LAST_3 is deliberately NOT a hard gate in this phase because Phase 8.12 found visually
acceptable candidates among LAST_3 failures.

Second holdout:
    Binance Spot
    BTCUSDT 15m
    ETHUSDT 15m
    BTCUSDT 1h
    ETHUSDT 1h
    2500 closed candles per dataset
    fixed end_at = 2026-05-15T00:00:00Z

This ends before the first Phase 8.10 holdout source period for the slowest 1h dataset,
so it is an older holdout.

Primary descriptive stratification (engineering-only, fixed before reading this holdout):
    R40_ALIGNMENT_LOW  : alignment < 0.50
    R40_ALIGNMENT_MID  : 0.50 <= alignment < 0.75
    R40_ALIGNMENT_HIGH : alignment >= 0.75

The 0.50/0.75 boundaries are descriptive engineering bins, NOT Brooks rules and NOT
production thresholds.

Sampling:
    Up to 2 candidates per dataset per R40 alignment stratum.
    Selection is deterministic by SHA256 and uses no outcome information.

Outputs:
    /out/blind/phase8_14_blind_manifest.json
    /out/blind/charts/*.png
    /out/blind/SHA256SUMS.txt

    /out/mapping/phase8_14_mapping_manifest.json
    /out/mapping/SHA256SUMS.txt

IMPORTANT BLIND-REVIEW WORKFLOW:
Upload/review the /blind pack first. Do NOT reveal the /mapping pack until blind labels
have been recorded.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

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


END_AT = datetime.fromisoformat("2026-05-15T00:00:00+00:00")
EXCHANGE = "binance"
MARKET_TYPE = "spot"
SOURCE_CANDLES = 2500
SNAPSHOT_WINDOW = 100
HORIZONS = (20, 40, 80)
SAMPLE_PER_DATASET_PER_STRATUM = 2

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
class MaturityEvidence:
    r40_alignment_last20: Decimal
    r40_ambiguous_last20: Decimal
    r40_flip_count_last40: int
    r40_current_run_bars: int
    r20_alignment_last20: Decimal
    r20_current_run_bars: int
    alignment_stratum: str


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
    transition: str
    candidate_structure: str
    pullback_start_index: int
    signal_index: int
    maturity: MaturityEvidence


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
    symbol: str
    timeframe: str
    captured_at: str
    snapshot_hash: str
    direction: str
    setup_type: str
    countertrend_legs: int
    survives_last3: bool
    transition: str
    candidate_structure: str
    pullback_start_index: int
    signal_index: int
    maturity: MaturityEvidence
    deterministic_rank: str


def q(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


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

    highest = max(c.high for c in ctx)
    lowest = min(c.low for c in ctx)
    total_range = highest - lowest
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


def rolling_states(
    candles: tuple[Candle, ...],
    *,
    window_bars: int,
    policy: FundamentalsExecutionPolicy,
) -> tuple[str, ...]:
    states = []
    for end_index in range(window_bars - 1, len(candles)):
        window = candles[end_index - window_bars + 1 : end_index + 1]
        scan = confirm_swings_causally(
            window,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        states.append(evaluate_br031_structure(scan).direction)
    return tuple(states)


def resolved_flip_count(states: tuple[str, ...]) -> int:
    resolved = [state for state in states if state in {"BULL_TREND", "BEAR_TREND"}]
    return sum(
        1
        for previous, current in zip(resolved, resolved[1:])
        if previous != current
    )


def current_run(states: tuple[str, ...], candidate_structure: str) -> int:
    count = 0
    for state in reversed(states):
        if state != candidate_structure:
            break
        count += 1
    return count


def alignment_stratum(value: Decimal) -> str:
    if value < Decimal("0.50"):
        return "R40_ALIGNMENT_LOW"
    if value < Decimal("0.75"):
        return "R40_ALIGNMENT_MID"
    return "R40_ALIGNMENT_HIGH"


def maturity_evidence(
    candles: tuple[Candle, ...],
    *,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> MaturityEvidence:
    states40 = rolling_states(
        candles,
        window_bars=40,
        policy=policy,
    )
    states20 = rolling_states(
        candles,
        window_bars=20,
        policy=policy,
    )

    last20_40 = states40[-20:]
    last40_40 = states40[-40:]
    last20_20 = states20[-20:]

    r40_alignment = q(
        sum(state == candidate_structure for state in last20_40)
        / len(last20_40)
    )
    r40_ambiguous = q(
        sum(state == "AMBIGUOUS" for state in last20_40)
        / len(last20_40)
    )
    r20_alignment = q(
        sum(state == candidate_structure for state in last20_20)
        / len(last20_20)
    )

    return MaturityEvidence(
        r40_alignment_last20=r40_alignment,
        r40_ambiguous_last20=r40_ambiguous,
        r40_flip_count_last40=resolved_flip_count(last40_40),
        r40_current_run_bars=current_run(states40, candidate_structure),
        r20_alignment_last20=r20_alignment,
        r20_current_run_bars=current_run(states20, candidate_structure),
        alignment_stratum=alignment_stratum(r40_alignment),
    )


def deterministic_rank(candidate: CandidateRecord) -> str:
    raw = (
        "PHASE8.14|"
        + candidate.symbol
        + "|"
        + candidate.timeframe
        + "|"
        + candidate.snapshot_hash
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def blind_id(candidate: CandidateRecord) -> str:
    raw = (
        "PHASE8.14.BLIND|"
        + candidate.symbol
        + "|"
        + candidate.timeframe
        + "|"
        + candidate.snapshot_hash
    )
    return "S" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:11].upper()


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

    # Deliberately hides maturity stratum, LAST3, leg count, transition and metrics.
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
            source="PHASE8_SECOND_UNSEEN_STRATIFIED_HOLDOUT",
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
            evaluate_horizon(
                pre_prefix,
                horizon=h,
                candidate_structure=structure.direction,
                policy=policy,
            )
            for h in HORIZONS
        )
        signal = tuple(
            evaluate_horizon(
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

        maturity = maturity_evidence(
            snapshot.candles,
            candidate_structure=structure.direction,
            policy=policy,
        )
        counts[f"stratum:{maturity.alignment_stratum}"] += 1

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
                transition=transition,
                candidate_structure=structure.direction,
                pullback_start_index=start_index,
                signal_index=signal_index,
                maturity=maturity,
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
        raise RuntimeError("Phase 8.14 refuses enabled autonomous trade decisions")

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

    # Deterministic stratified selection: max 2 per dataset per alignment stratum.
    grouped = defaultdict(list)
    for candidate in all_candidates:
        grouped[
            (
                candidate.symbol,
                candidate.timeframe,
                candidate.maturity.alignment_stratum,
            )
        ].append(candidate)

    selected: list[CandidateRecord] = []
    selection_counts = Counter()

    for key in sorted(grouped):
        ranked = sorted(grouped[key], key=deterministic_rank)
        chosen = ranked[:SAMPLE_PER_DATASET_PER_STRATUM]
        selected.extend(chosen)
        selection_counts[key[2]] += len(chosen)

    selected = sorted(
        selected,
        key=lambda c: (
            c.symbol,
            c.timeframe,
            c.maturity.alignment_stratum,
            deterministic_rank(c),
        ),
    )

    # Re-fetch by dataset and render selected candidates causally.
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
                window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

                snapshot = MarketSnapshot(
                    exchange=EXCHANGE,
                    market_type=MARKET_TYPE,
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=window,
                    captured_at=window[-1].close_time,
                    source="PHASE8_SECOND_UNSEEN_STRATIFIED_HOLDOUT_RENDER",
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
                    raise RuntimeError("selected candidate structure drift")

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
                        symbol=symbol,
                        timeframe=timeframe,
                        captured_at=candidate.captured_at,
                        snapshot_hash=candidate.snapshot_hash,
                        direction=candidate.direction,
                        setup_type=candidate.setup_type,
                        countertrend_legs=candidate.countertrend_legs,
                        survives_last3=candidate.survives_last3,
                        transition=candidate.transition,
                        candidate_structure=candidate.candidate_structure,
                        pullback_start_index=candidate.pullback_start_index,
                        signal_index=candidate.signal_index,
                        maturity=candidate.maturity,
                        deterministic_rank=deterministic_rank(candidate),
                    )
                )
    finally:
        await source.aclose()

    blind_items = sorted(blind_items, key=lambda item: item.blind_id)
    mapping_items = sorted(mapping_items, key=lambda item: item.blind_id)

    blind_manifest = {
        "phase": "8.14",
        "mode": "BLIND_SECOND_UNSEEN_STRATIFIED_HOLDOUT_REVIEW",
        "holdout_end_at": END_AT.isoformat(),
        "review_item_count": len(blind_items),
        "review_labels_allowed": ["KEEP", "REJECT", "UNCERTAIN"],
        "items": [asdict(item) for item in blind_items],
        "hidden_from_blind_review": [
            "R40 alignment stratum",
            "R40 current run",
            "LAST3 survival",
            "countertrend leg count",
            "transition metrics",
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
    blind_manifest_path = BLIND / "phase8_14_blind_manifest.json"
    blind_manifest_path.write_text(blind_payload, encoding="utf-8")

    mapping_manifest = {
        "phase": "8.14",
        "mode": "HIDDEN_MAPPING_FOR_POST_BLIND_ANALYSIS",
        "warning": (
            "Do not reveal this mapping until blind visual review labels have been recorded."
        ),
        "candidate_universe": (
            "LAST2 candidate AND MULTIHORIZON_CONTINUATION_LIKE; LAST3 is descriptive only"
        ),
        "second_holdout": {
            "end_at": END_AT.isoformat(),
            "source_candles_per_dataset": SOURCE_CANDLES,
            "snapshot_window": SNAPSHOT_WINDOW,
            "datasets": [
                {"symbol": symbol, "timeframe": timeframe}
                for symbol, timeframe in DATASETS
            ],
            "older_than_phase8_10_holdout": True,
        },
        "stratification": {
            "metric": "rolling40 structure alignment over last 20 rolling states",
            "R40_ALIGNMENT_LOW": "<0.50",
            "R40_ALIGNMENT_MID": ">=0.50 and <0.75",
            "R40_ALIGNMENT_HIGH": ">=0.75",
            "boundaries_are_engineering_bins_not_brooks_rules": True,
            "production_threshold_selected": False,
        },
        "dataset_counts": dataset_counts,
        "candidate_universe_count": len(all_candidates),
        "selection_counts_by_stratum": dict(sorted(selection_counts.items())),
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
    mapping_manifest_path = MAPPING / "phase8_14_mapping_manifest.json"
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

    print("===== PHASE8.14 SECOND UNSEEN STRATIFIED HOLDOUT =====")
    print(f"END_AT={END_AT.isoformat()}")
    print(f"SOURCE_CANDLES_PER_DATASET={SOURCE_CANDLES}")
    print(f"DATASETS={len(DATASETS)}")
    print()

    print("DATASET_COUNTS")
    for key in sorted(dataset_counts):
        print(key, dataset_counts[key])

    universe_by_stratum = Counter(
        candidate.maturity.alignment_stratum for candidate in all_candidates
    )

    print()
    print(f"CANDIDATE_UNIVERSE={len(all_candidates)}")
    print(f"UNIVERSE_BY_STRATUM={dict(sorted(universe_by_stratum.items()))}")
    print(f"SELECTED_FOR_BLIND_REVIEW={len(blind_items)}")
    print(f"SELECTION_BY_STRATUM={dict(sorted(selection_counts.items()))}")
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
    print("SECOND_HOLDOUT_OLDER_THAN_PHASE8_10=TRUE")
    print("LAST3_USED_AS_HARD_GATE=NO")
    print("OUTCOMES_USED_FOR_SELECTION=NO")
    print("OUTCOME_OR_PNL_COMPUTED=NO")
    print("STRATIFICATION_BINS_ARE_NOT_BROOKS_RULES=TRUE")
    print("PRODUCTION_THRESHOLD_SELECTED=NO")
    print("CURRENT_PRODUCTION_RULES_MODIFIED=NO")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_SECOND_UNSEEN_STRATIFIED_HOLDOUT=PASS")
    print("IMPORTANT=UPLOAD_BLIND_PACK_FIRST_DO_NOT_UPLOAD_MAPPING_YET")


if __name__ == "__main__":
    asyncio.run(main())
