"""Phase 8.6 diagnostic-only candidate audit.

Purpose:
- replay the exact BTCUSDT 15m historical horizon used in Phase 8
- compare localized EH-006 diagnostic scopes (LAST_2/LAST_3/LAST_5)
- extract the union of H2/L2 candidates
- render historical charts ending exactly at each candidate signal bar
- write a deterministic JSON audit manifest

Safety:
- NO database writes
- NO Telegram publishing
- NO PAPER runtime
- NO orders
- NO production engine/rule modification
- localized guard scopes are engineering diagnostics, not Brooks-authored rules
- entry/SL/TP shown on charts are the existing engineering geometry, historical only
"""

from __future__ import annotations

import asyncio
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
from app.modules.charting.matplotlib_renderer import MatplotlibSignalChartRenderer
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.shadow_replay.historical import BinanceHistoricalCandleSource


END_AT = datetime.fromisoformat("2026-09-02T10:45:00+00:00")
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
SOURCE_CANDLES = 500
SNAPSHOT_WINDOW = 100
MARKET_TYPE = "spot"
EXCHANGE = "binance"

VARIANTS: dict[str, int] = {
    "LAST_2_BARS": 2,
    "LAST_3_BARS": 3,
    "LAST_5_BARS": 5,
}


@dataclass(frozen=True, slots=True)
class CandidateDetection:
    variant: str
    scope_bars: int
    direction: str
    setup_type: str
    countertrend_legs: int
    start_index: int
    signal_index: int


@dataclass(frozen=True, slots=True)
class CandidateAuditRow:
    candidate_id: str
    captured_at: str
    snapshot_id: str
    snapshot_hash: str
    structure: str
    direction: str
    setup_type: str
    countertrend_legs: int
    pullback_start_index: int
    signal_index: int
    variants: tuple[str, ...]
    entry_price: str
    stop_loss: str
    targets: tuple[str, ...]
    signal_open: str
    signal_high: str
    signal_low: str
    signal_close: str
    chart_file: str
    source_basis_pages: tuple[int, ...]
    diagnostic_note: str


@dataclass(frozen=True, slots=True)
class DetectionResult:
    classification: str
    countertrend_legs: int
    start_index: int
    signal_index: int | None


def detect_with_guard_scope(
    candles: tuple[Candle, ...],
    *,
    trend_direction: str,
    start_index: int,
    guard_scope_bars: int,
) -> DetectionResult:
    """Use the existing state-machine semantics, changing only guard scan scope."""
    if trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        return DetectionResult("UNRESOLVED", 0, start_index, None)
    if start_index < 0 or start_index >= len(candles) - 1:
        return DetectionResult("INVALID_START", 0, start_index, None)
    if guard_scope_bars < 2:
        raise ValueError("guard_scope_bars must be at least 2")

    full_window = candles[start_index:]
    relative_guard_start = max(0, len(full_window) - guard_scope_bars)
    guard_window = full_window[relative_guard_start:]

    guard = assess_h1_h2_l1_l2_counting_window(guard_window)
    if not guard.allowed:
        return DetectionResult("BLOCKED", 0, start_index, None)

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
                return DetectionResult(
                    "H2" if trend_direction == "BULL_TREND" else "L2",
                    countertrend_legs,
                    start_index,
                    i,
                )
            in_countertrend_leg = False

    return DetectionResult("NO_SETUP", countertrend_legs, start_index, None)


def engineering_levels(
    *,
    snapshot: MarketSnapshot,
    signal_index: int,
    direction: str,
    start_index: int,
    policy: FundamentalsExecutionPolicy,
) -> tuple[Decimal, Decimal, tuple[Decimal, ...]]:
    """Historical visualization only; mirrors existing Phase 7C engineering geometry."""
    signal = snapshot.candles[signal_index]
    signal_range = signal.high - signal.low
    stop_buffer = signal_range * policy.stop_buffer_fraction_of_signal_range

    if direction == "LONG":
        entry = signal.high * (Decimal("1") + policy.entry_buffer_fraction)
        structural_low = min(
            c.low for c in snapshot.candles[start_index : signal_index + 1]
        )
        stop = structural_low - stop_buffer
        risk = entry - stop
        if risk <= 0:
            raise ValueError("invalid historical LONG engineering geometry")
        targets = tuple(
            entry + risk * multiple for multiple in policy.target_r_multiples
        )
        return entry, stop, targets

    entry = signal.low * (Decimal("1") - policy.entry_buffer_fraction)
    structural_high = max(
        c.high for c in snapshot.candles[start_index : signal_index + 1]
    )
    stop = structural_high + stop_buffer
    risk = stop - entry
    if risk <= 0:
        raise ValueError("invalid historical SHORT engineering geometry")
    targets = tuple(
        entry - risk * multiple for multiple in policy.target_r_multiples
    )
    return entry, stop, targets


