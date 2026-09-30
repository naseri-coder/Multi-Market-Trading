from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.modules.brooks_core.books_engine import BrooksBooksH2L2Engine
from app.modules.brooks_core.books_entities import (
    BarCountEvent,
    BookSecondEntryAssessment,
    BookSecondEntrySetup,
    BrooksContextAssessment,
    ContextMetrics,
)
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.structure_entities import ConfirmedSwing, SwingScanResult
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def snapshot():
    candles = []
    price = Decimal("100")
    for i in range(40):
        o = price
        c = price + Decimal("0.2")
        candles.append(Candle(
            open_time=BASE + timedelta(minutes=15*i),
            close_time=BASE + timedelta(minutes=15*(i+1)),
            open=o, high=c+Decimal("0.2"), low=o-Decimal("0.2"), close=c,
            volume=Decimal("1"),
        ))
        price = c
    return MarketSnapshot(
        exchange="binance", market_type="spot", symbol="BTCUSDT", timeframe="15m",
        candles=tuple(candles), captured_at=candles[-1].close_time, source="TEST",
    )


def context(regime="BULL_TREND"):
    return BrooksContextAssessment(
        regime=regime,
        always_in="LONG" if regime == "BULL_TREND" else "UNRESOLVED",
        reason="test",
        structure_direction="BULL_TREND",
        breakout_direction="LONG" if regime == "BULL_TREND" else "UNRESOLVED",
        breakout_streak=2,
        metrics=ContextMetrics(
            directional_bar_fraction=Decimal("0.7"),
            body_overlap_rate=Decimal("0.2"),
            bar_overlap_rate=Decimal("0.2"),
            adjusted_displacement=Decimal("0.6"),
            close_path_efficiency=Decimal("0.4"),
            ema_side_fraction=Decimal("0.8"),
            strong_bull_bar_count=8,
            strong_bear_bar_count=1,
            tight_range_like=False,
        ),
    )


@pytest.mark.asyncio
async def test_engine_reports_h2_but_keeps_trade_disabled_by_default():
    snap = snapshot()
    setup = BookSecondEntrySetup(
        direction="LONG", setup_type="H2_CONFIRMED", start_index=30,
        signal_index=39, entry_number=2, first_entry_index=34,
        second_excursion_index=37,
        events=(BarCountEvent(34,1,"H1"), BarCountEvent(39,2,"H2")),
    )
    assessment = BookSecondEntryAssessment(setup, "test", setup.events, 2)
    scan = SwingScanResult(
        swings=(ConfirmedSwing("HIGH", 30, 32, snap.candles[30].high),),
        ambiguous_indices=(), left_bars=2, right_bars=2,
    )
    engine = BrooksBooksH2L2Engine()
    with patch("app.modules.brooks_core.books_engine.assess_books_context", return_value=context()), \
         patch("app.modules.brooks_core.books_engine.confirm_swings_causally", return_value=scan), \
         patch("app.modules.brooks_core.books_engine.detect_book_second_entry", return_value=assessment):
        result = await engine.evaluate(snap)
    assert result.decision == "NO_SIGNAL"
    assert result.setup_type == "H2_CONFIRMED"
    assert "BB-RNG-17-HL-BAR-COUNT" in result.rule_ids


@pytest.mark.asyncio
async def test_engine_refuses_trading_range_continuation():
    snap = snapshot()
    engine = BrooksBooksH2L2Engine()
    with patch("app.modules.brooks_core.books_engine.assess_books_context", return_value=context("TRADING_RANGE")):
        result = await engine.evaluate(snap)
    assert result.decision == "NO_SIGNAL"
    assert result.setup_type is None
    assert any("trading-range" in text.lower() for text in result.reasoning)


@pytest.mark.asyncio
async def test_execution_when_explicitly_enabled_uses_signal_bar_stop_geometry():
    snap = snapshot()
    policy = BrooksBooksPolicy(enable_trade_decisions=True)
    setup = BookSecondEntrySetup(
        direction="LONG", setup_type="H2_CONFIRMED", start_index=30,
        signal_index=39, entry_number=2, first_entry_index=34,
        second_excursion_index=37,
        events=(BarCountEvent(34,1,"H1"), BarCountEvent(39,2,"H2")),
    )
    assessment = BookSecondEntryAssessment(setup, "test", setup.events, 2)
    scan = SwingScanResult(
        swings=(ConfirmedSwing("HIGH", 30, 32, snap.candles[30].high),),
        ambiguous_indices=(), left_bars=2, right_bars=2,
    )
    engine = BrooksBooksH2L2Engine(policy=policy)
    with patch("app.modules.brooks_core.books_engine.assess_books_context", return_value=context()), \
         patch("app.modules.brooks_core.books_engine.confirm_swings_causally", return_value=scan), \
         patch("app.modules.brooks_core.books_engine.detect_book_second_entry", return_value=assessment):
        result = await engine.evaluate(snap)
    assert result.decision == "LONG"
    assert result.stop_loss < snap.candles[39].low
    assert result.entry_price > snap.candles[39].high
    assert len(result.targets) == 2
