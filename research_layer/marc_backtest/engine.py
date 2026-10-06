"""Causal MARC R1 execution simulator for research-only validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.entities import (
    BacktestTrade,
    BacktestWindowResult,
    TradeFill,
)

D = Decimal


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Frozen execution assumptions around the already-frozen MARC signal rules."""

    base_cost_bps_per_side: float = 6.0
    stress_cost_bps_per_side: float = 10.0
    tp1_fraction: float = 0.25
    tp2_fraction: float = 0.25
    runner_fraction: float = 0.50
    scan_lookback: int = 32
    snapshot_window: int = 120

    def __post_init__(self) -> None:
        if self.base_cost_bps_per_side < 0 or self.stress_cost_bps_per_side < 0:
            raise ValueError("cost assumptions cannot be negative")
        if self.stress_cost_bps_per_side < self.base_cost_bps_per_side:
            raise ValueError("stress cost must not be below base cost")
        total = self.tp1_fraction + self.tp2_fraction + self.runner_fraction
        if abs(total - 1.0) > 1e-12:
            raise ValueError("MARC exit fractions must sum to one")
        if min(self.tp1_fraction, self.tp2_fraction, self.runner_fraction) <= 0:
            raise ValueError("MARC exit fractions must be positive")
        if self.scan_lookback < 24:
            raise ValueError("scan_lookback must cover MARC chop and validity windows")
        if self.snapshot_window < 99:
            raise ValueError("snapshot_window must preserve the MA99 regime context")


def _wilder_atr(
    candles: tuple[Candle, ...],
    period: int,
) -> tuple[Decimal | None, ...]:
    output: list[Decimal | None] = [None] * len(candles)
    if len(candles) <= period:
        return tuple(output)
    true_ranges: list[Decimal] = [D("0")]
    for index in range(1, len(candles)):
        candle = candles[index]
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    current = sum(true_ranges[1 : period + 1], D("0")) / D(period)
    output[period] = current
    for index in range(period + 1, len(candles)):
        current = (current * D(period - 1) + true_ranges[index]) / D(period)
        output[index] = current
    return tuple(output)


def _chandelier_level(
    *,
    candles: tuple[Candle, ...],
    atr: tuple[Decimal | None, ...],
    index: int,
    direction: str,
    length: int,
    multiplier: Decimal,
) -> Decimal | None:
    value = atr[index]
    if value is None or index + 1 < length:
        return None
    window = candles[index - length + 1 : index + 1]
    if direction == "LONG":
        return max(candle.high for candle in window) - multiplier * value
    return min(candle.low for candle in window) + multiplier * value


def _costed_r(
    *,
    direction: str,
    entry: Decimal,
    stop: Decimal,
    fills: list[tuple[Decimal, Decimal]],
    cost_bps_per_side: float,
) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("initial risk must be positive")
    sign = D("1") if direction == "LONG" else D("-1")
    gross = sum(
        fraction * sign * (price - entry)
        for fraction, price in fills
    )
    bps = D(str(cost_bps_per_side)) / D("10000")
    entry_cost = entry * bps
    exit_cost = sum(fraction * price * bps for fraction, price in fills)
    return float((gross - entry_cost - exit_cost) / risk)


