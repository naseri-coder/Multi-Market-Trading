"""Phase 8 read-only historical source protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.market_data.entities import Candle


class HistoricalCandleSource(Protocol):
    exchange: str

    async def get_closed_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        market_type: str,
        end_at: datetime,
    ) -> tuple[Candle, ...]: ...

    async def aclose(self) -> None: ...
