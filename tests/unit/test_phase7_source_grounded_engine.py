from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.brooks_core.source_grounded_engine import SourceGroundedPhase7Engine
from app.modules.market_data.entities import Candle, MarketSnapshot


def make_snapshot() -> MarketSnapshot:
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    candles = (
        Candle(
            open_time=start,
            close_time=start + timedelta(minutes=15),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1"),
        ),
        Candle(
            open_time=start + timedelta(minutes=15),
            close_time=start + timedelta(minutes=30),
            open=Decimal("104"),
            high=Decimal("108"),
            low=Decimal("92"),
            close=Decimal("103"),
            volume=Decimal("1"),
        ),
    )
    return MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=candles,
        captured_at=candles[-1].close_time + timedelta(seconds=1),
    )


@pytest.mark.asyncio
async def test_phase7a_engine_fails_closed_to_no_signal() -> None:
    result = await SourceGroundedPhase7Engine().evaluate(make_snapshot())
    assert result.decision == "NO_SIGNAL"
    assert result.entry_price is None
    assert "BR-010" in result.rule_ids
    assert any("EH-006" in reason for reason in result.reasoning)


@pytest.mark.asyncio
async def test_phase7a_engine_emits_auditable_rule_evidence() -> None:
    result = await SourceGroundedPhase7Engine().evaluate(make_snapshot())
    ids = {item.rule_id for item in result.rule_evidence}
    assert {"BR-010", "BR-011", "BR-012", "BR-019", "BR-020", "BR-027", "BR-029", "BR-030", "BR-035"} <= ids
