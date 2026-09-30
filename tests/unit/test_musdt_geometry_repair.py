from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 9, 21, 17, 0, tzinfo=UTC)
ADVANCED = SimpleNamespace(measured_move_target=None, measured_move_direction="UNRESOLVED")


def bar(index, open_, high, low, close):
    opened = BASE + timedelta(minutes=15 * index)
    return Candle(opened, opened + timedelta(minutes=15), D(open_), D(high), D(low), D(close), D("1"))


def snapshot(symbol="MUSDT", direction="LONG"):
    candles = [bar(i, "1.4700", "1.4720", "1.4680", "1.4700") for i in range(20)]
    signal = (
        bar(20, "1.4643", "1.4846", "1.4627", "1.4632")
        if direction == "LONG"
        else bar(20, "1.4830", "1.4846", "1.4627", "1.4835")
    )
    candles.append(signal)
    return MarketSnapshot("binance", "futures", symbol, "15m", tuple(candles), signal.close_time, "MUSDT_REPRO")


def candidate(direction="LONG", reference=None):
    signal = snapshot(direction=direction).candles[-1]
    reference = reference or (signal.low if direction == "LONG" else signal.high)
    return BrooksPatternCandidate(
        direction, f"MICRO_DOUBLE_{direction}_ANTICIPATORY", "DOUBLE_TOP_BOTTOM_REVERSAL", 20,
        ("micro double", "anticipatory entry"), ("BROOKS-GAP-068",),
        "SOURCE_INTERPRETATION", 1, "REVERSAL_OR_TRANSITION",
        metadata=(("entry_method", "LIMIT_OR_MARKET_ANTICIPATION"),
                  ("entry_trigger_semantic", "MICRO_DOUBLE_SECOND_TEST_ANTICIPATION"),
                  ("entry_reference_price", str(reference)),
                  ("economic_opportunity_id", f"MICRO_DOUBLE:TEST:{direction}")),
    )


def geometry(symbol="MUSDT", direction="LONG", reference=None):
    return BrooksTrilogyFullCoreEngine()._execution_geometry_with_identity(
        snapshot(symbol, direction), candidate(direction, reference), ADVANCED
    )


def test_musdt_zero_cap_uses_positive_structural_risk():
    entry, stop, targets, stop_basis, *_ = geometry()
    assert entry == D("1.4627")
    assert stop == D("1.4623")
    assert stop_basis == "setup_or_pullback_low_plus_recent_volatility_buffer"
    assert targets and all(target > entry for target in targets)


def test_musdt_quantization_does_not_collapse_prices():
    entry, stop, targets, *_ = geometry()
    tick = D("0.0001000")
    assert entry - stop >= tick
    assert all(target - entry >= tick for target in targets)


def test_short_boundary_is_directionally_symmetric():
    entry, stop, targets, stop_basis, *_ = geometry(direction="SHORT")
    assert entry == D("1.4846")
    assert stop == D("1.4850")
    assert stop_basis == "setup_or_pullback_high_plus_recent_volatility_buffer"
    assert targets and all(target < entry for target in targets)


def test_existing_positive_large_signal_cap_is_unchanged():
    plan = geometry(reference=D("1.4700"))
    assert plan[0] == D("1.4700")
    assert plan[1] == D("1.46489")
    assert plan[3] == "large_signal_money_management_cap"


def test_structurally_invalid_geometry_still_fails_closed():
    with pytest.raises(ValueError, match="invalid V5 risk geometry"):
        geometry(reference=D("1.4500"))


@pytest.mark.parametrize("symbol", ["MUSDT", "SUIUSDT", "1000SHIBUSDT"])
def test_zero_cap_guard_is_generic_not_symbol_specific(symbol):
    entry, stop, targets, *_ = geometry(symbol=symbol)
    assert stop < entry
    assert targets and all(target > entry for target in targets)
