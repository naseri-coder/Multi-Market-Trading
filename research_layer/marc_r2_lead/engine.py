"""Causal MARC R2 Lead Reversal Transition (LRT).

LRT keeps FRT v0.1 intact and requires the 15m reversal to lead the latest
fully closed 30m regime instead of entering after 30m has already aligned.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
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

D = Decimal


def _build_frames(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    timeframe: str,
    policy: MARCPolicy,
    source_name: str,
):
    snapshot = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe=timeframe,
        candles=candles,
        captured_at=candles[-1].close_time,
        source=source_name,
    )
    return build_indicator_frames(snapshot, policy=policy)


def _latest_closed_htf_index(
    htf_candles: tuple[Candle, ...],
    *,
    signal_close_time: datetime,
) -> int | None:
    close_times = [candle.close_time for candle in htf_candles]
    index = bisect_right(close_times, signal_close_time) - 1
    return index if index >= 0 else None


def _htf_is_aligned(
    *,
    htf_frame,
    direction: str,
) -> bool | None:
    if htf_frame.ma7 is None or htf_frame.ma25 is None or htf_frame.ma99 is None:
        return None
    if direction == "LONG":
        return htf_frame.close > htf_frame.ma99 and htf_frame.ma7 > htf_frame.ma25
    if direction == "SHORT":
        return htf_frame.close < htf_frame.ma99 and htf_frame.ma7 < htf_frame.ma25
    raise ValueError("direction must be LONG or SHORT")


def backtest_lead_reversal_window(
    *,
    candles_15m: tuple[Candle, ...],
    candles_30m: tuple[Candle, ...],
    symbol: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig | None = None,
    policy: MARCPolicy | None = None,
) -> BacktestWindowResult:
    """Run the single pre-registered LRT setup using closed 15m/30m data only."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("window timestamps must be timezone-aware")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end <= start:
        raise ValueError("end must be after start")

    selected_config = config or BacktestConfig()
    selected_policy = policy or MARCPolicy()
    if len(candles_15m) < selected_policy.minimum_indicator_bars + 1:
        raise ValueError("not enough 15m candles for MARC R2 LRT")
    if len(candles_30m) < selected_policy.minimum_indicator_bars:
        raise ValueError("not enough 30m candles for MARC R2 LRT")

    frames_15m = _build_frames(
        candles=candles_15m,
        symbol=symbol,
        timeframe="15m",
        policy=selected_policy,
        source_name="MARC_R2_LRT_15M_DATA",
    )
    frames_30m = _build_frames(
        candles=candles_30m,
        symbol=symbol,
        timeframe="30m",
        policy=selected_policy,
        source_name="MARC_R2_LRT_30M_DATA",
    )
    atr22 = _wilder_atr(candles_15m, selected_policy.chandelier_atr_period)
    engine = MARCSignalEngine(policy=selected_policy)

    last_index = max(
        (i for i, candle in enumerate(candles_15m) if candle.open_time < end),
        default=-1,
    )
    first_entry = next(
        (
            i
            for i, candle in enumerate(candles_15m)
            if candle.open_time >= start
        ),
        len(candles_15m),
    )
    index = max(selected_policy.minimum_indicator_bars - 1, first_entry - 1)
    trades = []
    rejections: Counter[str] = Counter()
    candidates = 0

    while index < last_index:
        suffix_start = max(0, index - selected_config.scan_lookback + 1)
        suffix = frames_15m[suffix_start : index + 1]
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
        entry_candle = candles_15m[entry_index]
        if entry_candle.open_time < start:
            index += 1
            continue
        if entry_candle.open_time >= end:
            break
        candidates += 1

        cross_age = _latest_cross_age(frames_15m, index, probe.direction)
        if cross_age is None or cross_age > FRT_MAX_CROSS_AGE_BARS:
            rejections["LRT_CROSS_NOT_FRESH"] += 1
            index += 1
            continue

        if not _ma99_slope_is_opposed(frames_15m, index, probe.direction):
            rejections["LRT_MA99_SLOPE_NOT_OPPOSED"] += 1
            index += 1
            continue

        signal_close = candles_15m[index].close_time
        htf_index = _latest_closed_htf_index(
            candles_30m,
            signal_close_time=signal_close,
        )
        if htf_index is None:
            rejections["LRT_HTF_UNAVAILABLE"] += 1
            index += 1
            continue

        htf_aligned = _htf_is_aligned(
            htf_frame=frames_30m[htf_index],
            direction=probe.direction,
        )
        if htf_aligned is None:
            rejections["LRT_HTF_INDICATORS_UNAVAILABLE"] += 1
            index += 1
            continue
        if htf_aligned:
            rejections["LRT_HTF_ALREADY_ALIGNED"] += 1
            index += 1
            continue

        snapshot_start = max(0, index - selected_config.snapshot_window + 1)
        snapshot_candles = candles_15m[snapshot_start : index + 1]
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe="15m",
            candles=snapshot_candles,
            captured_at=snapshot_candles[-1].close_time,
            source="MARC_R2_LRT_CAUSAL",
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
            rejections[plan.rejection_reason or "LRT_PLAN_REJECTED"] += 1
            index += 1
            continue

        if (
            _risk_pct(plan.candidate.entry_price, plan.candidate.stop_loss)
            < FRT_MIN_INITIAL_RISK_PCT
        ):
            rejections["LRT_INITIAL_RISK_TOO_TIGHT"] += 1
            index += 1
            continue

        trade, exit_index = _simulate_trade(
            candles=candles_15m,
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
