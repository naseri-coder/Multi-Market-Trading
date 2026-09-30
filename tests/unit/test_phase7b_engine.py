from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.brooks_core.phase7b_engine import Phase7BCausalStructureEngine
from app.modules.market_data.entities import Candle, MarketSnapshot


def make_snapshot():
    start = datetime(2026, 9, 2, tzinfo=UTC)
    candles = []
    for i in range(30):
        base = Decimal("100") + Decimal(i % 7)
        candles.append(
            Candle(
                open_time=start + timedelta(minutes=15*i),
                close_time=start + timedelta(minutes=15*(i+1)),
                open=base,
                high=base + Decimal("2"),
                low=base - Decimal("2"),
                close=base + Decimal("0.5"),
                volume=Decimal("1"),
            )
        )
    return MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time + timedelta(seconds=1),
    )


@pytest.mark.asyncio
async def test_phase7b_remains_fail_closed() -> None:
    result = await Phase7BCausalStructureEngine().evaluate(make_snapshot())
    assert result.decision == "NO_SIGNAL"
    assert result.rule_ids == ("BR-031",)
    assert any("Autonomous LONG/SHORT remains disabled" in r for r in result.reasoning)
