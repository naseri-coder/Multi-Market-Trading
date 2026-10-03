"""Current research contract invariants, with entirely synthetic inputs."""

from dataclasses import replace
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.brooks_core.engine_contract import TargetPlanLifecycle
from app.modules.risk_engine.service import RiskEngineService
from research_layer.current_risk_contract import read_current_risk


@pytest.fixture
def current_candidate(monkeypatch):
    context = SimpleNamespace(regime="BULL_TREND", channel_quality="UNRESOLVED")
    monkeypatch.setattr(
        "app.modules.risk_engine.calculator.build_market_context", lambda _: context
    )
    monkeypatch.setattr("research_layer.current_risk_contract.build_market_context", lambda _: context)
    return SimpleNamespace(
        direction="LONG", entry_price=Decimal("100"), stop_loss=Decimal("99"),
        targets=(Decimal("100.5"), Decimal("103")),
        target_plan_lifecycle=TargetPlanLifecycle("synthetic-plan", "TREND_TRADE", "LONG", 0),
        snapshot=SimpleNamespace(candles=(SimpleNamespace(high=Decimal("99.5"),
                                                       low=Decimal("98.5")),)),
        rule_ids=(), rule_evidence=(), setup_type="SYNTHETIC",
        reversal_outcome_context=None,
    )


def test_current_plan_public_allocation_invariants(current_candidate):
    view = read_current_risk(current_candidate, need_trade_plan=True)
    assert view["plan_rr"] == Decimal("1.5")
    assert all(view["invariants"].values())
    assert dict(view["trade_management_plan"].target_exit_fractions) == {
        1: Decimal("0"), 2: Decimal("0.5")
    }
    assert view["plan_breakdown"]["runner_objective"] is None
    assert view["plan_breakdown"]["runner_r"] == "0"
    assert view["plan_breakdown"]["weighted_runner_r"] == "0"


def test_supplied_assessment_is_reused_without_evaluation(current_candidate, monkeypatch):
    risk = RiskEngineService().evaluate(current_candidate)
    def forbidden(_self, _candidate):
        raise AssertionError("duplicate assessment")
    monkeypatch.setattr(RiskEngineService, "evaluate", forbidden)
    view = read_current_risk(current_candidate, assessment=risk)
    assert view["assessment"] is risk
    assert view["trade_management_plan"] is None


@pytest.mark.parametrize("field,value", [
    ("runner_policy", "invalid"), ("runner_objective", "103"),
    ("runner_r", "3"), ("weighted_runner_r", "1.5"),
])
def test_runner_metadata_mutation_fails_closed(current_candidate, field, value):
    risk = RiskEngineService().evaluate(current_candidate)
    risk = replace(risk, metadata=deepcopy(risk.metadata))
    risk.metadata["risk_semantic_breakdown"]["plan_reward"][field] = value
    with pytest.raises(ValueError, match="CURRENT_RISK_RUNNER_POLICY_MISMATCH"):
        read_current_risk(current_candidate, assessment=risk)


def test_geometry_mutation_is_rejected(current_candidate):
    current_candidate.targets = (Decimal("99.5"), Decimal("103"))
    with pytest.raises(ValueError, match="CURRENT_RISK_INVALID_GEOMETRY"):
        read_current_risk(current_candidate)


def test_missing_current_context_is_rejected(current_candidate):
    current_candidate.target_plan_lifecycle = None
    with pytest.raises(ValueError, match="CURRENT_RISK_CONTEXT_REQUIRED"):
        read_current_risk(current_candidate)


def test_independent_allocation_check_rejects_corrupted_contribution(current_candidate):
    risk = RiskEngineService().evaluate(current_candidate)
    risk.metadata["risk_semantic_breakdown"]["plan_reward"]["target_contributions"][1][
        "allocation_fraction"
    ] = "1"
    with pytest.raises(ValueError, match="CURRENT_RISK_PLAN_MISMATCH"):
        read_current_risk(current_candidate, assessment=risk)
