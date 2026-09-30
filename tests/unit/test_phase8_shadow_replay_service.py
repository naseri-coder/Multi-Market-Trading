from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.market_data.entities import Candle
from app.modules.shadow_replay.service import (
    CausalShadowReplayService,
    ShadowReplaySafetyError,
)


def candles(count=25):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    items = []
    for i in range(count):
        open_time = start + timedelta(minutes=15 * i)
        base = Decimal("100") + Decimal(i)
        items.append(
            Candle(
                open_time=open_time,
                close_time=open_time + timedelta(minutes=15),
                open=base,
                high=base + 2,
                low=base - 2,
                close=base + 1,
                volume=Decimal("10"),
            )
        )
    return tuple(items)


class RecordingEngine:
    def __init__(self):
        self.snapshots = []

    async def evaluate(self, snapshot):
        self.snapshots.append(snapshot)
        return BrooksEngineResult(
            decision="NO_SIGNAL",
            entry_price=None,
            stop_loss=None,
            targets=(),
            setup_type=None,
            reasoning=("no setup",),
            rule_ids=(),
            failed_rules=(),
            rule_evidence=(),
            engine_version="test-engine",
            rule_set_version="test-rules",
            configuration_version="test-config",
        )


@pytest.mark.asyncio
async def test_replay_is_causal_and_snapshot_hashes_are_deterministic():
    source = candles(25)

    engine1 = RecordingEngine()
    report1 = await CausalShadowReplayService(
        engine=engine1,
        window_size=20,
    ).replay(
        exchange="binance",
        market_type="spot",
        symbol="btcusdt",
        timeframe="15m",
        candles=source,
    )

    engine2 = RecordingEngine()
    report2 = await CausalShadowReplayService(
        engine=engine2,
        window_size=20,
    ).replay(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=source,
    )

    assert len(report1.observations) == 6
    assert [x.snapshot_hash for x in report1.observations] == [
        x.snapshot_hash for x in report2.observations
    ]

    for snapshot in engine1.snapshots:
        assert snapshot.captured_at == snapshot.candles[-1].close_time
        assert all(c.close_time <= snapshot.captured_at for c in snapshot.candles)
        assert snapshot.source == "SHADOW_REPLAY"


class TradeableEngine:
    async def evaluate(self, snapshot):
        return BrooksEngineResult(
            decision="LONG",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            targets=(Decimal("110"),),
            setup_type="H2_CONFIRMED",
            reasoning=("tradeable",),
            rule_ids=(),
            failed_rules=(),
            rule_evidence=(),
            engine_version="test-engine",
            rule_set_version="test-rules",
            configuration_version="test-config",
        )


@pytest.mark.asyncio
async def test_phase8_rejects_tradeable_engine_results():
    service = CausalShadowReplayService(
        engine=TradeableEngine(),
        window_size=20,
    )
    with pytest.raises(ShadowReplaySafetyError):
        await service.replay(
            exchange="binance",
            market_type="spot",
            symbol="BTCUSDT",
            timeframe="15m",
            candles=candles(20),
        )