def candidate_id(
    *,
    captured_at: str,
    direction: str,
    setup_type: str,
    snapshot_hash: str,
) -> str:
    payload = "|".join(
        ("PHASE8_CANDIDATE_AUDIT_V1", captured_at, direction, setup_type, snapshot_hash)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


async def main() -> None:
    output_dir = Path("/out")
    charts_dir = output_dir / "candidate_charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("candidate audit refuses enabled autonomous trade decisions")

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

    renderer = MatplotlibSignalChartRenderer(dpi=140, max_candles=100)

    # Keyed by deterministic snapshot hash + setup direction.
    candidates: dict[tuple[str, str], dict[str, object]] = {}
    variant_counts = {name: {"H2": 0, "L2": 0} for name in VARIANTS}

    for end_index in range(SNAPSHOT_WINDOW - 1, len(candles)):
        window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]

        snapshot = MarketSnapshot(
            exchange=EXCHANGE,
            market_type=MARKET_TYPE,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            candles=window,
            captured_at=window[-1].close_time,
            source="PHASE8_CANDIDATE_AUDIT",
        )

        # Hard no-lookahead invariants.
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

        wanted_kind = "HIGH" if structure.direction == "BULL_TREND" else "LOW"
        candidate_swings = [s for s in scan.swings if s.kind == wanted_kind]
        if not candidate_swings:
            continue

        start_index = candidate_swings[-1].candle_index
        if len(snapshot.candles) - start_index > policy.pullback_window_bars:
            start_index = len(snapshot.candles) - policy.pullback_window_bars

        for variant, scope in VARIANTS.items():
            result = detect_with_guard_scope(
                snapshot.candles,
                trend_direction=structure.direction,
                start_index=start_index,
                guard_scope_bars=scope,
            )

            if result.classification not in {"H2", "L2"}:
                continue

            variant_counts[variant][result.classification] += 1

            assert result.signal_index == len(snapshot.candles) - 1

            direction = "LONG" if result.classification == "H2" else "SHORT"
            setup_type = "H2_CONFIRMED" if direction == "LONG" else "L2_CONFIRMED"
            key = (snapshot.snapshot_hash, direction)

            existing = candidates.get(key)
            if existing is None:
                candidates[key] = {
                    "snapshot": snapshot,
                    "structure": structure.direction,
                    "direction": direction,
                    "setup_type": setup_type,
                    "legs": result.countertrend_legs,
                    "start_index": result.start_index,
                    "signal_index": result.signal_index,
                    "variants": {variant},
                }
            else:
                existing["variants"].add(variant)  # type: ignore[union-attr]

    rows: list[CandidateAuditRow] = []

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            item["snapshot"].captured_at,  # type: ignore[union-attr]
            item["direction"],
        ),
    )

    for item in ordered:
        snapshot: MarketSnapshot = item["snapshot"]  # type: ignore[assignment]
        direction: str = item["direction"]  # type: ignore[assignment]
        setup_type: str = item["setup_type"]  # type: ignore[assignment]
        start_index: int = item["start_index"]  # type: ignore[assignment]
        signal_index: int = item["signal_index"]  # type: ignore[assignment]
        legs: int = item["legs"]  # type: ignore[assignment]
        variants = tuple(sorted(item["variants"]))  # type: ignore[arg-type]

        entry, stop, targets = engineering_levels(
            snapshot=snapshot,
            signal_index=signal_index,
            direction=direction,
            start_index=start_index,
            policy=policy,
        )

        cid = candidate_id(
            captured_at=snapshot.captured_at.isoformat(),
            direction=direction,
            setup_type=setup_type,
            snapshot_hash=snapshot.snapshot_hash,
        )

        chart_name = (
            f"{snapshot.captured_at.strftime('%Y%m%dT%H%M%S')}_"
            f"{setup_type}_{cid}.png"
        )
        chart_path = charts_dir / chart_name

        renderer.render(
            snapshot=snapshot,
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            targets=targets,
            setup_type=f"{setup_type} DIAGNOSTIC",
            output_path=chart_path,
        )

        signal = snapshot.candles[signal_index]

        rows.append(
            CandidateAuditRow(
                candidate_id=cid,
                captured_at=snapshot.captured_at.isoformat(),
                snapshot_id=snapshot.snapshot_id,
                snapshot_hash=snapshot.snapshot_hash,
                structure=str(item["structure"]),
                direction=direction,
                setup_type=setup_type,
                countertrend_legs=legs,
                pullback_start_index=start_index,
                signal_index=signal_index,
                variants=variants,
                entry_price=str(entry),
                stop_loss=str(stop),
                targets=tuple(str(x) for x in targets),
                signal_open=str(signal.open),
                signal_high=str(signal.high),
                signal_low=str(signal.low),
                signal_close=str(signal.close),
                chart_file=f"candidate_charts/{chart_name}",
                source_basis_pages=(11,) if direction == "LONG" else (12,),
                diagnostic_note=(
                    "Localized EH-006 guard scope is an engineering A/B diagnostic, "
                    "not a Brooks-authored rule. Entry/SL/TP are historical "
                    "engineering visualization only."
                ),
            )
        )

    overlap_counts = {
        "ALL_2_3_5": sum(
            1
            for row in rows
            if set(row.variants)
            == {"LAST_2_BARS", "LAST_3_BARS", "LAST_5_BARS"}
        ),
        "LAST_2_AND_3": sum(
            1
            for row in rows
            if {"LAST_2_BARS", "LAST_3_BARS"}.issubset(set(row.variants))
        ),
        "LAST_2_ONLY": sum(
            1 for row in rows if row.variants == ("LAST_2_BARS",)
        ),
    }

    manifest = {
        "phase": "8.6",
        "mode": "DIAGNOSTIC_ONLY",
        "exchange": EXCHANGE,
        "market_type": MARKET_TYPE,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "end_at": END_AT.isoformat(),
        "source_candles": SOURCE_CANDLES,
        "snapshot_window": SNAPSHOT_WINDOW,
        "policy_configuration_version": policy.configuration_version,
        "autonomous_trade_decisions": False,
        "guard_variants": VARIANTS,
        "variant_detection_counts": variant_counts,
        "unique_candidate_count": len(rows),
        "overlap_counts": overlap_counts,
        "candidates": [asdict(row) for row in rows],
    }

    manifest_path = output_dir / "phase8_candidate_audit.json"
    manifest_json = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    manifest_path.write_text(manifest_json + "\n", encoding="utf-8")

    digest = hashlib.sha256((manifest_json + "\n").encode("utf-8")).hexdigest()

    print("===== PHASE8.6 CANDIDATE AUDIT =====")
    print(f"UNIQUE_CANDIDATES={len(rows)}")
    for variant in VARIANTS:
        counts = variant_counts[variant]
        print(
            f"{variant}: H2={counts['H2']} L2={counts['L2']} "
            f"TOTAL={counts['H2'] + counts['L2']}"
        )
    print(f"OVERLAP_COUNTS={overlap_counts}")
    print(f"MANIFEST={manifest_path}")
    print(f"MANIFEST_SHA256={digest}")
    print(f"CHARTS_DIR={charts_dir}")

    print()
    print("CANDIDATES")
    for row in rows:
        print(
            f"{row.candidate_id} "
            f"{row.captured_at} "
            f"{row.setup_type} "
            f"legs={row.countertrend_legs} "
            f"variants={','.join(row.variants)} "
            f"chart={row.chart_file}"
        )

    # Baseline expectations from Phase 8.5.
    assert variant_counts["LAST_2_BARS"] == {"H2": 5, "L2": 2}
    assert variant_counts["LAST_3_BARS"] == {"H2": 4, "L2": 2}
    assert variant_counts["LAST_5_BARS"] == {"H2": 2, "L2": 1}

    assert all(row.signal_index == SNAPSHOT_WINDOW - 1 for row in rows)
    assert all(Path("/out", row.chart_file).is_file() for row in rows)

    print()
    print("CURRENT_PRODUCTION_GUARD_MODIFIED=NO")
    print("AUTONOMOUS_TRADE_DECISIONS=FALSE")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_CANDIDATE_AUDIT=PASS")


if __name__ == "__main__":
    asyncio.run(main())
