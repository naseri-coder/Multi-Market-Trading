import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.volatility import average_true_range
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def candle(i: int, low: Decimal, high: Decimal) -> Candle:
    opened = BASE + timedelta(minutes=15 * i)
    mid = (low + high) / Decimal("2")
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=15),
        open=mid,
        high=high,
        low=low,
        close=mid,
        volume=Decimal("10"),
    )


def candidate(index: int) -> BrooksPatternCandidate:
    return BrooksPatternCandidate(
        direction="LONG",
        setup_type="TEST_LONG",
        family="BREAKOUT_PULLBACK",
        signal_index=index,
        reasons=("r1", "r2"),
        source_rule_ids=("BB-RNG-29-SIGNAL-BAR-STOP",),
        taxonomy="SOURCE_INTERPRETATION",
        priority=1,
        context_required="ANY",
    )


def snapshot(signal_range: Decimal) -> MarketSnapshot:
    items = [candle(i, Decimal("95"), Decimal("105")) for i in range(20)]
    items.append(candle(20, Decimal("100") - signal_range / 2, Decimal("100") + signal_range / 2))
    return MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(items),
        captured_at=items[-1].close_time,
        source="PHASE82_SCENARIO",
    )


def old_stop(s: MarketSnapshot) -> Decimal:
    policy = BrooksFullCorePolicy().context
    bar = s.candles[-1]
    spread = bar.high - bar.low
    atr = average_true_range(s.candles, period=policy.atr_period)
    buffer = max(
        spread * policy.stop_buffer_fraction_of_signal_range, atr * policy.atr_stop_buffer_multiple
    )
    return bar.low - buffer


engine = BrooksTrilogyFullCoreEngine(policy=BrooksFullCorePolicy())
for name, size in (
    ("NORMAL", Decimal("10")),
    ("LARGE", Decimal("25")),
    ("TINY_DOJI", Decimal("2")),
):
    snap = snapshot(size)
    entry, stop, targets = engine._execution_geometry(snap, candidate(20))
    before = old_stop(snap)
    print(
        f"{name}|signal_range={size}|old_stop={before}|new_stop={stop}|entry={entry}|new_risk={entry - stop}|T1={targets[0]}"
    )
