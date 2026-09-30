from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock
import pytest

from app.modules.brooks_core.analyzer_adapter import BrooksCoreAnalyzerAdapter
from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence

def snapshot():
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    c = Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1"),
    )
    return MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=(c,),
        captured_at=start + timedelta(minutes=16),
    )

@pytest.mark.asyncio
async def test_tradeable_result_renders_chart(tmp_path: Path):
    engine = AsyncMock()
    engine.evaluate.return_value = BrooksEngineResult(
        decision="LONG",
        entry_price=Decimal("106"),
        stop_loss=Decimal("99"),
        targets=(Decimal("120"),),
        setup_type="H2",
        reasoning=("reviewed engine reason",),
        rule_ids=("BR-007",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR-007", "PASS", (11,)),),
        engine_version="engine-v1",
        rule_set_version="rules-v1",
        configuration_version="cfg-v1",
    )
    renderer = Mock()
    renderer.render.return_value = tmp_path / "x.png"

    s = snapshot()
    decision = await BrooksCoreAnalyzerAdapter(
        engine=engine,
        renderer=renderer,
        chart_directory=tmp_path,
    ).analyze(s)

    assert decision.decision == "LONG"
    assert decision.market_snapshot_id == s.snapshot_id
    assert decision.market_snapshot_hash == s.snapshot_hash
    assert decision.chart_path == str(tmp_path / "x.png")
    assert len(decision.source_signal_id) == 64
    renderer.render.assert_called_once()

@pytest.mark.asyncio
async def test_no_signal_skips_render(tmp_path: Path):
    engine = AsyncMock()
    engine.evaluate.return_value = BrooksEngineResult(
        decision="NO_SIGNAL",
        entry_price=None,
        stop_loss=None,
        targets=(),
        setup_type=None,
        reasoning=("no trade",),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        engine_version="engine-v1",
        rule_set_version="rules-v1",
        configuration_version="cfg-v1",
    )
    renderer = Mock()
    decision = await BrooksCoreAnalyzerAdapter(
        engine=engine,
        renderer=renderer,
        chart_directory=tmp_path,
    ).analyze(snapshot())

    assert decision.decision == "NO_SIGNAL"
    assert decision.chart_path is None
    renderer.render.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_removes_only_stale_png_charts(tmp_path: Path):
    stale_chart = tmp_path / "stale.png"
    unrelated = tmp_path / "keep.txt"
    stale_chart.write_bytes(b"stale")
    unrelated.write_text("keep")

    engine = AsyncMock()
    engine.evaluate.return_value = BrooksEngineResult(
        decision="NO_SIGNAL",
        entry_price=None,
        stop_loss=None,
        targets=(),
        setup_type=None,
        reasoning=("no trade",),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        engine_version="engine-v1",
        rule_set_version="rules-v1",
        configuration_version="cfg-v1",
    )
    renderer = Mock()

    await BrooksCoreAnalyzerAdapter(
        engine=engine,
        renderer=renderer,
        chart_directory=tmp_path,
    ).analyze(snapshot())

    assert not stale_chart.exists()
    assert unrelated.read_text() == "keep"
    renderer.render.assert_not_called()
