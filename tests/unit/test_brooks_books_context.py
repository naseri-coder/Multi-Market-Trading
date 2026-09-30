from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.brooks_core.structure_entities import StructureEvaluation, SwingScanResult
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def mk_candle(i, o, h, l, c):
    return Candle(
        open_time=BASE + timedelta(minutes=15 * i),
        close_time=BASE + timedelta(minutes=15 * (i + 1)),
        open=Decimal(str(o)), high=Decimal(str(h)), low=Decimal(str(l)), close=Decimal(str(c)),
        volume=Decimal("1"),
    )


def snapshot(candles):
    return MarketSnapshot(
        exchange="binance", market_type="spot", symbol="BTCUSDT", timeframe="15m",
        candles=tuple(candles), captured_at=candles[-1].close_time, source="TEST",
    )


def test_two_strong_followthrough_bars_can_establish_bull_context():
    candles = []
    price = Decimal("100")
    for i in range(38):
        o = price
        c = price + Decimal("0.15") if i % 2 == 0 else price - Decimal("0.05")
        candles.append(mk_candle(i, o, max(o, c)+Decimal("0.20"), min(o, c)-Decimal("0.20"), c))
        price = c
    candles.append(mk_candle(38, price, price+Decimal("2.1"), price-Decimal("0.1"), price+Decimal("2.0")))
    price += Decimal("2.0")
    candles.append(mk_candle(39, price, price+Decimal("2.1"), price-Decimal("0.1"), price+Decimal("2.0")))

    ambiguous = StructureEvaluation("AMBIGUOUS", "test unresolved")
    with patch("app.modules.brooks_core.context_classifier.evaluate_br031_structure", return_value=ambiguous):
        result = assess_books_context(snapshot(candles), policy=BrooksBooksPolicy())
    assert result.regime == "BULL_TREND"
    assert result.always_in == "LONG"
    assert result.breakout_streak >= 2


def test_opposite_strong_breakout_against_bull_structure_is_transition():
    candles = []
    price = Decimal("100")
    for i in range(38):
        c = price + Decimal("0.1")
        candles.append(mk_candle(i, price, c+Decimal("0.15"), price-Decimal("0.15"), c))
        price = c
    candles.append(mk_candle(38, price, price+Decimal("0.1"), price-Decimal("2.1"), price-Decimal("2.0")))
    price -= Decimal("2.0")
    candles.append(mk_candle(39, price, price+Decimal("0.1"), price-Decimal("2.1"), price-Decimal("2.0")))

    bull = StructureEvaluation("BULL_TREND", "test bull")
    with patch("app.modules.brooks_core.context_classifier.evaluate_br031_structure", return_value=bull):
        result = assess_books_context(snapshot(candles), policy=BrooksBooksPolicy())
    assert result.regime == "TRANSITION"
    assert result.breakout_direction == "SHORT"


def test_overlapping_small_bodies_without_breakout_is_trading_range():
    candles = []
    for i in range(40):
        o = Decimal("100") + Decimal("0.03") * Decimal(i % 3)
        c = Decimal("100.04") if i % 2 == 0 else Decimal("99.98")
        candles.append(mk_candle(i, o, Decimal("100.40"), Decimal("99.60"), c))
    ambiguous = StructureEvaluation("AMBIGUOUS", "test unresolved")
    with patch("app.modules.brooks_core.context_classifier.evaluate_br031_structure", return_value=ambiguous):
        result = assess_books_context(snapshot(candles), policy=BrooksBooksPolicy())
    assert result.regime == "TRADING_RANGE"
    assert result.metrics.tight_range_like is True
