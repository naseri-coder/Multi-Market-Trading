"""Event-probability diagnostics remain separate from current weighted Risk."""

from decimal import Decimal as D

from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.signal_intelligence.probability import _current_trade_math

from tests.unit.test_v6_weighted_risk import candidate


def test_legacy_event_payoff_is_not_relabelled_as_weighted_plan_reward(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.modules.risk_engine.calculator.build_market_context",
        lambda _: SimpleNamespace(regime="BULL_TREND", channel_quality="TIGHT"),
    )
    c = candidate()
    risk, diagnostic_reward = _current_trade_math(c)
    _, metadata = RiskCalculator().calculate_with_breakdown(c)
    assert risk == 1.0
    assert diagnostic_reward == 0.5
    assert D(metadata["plan_rr"]) == D("1.5")


def test_historical_probability_zero_risk_geometry_has_no_payoff():
    c = candidate()
    c.stop_loss = c.entry_price
    assert _current_trade_math(c) == (None, None)
