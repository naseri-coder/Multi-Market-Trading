from __future__ import annotations

from decimal import Decimal
from typing import Any


class MarketRegimeAnalyzer:
    """
    Real market regime detector based on canonical MarketSnapshot candles.

    Detects:
    - TREND
    - RANGE
    - HIGH_VOLATILITY
    - LOW_VOLATILITY
    """

    def analyze(
        self,
        snapshot: Any,
    ) -> dict[str, Any]:

        candles = getattr(snapshot, "candles", None)

        if not candles or len(candles) < 20:
            return {
                "market_regime": "UNKNOWN",
                "reason": "Insufficient candles",
            }

        closes = [
            float(candle.close)
            for candle in candles
        ]

        highs = [
            float(candle.high)
            for candle in candles
        ]

        lows = [
            float(candle.low)
            for candle in candles
        ]

        recent_closes = closes[-20:]

        average_price = sum(recent_closes) / len(recent_closes)

        last_price = recent_closes[-1]

        price_change = (
            (last_price - recent_closes[0])
            / recent_closes[0]
        )

        volatility_values = []

        for high, low, close in zip(
            highs[-20:],
            lows[-20:],
            closes[-20:],
        ):
            if close:
                volatility_values.append(
                    (high - low) / close
                )

        volatility = (
            sum(volatility_values)
            /
            len(volatility_values)
        )

        trend_strength = abs(
            price_change
        )

        if volatility >= 0.02:
            regime = "HIGH_VOLATILITY"

        elif volatility <= 0.005:
            regime = "LOW_VOLATILITY"

        elif trend_strength >= 0.01:
            regime = "TREND"

        else:
            regime = "RANGE"

        return {
            "market_regime": regime,
            "volatility": round(volatility, 6),
            "trend_strength": round(trend_strength, 6),
            "last_price": last_price,
            "average_price": round(
                average_price,
                4,
            ),
        }
