from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
import pytest

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.volatility import average_bar_range
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)

def _bar(i, low, high):
    opened = BASE + timedelta(minutes=15*i); mid=(low+high)/2
    return Candle(opened, opened+timedelta(minutes=15), mid, high, low, mid, Decimal("1"))

def _snap(size, symbol="BTCUSDT"):
    cs=[_bar(i, Decimal("95"), Decimal("105")) for i in range(20)]
    cs.append(_bar(20, Decimal("100")-size/2, Decimal("100")+size/2))
    return MarketSnapshot("binance","futures",symbol,"15m",tuple(cs),cs[-1].close_time,"TEST")

def _candidate(direction="LONG"):
    return BrooksPatternCandidate(direction, "TEST_"+direction, "BREAKOUT_PULLBACK", 20,
        ("r1","r2"), ("BB-RNG-29-SIGNAL-BAR-STOP",), "SOURCE_INTERPRETATION", 1, "ANY")

def test_average_bar_range_uses_recent_closed_bars():
    assert average_bar_range(_snap(Decimal("2")).candles[:20], period=20) == Decimal("10")

def test_normal_signal_bar_stop_uses_recent_volatility_buffer():
    e=BrooksTrilogyFullCoreEngine(); s=_snap(Decimal("10")); entry,stop,_=e._execution_geometry(s,_candidate())
    assert stop == s.candles[-1].low - Decimal("1.00")
    assert entry == s.candles[-1].high + Decimal("0.10")

def test_large_signal_bar_uses_money_management_fraction_inside_bar():
    e=BrooksTrilogyFullCoreEngine(); s=_snap(Decimal("25")); entry,stop,_=e._execution_geometry(s,_candidate())
    expected_risk=(entry-s.candles[-1].low)*Decimal("0.70")
    assert entry-stop == expected_risk
    assert stop > s.candles[-1].low

def test_tiny_signal_bar_cannot_shrink_stop_below_recent_standard_range():
    e=BrooksTrilogyFullCoreEngine(); s=_snap(Decimal("2")); entry,stop,_=e._execution_geometry(s,_candidate())
    assert entry-stop == Decimal("10")
    assert stop < s.candles[-1].low - Decimal("0.10")

def test_short_geometry_is_symmetric():
    e=BrooksTrilogyFullCoreEngine(); s=_snap(Decimal("10")); entry,stop,_=e._execution_geometry(s,_candidate("SHORT"))
    assert stop == s.candles[-1].high + Decimal("1.00")
    assert entry == s.candles[-1].low - Decimal("0.10")

def test_targets_are_structural_and_never_fixed_r_fallbacks():
    e=BrooksTrilogyFullCoreEngine(); s=_snap(Decimal("10"))
    advanced=SimpleNamespace(measured_move_target=None, measured_move_direction="UNRESOLVED")
    entry,stop,targets,_,basis=e._execution_geometry(s,_candidate(),advanced)
    assert targets == (Decimal("115"),)
    assert basis == "recent_structure_measured_move"
    assert all(t not in {entry+(entry-stop), entry+2*(entry-stop)} for t in targets)


def test_unknown_symbol_fails_closed_without_tick_guessing():
    e=BrooksTrilogyFullCoreEngine(); s=_snap(Decimal("10"), symbol="UNKNOWNUSDT")
    with pytest.raises(ValueError, match="tick-size metadata"):
        e._execution_geometry(s,_candidate())
