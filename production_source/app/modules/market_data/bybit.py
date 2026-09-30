"""Bybit V5 public REST adapter."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import httpx

from app.modules.market_data.entities import (
    Candle, MarketSnapshot, TIMEFRAME_SECONDS, validate_candle_sequence
)
from app.modules.market_data.errors import (
    InsufficientClosedCandlesError,
    MarketDataResponseError,
    UnsupportedTimeframeError,
)
from app.modules.market_data.http import AsyncJsonHttpClient

BYBIT_TIMEFRAMES = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W",
}
BYBIT_MARKET_TYPES = {"spot", "linear", "inverse"}

def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)

class BybitMarketDataProvider:
    exchange = "bybit"

    def __init__(
        self,
        *,
        base_url: str = "https://api.bybit.com",
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
        interval = BYBIT_TIMEFRAMES.get(timeframe)
        if interval is None:
            raise UnsupportedTimeframeError(timeframe)
        if market_type not in BYBIT_MARKET_TYPES:
            raise ValueError("market_type must be spot, linear, or inverse")
        if not 2 <= limit <= 999:
            raise ValueError("limit must be between 2 and 999")

        captured_at = self.clock()
        try:
            payload = await self.http.get_json(
                "/v5/market/kline",
                params={
                    "category": market_type,
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": limit + 1,
                    "end": int(captured_at.timestamp() * 1000) - 1,
                },
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataResponseError("Bybit kline request failed") from exc

        if not isinstance(payload, dict) or payload.get("retCode") != 0:
            raise MarketDataResponseError("Bybit returned unsuccessful response")
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise MarketDataResponseError("malformed Bybit kline result")

        delta = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
        candles = []
        try:
            for row in reversed(result["list"]):
                if not isinstance(row, list) or len(row) < 6:
                    raise MarketDataResponseError("malformed Bybit kline")
                open_time = _dt(int(row[0]))
                close_time = open_time + delta
                if close_time > captured_at:
                    continue
                candles.append(
                    Candle(
                        open_time=open_time,
                        close_time=close_time,
                        open=Decimal(str(row[1])),
                        high=Decimal(str(row[2])),
                        low=Decimal(str(row[3])),
                        close=Decimal(str(row[4])),
                        volume=Decimal(str(row[5])),
                    )
                )
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise MarketDataResponseError("unable to normalize Bybit klines") from exc

        if len(candles) < limit:
            raise InsufficientClosedCandlesError(
                f"requested {limit}, received {len(candles)} closed candles"
            )
        selected = tuple(candles[-limit:])
        validate_candle_sequence(selected, timeframe=timeframe)
        snapshot = MarketSnapshot(
            exchange=self.exchange,
            market_type=market_type,
            symbol=symbol.upper(),
            timeframe=timeframe,
            candles=selected,
            captured_at=captured_at,
        )
        snapshot.assert_fresh(now=captured_at)
        return snapshot

    async def aclose(self) -> None:
        await self.http.aclose()
