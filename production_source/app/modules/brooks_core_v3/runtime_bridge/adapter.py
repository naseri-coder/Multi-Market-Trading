"""Adapter from the deployed canonical market-data contract to Phase-3 domain types."""

from __future__ import annotations

from app.modules.brooks_core_v3.domain.models import Candle as DomainCandle
from app.modules.brooks_core_v3.domain.models import MarketSnapshot as DomainMarketSnapshot
from app.modules.market_data.entities import MarketSnapshot


def to_domain_snapshot(snapshot: MarketSnapshot) -> DomainMarketSnapshot:
    source = f"{snapshot.exchange}:{snapshot.market_type}:{snapshot.source}"
    candles = tuple(
        DomainCandle(
            open_time=candle.open_time,
            close_time=candle.close_time,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            is_closed=True,
            source=source,
        )
        for candle in snapshot.candles
    )
    return DomainMarketSnapshot(
        market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        candles=candles,
        as_of=snapshot.captured_at,
        last_closed_candle_time=snapshot.candles[-1].close_time,
        data_version="canonical-market-data-v1",
    )
