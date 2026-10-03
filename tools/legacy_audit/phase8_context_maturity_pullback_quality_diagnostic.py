"""Phase 8.13 — Context Maturity & Pullback Quality Diagnostic.

DIAGNOSTIC ONLY. No production rule changes. No outcomes/P&L.

Purpose:
Measure why some H2/L2 candidates that already pass multi-horizon context still look
visually weak, and whether LAST_3 is discarding visually acceptable setups.

Inputs:
  /visual/phase8_holdout_visual_review_manifest.json
  /composite/phase8_holdout_composite_validation.json

The 16 visual labels come from the completed blind Phase 8.12 review and are used only
to compare descriptive feature distributions. They are NOT ground truth and must not
be converted into production thresholds from this small sample.

Source-grounded concepts:
- trend vs trading range (reviewed PDF p5)
- context / bars to the left matter (p27, pp116-123)
- HH/HL vs LH/LL structure (p127)
- context and momentum matter (pp128-130)
- EMA20 is secondary context (p20, pp133-135)

Engineering-only diagnostics:
- rolling 20/40-bar structural stability
- structure flip count
- pullback duration and depth relative to prior structural impulse
- pullback overlap and countertrend-body fraction
- signal-bar body/close-location/range/break margin
These measurements and any later thresholds are NOT Brooks-authored rules.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Iterable

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


VISUAL_MANIFEST: Path | None = None
COMPOSITE_MANIFEST: Path | None = None
OUT: Path | None = None

EXCHANGE = "binance"
MARKET_TYPE = "spot"
SOURCE_CANDLES = 2000
SNAPSHOT_WINDOW = 100

# Blind Phase 8.12 review labels. These are review judgments, not price outcomes.
REVIEW_LABELS = {
    "61d56926ed7e1b58": "KEEP",
    "cf152f093646a6e9": "KEEP",
    "0018f575ce807690": "UNCERTAIN",
    "6dff1a96dde9a0b7": "KEEP",
    "6dec55375c7b966c": "KEEP",
    "400b6378360e708e": "UNCERTAIN",
    "029e1b8e75505b26": "KEEP",
    "c7299f56be4f357f": "REJECT",
    "497f417c28a8d37c": "REJECT",
    "d1a48bff56b57cf6": "REJECT",
    "78c1af45d0aaff8c": "KEEP",
    "c4d97ad168913426": "KEEP",
    "c6cd5df4f40b34df": "UNCERTAIN",
    "0360bf8274bd847e": "KEEP",
    "8d288473ed9f246b": "KEEP",
    "6ecdfefb2083a979": "KEEP",
}


@dataclass(frozen=True, slots=True)
class StructureMaturity:
    rolling20_alignment_last20: Decimal
    rolling20_ambiguous_last20: Decimal
    rolling20_flip_count_last40: int
    rolling20_current_run_bars: int
    rolling40_alignment_last20: Decimal
    rolling40_ambiguous_last20: Decimal
    rolling40_flip_count_last40: int
    rolling40_current_run_bars: int


@dataclass(frozen=True, slots=True)
class PullbackQuality:
    duration_bars: int
    impulse_size: Decimal | None
    depth_ratio_vs_prior_impulse: Decimal | None
    extreme_offset_bars: int | None
    overlap_frequency: Decimal
    countertrend_body_fraction: Decimal
    same_direction_body_fraction: Decimal
    pullback_range_vs_prior_impulse: Decimal | None


@dataclass(frozen=True, slots=True)
class SignalBarQuality:
    body_fraction: Decimal
    directional_body: bool
    directional_close_location: Decimal
    range_vs_median_prior20: Decimal
    breakout_margin_vs_median_prior20: Decimal
    ema20_distance_vs_median_prior20: Decimal
    ema20_directionally_aligned: bool


@dataclass(frozen=True, slots=True)
class CandidateDiagnostic:
    review_id: str
    review_label: str
    sample_group: str
    symbol: str
    timeframe: str
    captured_at: str
    direction: str
    setup_type: str
    countertrend_legs: int
    survives_last3: bool
    transition: str
    composite_v1_pass: bool
    candidate_structure: str
    pullback_start_index: int
    signal_index: int
    snapshot_hash_verified: bool
    structure_maturity: StructureMaturity
    pullback_quality: PullbackQuality
    signal_bar_quality: SignalBarQuality


def q(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def median_decimal(values: Iterable[Decimal]) -> Decimal:
    vals = tuple(values)
    if not vals:
        return Decimal("0")
    return q(median(vals))


def ema(values: tuple[Decimal, ...], length: int) -> tuple[Decimal, ...]:
    if not values:
        return ()
    alpha = Decimal("2") / Decimal(length + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (Decimal("1") - alpha) * result[-1])
    return tuple(result)


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


def rolling_structure_states(
    candles: tuple[Candle, ...],
    *,
    window_bars: int,
    policy: FundamentalsExecutionPolicy,
) -> tuple[str, ...]:
    states = []
    for end in range(window_bars - 1, len(candles)):
        window = candles[end - window_bars + 1 : end + 1]
        scan = confirm_swings_causally(
            window,
            left_bars=policy.swing_left_bars,
            right_bars=policy.swing_right_bars,
        )
        states.append(evaluate_br031_structure(scan).direction)
    return tuple(states)


def resolved_flip_count(states: tuple[str, ...]) -> int:
    resolved = [s for s in states if s in {"BULL_TREND", "BEAR_TREND"}]
    return sum(1 for a, b in zip(resolved, resolved[1:]) if a != b)


def current_run(states: tuple[str, ...], candidate_structure: str) -> int:
    count = 0
    for state in reversed(states):
        if state != candidate_structure:
            break
        count += 1
    return count


def maturity_metrics(
    candles: tuple[Candle, ...],
    *,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> StructureMaturity:
    states20 = rolling_structure_states(
        candles,
        window_bars=20,
        policy=policy,
    )
    states40 = rolling_structure_states(
        candles,
        window_bars=40,
        policy=policy,
    )

    last20_20 = states20[-20:]
    last20_40 = states40[-20:]
    last40_20 = states20[-40:]
    last40_40 = states40[-40:]

    return StructureMaturity(
        rolling20_alignment_last20=q(
            sum(s == candidate_structure for s in last20_20) / len(last20_20)
        ),
        rolling20_ambiguous_last20=q(
            sum(s == "AMBIGUOUS" for s in last20_20) / len(last20_20)
        ),
        rolling20_flip_count_last40=resolved_flip_count(last40_20),
        rolling20_current_run_bars=current_run(states20, candidate_structure),
        rolling40_alignment_last20=q(
            sum(s == candidate_structure for s in last20_40) / len(last20_40)
        ),
        rolling40_ambiguous_last20=q(
            sum(s == "AMBIGUOUS" for s in last20_40) / len(last20_40)
        ),
        rolling40_flip_count_last40=resolved_flip_count(last40_40),
        rolling40_current_run_bars=current_run(states40, candidate_structure),
    )


def pullback_metrics(
    candles: tuple[Candle, ...],
    *,
    start_index: int,
    signal_index: int,
    candidate_structure: str,
    scan,
) -> PullbackQuality:
    pullback = candles[start_index : signal_index + 1]
    if len(pullback) < 2:
        raise RuntimeError("pullback window unexpectedly short")

    wanted_anchor_kind = "HIGH" if candidate_structure == "BULL_TREND" else "LOW"
    opposite_kind = "LOW" if candidate_structure == "BULL_TREND" else "HIGH"

    anchor_candidates = [
        s for s in scan.swings
        if s.kind == wanted_anchor_kind and s.candle_index <= start_index
    ]
    anchor = anchor_candidates[-1] if anchor_candidates else None

    prior_opposites = []
    if anchor is not None:
        prior_opposites = [
            s for s in scan.swings
            if s.kind == opposite_kind and s.candle_index < anchor.candle_index
        ]
    prior = prior_opposites[-1] if prior_opposites else None

    impulse_size = None
    depth_ratio = None
    pullback_range_ratio = None
    extreme_offset = None

    if anchor is not None and prior is not None:
        impulse_size = abs(anchor.price - prior.price)
        if impulse_size > 0:
            if candidate_structure == "BULL_TREND":
                extreme_price = min(c.low for c in pullback)
                extreme_abs_index = start_index + min(
                    range(len(pullback)),
                    key=lambda i: pullback[i].low,
                )
                adverse = max(Decimal("0"), anchor.price - extreme_price)
            else:
                extreme_price = max(c.high for c in pullback)
                extreme_abs_index = start_index + max(
                    range(len(pullback)),
                    key=lambda i: pullback[i].high,
                )
                adverse = max(Decimal("0"), extreme_price - anchor.price)

            depth_ratio = adverse / impulse_size
            extreme_offset = extreme_abs_index - start_index

            p_high = max(c.high for c in pullback)
            p_low = min(c.low for c in pullback)
            pullback_range_ratio = (p_high - p_low) / impulse_size

    overlaps = 0
    for previous, current in zip(pullback, pullback[1:]):
        if min(previous.high, current.high) >= max(previous.low, current.low):
            overlaps += 1
    overlap_frequency = Decimal(overlaps) / Decimal(len(pullback) - 1)

    countertrend_bodies = 0
    same_direction_bodies = 0
    for c in pullback[1:]:
        if candidate_structure == "BULL_TREND":
            if c.close < c.open:
                countertrend_bodies += 1
            elif c.close > c.open:
                same_direction_bodies += 1
        else:
            if c.close > c.open:
                countertrend_bodies += 1
            elif c.close < c.open:
                same_direction_bodies += 1

    denom = max(1, len(pullback) - 1)

    return PullbackQuality(
        duration_bars=signal_index - start_index,
        impulse_size=None if impulse_size is None else q(impulse_size),
        depth_ratio_vs_prior_impulse=None if depth_ratio is None else q(depth_ratio),
        extreme_offset_bars=extreme_offset,
        overlap_frequency=q(overlap_frequency),
        countertrend_body_fraction=q(countertrend_bodies / denom),
        same_direction_body_fraction=q(same_direction_bodies / denom),
        pullback_range_vs_prior_impulse=(
            None if pullback_range_ratio is None else q(pullback_range_ratio)
        ),
    )


def signal_metrics(
    candles: tuple[Candle, ...],
    *,
    signal_index: int,
    candidate_structure: str,
) -> SignalBarQuality:
    signal = candles[signal_index]
    previous = candles[signal_index - 1]

    bar_range = signal.high - signal.low
    body = abs(signal.close - signal.open)
    body_fraction = Decimal("0") if bar_range == 0 else body / bar_range

    if candidate_structure == "BULL_TREND":
        directional_body = signal.close > signal.open
        close_location = (
            Decimal("0.5")
            if bar_range == 0
            else (signal.close - signal.low) / bar_range
        )
    else:
        directional_body = signal.close < signal.open
        close_location = (
            Decimal("0.5")
            if bar_range == 0
            else (signal.high - signal.close) / bar_range
        )

    prior = candles[max(0, signal_index - 20) : signal_index]
    prior_ranges = tuple(c.high - c.low for c in prior)
    median_range = median_decimal(prior_ranges)
    if median_range <= 0:
        median_range = Decimal("1")

    range_ratio = bar_range / median_range

    if candidate_structure == "BULL_TREND":
        breakout_margin = signal.high - previous.high
    else:
        breakout_margin = previous.low - signal.low
    breakout_margin_ratio = breakout_margin / median_range

    closes = tuple(c.close for c in candles[: signal_index + 1])
    ema20_values = ema(closes, 20)
    ema20_value = ema20_values[-1]
    if candidate_structure == "BULL_TREND":
        ema_distance = signal.close - ema20_value
        ema_aligned = signal.close >= ema20_value
    else:
        ema_distance = ema20_value - signal.close
        ema_aligned = signal.close <= ema20_value

    return SignalBarQuality(
        body_fraction=q(body_fraction),
        directional_body=directional_body,
        directional_close_location=q(close_location),
        range_vs_median_prior20=q(range_ratio),
        breakout_margin_vs_median_prior20=q(breakout_margin_ratio),
        ema20_distance_vs_median_prior20=q(ema_distance / median_range),
        ema20_directionally_aligned=ema_aligned,
    )


def float_or_none(value):
    if value is None:
        return None
    return float(value)


def summarize_group(rows: list[CandidateDiagnostic]) -> dict:
    if not rows:
        return {"count": 0}

    feature_extractors = {
        "countertrend_legs": lambda r: Decimal(r.countertrend_legs),
        "rolling20_alignment_last20": lambda r: r.structure_maturity.rolling20_alignment_last20,
        "rolling20_flip_count_last40": lambda r: Decimal(r.structure_maturity.rolling20_flip_count_last40),
        "rolling20_current_run_bars": lambda r: Decimal(r.structure_maturity.rolling20_current_run_bars),
        "rolling40_alignment_last20": lambda r: r.structure_maturity.rolling40_alignment_last20,
        "rolling40_flip_count_last40": lambda r: Decimal(r.structure_maturity.rolling40_flip_count_last40),
        "rolling40_current_run_bars": lambda r: Decimal(r.structure_maturity.rolling40_current_run_bars),
        "pullback_duration_bars": lambda r: Decimal(r.pullback_quality.duration_bars),
        "pullback_depth_ratio": lambda r: r.pullback_quality.depth_ratio_vs_prior_impulse,
        "pullback_overlap_frequency": lambda r: r.pullback_quality.overlap_frequency,
        "pullback_countertrend_body_fraction": lambda r: r.pullback_quality.countertrend_body_fraction,
        "signal_body_fraction": lambda r: r.signal_bar_quality.body_fraction,
        "signal_directional_close_location": lambda r: r.signal_bar_quality.directional_close_location,
        "signal_range_vs_median_prior20": lambda r: r.signal_bar_quality.range_vs_median_prior20,
        "signal_breakout_margin_vs_median_prior20": lambda r: r.signal_bar_quality.breakout_margin_vs_median_prior20,
        "signal_ema20_distance_vs_median_prior20": lambda r: r.signal_bar_quality.ema20_distance_vs_median_prior20,
    }

    features = {}
    for name, extractor in feature_extractors.items():
        values = [extractor(row) for row in rows]
        values = [v for v in values if v is not None]
        if not values:
            features[name] = None
            continue
        values = [Decimal(v) for v in values]
        features[name] = {
            "n": len(values),
            "min": str(q(min(values))),
            "median": str(q(median(values))),
            "max": str(q(max(values))),
        }

    return {
        "count": len(rows),
        "last3_true": sum(r.survives_last3 for r in rows),
        "directional_signal_body_true": sum(
            r.signal_bar_quality.directional_body for r in rows
        ),
        "ema20_aligned_true": sum(
            r.signal_bar_quality.ema20_directionally_aligned for r in rows
        ),
        "features": features,
    }


async def main() -> None:
    if VISUAL_MANIFEST is None or COMPOSITE_MANIFEST is None or OUT is None:
        raise RuntimeError("explicit --visual-manifest, --composite-manifest and --output-dir are required")
    if not VISUAL_MANIFEST.is_file():
        raise FileNotFoundError(VISUAL_MANIFEST)
    if not COMPOSITE_MANIFEST.is_file():
        raise FileNotFoundError(COMPOSITE_MANIFEST)

    visual = json.loads(VISUAL_MANIFEST.read_text(encoding="utf-8"))
    composite = json.loads(COMPOSITE_MANIFEST.read_text(encoding="utf-8"))

    items = visual["items"]
    review_ids = {item["review_id"] for item in items}
    if review_ids != set(REVIEW_LABELS):
        raise RuntimeError(
            f"review-id drift: missing={sorted(set(REVIEW_LABELS)-review_ids)} "
            f"extra={sorted(review_ids-set(REVIEW_LABELS))}"
        )

    # Locate source holdout candidate records for snapshot hash verification.
    source_lookup = {}
    for report in composite["datasets"]:
        for candidate in report["candidates"]:
            key = (
                report["symbol"],
                report["timeframe"],
                candidate["captured_at"],
                candidate["setup_type"],
            )
            source_lookup[key] = candidate

    end_at = datetime.fromisoformat(composite["holdout"]["end_at"])

    grouped = defaultdict(list)
    for item in items:
        grouped[(item["symbol"], item["timeframe"])].append(item)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.13 refuses enabled autonomous trade decisions")

    source = BinanceHistoricalCandleSource()
    diagnostics: list[CandidateDiagnostic] = []

    try:
        for symbol, timeframe in sorted(grouped):
            candles = await source.get_closed_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=SOURCE_CANDLES,
                market_type=MARKET_TYPE,
                end_at=end_at,
            )
            by_close = {c.close_time.isoformat(): i for i, c in enumerate(candles)}

            for item in sorted(grouped[(symbol, timeframe)], key=lambda x: x["captured_at"]):
                captured_at = item["captured_at"]
                if captured_at not in by_close:
                    raise RuntimeError(f"cannot locate {symbol} {timeframe} {captured_at}")

                end_index = by_close[captured_at]
                if end_index < SNAPSHOT_WINDOW - 1:
                    raise RuntimeError("candidate lacks 100 bars")

                window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]
                snapshot = MarketSnapshot(
                    exchange=EXCHANGE,
                    market_type=MARKET_TYPE,
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=window,
                    captured_at=window[-1].close_time,
                    source="PHASE8_CONTEXT_MATURITY_PULLBACK_QUALITY",
                )

                assert snapshot.captured_at.isoformat() == captured_at
                assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)

                scan = confirm_swings_causally(
                    snapshot.candles,
                    left_bars=policy.swing_left_bars,
                    right_bars=policy.swing_right_bars,
                )
                structure = evaluate_br031_structure(scan).direction
                if structure not in {"BULL_TREND", "BEAR_TREND"}:
                    raise RuntimeError("selected candidate became ambiguous")

                wanted = "HIGH" if structure == "BULL_TREND" else "LOW"
                anchors = [s for s in scan.swings if s.kind == wanted]
                if not anchors:
                    raise RuntimeError("selected candidate lacks anchor")

                start_index = anchors[-1].candle_index
                if len(snapshot.candles) - start_index > policy.pullback_window_bars:
                    start_index = len(snapshot.candles) - policy.pullback_window_bars

                last2 = detect_candidate(
                    snapshot.candles,
                    trend_direction=structure,
                    start_index=start_index,
                    guard_scope_bars=2,
                )
                last3 = detect_candidate(
                    snapshot.candles,
                    trend_direction=structure,
                    start_index=start_index,
                    guard_scope_bars=3,
                )
                if last2 is None:
                    raise RuntimeError("visual candidate no longer passes LAST2")

                direction, setup_type, legs, signal_index = last2
                if direction != item["direction"] or setup_type != item["setup_type"]:
                    raise RuntimeError("candidate setup drift")
                if bool(last3 is not None) != bool(item["survives_last3"]):
                    raise RuntimeError("candidate LAST3 drift")

                source_key = (symbol, timeframe, captured_at, setup_type)
                source_candidate = source_lookup.get(source_key)
                if source_candidate is None:
                    raise RuntimeError(f"source candidate missing: {source_key}")

                # MarketSnapshot hash does not depend on diagnostic source string.
                snapshot_hash_verified = (
                    snapshot.snapshot_hash == source_candidate["snapshot_hash"]
                )
                if not snapshot_hash_verified:
                    raise RuntimeError(f"snapshot hash drift: {source_key}")

                diagnostics.append(
                    CandidateDiagnostic(
                        review_id=item["review_id"],
                        review_label=REVIEW_LABELS[item["review_id"]],
                        sample_group=item["sample_group"],
                        symbol=symbol,
                        timeframe=timeframe,
                        captured_at=captured_at,
                        direction=direction,
                        setup_type=setup_type,
                        countertrend_legs=legs,
                        survives_last3=bool(last3 is not None),
                        transition=item["transition"],
                        composite_v1_pass=bool(item["composite_v1_pass"]),
                        candidate_structure=structure,
                        pullback_start_index=start_index,
                        signal_index=signal_index,
                        snapshot_hash_verified=True,
                        structure_maturity=maturity_metrics(
                            snapshot.candles,
                            candidate_structure=structure,
                            policy=policy,
                        ),
                        pullback_quality=pullback_metrics(
                            snapshot.candles,
                            start_index=start_index,
                            signal_index=signal_index,
                            candidate_structure=structure,
                            scan=scan,
                        ),
                        signal_bar_quality=signal_metrics(
                            snapshot.candles,
                            signal_index=signal_index,
                            candidate_structure=structure,
                        ),
                    )
                )
    finally:
        await source.aclose()

    diagnostics = sorted(
        diagnostics,
        key=lambda r: (r.review_label, r.symbol, r.timeframe, r.captured_at),
    )

    by_label = defaultdict(list)
    for row in diagnostics:
        by_label[row.review_label].append(row)

    label_summary = {
        label: summarize_group(by_label[label])
        for label in ("KEEP", "UNCERTAIN", "REJECT")
    }

    legs_by_label = {
        label: dict(sorted(Counter(r.countertrend_legs for r in rows).items()))
        for label, rows in by_label.items()
    }

    manifest = {
        "phase": "8.13",
        "mode": "CONTEXT_MATURITY_PULLBACK_QUALITY_DIAGNOSTIC_ONLY",
        "warning": (
            "16 blind-review labels are descriptive judgments, not price outcomes or "
            "ground truth. No threshold may be promoted from this sample alone."
        ),
        "source_grounded_concepts": {
            "p5": "trend vs trading range",
            "p27": "bars to the left / context",
            "p116_123": "context matters more than isolated pattern",
            "p127": "HH/HL and LH/LL structure",
            "p128_130": "context and momentum",
            "p20_p133_135": "EMA20 is secondary context",
        },
        "engineering_measurements_not_brooks_rules": [
            "rolling20/40 structural alignment",
            "resolved structure flip counts",
            "contiguous current structure run",
            "pullback duration",
            "pullback depth relative to prior structural impulse",
            "pullback overlap",
            "countertrend body fraction",
            "signal body fraction",
            "signal directional close location",
            "signal range versus median prior 20",
            "signal breakout margin versus median prior 20",
            "EMA20 distance versus median prior 20",
        ],
        "review_item_count": len(diagnostics),
        "review_label_counts": dict(sorted(Counter(r.review_label for r in diagnostics).items())),
        "legs_by_review_label": legs_by_label,
        "label_summary": label_summary,
        "candidates": [asdict(row) for row in diagnostics],
        "safety": {
            "production_rules_modified": False,
            "outcome_or_pnl_computed": False,
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

    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "phase8_context_maturity_pullback_quality_diagnostic.json"
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    print("===== PHASE8.13 CONTEXT MATURITY & PULLBACK QUALITY =====")
    print(f"REVIEW_ITEMS={len(diagnostics)}")
    print(f"REVIEW_LABEL_COUNTS={manifest['review_label_counts']}")
    print(f"LEGS_BY_LABEL={legs_by_label}")
    print()

    print("CANDIDATE_MATRIX")
    for row in diagnostics:
        m = row.structure_maturity
        p = row.pullback_quality
        s = row.signal_bar_quality
        print(
            f"{row.review_id} "
            f"{row.review_label} "
            f"{row.symbol} {row.timeframe} "
            f"{row.setup_type} legs={row.countertrend_legs} "
            f"LAST3={row.survives_last3} "
            f"R20_ALIGN={m.rolling20_alignment_last20} "
            f"R20_FLIPS={m.rolling20_flip_count_last40} "
            f"R20_RUN={m.rolling20_current_run_bars} "
            f"R40_ALIGN={m.rolling40_alignment_last20} "
            f"R40_FLIPS={m.rolling40_flip_count_last40} "
            f"R40_RUN={m.rolling40_current_run_bars} "
            f"PB_DUR={p.duration_bars} "
            f"PB_DEPTH={p.depth_ratio_vs_prior_impulse} "
            f"PB_OVERLAP={p.overlap_frequency} "
            f"PB_CT_BODY={p.countertrend_body_fraction} "
            f"SIG_BODY={s.body_fraction} "
            f"SIG_CLOSE={s.directional_close_location} "
            f"SIG_RANGE={s.range_vs_median_prior20} "
            f"SIG_BREAK={s.breakout_margin_vs_median_prior20} "
            f"EMA_DIST={s.ema20_distance_vs_median_prior20}"
        )

    print()
    print("LABEL_SUMMARY")
    for label in ("KEEP", "UNCERTAIN", "REJECT"):
        summary = label_summary[label]
        print(f"{label} count={summary['count']}")
        for feature, stats in summary.get("features", {}).items():
            if stats is not None:
                print(
                    f"  {feature}: "
                    f"n={stats['n']} min={stats['min']} "
                    f"median={stats['median']} max={stats['max']}"
                )

    print()
    print(f"MANIFEST={output}")
    print(f"MANIFEST_SHA256={digest}")
    print("SNAPSHOT_HASH_VERIFICATION=PASS")
    print("BLIND_REVIEW_LABELS_USED_AS_DESCRIPTIVE_ONLY=TRUE")
    print("OUTCOME_OR_PNL_COMPUTED=NO")
    print("ENGINEERING_METRICS_ARE_NOT_BROOKS_RULES=TRUE")
    print("PRODUCTION_THRESHOLD_SELECTED=NO")
    print("CURRENT_PRODUCTION_RULES_MODIFIED=NO")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_CONTEXT_MATURITY_PULLBACK_QUALITY=PASS")


def _parse_args():
    parser = argparse.ArgumentParser(description="Legacy Phase 8.13 diagnostic")
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--composite-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    VISUAL_MANIFEST = args.visual_manifest.resolve()
    COMPOSITE_MANIFEST = args.composite_manifest.resolve()
    OUT = args.output_dir.resolve()
    asyncio.run(main())
