"""Causal MARC R2 Fresh Reversal Lead hypothesis.

The frozen FRT v0.1 entry is retained. A candidate is accepted only while the
latest fully closed 30m regime has not yet aligned with the new 15m direction.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from datetime import UTC, datetime

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.data import resample_15m_to_30m
from research_layer.marc_backtest.engine import (
    BacktestConfig,
    _simulate_trade,
    _wilder_atr,
)
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_pure.engine import (
    FRT_MAX_CROSS_AGE_BARS,
    FRT_MIN_INITIAL_RISK_PCT,
    _latest_cross_age,
    _ma99_slope_is_opposed,
    _risk_pct,
)


def _latest_closed_30m_alignment(
    *,
    candles_30m: tuple[Candle, ...],
    frames_30m,
    signal_close_time: datetime,
    direction: str,
) -> str:
    close_times = [candle.close_time for candle in candles_30m]
    index = bisect_right(close_times, signal_close_time) - 1
    if index < 0:
        return "UNAVAILABLE"
    frame = frames_30m[index]
    if frame.ma7 is None or frame.ma25 is None or frame.ma99 is None:
        return "UNAVAILABLE"

    if frame.close > frame.ma99 and frame.ma7 > frame.ma25:
        state = "BULL"
    elif frame.close < frame.ma99 and frame.ma7 < frame.ma25:
        state = "BEAR"
    else:
        state = "MIXED"

    if state == "MIXED":
        return "MIXED"
    if (direction == "LONG" and state == "BULL") or (
        direction == "SHORT" and state == "BEAR"
    ):
        return "ALIGNED"
    return "OPPOSED"


def backtest_frt_lead_reversal_window(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig | None = None,
    policy: MARCPolicy | None = None,
) -> BacktestWindowResult:
    """Run FRT v0.1 plus the single 30m-not-yet-aligned condition."""
    if timeframe != "15m":
        raise ValueError("MARC R2 FRT Lead is a 15m-only research setup")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("window timestamps must be timezone-aware")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end <= start:
        raise ValueError("end must be after start")

    selected_config = config or BacktestConfig()
    selected_policy = policy or MARCPolicy()
    if len(candles) < selected_policy.minimum_indicator_bars + 1:
        raise ValueError("not enough candles for MARC R2 FRT Lead")

    source = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe="15m",
        candles=candles,
        captured_at=candles[-1].close_time,
        source="MARC_R2_FRT_LEAD_DATA",
    )
    frames = build_indicator_frames(source, policy=selected_policy)

    candles_30m = resample_15m_to_30m(candles)
    frames_30m = ()
    if len(candles_30m) >= selected_policy.minimum_indicator_bars:
        source_30m = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe="30m",
            candles=candles_30m,
            captured_at=candles_30m[-1].close_time,
            source="MARC_R2_FRT_LEAD_HTF",
        )
        frames_30m = build_indicator_frames(source_30m, policy=selected_policy)

    atr22 = _wilder_atr(candles, selected_policy.chandelier_atr_period)
    engine = MARCSignalEngine(policy=selected_policy)

    last_index = max(
        (i for i, candle in enumerate(candles) if candle.open_time < end),
        default=-1,
    )
    first_entry = next(
        (i for i, candle in enumerate(candles) if candle.open_time >= start),
        len(candles),
    )
    index = max(selected_policy.minimum_indicator_bars - 1, first_entry - 1)
    trades = []
    rejections: Counter[str] = Counter()
    candidates = 0

    while index < last_index:
        suffix_start = max(0, index - selected_config.scan_lookback + 1)
        suffix = frames[suffix_start : index + 1]
        probe = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe="15m",
            snapshot_id=f"probe:{symbol}:15m:{index}",
            snapshot_hash=f"probe:{index}",
            policy=selected_policy,
        )
        if not probe.trade_ready or not probe.fresh or probe.direction is None:
            index += 1
            continue

        entry_index = index + 1
        entry_candle = candles[entry_index]
        if entry_candle.open_time < start:
            index += 1
            continue
        if entry_candle.open_time >= end:
            break
        candidates += 1

        cross_age = _latest_cross_age(frames, index, probe.direction)
        if cross_age is None or cross_age > FRT_MAX_CROSS_AGE_BARS:
            rejections["FRT_LEAD_CROSS_NOT_FRESH"] += 1
            index += 1
            continue
        if not _ma99_slope_is_opposed(frames, index, probe.direction):
            rejections["FRT_LEAD_MA99_SLOPE_NOT_OPPOSED"] += 1
            index += 1
            continue

        if not frames_30m:
            rejections["FRT_LEAD_30M_UNAVAILABLE"] += 1
            index += 1
            continue
        alignment = _latest_closed_30m_alignment(
            candles_30m=candles_30m,
            frames_30m=frames_30m,
            signal_close_time=candles[index].close_time,
            direction=probe.direction,
        )
        if alignment == "UNAVAILABLE":
            rejections["FRT_LEAD_30M_UNAVAILABLE"] += 1
            index += 1
            continue
        if alignment == "ALIGNED":
            rejections["FRT_LEAD_30M_ALREADY_ALIGNED"] += 1
            index += 1
            continue

        snapshot_start = max(0, index - selected_config.snapshot_window + 1)
        snapshot_candles = candles[snapshot_start : index + 1]
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe="15m",
            candles=snapshot_candles,
            captured_at=snapshot_candles[-1].close_time,
            source="MARC_R2_FRT_LEAD_CAUSAL",
        )
        decision = evaluate_indicator_frames(
            suffix,
            symbol=symbol.upper(),
            timeframe="15m",
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            policy=selected_policy,
        )
        plan = engine.build_entry_plan(
            snapshot,
            decision,
            entry_price=entry_candle.open,
        )
        if not plan.accepted or plan.candidate is None:
            rejections[plan.rejection_reason or "FRT_LEAD_PLAN_REJECTED"] += 1
            index += 1
            continue

        if (
            _risk_pct(plan.candidate.entry_price, plan.candidate.stop_loss)
            < FRT_MIN_INITIAL_RISK_PCT
        ):
            rejections["FRT_LEAD_INITIAL_RISK_TOO_TIGHT"] += 1
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
        index = max(index + 1, exit_index)

    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe="15m",
        start=start,
        end=end,
        candidate_count=candidates,
        rejected_plan_count=sum(rejections.values()),
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )
