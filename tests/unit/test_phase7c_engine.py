from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.modules.brooks_core.fundamentals_engine as module
from app.modules.brooks_core.fundamentals_engine import BrooksFundamentalsH2L2Engine
from app.modules.brooks_core.fundamentals_policy import FundamentalsExecutionPolicy
from app.modules.brooks_core.second_entry import SecondEntryAssessment, SecondEntrySetup
from app.modules.brooks_core.structure_entities import StructureEvaluation, SwingScanResult, ConfirmedSwing
from app.modules.market_data.entities import Candle, MarketSnapshot


def snapshot():
    start = datetime(2026, 9, 2, tzinfo=UTC)
    candles = []
    for i in range(25):
        base = Decimal("100") + Decimal(i) / Decimal("10")
        candles.append(
            Candle(
                open_time=start + timedelta(minutes=15 * i),
                close_time=start + timedelta(minutes=15 * (i + 1)),
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


def fake_scan():
    return SwingScanResult(
        swings=(
            ConfirmedSwing("HIGH", 5, 7, Decimal("105")),
            ConfirmedSwing("LOW", 8, 10, Decimal("98")),
            ConfirmedSwing("HIGH", 12, 14, Decimal("110")),
            ConfirmedSwing("LOW", 15, 17, Decimal("102")),
            ConfirmedSwing("HIGH", 18, 20, Decimal("115")),
        ),
        ambiguous_indices=(),
        left_bars=2,
        right_bars=2,
    )


@pytest.mark.asyncio
async def test_detected_setup_still_no_signal_by_default(monkeypatch):
    monkeypatch.setattr(module, "confirm_swings_causally", lambda *a, **k: fake_scan())
    monkeypatch.setattr(
        module,
        "evaluate_br031_structure",
        lambda scan: StructureEvaluation(
            direction="BULL_TREND",
            reason="HH/HL",
            supporting_swing_indices=(5, 8, 12, 15),
        ),
    )
    monkeypatch.setattr(
        module,
        "detect_second_entry",
        lambda *a, **k: SecondEntryAssessment(
            SecondEntrySetup(
                direction="LONG",
                setup_type="H2_CONFIRMED",
                start_index=18,
                signal_index=24,
                countertrend_legs=2,
                source_pages=(11,),
            ),
            "detected",
        ),
    )

    result = await BrooksFundamentalsH2L2Engine().evaluate(snapshot())
    assert result.decision == "NO_SIGNAL"
    assert result.setup_type == "H2_CONFIRMED"
    assert any("disabled by default" in item for item in result.reasoning)


@pytest.mark.asyncio
async def test_explicit_engineering_execution_can_emit_long(monkeypatch):
    monkeypatch.setattr(module, "confirm_swings_causally", lambda *a, **k: fake_scan())
    monkeypatch.setattr(
        module,
        "evaluate_br031_structure",
        lambda scan: StructureEvaluation(
            direction="BULL_TREND",
            reason="HH/HL",
            supporting_swing_indices=(5, 8, 12, 15),
        ),
    )
    monkeypatch.setattr(
        module,
        "detect_second_entry",
        lambda *a, **k: SecondEntryAssessment(
            SecondEntrySetup(
                direction="LONG",
                setup_type="H2_CONFIRMED",
                start_index=18,
                signal_index=24,
                countertrend_legs=2,
                source_pages=(11,),
            ),
            "detected",
        ),
    )

    engine = BrooksFundamentalsH2L2Engine(
        policy=FundamentalsExecutionPolicy(enable_trade_decisions=True)
    )
    result = await engine.evaluate(snapshot())
    assert result.decision == "LONG"
    assert result.entry_price > snapshot().candles[-1].high
    assert result.stop_loss < result.entry_price
    assert len(result.targets) == 2
    assert "ENG-EXEC-001" in result.rule_ids
