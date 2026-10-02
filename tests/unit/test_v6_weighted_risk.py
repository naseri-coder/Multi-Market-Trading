"""Historical weighted-risk scenarios expressed with the current Risk contract."""

from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest
from app.modules.risk_engine.calculator import RiskCalculator

from tests.unit.test_risk_semantic_repair import candidate as current_candidate


def candidate(targets=(D("100.5"), D("103")), direction="LONG", witness=True):
    sign = D(1) if direction == "LONG" else D(-1)
    prices = tuple(D(100) + sign * (p - D(100)) for p in targets)
    result = current_candidate(
        direction=direction,
        stop=D(100) - sign,
        targets=prices,
        bar_high=D("99.5") if direction == "LONG" else D("101.5"),
        bar_low=D("98.5") if direction == "LONG" else D("100.5"),
    )
    if witness:
        result.rule_evidence += (
            NS(
                rule_id="ENG-V5-STRUCTURAL-TARGET",
                status="PASS",
                evidence=(
                    ("setup_type", "TEST"),
                    ("direction", direction),
                    ("fixed_r_fallback", "false"),
                    ("target_basis", "synthetic confirmed swing"),
                ),
            ),
        )
    return result


@pytest.fixture(autouse=True)
def context(monkeypatch):
    value = NS(regime="BULL_TREND", channel_quality="TIGHT")
    monkeypatch.setattr("app.modules.risk_engine.calculator.build_market_context", lambda _: value)
    return value


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_confirmed_far_target_does_not_invent_runner_objective(direction):
    score, metadata = RiskCalculator().calculate_with_breakdown(candidate(direction=direction))
    reward = metadata["plan_reward"]
    assert D(metadata["plan_rr"]) == D("1.5")
    assert reward["runner_fraction"] == "0.5"
    assert reward["runner_objective"] is None
    assert reward["runner_r"] == reward["weighted_runner_r"] == "0"
    assert reward["runner_policy"] == "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE"
    assert score == 93.25


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_no_farther_level_gives_runner_zero(direction):
    score, metadata = RiskCalculator().calculate_with_breakdown(
        candidate(targets=(D("100.5"),), direction=direction),
    )
    assert metadata["plan_rr"] == "0.0"
    assert metadata["plan_reward"]["runner_fraction"] == "1"
    assert metadata["plan_reward"]["weighted_runner_r"] == "0"
    assert metadata["plan_reward"]["initial_risk"] == "1"
    assert score == 64


def test_structural_witness_cannot_change_undefined_runner_reward():
    _, with_witness = RiskCalculator().calculate_with_breakdown(candidate(witness=True))
    _, without_witness = RiskCalculator().calculate_with_breakdown(candidate(witness=False))
    assert with_witness["plan_reward"] == without_witness["plan_reward"]


def test_range_uses_actual_fractions_without_runner(context):
    context.regime = "TRADING_RANGE"
    _, metadata = RiskCalculator().calculate_with_breakdown(candidate())
    assert D(metadata["plan_rr"]) == D("1.75")
    assert metadata["plan_reward"]["runner_fraction"] == "0.0"
