"""Causal setup-morphology features for frozen MARC FRT shadow trades."""

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
from research_layer.marc_r2_pure.engine import _cross_direction

D = Decimal

IMPULSE_LOOKBACK_BARS = 3
IMPULSE_MIN_ATR = D("0.50")
SPREAD_MIN_ATR = D("0.10")
SPREAD_EXPANSION_LOOKBACK_BARS = 2
CONFIRMATION_CLOSE_LOCATION_MIN = D("0.65")
MAX_EXTENSION_ATR = D("0.75")


@dataclass(frozen=True, slots=True)
class MorphologyFRTTrade:
    symbol: str
    entry_time: datetime
    direction: str
    morphology_class: str
    quality_score: int
    impulse_3_atr: float
    spread_atr: float
    spread_expansion_2_atr: float
    confirmation_close_location: float
    confirmation_bodies_directional: bool
    extension_atr: float
    initial_risk_pct: float
    gross_r: float
    base_net_r: float
    stress_net_r: float
    source_signal_id: str


def _sign(direction: str) -> D:
    if direction == "LONG":
        return D("1")
    if direction == "SHORT":
        return D("-1")
    raise ValueError("direction must be LONG or SHORT")


def _latest_cross_index(frames, index: int, direction: str) -> int | None:
    for cursor in range(index, 0, -1):
        if _cross_direction(frames[cursor - 1], frames[cursor]) == direction:
            return cursor
    return None


def _directional_close_location(candle: Candle, direction: str) -> D:
    span = candle.high - candle.low
    if span <= 0:
        return D("0.5")
    if direction == "LONG":
        return (candle.close - candle.low) / span
    if direction == "SHORT":
        return (candle.high - candle.close) / span
    raise ValueError("direction must be LONG or SHORT")


def _body_is_directional(candle: Candle, direction: str) -> bool:
    if direction == "LONG":
        return candle.close > candle.open
    if direction == "SHORT":
        return candle.close < candle.open
    raise ValueError("direction must be LONG or SHORT")


def _morphology_class(direction: str, score: int) -> str:
    if score == 4:
        tier = "A"
    elif score == 3:
        tier = "B"
    else:
        tier = "C"
    return f"{direction}_{tier}"


def annotate_frt_morphology(
    *,
    candles: tuple[Candle, ...],
    trades: tuple[BacktestTrade, ...],
    symbol: str,
    policy: MARCPolicy | None = None,
) -> tuple[MorphologyFRTTrade, ...]:
    """Annotate every FRT trade from data known before the entry open."""
    selected_policy = policy or MARCPolicy()
    by_entry = {trade.entry_time: trade for trade in trades}
    output: list[MorphologyFRTTrade] = []

    for segment in split_contiguous_candles(candles, timeframe="15m"):
        if len(segment) < selected_policy.minimum_indicator_bars:
            continue
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol=symbol.upper(),
            timeframe="15m",
            candles=segment,
            captured_at=segment[-1].close_time,
            source="MARC_R4_MORPHOLOGY_FEATURES",
        )
        frames = build_indicator_frames(snapshot, policy=selected_policy)
        opens = [candle.open_time for candle in segment]
        matching = sorted(time for time in by_entry if opens[0] <= time <= opens[-1])

        for entry_time in matching:
            entry_index = bisect_left(opens, entry_time)
            if entry_index >= len(segment) or opens[entry_index] != entry_time:
                continue
            confirmation_index = entry_index - 1
            if confirmation_index < max(
                IMPULSE_LOOKBACK_BARS,
                SPREAD_EXPANSION_LOOKBACK_BARS,
                1,
            ):
                continue

            trade = by_entry[entry_time]
            direction = trade.direction
            sign = _sign(direction)
            frame = frames[confirmation_index]
            impulse_prior = frames[confirmation_index - IMPULSE_LOOKBACK_BARS]
            spread_prior = frames[
                confirmation_index - SPREAD_EXPANSION_LOOKBACK_BARS
            ]
            if (
                frame.atr14 is None
                or frame.atr14 <= 0
                or frame.ma7 is None
                or frame.ma25 is None
                or frame.ma99 is None
                or spread_prior.ma7 is None
                or spread_prior.ma25 is None
            ):
                continue

            cross_index = _latest_cross_index(frames, confirmation_index, direction)
            if cross_index is None:
                continue

            impulse = (
                sign * (frame.close - impulse_prior.close) / frame.atr14
            )
            spread_now = sign * (frame.ma7 - frame.ma25) / frame.atr14
            spread_before = sign * (
                spread_prior.ma7 - spread_prior.ma25
            ) / frame.atr14
            spread_expansion = spread_now - spread_before
            extension = sign * (frame.close - frame.ma99) / frame.atr14

            confirmation_candles = (
                segment[confirmation_index - 1],
                segment[confirmation_index],
            )
            close_location = sum(
                (
                    _directional_close_location(candle, direction)
                    for candle in confirmation_candles
                ),
                D("0"),
            ) / D("2")
            directional_bodies = all(
                _body_is_directional(candle, direction)
                for candle in confirmation_candles
            )

            score = 0
            if impulse >= IMPULSE_MIN_ATR:
                score += 1
            if spread_now >= SPREAD_MIN_ATR and spread_expansion > 0:
                score += 1
            if (
                directional_bodies
                and close_location >= CONFIRMATION_CLOSE_LOCATION_MIN
            ):
                score += 1
            if extension <= MAX_EXTENSION_ATR:
                score += 1

            entry = D(str(trade.entry_price))
            stop = D(str(trade.stop_loss))
            risk_pct = abs(entry - stop) / entry

            output.append(
                MorphologyFRTTrade(
                    symbol=symbol.upper(),
                    entry_time=trade.entry_time,
                    direction=direction,
                    morphology_class=_morphology_class(direction, score),
                    quality_score=score,
                    impulse_3_atr=float(impulse),
                    spread_atr=float(spread_now),
                    spread_expansion_2_atr=float(spread_expansion),
                    confirmation_close_location=float(close_location),
                    confirmation_bodies_directional=directional_bodies,
                    extension_atr=float(extension),
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
            f"MARC R4 morphology coverage incomplete for {symbol}: missing={missing}"
        )
    return tuple(output)
