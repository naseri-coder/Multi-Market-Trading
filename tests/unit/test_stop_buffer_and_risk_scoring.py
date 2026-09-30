from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.volatility import average_bar_range
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.signal_automation.entities import BrooksRuleEvidence

UTC = timezone.utc


def _snapshot() -> MarketSnapshot:
    start = datetime(2026, 9, 6, tzinfo=UTC)
    candles = []
    close = Decimal("100")
    for index in range(20):
        spread = Decimal("2") if index < 19 else Decimal("0.20")
        candle = Candle(
            start + timedelta(minutes=15 * index),
            start + timedelta(minutes=15 * (index + 1)),
            close,
            close + spread / 2,
            close - spread / 2,
            close,
            Decimal("100"),
        )
        candles.append(candle
        )
    return MarketSnapshot(
        "binance", "futures", "TEST", "15m", tuple(candles), candles[-1].close_time
    )


def test_average_bar_range_uses_recent_market_size():
    snapshot = _snapshot()
    average = average_bar_range(snapshot.candles[:-1], period=19)
    assert average == Decimal("2")


def test_tiny_signal_bar_uses_recent_market_stop_floor():
    snapshot = _snapshot()
    candidate = BrooksPatternCandidate(
        "LONG", "TEST", "BREAKOUT_PULLBACK", 19,
        ("reason one", "reason two"), ("R1",), "ENGINEERING_POLICY", 1, "ANY"
    )
    policy = BrooksFullCorePolicy(
        context=BrooksBooksPolicy(
            stop_recent_range_period=19,
            futures_tick_sizes=(("TEST", Decimal("0.01")),),
        ),
        enable_trade_decisions=True,
    )
    engine = BrooksTrilogyFullCoreEngine(policy=policy)
    entry, stop, _ = engine._execution_geometry(snapshot, candidate)
    assert entry - stop == Decimal("2")
    assert stop < snapshot.candles[-1].low - Decimal("0.01")


def _risk_candidate(stop_percent: Decimal):
    entry = Decimal("100")
    risk = entry * stop_percent / Decimal("100")
    stop = entry - risk
    target = entry + risk
    bar = SimpleNamespace(high=entry, low=stop)
    snapshot = SimpleNamespace(candles=(bar,))
    evidence = BrooksRuleEvidence(
        "TEST", "PASS", (1,),
        evidence=(("setup_type", "TEST"), ("direction", "LONG"), ("signal_index", "0")),
    )
    return SimpleNamespace(
        entry_price=entry,
        stop_loss=stop,
        targets=(target,),
        direction="LONG",
        snapshot=snapshot,
        setup_type="TEST",
        rule_evidence=(evidence,),
    )


def test_risk_score_does_not_reward_tighter_stop_when_rr_is_equal():
    calculator = RiskCalculator()
    scores = {
        calculator.calculate(_risk_candidate(stop_percent))
        for stop_percent in (
            Decimal("0.30"), Decimal("0.80"), Decimal("1.50"), Decimal("2.50"), Decimal("4.00")
        )
    }
    assert scores == {82.0}


def test_structural_points_accept_large_bar_money_management_stop():
    candidate = _risk_candidate(Decimal("1.00"))
    # Simulate a Chapter-29 large-bar money-management stop inside the signal bar.
    candidate.snapshot.candles[0].low = Decimal("95")
    candidate.stop_loss = Decimal("99")
    candidate.entry_price = Decimal("100")
    candidate.targets = (Decimal("101"),)
    assert RiskCalculator._structural_points(candidate) == Decimal("15")
    assert RiskCalculator().calculate(candidate) == 82.0
