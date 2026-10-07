"""Deterministic research interpretation of the previously described FM setup."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math

from research_layer.fm_backtest.data import Candle

D = Decimal


@dataclass(frozen=True, slots=True)
class FMPolicy:
    min_spike_bars: int = 5
    max_pullback_bars: int = 2
    max_pullback_fraction: Decimal = D("0.30")
    min_followthrough_bars: int = 3
    max_followthrough_bars: int = 4
    tp1_atr_before_destination: Decimal = D("0.10")
    base_cost_bps_per_side: Decimal = D("6")
    stress_cost_bps_per_side: Decimal = D("10")


@dataclass(frozen=True, slots=True)
class FMTrade:
    direction: str
    setup_time_ms: int
    entry_time_ms: int
    exit_time_ms: int
    entry: Decimal
    stop: Decimal
    target: Decimal
    destination: Decimal
    gross_r: float
    base_net_r: float
    stress_net_r: float
    outcome: str
    spike_bars: int
    pullback_bars: int
    followthrough_bars: int
    pullback_fraction: float


@dataclass(frozen=True, slots=True)
class ScanResult:
    trades: tuple[FMTrade, ...]
    setups: int
    missed_destination_before_fill: int
    invalidated_before_fill: int


def _true_range(current: Candle, previous: Candle) -> Decimal:
    return max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )


def _atr14(candles: tuple[Candle, ...]) -> tuple[Decimal | None, ...]:
    out: list[Decimal | None] = [None] * len(candles)
    if len(candles) < 15:
        return tuple(out)
    trs = [_true_range(candles[i], candles[i - 1]) for i in range(1, len(candles))]
    atr = sum(trs[:14], D("0")) / D("14")
    out[14] = atr
    for candle_index in range(15, len(candles)):
        tr = trs[candle_index - 1]
        atr = ((atr * D("13")) + tr) / D("14")
        out[candle_index] = atr
    return tuple(out)


def _fvg(candles: tuple[Candle, ...], index: int, direction: str) -> bool:
    if index < 2:
        return False
    if direction == "LONG":
        return candles[index].low > candles[index - 2].high
    if direction == "SHORT":
        return candles[index].high < candles[index - 2].low
    raise ValueError("direction must be LONG or SHORT")


def _directional_bar(candle: Candle, direction: str) -> bool:
    if direction == "LONG":
        return candle.close > candle.open
    if direction == "SHORT":
        return candle.close < candle.open
    raise ValueError("direction must be LONG or SHORT")


def _continues_no_pullback(previous: Candle, current: Candle, direction: str) -> bool:
    if not _directional_bar(current, direction):
        return False
    if direction == "LONG":
        return current.close > previous.close and current.low >= previous.low
    return current.close < previous.close and current.high <= previous.high


def _spike_from(
    candles: tuple[Candle, ...],
    start: int,
    direction: str,
    policy: FMPolicy,
) -> tuple[int, int] | None:
    if not _directional_bar(candles[start], direction):
        return None
    end = start
    while end + 1 < len(candles) and _continues_no_pullback(
        candles[end], candles[end + 1], direction
    ):
        end += 1
    bars = end - start + 1
    if bars < policy.min_spike_bars:
        return None
    has_fvg = any(_fvg(candles, i, direction) for i in range(start + 2, end + 1))
    if not has_fvg:
        return None
    return start, end


def _spike_geometry(
    candles: tuple[Candle, ...],
    start: int,
    end: int,
    direction: str,
) -> tuple[Decimal, Decimal, Decimal]:
    if direction == "LONG":
        origin = candles[start].low
        extreme = max(c.high for c in candles[start : end + 1])
        size = extreme - origin
    else:
        origin = candles[start].high
        extreme = min(c.low for c in candles[start : end + 1])
        size = origin - extreme
    return origin, extreme, size


def _pullback_candidates(
    candles: tuple[Candle, ...],
    start_index: int,
    spike_extreme: Decimal,
    spike_size: Decimal,
    direction: str,
    policy: FMPolicy,
) -> tuple[tuple[int, int, Decimal, Decimal], ...]:
    if start_index >= len(candles) or spike_size <= 0:
        return ()
    output: list[tuple[int, int, Decimal, Decimal]] = []
    for length in range(1, policy.max_pullback_bars + 1):
        end = start_index + length - 1
        if end >= len(candles):
            break
        bars = candles[start_index : end + 1]
        if direction == "LONG":
            if not any(c.close < c.open for c in bars):
                continue
            pb_extreme = min(c.low for c in bars)
            retrace = spike_extreme - pb_extreme
        else:
            if not any(c.close > c.open for c in bars):
                continue
            pb_extreme = max(c.high for c in bars)
            retrace = pb_extreme - spike_extreme
        fraction = retrace / spike_size
        if fraction < 0 or fraction > policy.max_pullback_fraction:
            continue
        output.append((start_index, end, pb_extreme, fraction))
    return tuple(output)


def _breaks_extreme(candle: Candle, spike_extreme: Decimal, direction: str) -> bool:
    if direction == "LONG":
        return candle.high > spike_extreme and candle.close > candle.open
    return candle.low < spike_extreme and candle.close < candle.open


def _followthrough(
    candles: tuple[Candle, ...],
    break_index: int,
    direction: str,
    policy: FMPolicy,
) -> tuple[int, int] | None:
    max_end = min(
        len(candles) - 1,
        break_index + policy.max_followthrough_bars - 1,
    )
    for end in range(
        break_index + policy.min_followthrough_bars - 1,
        max_end + 1,
    ):
        bars = candles[break_index : end + 1]
        if not all(_directional_bar(c, direction) for c in bars):
            return None
        # The "new gap" must be formed entirely by post-break follow-through
        # candles, so the earliest eligible third candle is break_index + 2.
        gap_indices = [
            i
            for i in range(break_index + 2, end + 1)
            if _fvg(candles, i, direction)
        ]
        if gap_indices:
            return end, gap_indices[0]
    return None


def _costed_r(
    *,
    direction: str,
    entry: Decimal,
    exit_price: Decimal,
    stop: Decimal,
    cost_bps: Decimal,
) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("risk must be positive")
    if direction == "LONG":
        pnl = exit_price - entry
    else:
        pnl = entry - exit_price
    gross = pnl / risk
    friction = ((entry + exit_price) * cost_bps / D("10000")) / risk
    return float(gross - friction)


def _gross_r(
    *,
    direction: str,
    entry: Decimal,
    exit_price: Decimal,
    stop: Decimal,
) -> float:
    risk = abs(entry - stop)
    if direction == "LONG":
        return float((exit_price - entry) / risk)
    return float((entry - exit_price) / risk)


def _simulate_setup(
    *,
    candles: tuple[Candle, ...],
    atr: tuple[Decimal | None, ...],
    direction: str,
    spike_start: int,
    spike_end: int,
    pullback_start: int,
    pullback_end: int,
    pullback_extreme: Decimal,
    pullback_fraction: Decimal,
    follow_end: int,
    gap_index: int,
    spike_size: Decimal,
    policy: FMPolicy,
) -> tuple[FMTrade | None, int, str]:
    setup_index = follow_end
    current_atr = atr[setup_index]
    if current_atr is None or current_atr <= 0:
        return None, setup_index, "NO_ATR"

    if direction == "LONG":
        destination = pullback_extreme + spike_size
        target = destination - policy.tp1_atr_before_destination * current_atr
        entry = candles[gap_index].low
        stop = pullback_extreme
        if not (stop < entry < target):
            return None, setup_index, "GEOMETRY_INVALID"
    else:
        destination = pullback_extreme - spike_size
        target = destination + policy.tp1_atr_before_destination * current_atr
        entry = candles[gap_index].high
        stop = pullback_extreme
        if not (target < entry < stop):
            return None, setup_index, "GEOMETRY_INVALID"

    fill_index: int | None = None
    cursor = setup_index + 1
    while cursor < len(candles):
        candle = candles[cursor]
        if direction == "LONG":
            destination_touched = candle.high >= destination
            invalidated = candle.low <= stop
            fill_touched = candle.low <= entry <= candle.high
        else:
            destination_touched = candle.low <= destination
            invalidated = candle.high >= stop
            fill_touched = candle.low <= entry <= candle.high

        # Pending-order ambiguity is resolved conservatively: destination or
        # invalidation cancels the setup before granting a same-bar fill.
        if destination_touched:
            return None, cursor, "DESTINATION_BEFORE_FILL"
        if invalidated:
            return None, cursor, "INVALIDATED_BEFORE_FILL"
        if fill_touched:
            fill_index = cursor
            break
        cursor += 1

    if fill_index is None:
        return None, len(candles) - 1, "NO_FILL"

    exit_index = fill_index
    exit_price = candles[fill_index].close
    outcome = "WINDOW_END"
    for cursor in range(fill_index, len(candles)):
        candle = candles[cursor]
        if direction == "LONG":
            stop_hit = candle.low <= stop
            target_hit = candle.high >= target
        else:
            stop_hit = candle.high >= stop
            target_hit = candle.low <= target

        if stop_hit and target_hit:
            exit_index = cursor
            exit_price = stop
            outcome = "STOP_FIRST_AMBIGUOUS"
            break
        if stop_hit:
            exit_index = cursor
            exit_price = stop
            outcome = "STOP"
            break
        if target_hit:
            exit_index = cursor
            exit_price = target
            outcome = "TP1"
            break
        exit_index = cursor
        exit_price = candle.close

    return (
        FMTrade(
            direction=direction,
            setup_time_ms=candles[setup_index].open_time_ms,
            entry_time_ms=candles[fill_index].open_time_ms,
            exit_time_ms=candles[exit_index].open_time_ms,
            entry=entry,
            stop=stop,
            target=target,
            destination=destination,
            gross_r=_gross_r(
                direction=direction,
                entry=entry,
                exit_price=exit_price,
                stop=stop,
            ),
            base_net_r=_costed_r(
                direction=direction,
                entry=entry,
                exit_price=exit_price,
                stop=stop,
                cost_bps=policy.base_cost_bps_per_side,
            ),
            stress_net_r=_costed_r(
                direction=direction,
                entry=entry,
                exit_price=exit_price,
                stop=stop,
                cost_bps=policy.stress_cost_bps_per_side,
            ),
            outcome=outcome,
            spike_bars=spike_end - spike_start + 1,
            pullback_bars=pullback_end - pullback_start + 1,
            followthrough_bars=follow_end - (pullback_end + 1) + 1,
            pullback_fraction=float(pullback_fraction),
        ),
        exit_index,
        "TRADE",
    )


def scan_fm(
    candles: tuple[Candle, ...],
    *,
    policy: FMPolicy | None = None,
) -> ScanResult:
    selected = policy or FMPolicy()
    atr = _atr14(candles)
    trades: list[FMTrade] = []
    setups = 0
    missed = 0
    invalidated = 0

    i = 0
    while i < len(candles) - 12:
        found = False
        for direction in ("LONG", "SHORT"):
            spike = _spike_from(candles, i, direction, selected)
            if spike is None:
                continue
            spike_start, spike_end = spike
            _, spike_extreme, spike_size = _spike_geometry(
                candles, spike_start, spike_end, direction
            )
            pullbacks = _pullback_candidates(
                candles,
                spike_end + 1,
                spike_extreme,
                spike_size,
                direction,
                selected,
            )
            if not pullbacks:
                continue

            matched = None
            for pb_start, pb_end, pb_extreme, pb_fraction in pullbacks:
                break_index = pb_end + 1
                if break_index >= len(candles) or not _breaks_extreme(
                    candles[break_index], spike_extreme, direction
                ):
                    continue
                ft = _followthrough(candles, break_index, direction, selected)
                if ft is None:
                    continue
                matched = (
                    pb_start,
                    pb_end,
                    pb_extreme,
                    pb_fraction,
                    ft[0],
                    ft[1],
                )
                break
            if matched is None:
                continue

            (
                pb_start,
                pb_end,
                pb_extreme,
                pb_fraction,
                follow_end,
                gap_index,
            ) = matched
            setups += 1
            trade, resolved_index, status = _simulate_setup(
                candles=candles,
                atr=atr,
                direction=direction,
                spike_start=spike_start,
                spike_end=spike_end,
                pullback_start=pb_start,
                pullback_end=pb_end,
                pullback_extreme=pb_extreme,
                pullback_fraction=pb_fraction,
                follow_end=follow_end,
                gap_index=gap_index,
                spike_size=spike_size,
                policy=selected,
            )
            if trade is not None:
                trades.append(trade)
            elif status == "DESTINATION_BEFORE_FILL":
                missed += 1
            elif status == "INVALIDATED_BEFORE_FILL":
                invalidated += 1
            i = max(i + 1, resolved_index + 1)
            found = True
            break
        if not found:
            i += 1

    return ScanResult(
        trades=tuple(trades),
        setups=setups,
        missed_destination_before_fill=missed,
        invalidated_before_fill=invalidated,
    )
