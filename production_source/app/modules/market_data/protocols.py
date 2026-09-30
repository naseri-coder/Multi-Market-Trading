"""Exchange-independent provider interface."""

from typing import Protocol
from app.modules.market_data.entities import MarketSnapshot

class MarketDataProvider(Protocol):
    exchange: str
    async def get_snapshot(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        market_type: str,
    ) -> MarketSnapshot: ...
