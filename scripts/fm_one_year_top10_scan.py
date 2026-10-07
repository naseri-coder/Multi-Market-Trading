#!/usr/bin/env python3
"""One-year causal FM strategy scan on 10 large Binance USD-M futures assets.

FM is tested with two execution interpretations because the earlier discussion
left the exact entry mechanic unresolved:

STOP:
    After the first weak 1-2 bar pullback, enter on a stop through the spike
    extreme. This is closest to the user's original "stop order" wording.

CONFIRMED_LIMIT:
    Require a 3-4 bar leg-2 continuation with a fresh directional FVG, then
    place a pullback limit at the high/low of the final confirmation candle,
    valid for the next two bars. This matches the later "entry after leg-2
    confirmation / sell limit at sell-candle high" interpretation.

Everything else is identical and frozen before the scan.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from research_layer.marc_backtest.data import (
    fetch_binance_vision_monthly_klines,
    resample_15m_to_30m,
    split_contiguous_candles,
)
from research_layer.statistics import max_drawdown, profit_factor

D = Decimal

SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "TRXUSDT",
    "ZECUSDT",
    "HYPEUSDT",
    "DOGEUSDT",
    "LINKUSDT",
)
TIMEFRAMES = ("15m", "30m")

MIN_SPIKE_BARS = 5
MAX_PULLBACK_BARS = 2
MAX_RETRACE = D("0.30")
MIN_LEG2_CONFIRM_BARS = 3
MAX_LEG2_CONFIRM_BARS = 4
LIMIT_VALID_BARS = 2
TP_FRACTION_OF_MEASURED_MOVE = D("0.95")
BASE_COST_BPS_PER_SIDE = D("6")
STRESS_COST_BPS_PER_SIDE = D("10")


@dataclass(frozen=True, slots=True)
class FMTrade:
    symbol: str
    timeframe: str
    execution: str
    direction: str
    spike_start: str
    spike_end: str
    spike_bars: int
    pullback_bars: int
    retrace_fraction: float
    entry_time: str
    entry: float
    stop: float
    target: float
    measured_target: float
    exit_time: str
    exit: float
    exit_reason: str
    duration_bars: int
    gross_r: float
    base_net_r: float
    stress_net_r: float


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FM one-year top-10 crypto scan")
    p.add_argument("--start", type=_date, default=_date("2025-10-01"))
    p.add_argument("--end", type=_date, default=_date("2026-10-01"))
    p.add_argument("--output-dir", type=Path, default=Path("research_output/fm_one_year_top10_v0_1"))
    p.add_argument("--request-delay", type=float, default=0.03)
    p.add_argument("--base-url", default="https://data.binance.vision")
    return p


def _bull_fvg(candles, index: int) -> bool:
    return index >= 2 and candles[index].low > candles[index - 2].high


def _bear_fvg(candles, index: int) -> bool:
    return index >= 2 and candles[index].high < candles[index - 2].low


def _has_fvg(candles, start: int, end: int, direction: str) -> bool:
    for index in range(max(start, 2), end + 1):
        if direction == "LONG" and _bull_fvg(candles, index):
            return True
        if direction == "SHORT" and _bear_fvg(candles, index):
            return True
    return False


def _microchannel_continues(previous, current, direction: str) -> bool:
    if direction == "LONG":
        return current.low >= previous.low
    return current.high <= previous.high


def _direction_at(candles, index: int) -> str | None:
    if index + 1 >= len(candles):
        return None
    a, b = candles[index], candles[index + 1]
    if b.low >= a.low and b.close > a.close:
        return "LONG"
    if b.high <= a.high and b.close < a.close:
        return "SHORT"
    return None


def _spike_geometry(candles, start: int, end: int, direction: str):
    block = candles[start : end + 1]
    if direction == "LONG":
        origin = min(c.low for c in block)
        extreme = max(c.high for c in block)
        size = extreme - origin
        directional = candles[end].close > candles[start].close
    else:
        origin = max(c.high for c in block)
        extreme = min(c.low for c in block)
        size = origin - extreme
        directional = candles[end].close < candles[start].close
    return origin, extreme, size, directional


def _pullback(candles, start: int, pb_len: int, *, direction: str, spike_origin, spike_extreme, spike_size):
    end = start + pb_len - 1
    if end >= len(candles) or spike_size <= 0:
        return None
    block = candles[start : end + 1]

    if direction == "LONG":
        pb_extreme = min(c.low for c in block)
        retrace = (spike_extreme - pb_extreme) / spike_size
        # It must actually pull back and must not invalidate the spike origin.
        if pb_extreme >= spike_extreme or pb_extreme <= spike_origin:
            return None
    else:
        pb_extreme = max(c.high for c in block)
        retrace = (pb_extreme - spike_extreme) / spike_size
        if pb_extreme <= spike_extreme or pb_extreme >= spike_origin:
            return None

    if retrace <= 0 or retrace > MAX_RETRACE:
        return None
    return end, pb_extreme, retrace


def _leg2_confirmation(candles, start: int, direction: str, spike_extreme):
    """Return final confirmation index for the earliest valid 3/4 bar leg-2."""
    for bars in range(MIN_LEG2_CONFIRM_BARS, MAX_LEG2_CONFIRM_BARS + 1):
        end = start + bars - 1
        if end >= len(candles):
            return None
        ok = True
        for index in range(start + 1, end + 1):
            if not _microchannel_continues(candles[index - 1], candles[index], direction):
                ok = False
                break
        if not ok:
            continue
        block = candles[start : end + 1]
        if direction == "LONG":
            broke = max(c.high for c in block) > spike_extreme
        else:
            broke = min(c.low for c in block) < spike_extreme
        if not broke:
            continue
        if not _has_fvg(candles, start, end, direction):
            continue
        return end
    return None


def _simulate(candles, entry_index: int, entry, stop, target, direction: str):
    """Conservative OHLC simulation: stop wins any same-bar ambiguity."""
    if direction == "LONG":
        risk = entry - stop
    else:
        risk = stop - entry
    if risk <= 0:
        return None

    for index in range(entry_index, len(candles)):
        c = candles[index]
        if direction == "LONG":
            if c.open <= stop:
                exit_price, reason = c.open, "STOP_GAP"
            elif c.open >= target:
                exit_price, reason = target, "TARGET_GAP_CONSERVATIVE"
            else:
                hit_stop = c.low <= stop
                hit_target = c.high >= target
                if hit_stop:
                    exit_price, reason = stop, "STOP_FIRST" if hit_target else "STOP"
                elif hit_target:
                    exit_price, reason = target, "TARGET"
                else:
                    continue
            gross = (exit_price - entry) / risk
        else:
            if c.open >= stop:
                exit_price, reason = c.open, "STOP_GAP"
            elif c.open <= target:
                exit_price, reason = target, "TARGET_GAP_CONSERVATIVE"
            else:
                hit_stop = c.high >= stop
                hit_target = c.low <= target
                if hit_stop:
                    exit_price, reason = stop, "STOP_FIRST" if hit_target else "STOP"
                elif hit_target:
                    exit_price, reason = target, "TARGET"
                else:
                    continue
            gross = (entry - exit_price) / risk

        base_cost = (BASE_COST_BPS_PER_SIDE / D("10000")) * (entry + exit_price) / risk
        stress_cost = (STRESS_COST_BPS_PER_SIDE / D("10000")) * (entry + exit_price) / risk
        return index, exit_price, reason, gross, gross - base_cost, gross - stress_cost

    c = candles[-1]
    exit_price = c.close
    if direction == "LONG":
        gross = (exit_price - entry) / risk
    else:
        gross = (entry - exit_price) / risk
    base_cost = (BASE_COST_BPS_PER_SIDE / D("10000")) * (entry + exit_price) / risk
    stress_cost = (STRESS_COST_BPS_PER_SIDE / D("10000")) * (entry + exit_price) / risk
    return len(candles) - 1, exit_price, "WINDOW_END", gross, gross - base_cost, gross - stress_cost


def _trade(
    *,
    candles,
    symbol,
    timeframe,
    execution,
    direction,
    spike_start,
    spike_end,
    spike_extreme,
    spike_size,
    pb_start,
    pb_len,
    pb_end,
    pb_extreme,
    retrace,
    leg2_end,
):
    if direction == "LONG":
        measured_target = pb_extreme + spike_size
        target = pb_extreme + TP_FRACTION_OF_MEASURED_MOVE * spike_size
        stop = pb_extreme
    else:
        measured_target = pb_extreme - spike_size
        target = pb_extreme - TP_FRACTION_OF_MEASURED_MOVE * spike_size
        stop = pb_extreme

    if execution == "STOP":
        # Stop order sits at the original spike extreme immediately after the
        # weak pullback. Valid through the four-bar leg-2 observation window.
        entry = spike_extreme
        fill_index = None
        for index in range(pb_end + 1, min(pb_end + 1 + MAX_LEG2_CONFIRM_BARS, len(candles))):
            c = candles[index]
            if direction == "LONG" and c.high >= entry:
                fill_index = index
                break
            if direction == "SHORT" and c.low <= entry:
                fill_index = index
                break
        if fill_index is None:
            return None
    else:
        if leg2_end is None:
            return None
        signal = candles[leg2_end]
        entry = signal.low if direction == "LONG" else signal.high
        fill_index = None
        for index in range(leg2_end + 1, min(leg2_end + 1 + LIMIT_VALID_BARS, len(candles))):
            c = candles[index]
            if c.low <= entry <= c.high:
                fill_index = index
                break
        if fill_index is None:
            return None

    if direction == "LONG":
        if not (stop < entry < target < measured_target):
            return None
    else:
        if not (stop > entry > target > measured_target):
            return None

    outcome = _simulate(candles, fill_index, entry, stop, target, direction)
    if outcome is None:
        return None
    exit_index, exit_price, reason, gross, base, stress = outcome

    return FMTrade(
        symbol=symbol,
        timeframe=timeframe,
        execution=execution,
        direction=direction,
        spike_start=candles[spike_start].open_time.isoformat(),
        spike_end=candles[spike_end].close_time.isoformat(),
        spike_bars=spike_end - spike_start + 1,
        pullback_bars=pb_len,
        retrace_fraction=float(retrace),
        entry_time=candles[fill_index].open_time.isoformat(),
        entry=float(entry),
        stop=float(stop),
        target=float(target),
        measured_target=float(measured_target),
        exit_time=candles[exit_index].close_time.isoformat(),
        exit=float(exit_price),
        exit_reason=reason,
        duration_bars=exit_index - fill_index + 1,
        gross_r=float(gross),
        base_net_r=float(base),
        stress_net_r=float(stress),
    )


def scan_segment(candles, symbol: str, timeframe: str):
    trades = {"STOP": [], "CONFIRMED_LIMIT": []}
    counts = Counter()
    index = 0

    while index + MIN_SPIKE_BARS + 6 < len(candles):
        direction = _direction_at(candles, index)
        if direction is None:
            index += 1
            continue

        end = index + 1
        while end + 1 < len(candles) and _microchannel_continues(
            candles[end], candles[end + 1], direction
        ):
            end += 1

        spike_bars = end - index + 1
        if spike_bars < MIN_SPIKE_BARS:
            index += 1
            continue

        origin, extreme, size, directional = _spike_geometry(candles, index, end, direction)
        if not directional or size <= 0:
            counts["SPIKE_NOT_DIRECTIONAL"] += 1
            index = max(index + 1, end)
            continue
        if not _has_fvg(candles, index, end, direction):
            counts["SPIKE_NO_FVG"] += 1
            index = max(index + 1, end)
            continue
        counts["SPIKE_FVG"] += 1

        matched = False
        for pb_len in (1, 2):
            pb_start = end + 1
            pb = _pullback(
                candles,
                pb_start,
                pb_len,
                direction=direction,
                spike_origin=origin,
                spike_extreme=extreme,
                spike_size=size,
            )
            if pb is None:
                continue
            pb_end, pb_extreme, retrace = pb
            counts["WEAK_PULLBACK"] += 1

            leg2_start = pb_end + 1
            leg2_end = _leg2_confirmation(candles, leg2_start, direction, extreme)
            if leg2_end is not None:
                counts["LEG2_CONFIRMED"] += 1

            # STOP interpretation does not look ahead to require confirmation,
            # but the same structural geometry/target is used.
            stop_trade = _trade(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                execution="STOP",
                direction=direction,
                spike_start=index,
                spike_end=end,
                spike_extreme=extreme,
                spike_size=size,
                pb_start=pb_start,
                pb_len=pb_len,
                pb_end=pb_end,
                pb_extreme=pb_extreme,
                retrace=retrace,
                leg2_end=leg2_end,
            )
            if stop_trade is not None:
                trades["STOP"].append(stop_trade)
                counts["STOP_TRADE"] += 1

            limit_trade = _trade(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                execution="CONFIRMED_LIMIT",
                direction=direction,
                spike_start=index,
                spike_end=end,
                spike_extreme=extreme,
                spike_size=size,
                pb_start=pb_start,
                pb_len=pb_len,
                pb_end=pb_end,
                pb_extreme=pb_extreme,
                retrace=retrace,
                leg2_end=leg2_end,
            )
            if limit_trade is not None:
                trades["CONFIRMED_LIMIT"].append(limit_trade)
                counts["LIMIT_TRADE"] += 1

            if stop_trade is not None or limit_trade is not None:
                matched = True
                break

        # Avoid creating duplicate setups from the same maximal spike.
        index = max(index + 1, end + 1 if matched else end)

    return trades, counts


def _finite_pf(values):
    pf = profit_factor(values)
    return None if not math.isfinite(pf) else pf


def _summary(trades):
    values = [t.base_net_r for t in trades]
    stress = [t.stress_net_r for t in trades]
    gross = [t.gross_r for t in trades]
    wins = sum(v > 0 for v in values)
    return {
        "trades": len(trades),
        "win_rate": wins / len(trades) if trades else None,
        "gross_expectancy_r": sum(gross) / len(gross) if gross else None,
        "base_expectancy_r": sum(values) / len(values) if values else None,
        "stress_expectancy_r": sum(stress) / len(stress) if stress else None,
        "base_profit_factor": _finite_pf(values) if values else None,
        "stress_profit_factor": _finite_pf(stress) if stress else None,
        "base_total_r": sum(values) if values else 0.0,
        "base_max_drawdown_r": max_drawdown(values) if values else None,
        "long_trades": sum(t.direction == "LONG" for t in trades),
        "short_trades": sum(t.direction == "SHORT" for t in trades),
    }


async def _run(args):
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    all_trades = {"STOP": [], "CONFIRMED_LIMIT": []}
    stream_summaries = defaultdict(dict)
    scan_counts = {}

    for symbol in SYMBOLS:
        archive = await fetch_binance_vision_monthly_klines(
            symbol=symbol,
            start=args.start,
            end=args.end,
            timeframe="15m",
            request_delay_seconds=args.request_delay,
            base_url=args.base_url,
        )
        c15 = archive.candles
        c30 = resample_15m_to_30m(c15)
        print(
            f"FM_DATA symbol={symbol} c15={len(c15)} c30={len(c30)} "
            f"archives={archive.verified_archives} gaps={archive.gap_count}",
            flush=True,
        )

        for timeframe, candles in (("15m", c15), ("30m", c30)):
            stream_counts = Counter()
            stream_trades = {"STOP": [], "CONFIRMED_LIMIT": []}
            for segment in split_contiguous_candles(candles, timeframe=timeframe):
                if len(segment) < 100:
                    continue
                found, counts = scan_segment(segment, symbol, timeframe)
                stream_counts.update(counts)
                for execution in stream_trades:
                    stream_trades[execution].extend(found[execution])

            scan_counts[f"{symbol}:{timeframe}"] = dict(stream_counts)
            for execution in ("STOP", "CONFIRMED_LIMIT"):
                # One-position-at-a-time dedup: if two setups overlap, keep the
                # first entry and skip later entries until it exits.
                ordered = sorted(
                    stream_trades[execution],
                    key=lambda t: (t.entry_time, t.exit_time),
                )
                filtered = []
                last_exit = None
                for trade in ordered:
                    entry_dt = datetime.fromisoformat(trade.entry_time)
                    if last_exit is not None and entry_dt <= last_exit:
                        continue
                    filtered.append(trade)
                    last_exit = datetime.fromisoformat(trade.exit_time)

                all_trades[execution].extend(filtered)
                stream_summaries[execution][f"{symbol}:{timeframe}"] = _summary(filtered)
                s = stream_summaries[execution][f"{symbol}:{timeframe}"]
                print(
                    f"FM_STREAM execution={execution} symbol={symbol} tf={timeframe} "
                    f"trades={s['trades']} wr={s['win_rate']} "
                    f"base_exp={s['base_expectancy_r']} pf={s['base_profit_factor']}",
                    flush=True,
                )

    report = {
        "schema": "FM_ONE_YEAR_TOP10_SCAN_V1",
        "period": {
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "symbols": list(SYMBOLS),
        "timeframes": list(TIMEFRAMES),
        "data_source": "Binance Vision USD-M Futures monthly 15m archives; checksum verified; 30m UTC resampled",
        "frozen_rules": {
            "spike": ">=5-bar directional microchannel with at least one literal 3-candle FVG",
            "pullback": "first 1-2 bars, >0 and <=30% retracement of spike",
            "leg2_confirmation": "3-4 bar directional continuation, breaks spike extreme, contains a new FVG",
            "stop": "beyond first pullback extreme (exact extreme in this research scan)",
            "measured_move": "one full spike projected from pullback extreme",
            "tp1": "95% of measured move so TP1 remains before the measured target",
            "same_bar_ambiguity": "STOP_FIRST",
            "base_cost": "6 bps per side",
            "stress_cost": "10 bps per side",
            "execution_variants": {
                "STOP": "stop at spike extreme after weak pullback; valid through next 4 bars",
                "CONFIRMED_LIMIT": "after 3-4 bar leg2 + fresh FVG, limit at final confirmation candle low/high; valid 2 bars",
            },
        },
        "overall": {},
        "streams": stream_summaries,
        "scan_counts": scan_counts,
    }

    for execution in ("STOP", "CONFIRMED_LIMIT"):
        all_trades[execution].sort(key=lambda t: (t.entry_time, t.symbol, t.timeframe))
        report["overall"][execution] = _summary(all_trades[execution])
        by_tf = {}
        for tf in TIMEFRAMES:
            by_tf[tf] = _summary([t for t in all_trades[execution] if t.timeframe == tf])
        report["overall"][execution]["by_timeframe"] = by_tf

        by_symbol = {}
        for symbol in SYMBOLS:
            by_symbol[symbol] = _summary([t for t in all_trades[execution] if t.symbol == symbol])
        report["overall"][execution]["by_symbol"] = by_symbol

        (output / f"fm_{execution.lower()}_trades.json").write_text(
            json.dumps([asdict(t) for t in all_trades[execution]], indent=2),
            encoding="utf-8",
        )

        s = report["overall"][execution]
        print(
            f"FM_FINAL execution={execution} trades={s['trades']} "
            f"win_rate={s['win_rate']} gross_exp={s['gross_expectancy_r']} "
            f"base_exp={s['base_expectancy_r']} base_pf={s['base_profit_factor']} "
            f"stress_exp={s['stress_expectancy_r']} stress_pf={s['stress_profit_factor']} "
            f"total_r={s['base_total_r']} max_dd_r={s['base_max_drawdown_r']}",
            flush=True,
        )

    path = output / "fm_one_year_top10_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"FM_REPORT {path}", flush=True)


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