def _simulate_trade(
    *,
    candles: tuple[Candle, ...],
    atr22: tuple[Decimal | None, ...],
    candidate,
    entry_index: int,
    last_index: int,
    config: BacktestConfig,
    policy: MARCPolicy,
) -> tuple[BacktestTrade, int]:
    direction = candidate.direction
    entry = candidate.entry_price
    stop = candidate.stop_loss
    tp1, tp2 = candidate.targets
    tp1_fraction = D(str(config.tp1_fraction))
    tp2_fraction = D(str(config.tp2_fraction))
    remaining = D("1")
    tp1_hit = False
    tp2_hit = False
    runner_active = False
    trail: Decimal | None = None
    fills_raw: list[tuple[Decimal, Decimal]] = []
    fills: list[TradeFill] = []
    terminal_reason = "WINDOW_END"
    exit_index = last_index

    def fill(candle: Candle, price: Decimal, fraction: Decimal, reason: str, *, at_open=False):
        nonlocal remaining
        if fraction <= 0 or fraction > remaining:
            raise RuntimeError("invalid MARC backtest fill fraction")
        fills_raw.append((fraction, price))
        fills.append(
            TradeFill(
                time=candle.open_time if at_open else candle.close_time,
                price=float(price),
                fraction=float(fraction),
                reason=reason,
            )
        )
        remaining -= fraction

    def target_fill(
        candle: Candle,
        price: Decimal,
        fraction: Decimal,
        reason: str,
        *,
        at_open: bool = False,
    ) -> None:
        nonlocal tp1_hit, tp2_hit
        actual_fraction = min(fraction, remaining)
        fill(candle, price, actual_fraction, reason, at_open=at_open)
        if reason == "TP1":
            tp1_hit = True
        elif reason == "TP2":
            tp2_hit = True
        else:
            raise RuntimeError("unknown MARC target fill")

    for index in range(entry_index, last_index + 1):
        candle = candles[index]
        effective_stop = stop
        if runner_active and trail is not None:
            if direction == "LONG":
                effective_stop = max(effective_stop, trail)
            else:
                effective_stop = min(effective_stop, trail)

        if direction == "LONG":
            if candle.open <= effective_stop:
                fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                terminal_reason = "STOP_GAP"
                exit_index = index
                break
            gap_targets = []
            if not tp1_hit and candle.open >= tp1:
                gap_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.open >= tp2:
                gap_targets.append((tp2, tp2_fraction, "TP2"))
        else:
            if candle.open >= effective_stop:
                fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                terminal_reason = "STOP_GAP"
                exit_index = index
                break
            gap_targets = []
            if not tp1_hit and candle.open <= tp1:
                gap_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.open <= tp2:
                gap_targets.append((tp2, tp2_fraction, "TP2"))

        for price, fraction, reason in gap_targets:
            target_fill(candle, price, fraction, reason, at_open=True)

        # A TP2 filled at the candle open is known to occur before any later
        # intrabar movement. If a Chandelier level was already derived from
        # prior closed candles, the remaining runner becomes active immediately
        # after that deterministic open-time fill.
        if tp2_hit and not runner_active:
            runner_active = True
            if trail is not None:
                if direction == "LONG":
                    effective_stop = max(effective_stop, trail)
                    trail_breached_at_open = candle.open <= effective_stop
                else:
                    effective_stop = min(effective_stop, trail)
                    trail_breached_at_open = candle.open >= effective_stop
                if trail_breached_at_open:
                    fill(candle, candle.open, remaining, "STOP_GAP", at_open=True)
                    terminal_reason = "STOP_GAP"
                    exit_index = index
                    break

        pending_targets = []
        if direction == "LONG":
            if not tp1_hit and candle.high >= tp1:
                pending_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.high >= tp2:
                pending_targets.append((tp2, tp2_fraction, "TP2"))
            stop_touched = candle.low <= effective_stop
        else:
            if not tp1_hit and candle.low <= tp1:
                pending_targets.append((tp1, tp1_fraction, "TP1"))
            if not tp2_hit and candle.low <= tp2:
                pending_targets.append((tp2, tp2_fraction, "TP2"))
            stop_touched = candle.high >= effective_stop

        if stop_touched and pending_targets:
            fill(candle, effective_stop, remaining, "STOP_FIRST_AMBIGUOUS")
            terminal_reason = "STOP_FIRST_AMBIGUOUS"
            exit_index = index
            break
        if stop_touched:
            fill(candle, effective_stop, remaining, "TRAIL_STOP" if runner_active else "STOP")
            terminal_reason = "TRAIL_STOP" if runner_active else "STOP"
            exit_index = index
            break

        for price, fraction, reason in pending_targets:
            target_fill(candle, price, fraction, reason)
            if remaining == 0:
                terminal_reason = reason
                exit_index = index
                break
        if remaining == 0:
            break

        raw_trail = _chandelier_level(
            candles=candles,
            atr=atr22,
            index=index,
            direction=direction,
            length=policy.chandelier_length,
            multiplier=policy.chandelier_multiplier,
        )
        if raw_trail is not None:
            if trail is None:
                trail = raw_trail
            elif direction == "LONG":
                trail = max(trail, raw_trail)
            else:
                trail = min(trail, raw_trail)

        if tp2_hit:
            runner_active = True

    if remaining > 0:
        candle = candles[last_index]
        fill(candle, candle.close, remaining, "WINDOW_END")
        terminal_reason = "WINDOW_END"
        exit_index = last_index

    if abs(sum(fraction for fraction, _ in fills_raw) - D("1")) > D("0.0000001"):
        raise RuntimeError("MARC backtest trade did not close exactly one position")

    gross_r = _costed_r(
        direction=direction,
        entry=entry,
        stop=stop,
        fills=fills_raw,
        cost_bps_per_side=0.0,
    )
    base_net_r = _costed_r(
        direction=direction,
        entry=entry,
        stop=stop,
        fills=fills_raw,
        cost_bps_per_side=config.base_cost_bps_per_side,
    )
    stress_net_r = _costed_r(
        direction=direction,
        entry=entry,
        stop=stop,
        fills=fills_raw,
        cost_bps_per_side=config.stress_cost_bps_per_side,
    )
    return (
        BacktestTrade(
            symbol=candidate.symbol,
            timeframe=candidate.timeframe,
            direction=direction,
            source_signal_id=candidate.source_signal_id,
            entry_time=candles[entry_index].open_time,
            entry_price=float(entry),
            stop_loss=float(stop),
            exit_time=fills[-1].time,
            duration_bars=exit_index - entry_index + 1,
            fills=tuple(fills),
            gross_r=gross_r,
            base_net_r=base_net_r,
            stress_net_r=stress_net_r,
            tp1_hit=tp1_hit,
            tp2_hit=tp2_hit,
            terminal_reason=terminal_reason,
        ),
        exit_index,
    )


