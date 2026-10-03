"""Phase 8.17 — Regime Transition & V-Reversal Diagnostic.

DIAGNOSTIC ONLY.
No production rule changes. No outcomes, P&L, or win rate.

Purpose
-------
Investigate the visual failure modes seen in the second blind holdout:
- violent reversal / V-recovery
- late regime flip
- post-impulse trading range / compression
- immature continuation after a fresh breakout

Inputs
------
/labels/phase8_15_blind_review_labels.json
/mapping/phase8_14_mapping_manifest.json

The blind labels were locked before the mapping was revealed. They are descriptive
human review judgments only; they are NOT market outcomes or ground truth.

This phase intentionally DOES NOT select a production threshold.

Source-grounded concepts from the reviewed Brooks fundamentals PDF:
- trend vs trading range
- context / bars to the left matter
- HH/HL and LH/LL structure
- context and momentum matter
- EMA20 is secondary context

Engineering-only measurements in this script:
- old20 vs recent20 direction-adjusted displacement
- four causal 10-bar displacement signs and sign-flip count
- close-path efficiency
- largest recent bar-range shock relative to median recent range
- shock body direction and post-shock recovery direction
- recent range/compression ratios
- directional close location within 40-bar range
- rolling-40 structure current run and bars since opposite resolved structure

None of these numeric measurements are Brooks-authored thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import median

from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.brooks_core.fundamentals_policy import FundamentalsExecutionPolicy
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.shadow_replay.historical import BinanceHistoricalCandleSource

LABELS_PATH: Path | None = None
MAPPING_PATH: Path | None = None
OUT: Path | None = None

EXCHANGE = "binance"
MARKET_TYPE = "spot"
SNAPSHOT_WINDOW = 100


@dataclass(frozen=True, slots=True)
class SegmentEvidence:
    bars: int
    adjusted_displacement: Decimal
    close_path_efficiency: Decimal
    direction_class: str


@dataclass(frozen=True, slots=True)
class ShockEvidence:
    largest_range_ratio_vs_median40: Decimal
    shock_offset_from_signal_bars: int
    shock_body_relation: str
    post_shock_adjusted_displacement: Decimal
    post_shock_direction_class: str


@dataclass(frozen=True, slots=True)
class RangeCompressionEvidence:
    recent10_range_vs_previous20_range: Decimal
    recent10_median_bar_range_vs_previous20: Decimal
    recent10_close_path_efficiency: Decimal
    body_sign_flip_fraction_recent20: Decimal
    directional_close_location_in_40bar_range: Decimal


@dataclass(frozen=True, slots=True)
class StructureTransitionEvidence:
    r40_current_run_bars_recomputed: int
    bars_since_last_opposite_resolved_r40_state: int | None
    bars_since_last_ambiguous_r40_state: int | None
    r40_resolved_flip_count_last40_recomputed: int


@dataclass(frozen=True, slots=True)
class CandidateDiagnostic:
    blind_id: str
    review_label: str
    symbol: str
    timeframe: str
    captured_at: str
    setup_type: str
    direction: str
    candidate_structure: str
    countertrend_legs: int
    survives_last3: bool
    r40_alignment_stratum: str
    r40_alignment: Decimal
    r40_current_run_from_mapping: int
    snapshot_hash_verified: bool
    old20: SegmentEvidence
    recent20: SegmentEvidence
    transition_class: str
    ten_bar_sequence: tuple[str, str, str, str]
    ten_bar_adjusted_displacements: tuple[Decimal, Decimal, Decimal, Decimal]
    ten_bar_sign_flip_count: int
    shock: ShockEvidence
    range_compression: RangeCompressionEvidence
    structure_transition: StructureTransitionEvidence


def q(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def med(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        return Decimal("0")
    return q(median(values))


def direction_class(value: Decimal) -> str:
    if value > 0:
        return "ALIGNED"
    if value < 0:
        return "OPPOSITE"
    return "NEUTRAL"


def segment_evidence(
    candles: tuple[Candle, ...],
    *,
    candidate_structure: str,
) -> SegmentEvidence:
    if len(candles) < 2:
        raise ValueError("segment requires >= 2 candles")

    high = max(c.high for c in candles)
    low = min(c.low for c in candles)
    total_range = high - low
    net = candles[-1].close - candles[0].close

    signed = Decimal("0") if total_range == 0 else net / total_range
    adjusted = signed if candidate_structure == "BULL_TREND" else -signed

    path = sum(
        abs(current.close - previous.close)
        for previous, current in zip(candles, candles[1:], strict=False)
    )
    efficiency = Decimal("0") if path == 0 else abs(net) / path

    return SegmentEvidence(
        bars=len(candles),
        adjusted_displacement=q(adjusted),
        close_path_efficiency=q(efficiency),
        direction_class=direction_class(adjusted),
    )


def transition_class(old20: SegmentEvidence, recent20: SegmentEvidence) -> str:
    return f"OLD_{old20.direction_class}__RECENT_{recent20.direction_class}"


def ten_bar_sequence(
    last40: tuple[Candle, ...],
    *,
    candidate_structure: str,
) -> tuple[
    tuple[str, str, str, str],
    tuple[Decimal, Decimal, Decimal, Decimal],
    int,
]:
    if len(last40) != 40:
        raise ValueError("last40 must contain exactly 40 candles")

    chunks = tuple(last40[i : i + 10] for i in (0, 10, 20, 30))
    evidences = tuple(
        segment_evidence(chunk, candidate_structure=candidate_structure) for chunk in chunks
    )
    classes = tuple(e.direction_class for e in evidences)
    values = tuple(e.adjusted_displacement for e in evidences)

    resolved = [c for c in classes if c != "NEUTRAL"]
    flips = sum(1 for a, b in zip(resolved, resolved[1:], strict=False) if a != b)

    return classes, values, flips


def body_relation(candle: Candle, candidate_structure: str) -> str:
    if candle.close == candle.open:
        return "DOJI"
    bullish = candle.close > candle.open
    aligned = (candidate_structure == "BULL_TREND" and bullish) or (
        candidate_structure == "BEAR_TREND" and not bullish
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
    offset = (len(last40) - 1) - shock_index

    post = last40[shock_index:]
    if len(post) >= 2:
        post_ev = segment_evidence(
            post,
            candidate_structure=candidate_structure,
        )
        post_disp = post_ev.adjusted_displacement
        post_class = post_ev.direction_class
    else:
        post_disp = Decimal("0")
        post_class = "NEUTRAL"

    return ShockEvidence(
        largest_range_ratio_vs_median40=q(ratio),
        shock_offset_from_signal_bars=offset,
        shock_body_relation=body_relation(shock, candidate_structure),
        post_shock_adjusted_displacement=q(post_disp),
        post_shock_direction_class=post_class,
    )


def range_compression_evidence(
    last40: tuple[Candle, ...],
    *,
    candidate_structure: str,
) -> RangeCompressionEvidence:
    previous20 = last40[10:30]
    recent10 = last40[30:40]
    recent20 = last40[20:40]

    prev20_range = max(c.high for c in previous20) - min(c.low for c in previous20)
    rec10_range = max(c.high for c in recent10) - min(c.low for c in recent10)
    range_ratio = Decimal("0") if prev20_range == 0 else rec10_range / prev20_range

    prev20_med_bar = med(tuple(c.high - c.low for c in previous20))
    rec10_med_bar = med(tuple(c.high - c.low for c in recent10))
    med_ratio = Decimal("0") if prev20_med_bar == 0 else rec10_med_bar / prev20_med_bar

    rec10_eff = segment_evidence(
        recent10,
        candidate_structure=candidate_structure,
    ).close_path_efficiency

    signs = []
    for c in recent20:
        if c.close > c.open:
            signs.append(1)
        elif c.close < c.open:
            signs.append(-1)
        else:
            signs.append(0)
    nonzero = [s for s in signs if s != 0]
    if len(nonzero) < 2:
        flip_fraction = Decimal("0")
    else:
        flips = sum(1 for a, b in zip(nonzero, nonzero[1:], strict=False) if a != b)
        flip_fraction = Decimal(flips) / Decimal(len(nonzero) - 1)

    high40 = max(c.high for c in last40)
    low40 = min(c.low for c in last40)
    width40 = high40 - low40
    signal_close = last40[-1].close
    if width40 == 0:
        directional_location = Decimal("0.5")
    elif candidate_structure == "BULL_TREND":
        directional_location = (signal_close - low40) / width40
    else:
        directional_location = (high40 - signal_close) / width40

    return RangeCompressionEvidence(
        recent10_range_vs_previous20_range=q(range_ratio),
        recent10_median_bar_range_vs_previous20=q(med_ratio),
        recent10_close_path_efficiency=q(rec10_eff),
        body_sign_flip_fraction_recent20=q(flip_fraction),
        directional_close_location_in_40bar_range=q(directional_location),
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


def bars_since_last(
    states: tuple[str, ...],
    predicate,
) -> int | None:
    for offset, state in enumerate(reversed(states)):
        if predicate(state):
            return offset
    return None


def structure_transition_evidence(
    candles: tuple[Candle, ...],
    *,
    candidate_structure: str,
    policy: FundamentalsExecutionPolicy,
) -> StructureTransitionEvidence:
    states = rolling40_states(candles, policy=policy)

    run = 0
    for state in reversed(states):
        if state != candidate_structure:
            break
        run += 1

    opposite = "BEAR_TREND" if candidate_structure == "BULL_TREND" else "BULL_TREND"

    recent40 = states[-40:]
    resolved = [s for s in recent40 if s in {"BULL_TREND", "BEAR_TREND"}]
    flips = sum(1 for a, b in zip(resolved, resolved[1:], strict=False) if a != b)

    return StructureTransitionEvidence(
        r40_current_run_bars_recomputed=run,
        bars_since_last_opposite_resolved_r40_state=bars_since_last(
            states,
            lambda state: state == opposite,
        ),
        bars_since_last_ambiguous_r40_state=bars_since_last(
            states,
            lambda state: state == "AMBIGUOUS",
        ),
        r40_resolved_flip_count_last40_recomputed=flips,
    )


def feature_summary(rows: list[CandidateDiagnostic]) -> dict:
    if not rows:
        return {"count": 0}

    extractors = {
        "r40_alignment": lambda r: r.r40_alignment,
        "r40_current_run": lambda r: Decimal(r.r40_current_run_from_mapping),
        "old20_adjusted_displacement": lambda r: r.old20.adjusted_displacement,
        "old20_efficiency": lambda r: r.old20.close_path_efficiency,
        "recent20_adjusted_displacement": lambda r: r.recent20.adjusted_displacement,
        "recent20_efficiency": lambda r: r.recent20.close_path_efficiency,
        "ten_bar_sign_flip_count": lambda r: Decimal(r.ten_bar_sign_flip_count),
        "shock_range_ratio": lambda r: r.shock.largest_range_ratio_vs_median40,
        "shock_offset": lambda r: Decimal(r.shock.shock_offset_from_signal_bars),
        "post_shock_adjusted_displacement": lambda r: r.shock.post_shock_adjusted_displacement,
        "recent10_range_vs_previous20": lambda r: (
            r.range_compression.recent10_range_vs_previous20_range
        ),
        "recent10_median_bar_range_ratio": lambda r: (
            r.range_compression.recent10_median_bar_range_vs_previous20
        ),
        "recent10_efficiency": lambda r: r.range_compression.recent10_close_path_efficiency,
        "body_sign_flip_fraction_recent20": lambda r: (
            r.range_compression.body_sign_flip_fraction_recent20
        ),
        "directional_close_location_40": lambda r: (
            r.range_compression.directional_close_location_in_40bar_range
        ),
    }

    features = {}
    for name, fn in extractors.items():
        values = [Decimal(fn(row)) for row in rows]
        features[name] = {
            "min": str(q(min(values))),
            "median": str(q(median(values))),
            "max": str(q(max(values))),
        }

    return {
        "count": len(rows),
        "transition_classes": dict(sorted(Counter(r.transition_class for r in rows).items())),
        "shock_body_relations": dict(
            sorted(Counter(r.shock.shock_body_relation for r in rows).items())
        ),
        "post_shock_direction_classes": dict(
            sorted(Counter(r.shock.post_shock_direction_class for r in rows).items())
        ),
        "ten_bar_sequences": dict(
            sorted(Counter(">".join(r.ten_bar_sequence) for r in rows).items())
        ),
        "features": features,
    }


async def main() -> None:
    if LABELS_PATH is None or MAPPING_PATH is None or OUT is None:
        raise RuntimeError("explicit --labels, --mapping and --output-dir are required")
    if not LABELS_PATH.is_file():
        raise FileNotFoundError(LABELS_PATH)
    if not MAPPING_PATH.is_file():
        raise FileNotFoundError(MAPPING_PATH)

    labels_manifest = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    mapping_manifest = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))

    if labels_manifest.get("mapping_seen") is not False:
        raise RuntimeError("blind-label lock does not assert mapping_seen=false")

    label_lookup = {item["blind_id"]: item["label"] for item in labels_manifest["items"]}
    mapping_items = mapping_manifest["items"]
    mapping_ids = {item["blind_id"] for item in mapping_items}

    if set(label_lookup) != mapping_ids:
        raise RuntimeError(
            f"blind/mapping id mismatch: "
            f"labels_only={sorted(set(label_lookup) - mapping_ids)} "
            f"mapping_only={sorted(mapping_ids - set(label_lookup))}"
        )

    if len(mapping_items) != 24:
        raise RuntimeError(f"expected 24 mapping items, got {len(mapping_items)}")

    end_at = datetime.fromisoformat(mapping_manifest["second_holdout"]["end_at"])
    source_candles = int(mapping_manifest["second_holdout"]["source_candles_per_dataset"])

    grouped = defaultdict(list)
    for item in mapping_items:
        grouped[(item["symbol"], item["timeframe"])].append(item)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.17 refuses enabled autonomous trade decisions")

    source = BinanceHistoricalCandleSource()
    diagnostics: list[CandidateDiagnostic] = []

    try:
        for symbol, timeframe in sorted(grouped):
            candles = await source.get_closed_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=source_candles,
                market_type=MARKET_TYPE,
                end_at=end_at,
            )
            by_close = {c.close_time.isoformat(): i for i, c in enumerate(candles)}

            for item in grouped[(symbol, timeframe)]:
                captured_at = item["captured_at"]
                if captured_at not in by_close:
                    raise RuntimeError(f"cannot relocate {symbol} {timeframe} {captured_at}")

                end_index = by_close[captured_at]
                if end_index < SNAPSHOT_WINDOW - 1:
                    raise RuntimeError("candidate lacks 100-bar snapshot")

                window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

                snapshot = MarketSnapshot(
                    exchange=EXCHANGE,
                    market_type=MARKET_TYPE,
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=window,
                    captured_at=window[-1].close_time,
                    source="PHASE8_REGIME_TRANSITION_DIAGNOSTIC",
                )

                if snapshot.snapshot_hash != item["snapshot_hash"]:
                    raise RuntimeError(f"snapshot hash drift {item['blind_id']}")
                if snapshot.captured_at.isoformat() != captured_at:
                    raise RuntimeError(f"captured_at drift {item['blind_id']}")
                assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)

                signal_index = int(item["signal_index"])
                if signal_index != len(snapshot.candles) - 1:
                    raise RuntimeError(
                        f"expected candidate on final causal bar: {item['blind_id']}"
                    )

                candidate_structure = item["candidate_structure"]
                last40 = snapshot.candles[signal_index - 39 : signal_index + 1]
                old20_candles = last40[:20]
                recent20_candles = last40[20:]

                old20 = segment_evidence(
                    old20_candles,
                    candidate_structure=candidate_structure,
                )
                recent20 = segment_evidence(
                    recent20_candles,
                    candidate_structure=candidate_structure,
                )

                seq, seq_values, seq_flips = ten_bar_sequence(
                    last40,
                    candidate_structure=candidate_structure,
                )

                maturity = item["maturity"]
                structure_transition = structure_transition_evidence(
                    snapshot.candles,
                    candidate_structure=candidate_structure,
                    policy=policy,
                )

                # Verify recomputed R40 current-run semantics against Phase 8.14.
                if structure_transition.r40_current_run_bars_recomputed != int(
                    maturity["r40_current_run_bars"]
                ):
                    raise RuntimeError(
                        f"R40 current-run drift {item['blind_id']}: "
                        f"{structure_transition.r40_current_run_bars_recomputed} "
                        f"!= {maturity['r40_current_run_bars']}"
                    )

                diagnostics.append(
                    CandidateDiagnostic(
                        blind_id=item["blind_id"],
                        review_label=label_lookup[item["blind_id"]],
                        symbol=symbol,
                        timeframe=timeframe,
                        captured_at=captured_at,
                        setup_type=item["setup_type"],
                        direction=item["direction"],
                        candidate_structure=candidate_structure,
                        countertrend_legs=int(item["countertrend_legs"]),
                        survives_last3=bool(item["survives_last3"]),
                        r40_alignment_stratum=maturity["alignment_stratum"],
                        r40_alignment=q(maturity["r40_alignment_last20"]),
                        r40_current_run_from_mapping=int(maturity["r40_current_run_bars"]),
                        snapshot_hash_verified=True,
                        old20=old20,
                        recent20=recent20,
                        transition_class=transition_class(old20, recent20),
                        ten_bar_sequence=seq,
                        ten_bar_adjusted_displacements=seq_values,
                        ten_bar_sign_flip_count=seq_flips,
                        shock=shock_evidence(
                            last40,
                            candidate_structure=candidate_structure,
                        ),
                        range_compression=range_compression_evidence(
                            last40,
                            candidate_structure=candidate_structure,
                        ),
                        structure_transition=structure_transition,
                    )
                )
    finally:
        await source.aclose()

    diagnostics = sorted(diagnostics, key=lambda r: r.blind_id)

    label_counts = Counter(r.review_label for r in diagnostics)
    by_label = defaultdict(list)
    for row in diagnostics:
        by_label[row.review_label].append(row)

    cross_transition = defaultdict(Counter)
    for row in diagnostics:
        cross_transition[row.transition_class][row.review_label] += 1

    cross_stratum = defaultdict(Counter)
    for row in diagnostics:
        cross_stratum[row.r40_alignment_stratum][row.review_label] += 1

    manifest = {
        "phase": "8.17",
        "mode": "REGIME_TRANSITION_V_REVERSAL_DIAGNOSTIC_ONLY",
        "blind_labels_sha256": hashlib.sha256(LABELS_PATH.read_bytes()).hexdigest(),
        "mapping_manifest_sha256": hashlib.sha256(MAPPING_PATH.read_bytes()).hexdigest(),
        "review_item_count": len(diagnostics),
        "review_label_counts": dict(sorted(label_counts.items())),
        "transition_class_by_review_label": {
            key: dict(sorted(value.items())) for key, value in sorted(cross_transition.items())
        },
        "r40_stratum_by_review_label": {
            key: dict(sorted(value.items())) for key, value in sorted(cross_stratum.items())
        },
        "label_summary": {
            label: feature_summary(by_label[label]) for label in ("KEEP", "UNCERTAIN", "REJECT")
        },
        "candidates": [asdict(row) for row in diagnostics],
        "interpretation_constraints": [
            "Blind labels are descriptive visual judgments, not outcomes.",
            "No feature threshold is selected in Phase 8.17.",
            "No feature is a Brooks-authored numeric rule.",
            "Small sample; findings require another unseen validation before policy use.",
        ],
        "safety": {
            "production_rules_modified": False,
            "production_threshold_selected": False,
            "outcomes_used": False,
            "outcome_or_pnl_computed": False,
            "database_writes": False,
            "telegram_publish": False,
            "paper_runtime_used": False,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=str,
        )
        + "\n"
    )

    output = OUT / "phase8_regime_transition_diagnostic.json"
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    print("===== PHASE8.17 REGIME TRANSITION & V-REVERSAL DIAGNOSTIC =====")
    print(f"REVIEW_ITEMS={len(diagnostics)}")
    print(f"REVIEW_LABEL_COUNTS={dict(sorted(label_counts.items()))}")
    print()

    print("TRANSITION_CLASS_BY_LABEL")
    for key in sorted(cross_transition):
        print(key, dict(sorted(cross_transition[key].items())))

    print()
    print("R40_STRATUM_BY_LABEL")
    for key in sorted(cross_stratum):
        print(key, dict(sorted(cross_stratum[key].items())))

    print()
    print("CANDIDATE_MATRIX")
    for row in diagnostics:
        rc = row.range_compression
        st = row.structure_transition
        print(
            f"{row.blind_id} {row.review_label} "
            f"{row.symbol} {row.timeframe} {row.setup_type} "
            f"STRATUM={row.r40_alignment_stratum} "
            f"R40_ALIGN={row.r40_alignment} "
            f"R40_RUN={row.r40_current_run_from_mapping} "
            f"LAST3={row.survives_last3} "
            f"LEGS={row.countertrend_legs} "
            f"TRANSITION={row.transition_class} "
            f"OLD20_DISP={row.old20.adjusted_displacement} "
            f"OLD20_EFF={row.old20.close_path_efficiency} "
            f"REC20_DISP={row.recent20.adjusted_displacement} "
            f"REC20_EFF={row.recent20.close_path_efficiency} "
            f"SEQ={'>'.join(row.ten_bar_sequence)} "
            f"SEQ_FLIPS={row.ten_bar_sign_flip_count} "
            f"SHOCK_RATIO={row.shock.largest_range_ratio_vs_median40} "
            f"SHOCK_OFFSET={row.shock.shock_offset_from_signal_bars} "
            f"SHOCK_BODY={row.shock.shock_body_relation} "
            f"POST_SHOCK={row.shock.post_shock_adjusted_displacement} "
            f"REC10_RANGE_RATIO={rc.recent10_range_vs_previous20_range} "
            f"REC10_BAR_RATIO={rc.recent10_median_bar_range_vs_previous20} "
            f"REC10_EFF={rc.recent10_close_path_efficiency} "
            f"BODY_FLIP={rc.body_sign_flip_fraction_recent20} "
            f"CLOSE_LOC40={rc.directional_close_location_in_40bar_range} "
            f"SINCE_OPP_R40={st.bars_since_last_opposite_resolved_r40_state} "
            f"SINCE_AMBIG_R40={st.bars_since_last_ambiguous_r40_state}"
        )

    print()
    print("LABEL_SUMMARY")
    for label in ("KEEP", "UNCERTAIN", "REJECT"):
        summary = manifest["label_summary"][label]
        print(
            f"{label} count={summary['count']} "
            f"TRANSITIONS={summary.get('transition_classes', {})} "
            f"SHOCK_BODY={summary.get('shock_body_relations', {})}"
        )
        for feature, stats in summary.get("features", {}).items():
            print(f"  {feature}: min={stats['min']} median={stats['median']} max={stats['max']}")

    print()
    print(f"MANIFEST={output}")
    print(f"MANIFEST_SHA256={digest}")
    print("BLIND_LABEL_LOCK_VERIFIED=PASS")
    print("SNAPSHOT_HASH_VERIFICATION=PASS")
    print("R40_CURRENT_RUN_RECOMPUTE_VERIFICATION=PASS")
    print("OUTCOMES_USED=NO")
    print("OUTCOME_OR_PNL_COMPUTED=NO")
    print("ENGINEERING_METRICS_ARE_NOT_BROOKS_RULES=TRUE")
    print("PRODUCTION_THRESHOLD_SELECTED=NO")
    print("CURRENT_PRODUCTION_RULES_MODIFIED=NO")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_REGIME_TRANSITION_DIAGNOSTIC=PASS")


def _parse_args():
    parser = argparse.ArgumentParser(description="Legacy Phase 8.17 regime diagnostic")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    LABELS_PATH = args.labels.resolve()
    MAPPING_PATH = args.mapping.resolve()
    OUT = args.output_dir.resolve()
    asyncio.run(main())
