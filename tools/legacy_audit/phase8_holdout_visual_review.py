"""Phase 8.11 — Unseen Holdout Visual Review Pack.

DIAGNOSTIC ONLY.

Input:
    /input/phase8_holdout_composite_validation.json

Output:
    /out/phase8_holdout_visual_review_manifest.json
    /out/charts/*.png
    /out/SHA256SUMS.txt

Selection:
1) 3 deterministic COMPOSITE_V1_PASS candidates per dataset (12 total).
2) ALL candidates that are MULTIHORIZON_CONTINUATION_LIKE but fail LAST_3.
   Phase 8.10 aggregate suggests there should be 4 of these, but the script does
   not hard-code that count.

The deterministic sample is selected by SHA256("PHASE8.11|" + snapshot_hash), not
by chronology or visual appearance.

No production rule is modified. No P&L/outcome is computed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
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
from matplotlib.patches import Rectangle

INPUT: Path | None = None
OUT: Path | None = None
CHARTS: Path | None = None

EXCHANGE = "binance"
MARKET_TYPE = "spot"
SOURCE_CANDLES = 2000
SNAPSHOT_WINDOW = 100
HORIZONS = (20, 40, 80)


@dataclass(frozen=True, slots=True)
class ReviewItem:
    review_id: str
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
    structure: str
    pullback_start_index: int
    signal_index: int
    last2_recomputed: bool
    last3_recomputed: bool
    chart_file: str
    reviewer_label: str = "UNREVIEWED"
    reviewer_notes: str = ""


def deterministic_rank(snapshot_hash: str) -> str:
    return hashlib.sha256(f"PHASE8.11|{snapshot_hash}".encode()).hexdigest()


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


def render_chart(
    *,
    snapshot: MarketSnapshot,
    scan,
    structure: str,
    start_index: int,
    signal_index: int,
    item: dict,
    output_path: Path,
) -> None:
    candles = snapshot.candles
    xs = [mdates.date2num(c.open_time) for c in candles]
    width = ((xs[1] - xs[0]) * 0.65) if len(xs) > 1 else 0.004

    fig, ax = plt.subplots(figsize=(13, 7), dpi=140)

    for x, c in zip(xs, candles):
        bullish = c.close >= c.open
        ax.vlines(x, float(c.low), float(c.high), linewidth=0.8)
        lower = min(float(c.open), float(c.close))
        height = abs(float(c.close) - float(c.open))
        if height == 0:
            height = max(float(c.high - c.low) * 0.02, 1e-12)
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
            s=26,
            label="confirmed swing high",
        )
    if lows:
        ax.scatter(
            [xs[s.candle_index] for s in lows],
            [float(s.price) for s in lows],
            marker="^",
            s=26,
            label="confirmed swing low",
        )

    # Context boundaries inside the 100-bar snapshot.
    for horizon, linestyle in ((80, ":"), (40, "--"), (20, "-.")):
        idx = len(candles) - horizon
        ax.axvline(
            xs[idx],
            linestyle=linestyle,
            linewidth=0.8,
            label=f"{horizon}-bar context start",
        )

    ax.axvline(
        xs[start_index],
        linewidth=1.1,
        linestyle="--",
        label="pullback anchor/start",
    )
    ax.axvline(
        xs[signal_index],
        linewidth=1.3,
        linestyle="-",
        label="candidate signal bar",
    )

    group = item["_sample_group"]
    title = (
        f"{item['symbol']} {item['timeframe']} {item['setup_type']} | "
        f"{group}\n"
        f"structure={structure} | transition={item['transition']} | "
        f"LAST3={item['survives_last3']} | composite={item['composite_v1_pass']}"
    )
    ax.set_title(title)
    ax.set_ylabel("Price")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax.grid(True, alpha=0.2)
    ax.legend(loc="best", fontsize=7, ncol=2)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("chart output missing")


async def main() -> None:
    if INPUT is None or OUT is None or CHARTS is None:
        raise RuntimeError("explicit --input and --output-dir are required")
    if not INPUT.is_file():
        raise FileNotFoundError(INPUT)

    source_manifest = json.loads(INPUT.read_text(encoding="utf-8"))
    datasets = source_manifest["datasets"]
    end_at = datetime.fromisoformat(source_manifest["holdout"]["end_at"])

    selected: list[dict] = []

    for report in datasets:
        symbol = report["symbol"]
        timeframe = report["timeframe"]
        candidates = report["candidates"]

        passes = [c for c in candidates if c["composite_v1_pass"]]
        passes = sorted(passes, key=lambda c: deterministic_rank(c["snapshot_hash"]))
        for candidate in passes[:3]:
            item = dict(candidate)
            item["symbol"] = symbol
            item["timeframe"] = timeframe
            item["_sample_group"] = "COMPOSITE_PASS_HASH_SAMPLE"
            selected.append(item)

        excluded_mh = [
            c
            for c in candidates
            if (c["transition"] == "MULTIHORIZON_CONTINUATION_LIKE" and not c["survives_last3"])
        ]
        for candidate in excluded_mh:
            item = dict(candidate)
            item["symbol"] = symbol
            item["timeframe"] = timeframe
            item["_sample_group"] = "MH_CONTINUATION_EXCLUDED_BY_LAST3"
            selected.append(item)

    # De-duplicate in case future source manifests change.
    dedup = {}
    for item in selected:
        key = (item["symbol"], item["timeframe"], item["snapshot_hash"])
        # Prefer the special excluded-by-LAST3 group when applicable.
        if key not in dedup or item["_sample_group"] == "MH_CONTINUATION_EXCLUDED_BY_LAST3":
            dedup[key] = item
    selected = list(dedup.values())

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in selected:
        grouped[(item["symbol"], item["timeframe"])].append(item)

    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8.11 refuses enabled autonomous trade decisions")

    source = BinanceHistoricalCandleSource()
    review_items: list[ReviewItem] = []

    try:
        for symbol, timeframe in sorted(grouped):
            candles = await source.get_closed_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=SOURCE_CANDLES,
                market_type=MARKET_TYPE,
                end_at=end_at,
            )

            index_by_close = {candle.close_time.isoformat(): i for i, candle in enumerate(candles)}

            for item in sorted(
                grouped[(symbol, timeframe)],
                key=lambda x: x["captured_at"],
            ):
                captured_at = item["captured_at"]
                if captured_at not in index_by_close:
                    raise RuntimeError(
                        f"cannot locate candidate close time {symbol} {timeframe} {captured_at}"
                    )

                end_index = index_by_close[captured_at]
                if end_index < SNAPSHOT_WINDOW - 1:
                    raise RuntimeError("candidate lacks 100-bar history")

                window = candles[end_index - SNAPSHOT_WINDOW + 1 : end_index + 1]
                snapshot = MarketSnapshot(
                    exchange=EXCHANGE,
                    market_type=MARKET_TYPE,
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=window,
                    captured_at=window[-1].close_time,
                    source="PHASE8_HOLDOUT_VISUAL_REVIEW",
                )

                assert snapshot.captured_at.isoformat() == captured_at
                assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)

                scan = confirm_swings_causally(
                    snapshot.candles,
                    left_bars=policy.swing_left_bars,
                    right_bars=policy.swing_right_bars,
                )
                structure_obj = evaluate_br031_structure(scan)
                structure = structure_obj.direction
                if structure not in {"BULL_TREND", "BEAR_TREND"}:
                    raise RuntimeError("selected holdout candidate became ambiguous")

                wanted = "HIGH" if structure == "BULL_TREND" else "LOW"
                anchors = [s for s in scan.swings if s.kind == wanted]
                if not anchors:
                    raise RuntimeError("selected holdout candidate has no anchor")

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
                    raise RuntimeError("selected source candidate no longer passes LAST2")

                direction, setup_type, legs, signal_index = last2

                if direction != item["direction"] or setup_type != item["setup_type"]:
                    raise RuntimeError("candidate direction/setup drift")
                if bool(last3 is not None) != bool(item["survives_last3"]):
                    raise RuntimeError("LAST3 survival drift")

                review_id = hashlib.sha256(
                    ("PHASE8.11|" + symbol + "|" + timeframe + "|" + item["snapshot_hash"]).encode(
                        "utf-8"
                    )
                ).hexdigest()[:16]

                chart_name = (
                    f"{symbol}_{timeframe}_"
                    f"{snapshot.captured_at.strftime('%Y%m%dT%H%M%S')}_"
                    f"{setup_type}_{review_id}.png"
                )

                render_chart(
                    snapshot=snapshot,
                    scan=scan,
                    structure=structure,
                    start_index=start_index,
                    signal_index=signal_index,
                    item=item,
                    output_path=CHARTS / chart_name,
                )

                review_items.append(
                    ReviewItem(
                        review_id=review_id,
                        sample_group=item["_sample_group"],
                        symbol=symbol,
                        timeframe=timeframe,
                        captured_at=captured_at,
                        direction=direction,
                        setup_type=setup_type,
                        countertrend_legs=legs,
                        survives_last3=bool(last3 is not None),
                        transition=item["transition"],
                        composite_v1_pass=bool(item["composite_v1_pass"]),
                        structure=structure,
                        pullback_start_index=start_index,
                        signal_index=signal_index,
                        last2_recomputed=True,
                        last3_recomputed=bool(last3 is not None),
                        chart_file=f"charts/{chart_name}",
                    )
                )
    finally:
        await source.aclose()

    review_items = sorted(
        review_items,
        key=lambda r: (r.symbol, r.timeframe, r.captured_at, r.review_id),
    )

    counts = Counter(item.sample_group for item in review_items)
    manifest = {
        "phase": "8.11",
        "mode": "UNSEEN_HOLDOUT_VISUAL_REVIEW_PACK",
        "selection": {
            "composite_pass_per_dataset": 3,
            "composite_pass_selection": ("lowest SHA256(PHASE8.11|snapshot_hash), deterministic"),
            "include_all_multihorizon_continuation_excluded_by_last3": True,
            "selection_performed_without_outcomes": True,
        },
        "source_holdout_manifest_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "review_item_count": len(review_items),
        "sample_group_counts": dict(sorted(counts.items())),
        "items": [asdict(item) for item in review_items],
        "review_labels_allowed": ("KEEP", "REJECT", "UNCERTAIN"),
        "safety": {
            "production_rules_modified": False,
            "outcome_or_pnl_computed": False,
            "database_writes": False,
            "telegram_publish": False,
            "paper_runtime_used": False,
        },
    }

    payload = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    manifest_path = OUT / "phase8_holdout_visual_review_manifest.json"
    manifest_path.write_text(payload, encoding="utf-8")

    sums = []
    for file_path in [manifest_path, *sorted(CHARTS.glob("*.png"))]:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        sums.append(f"{digest}  {file_path.relative_to(OUT)}")
    sums_path = OUT / "SHA256SUMS.txt"
    sums_path.write_text("\n".join(sums) + "\n", encoding="utf-8")

    print("===== PHASE8.11 UNSEEN HOLDOUT VISUAL REVIEW PACK =====")
    print(f"REVIEW_ITEMS={len(review_items)}")
    print(f"SAMPLE_GROUP_COUNTS={dict(sorted(counts.items()))}")
    print(f"CHART_COUNT={len(list(CHARTS.glob('*.png')))}")
    print(f"MANIFEST={manifest_path}")
    print(f"SHA256SUMS={sums_path}")
    print()

    for item in review_items:
        print(
            f"{item.review_id} "
            f"{item.sample_group} "
            f"{item.symbol} {item.timeframe} "
            f"{item.captured_at} "
            f"{item.setup_type} "
            f"legs={item.countertrend_legs} "
            f"LAST3={item.survives_last3} "
            f"transition={item.transition} "
            f"chart={item.chart_file}"
        )

    print()
    print("SELECTION_USED_OUTCOMES=NO")
    print("OUTCOME_OR_PNL_COMPUTED=NO")
    print("COMPOSITE_V1_PRODUCTION_APPROVED=NO")
    print("CURRENT_PRODUCTION_RULES_MODIFIED=NO")
    print("DATABASE_WRITES=NONE")
    print("TELEGRAM_PUBLISH=NONE")
    print("PAPER_RUNTIME=UNUSED")
    print("NO_LOOKAHEAD_ASSERTIONS=PASS")
    print("PHASE8_HOLDOUT_VISUAL_REVIEW_PACK=PASS")


def _parse_args():
    parser = argparse.ArgumentParser(description="Legacy Phase 8.11 visual review pack")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    INPUT = args.input.resolve()
    OUT = args.output_dir.resolve()
    CHARTS = OUT / "charts"
    asyncio.run(main())