def backtest_window(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig | None = None,
    policy: MARCPolicy | None = None,
) -> BacktestWindowResult:
    """Run one standalone symbol/timeframe window with no overlapping positions."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("window timestamps must be timezone-aware")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end <= start:
        raise ValueError("end must be after start")

    selected_config = config or BacktestConfig()
    selected_policy = policy or MARCPolicy()
    selected_policy.cross_validity_bars(timeframe)
    if len(candles) < selected_policy.minimum_indicator_bars + 1:
        raise ValueError("not enough candles for MARC backtest")

    source = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=candles,
        captured_at=candles[-1].close_time,
        source="MARC_BACKTEST_DATA",
    )
    frames = build_indicator_frames(source, policy=selected_policy)
    atr22 = _wilder_atr(candles, selected_policy.chandelier_atr_period)

    last_index = max(
        (index for index, candle in enumerate(candles) if candle.open_time < end),
        default=-1,
    )
    if last_index < selected_policy.minimum_indicator_bars:
        raise ValueError("window has no evaluable candles")

    first_entry_index = next(
        (
            index
            for index, candle in enumerate(candles)
            if candle.open_time >= start
        ),
        len(candles),
    )
    index = max(selected_policy.minimum_indicator_bars - 1, first_entry_index - 1)
    engine = MARCSignalEngine(policy=selected_policy)
    trades: list[BacktestTrade] = []
    rejections: Counter[str] = Counter()
    candidate_count = 0

    while index < last_index:
        suffix_start = max(0, index - selected_config.scan_lookback + 1)
        suffix = frames[suffix_start : index + 1]
        probe = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe=timeframe,
            snapshot_id=f"probe:{symbol}:{timeframe}:{index}",
            snapshot_hash=f"probe:{index}",
            policy=selected_policy,
        )
        if not probe.trade_ready or not probe.fresh:
            index += 1
            continue

        snapshot_start = max(0, index - selected_config.snapshot_window + 1)
        snapshot_candles = candles[snapshot_start : index + 1]
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe=timeframe,
            candles=snapshot_candles,
            captured_at=snapshot_candles[-1].close_time,
            source="MARC_BACKTEST_CAUSAL",
        )
        decision = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe=timeframe,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            policy=selected_policy,
        )
        entry_index = index + 1
        entry_candle = candles[entry_index]
        if entry_candle.open_time < start:
            index += 1
            continue
        if entry_candle.open_time >= end:
            break

        candidate_count += 1
        plan = engine.build_entry_plan(
            snapshot,
            decision,
            entry_price=entry_candle.open,
        )
        if not plan.accepted or plan.candidate is None:
            rejections[plan.rejection_reason or "UNKNOWN_REJECTION"] += 1
            index += 1
            continue

        trade, exit_index = _simulate_trade(
            candles=candles,
            atr22=atr22,
            candidate=plan.candidate,
            entry_index=entry_index,
            last_index=last_index,
            config=selected_config,
            policy=selected_policy,
        )
        trades.append(trade)

        # A position is unique per symbol/timeframe. A setup confirmed at the
        # exit candle close may be considered for the following bar.
        index = max(index + 1, exit_index)

    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        candidate_count=candidate_count,
        rejected_plan_count=sum(rejections.values()),
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )
