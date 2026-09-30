"""Phase-3 ports owned by the Brooks Core v3 domain."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from .models import Candle, Signal


class MarketDataProvider(Protocol):
    def provider_id(self) -> str: ...

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]: ...

    async def get_latest_closed_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> Sequence[Candle]: ...


class SignalPublisher(Protocol):
    async def publish(self, signal: Signal, chart_artifact_ref: str | None) -> object: ...
