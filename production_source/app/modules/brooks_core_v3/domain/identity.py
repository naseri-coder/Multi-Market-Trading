"""Deterministic identity helpers for the Phase-3 snapshot boundary."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from .models import Candle, MarketSnapshot


def _candle_payload(candle: Candle) -> dict[str, object]:
    return {
        "open_time": candle.open_time.astimezone(UTC).isoformat(),
        "close_time": candle.close_time.astimezone(UTC).isoformat(),
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
        "is_closed": candle.is_closed,
        "source": candle.source,
    }


def _series_payload(series: tuple[tuple[str, tuple[Candle, ...]], ...]):
    return [
        [timeframe, [_candle_payload(candle) for candle in candles]]
        for timeframe, candles in series
    ]

def snapshot_hash(
    *,
    symbol: str,
    timeframe: str,
    candles: tuple[Candle, ...],
    as_of: datetime,
    data_version: str,
    higher_timeframe_series: tuple[tuple[str, tuple[Candle, ...]], ...] = (),
    lower_timeframe_series: tuple[tuple[str, tuple[Candle, ...]], ...] = (),
) -> str:
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": [_candle_payload(candle) for candle in candles],
        "as_of": as_of.astimezone(UTC).isoformat(),
        "data_version": data_version,
        "higher_timeframe_series": _series_payload(higher_timeframe_series),
        "lower_timeframe_series": _series_payload(lower_timeframe_series),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_market_snapshot(
    *,
    symbol: str,
    timeframe: str,
    candles: tuple[Candle, ...],
    as_of: datetime,
    data_version: str,
    higher_timeframe_series: tuple[tuple[str, tuple[Candle, ...]], ...] = (),
    lower_timeframe_series: tuple[tuple[str, tuple[Candle, ...]], ...] = (),
) -> MarketSnapshot:
    if not candles:
        raise ValueError("snapshot requires at least one candle")
    digest = snapshot_hash(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        as_of=as_of,
        data_version=data_version,
        higher_timeframe_series=higher_timeframe_series,
        lower_timeframe_series=lower_timeframe_series,
    )
    last_closed = candles[-1].close_time
    last_close_ms = int(last_closed.timestamp() * 1000)
    snapshot_id = f"{symbol}:{timeframe}:{last_close_ms}:{digest[:16]}"
    return MarketSnapshot(
        market_snapshot_id=snapshot_id,
        market_snapshot_hash=digest,
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        as_of=as_of,
        last_closed_candle_time=last_closed,
        data_version=data_version,
        higher_timeframe_series=higher_timeframe_series,
        lower_timeframe_series=lower_timeframe_series,
    )
