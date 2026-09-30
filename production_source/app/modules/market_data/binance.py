"""Binance Spot public REST adapter."""

from datetime import UTC, datetime
from decimal import Decimal
import httpx

from app.modules.market_data.entities import Candle, MarketSnapshot, validate_candle_sequence
from app.modules.market_data.errors import (
    InsufficientClosedCandlesError,
    MarketDataResponseError,
    UnsupportedTimeframeError,
)
from app.modules.market_data.http import AsyncJsonHttpClient

BINANCE_TIMEFRAMES = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
    "1d": "1d", "1w": "1w",
}

def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)

class BinanceSpotMarketDataProvider:
    exchange = "binance"

    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self.http = AsyncJsonHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        self.clock = clock

    async def get_snapshot(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        market_type: str,
    ) -> MarketSnapshot:
        if market_type != "spot":
            raise ValueError("BinanceSpotMarketDataProvider supports spot only")
        interval = BINANCE_TIMEFRAMES.get(timeframe)
        if interval is None:
            raise UnsupportedTimeframeError(timeframe)
        if not 2 <= limit <= 999:
            raise ValueError("limit must be between 2 and 999")

        captured_at = self.clock()
        try:
            payload = await self.http.get_json(
                "/api/v3/klines",
                params={
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": limit + 1,
                    "endTime": int(captured_at.timestamp() * 1000) - 1,
                },
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataResponseError("Binance kline request failed") from exc

        if not isinstance(payload, list):
            raise MarketDataResponseError("Binance response must be a list")

        candles = []
        try:
            for row in payload:
                if not isinstance(row, list) or len(row) < 7:
                    raise MarketDataResponseError("malformed Binance kline")
                close_time = _dt(int(row[6]))
                if close_time > captured_at:
                    continue
                candles.append(
                    Candle(
                        open_time=_dt(int(row[0])),
                        close_time=close_time,
                        open=Decimal(str(row[1])),
                        high=Decimal(str(row[2])),
                        low=Decimal(str(row[3])),
                        close=Decimal(str(row[4])),
                        volume=Decimal(str(row[5])),
                    )
                )
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise MarketDataResponseError("unable to normalize Binance klines") from exc

        if len(candles) < limit:
            raise InsufficientClosedCandlesError(
                f"requested {limit}, received {len(candles)} closed candles"
            )
        selected = tuple(candles[-limit:])
        validate_candle_sequence(selected, timeframe=timeframe)
        snapshot = MarketSnapshot(
            exchange=self.exchange,
            market_type="spot",
            symbol=symbol.upper(),
            timeframe=timeframe,
            candles=selected,
            captured_at=captured_at,
        )
        snapshot.assert_fresh(now=captured_at)
        return snapshot

    async def aclose(self) -> None:
        await self.http.aclose()
