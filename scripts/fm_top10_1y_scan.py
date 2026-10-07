#!/usr/bin/env python3
"""One-year FM scan on the top-ranked non-stable crypto futures universe."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from research_layer.fm_backtest.data import (
    load_15m_year,
    resample_30m,
    select_full_coverage_symbols,
)
from research_layer.fm_backtest.engine import FMPolicy, scan_fm
from research_layer.fm_backtest.report import summarize

# CoinMarketCap historical snapshot 2026-10-06, stablecoins removed.
# Candidates are kept in market-cap order and the first ten with complete
# Binance USD-M monthly 15m coverage for the full test year are selected.
RANKED_NON_STABLE_CANDIDATES = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "TRXUSDT",
    "ZECUSDT",
    "HYPEUSDT",
    "DOGEUSDT",
    "XMRUSDT",
    "LINKUSDT",
    "ADAUSDT",
    "XLMUSDT",
    "NEARUSDT",
    "BCHUSDT",
    "LTCUSDT",
)


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FM top-10 one-year scan")
    parser.add_argument("--start", type=_date, default=_date("2025-10-01"))
    parser.add_argument("--end", type=_date, default=_date("2026-10-01"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research_output/fm_top10_1y_v0_1"),
    )
    return parser


def _stream_payload(symbol: str, timeframe: str, result) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "setups": result.setups,
        "missed_destination_before_fill": result.missed_destination_before_fill,
        "invalidated_before_fill": result.invalidated_before_fill,
        "metrics": summarize(result.trades),
        "trades": [
            {
                "direction": trade.direction,
                "setup_time_ms": trade.setup_time_ms,
                "entry_time_ms": trade.entry_time_ms,
                "exit_time_ms": trade.exit_time_ms,
                "entry": str(trade.entry),
                "stop": str(trade.stop),
                "target": str(trade.target),
                "destination": str(trade.destination),
                "gross_r": trade.gross_r,
                "base_net_r": trade.base_net_r,
                "stress_net_r": trade.stress_net_r,
                "outcome": trade.outcome,
                "spike_bars": trade.spike_bars,
                "pullback_bars": trade.pullback_bars,
                "followthrough_bars": trade.followthrough_bars,
                "pullback_fraction": trade.pullback_fraction,
            }
            for trade in result.trades
        ],
    }


def _aggregate_streams(streams: list[dict[str, object]]) -> dict[str, object]:
    all_trades = []
    total_setups = 0
    missed = 0
    invalidated = 0
    for stream in streams:
        total_setups += int(stream["setups"])
        missed += int(stream["missed_destination_before_fill"])
        invalidated += int(stream["invalidated_before_fill"])
        all_trades.extend(stream["_trade_objects"])
    all_trades.sort(key=lambda trade: (trade.entry_time_ms, trade.direction))
    return {
        "setups": total_setups,
        "missed_destination_before_fill": missed,
        "invalidated_before_fill": invalidated,
        "metrics": summarize(tuple(all_trades)),
    }


def main() -> int:
    args = _parser().parse_args()
    if args.end <= args.start:
        raise ValueError("end must be after start")

    selected = select_full_coverage_symbols(
        ranked_candidates=RANKED_NON_STABLE_CANDIDATES,
        start=args.start,
        end=args.end,
        count=10,
    )
    print(f"FM_SELECTED_SYMBOLS {','.join(selected)}", flush=True)

    policy = FMPolicy()
    public_streams: list[dict[str, object]] = []
    internal_streams: list[dict[str, object]] = []

    for symbol in selected:
        candles_15m = load_15m_year(
            symbol=symbol,
            start=args.start,
            end=args.end,
        )
        candles_30m = resample_30m(candles_15m)
        print(
            f"FM_DATA_READY symbol={symbol} candles15m={len(candles_15m)} "
            f"candles30m={len(candles_30m)}",
            flush=True,
        )

        for timeframe, candles in (("15m", candles_15m), ("30m", candles_30m)):
            result = scan_fm(candles, policy=policy)
            payload = _stream_payload(symbol, timeframe, result)
            internal = dict(payload)
            internal["_trade_objects"] = list(result.trades)
            internal_streams.append(internal)
            public_streams.append(payload)

            metrics = payload["metrics"]
            base = metrics["base"]
            stress = metrics["stress"]
            print(
                f"FM_STREAM symbol={symbol} timeframe={timeframe} "
                f"setups={result.setups} trades={metrics['trades']} "
                f"win_rate={metrics['win_rate_base']} "
                f"base_exp={base['expectancy_r']} base_pf={base['profit_factor']} "
                f"stress_exp={stress['expectancy_r']} "
                f"stress_pf={stress['profit_factor']}",
                flush=True,
            )

    overall = _aggregate_streams(internal_streams)
    by_timeframe = {}
    for timeframe in ("15m", "30m"):
        subset = [s for s in internal_streams if s["timeframe"] == timeframe]
        by_timeframe[timeframe] = _aggregate_streams(subset)

    by_symbol = {}
    for symbol in selected:
        subset = [s for s in internal_streams if s["symbol"] == symbol]
        by_symbol[symbol] = _aggregate_streams(subset)

    report = {
        "schema": "FM_TOP10_1Y_RESEARCH_V0_1",
        "research_only": True,
        "runtime_approval": "DENIED_RESEARCH_ONLY",
        "period": {
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "universe": {
            "ranking_source": "CoinMarketCap historical snapshot 2026-10-06",
            "stablecoins_excluded": ["USDT", "USDC"],
            "ranked_candidates": list(RANKED_NON_STABLE_CANDIDATES),
            "selected_full_coverage_symbols": list(selected),
            "coverage_rule": (
                "first 10 market-cap-ranked non-stable candidates with every "
                "monthly Binance USD-M 15m archive present from 2025-10 through 2026-09"
            ),
        },
        "protocol": {
            "timeframes": ["15m", "30m"],
            "source": "Binance USD-M Futures monthly klines; SHA256 checksum verified",
            "fm_contract": {
                "spike": (
                    ">=5 same-direction bars with monotonic closes and no opposite "
                    "extreme pullback; at least one strict 3-candle FVG"
                ),
                "fvg": (
                    "LONG: candle[i].low > candle[i-2].high; "
                    "SHORT: candle[i].high < candle[i-2].low"
                ),
                "first_pullback": (
                    "1-2 bars; at least one opposite-body bar; retracement <=30% "
                    "of spike extreme-to-origin size"
                ),
                "break": "next bar after pullback breaks the spike extreme directionally",
                "followthrough": (
                    "3-4 same-direction bars after the break; a new FVG must be "
                    "formed entirely inside the post-break follow-through"
                ),
                "entry": (
                    "limit at low (LONG) / high (SHORT) of the first follow-through "
                    "bar completing the new FVG; pending until fill, destination, "
                    "or pullback invalidation"
                ),
                "stop": "exact first-pullback extreme; no discretionary buffer",
                "destination": (
                    "LONG = pullback_low + spike_size; "
                    "SHORT = pullback_high - spike_size"
                ),
                "tp1": (
                    "0.10 ATR14 before the measured-move destination in the trade direction"
                ),
                "ambiguity": (
                    "same-bar stop/target -> stop first; pending same-bar invalidation "
                    "or destination versus fill -> setup cancelled before fill"
                ),
            },
            "costs": {
                "base_bps_per_side": 6,
                "stress_bps_per_side": 10,
            },
            "important_limitation": (
                "This is a deterministic crypto research interpretation of the "
                "previously described FM setup. The original discussion left the "
                "exact FVG taxonomy, exact sell/buy candle, stop buffer, and TP1 "
                "offset non-authoritative; those choices are frozen above rather "
                "than optimized on PnL."
            ),
        },
        "overall": overall,
        "by_timeframe": by_timeframe,
        "by_symbol": by_symbol,
        "streams": public_streams,
    }

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "fm_top10_1y_report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    m = overall["metrics"]
    print(
        f"FM_FINAL trades={m['trades']} win_rate={m['win_rate_base']} "
        f"base_exp={m['base']['expectancy_r']} "
        f"base_pf={m['base']['profit_factor']} "
        f"stress_exp={m['stress']['expectancy_r']} "
        f"stress_pf={m['stress']['profit_factor']} "
        f"max_dd_base={m['base']['max_drawdown_r']}",
        flush=True,
    )
    print(f"FM_REPORT {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
