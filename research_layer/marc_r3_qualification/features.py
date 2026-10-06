"""Causal entry-time regime features for frozen MARC FRT trades."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.data import split_contiguous_candles
from research_layer.marc_backtest.entities import BacktestTrade

D = Decimal

ATR_PERCENTILE_LOOKBACK_BARS = 30 * 24 * 4
EFFICIENCY_LOOKBACK_BARS = 20
EFFICIENCY_TREND_THRESHOLD = D("0.35")


@dataclass(frozen=True, slots=True)
class QualifiedFRTTrade:
    symbol: str
    entry_time: datetime
    direction: str
    regime_cell: str
    volatility_bucket: str
    atr_percentile: float
    structure_bucket: str
    efficiency_ratio: float
    initial_risk_pct: float
    gross_r: float
    base_net_r: float
    stress_net_r: float
    source_signal_id: str


def _volatility_bucket(rank: Decimal) -> str:
    if rank < D("0.3333333333333333"):
        return "LOW"
    if rank > D("0.6666666666666667"):
        return "HIGH"
    return "MID"


def _efficiency_ratio(candles: tuple[Candle, ...], index: int) -> Decimal | None:
    if index < EFFICIENCY_LOOKBACK_BARS:
        return None
    start = index - EFFICIENCY_LOOKBACK_BARS
    displacement = abs(candles[index].close - candles[start].close)
    path = D("0")
    for cursor in range(start + 1, index + 1):
        path += abs(candles[cursor].close - candles[cursor - 1].close)
    if path <= 0:
        return D("0")
    return displacement / path


def _segment_features(
    *,
    candles: tuple[Candle, ...],
    symbol: str,
    policy: MARCPolicy,
) -> tuple[tuple[Candle, ...], tuple]:
    snapshot = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol=symbol.upper(),
        timeframe="15m",
        candles=candles,
        captured_at=candles[-1].close_time,
        source="MARC_R3_QUALIFICATION_FEATURES",
    )
    return candles, build_indicator_frames(snapshot, policy=policy)


def annotate_frt_trades(
    *,
    candles: tuple[Candle, ...],
    trades: tuple[BacktestTrade, ...],
    symbol: str,
    policy: MARCPolicy | None = None,
) -> tuple[QualifiedFRTTrade, ...]:
    """Annotate trades using only information closed before their entry open."""
    selected_policy = policy or MARCPolicy()
    segments = [
        _segment_features(candles=segment, symbol=symbol, policy=selected_policy)
        for segment in split_contiguous_candles(candles, timeframe="15m")
        if len(segment) >= selected_policy.minimum_indicator_bars
    ]

    by_entry = {trade.entry_time: trade for trade in trades}
    output: list[QualifiedFRTTrade] = []

    for segment, frames in segments:
        opens = [candle.open_time for candle in segment]
        matching_times = sorted(time for time in by_entry if opens[0] <= time <= opens[-1])
        for entry_time in matching_times:
            entry_index = bisect_left(opens, entry_time)
            if entry_index >= len(opens) or opens[entry_index] != entry_time:
                continue
            confirmation_index = entry_index - 1
            if confirmation_index <= ATR_PERCENTILE_LOOKBACK_BARS:
                continue
            frame = frames[confirmation_index]
            if frame.atr14 is None or frame.close <= 0:
                continue

            current_atr_pct = frame.atr14 / frame.close
            history: list[Decimal] = []
            start = confirmation_index - ATR_PERCENTILE_LOOKBACK_BARS
            for cursor in range(start, confirmation_index):
                prior = frames[cursor]
                if prior.atr14 is None or prior.close <= 0:
                    continue
                history.append(prior.atr14 / prior.close)
            if len(history) != ATR_PERCENTILE_LOOKBACK_BARS:
                continue

            rank = D(sum(value <= current_atr_pct for value in history)) / D(len(history))
            vol = _volatility_bucket(rank)
            efficiency = _efficiency_ratio(segment, confirmation_index)
            if efficiency is None:
                continue
            structure = (
                "TREND"
                if efficiency >= EFFICIENCY_TREND_THRESHOLD
                else "CHOP"
            )
            trade = by_entry[entry_time]
            risk_pct = abs(D(str(trade.entry_price)) - D(str(trade.stop_loss))) / D(
                str(trade.entry_price)
            )
            output.append(
                QualifiedFRTTrade(
                    symbol=symbol.upper(),
                    entry_time=trade.entry_time,
                    direction=trade.direction,
                    regime_cell=f"{vol}_{structure}",
                    volatility_bucket=vol,
                    atr_percentile=float(rank),
                    structure_bucket=structure,
                    efficiency_ratio=float(efficiency),
                    initial_risk_pct=float(risk_pct),
                    gross_r=trade.gross_r,
                    base_net_r=trade.base_net_r,
                    stress_net_r=trade.stress_net_r,
                    source_signal_id=trade.source_signal_id,
                )
            )

    output.sort(key=lambda item: (item.entry_time, item.symbol, item.source_signal_id))
    if len(output) != len(trades):
        missing = len(trades) - len(output)
        raise RuntimeError(
            f"MARC R3 feature coverage incomplete for {symbol}: missing={missing}"
        )
    return tuple(output)
