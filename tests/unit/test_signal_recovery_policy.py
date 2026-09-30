from types import SimpleNamespace

from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import ProbabilityAssessment
from app.modules.signal_intelligence.service import SignalIntelligenceService


def probability(*, favorable: bool = False, calibrated: bool = True) -> ProbabilityAssessment:
    return ProbabilityAssessment(
        calibrated=calibrated,
        probability=0.57 if calibrated else None,
        empirical_win_rate=0.65 if calibrated else None,
        lower_bound=0.43 if calibrated else None,
        upper_bound=0.82 if calibrated else None,
        historical_reliability=0.61 if calibrated else 0.0,
        sample_size=20 if calibrated else 0,
        wins=13 if calibrated else 0,
        losses=7 if calibrated else 0,
        scope="DIRECTION_TIMEFRAME",
        break_even_probability=0.5 if calibrated else None,
        expected_value_r=-0.14 if calibrated else None,
        trader_equation_favorable=favorable,
    )


def quality_candidate():
    return SimpleNamespace(
        snapshot=None,
        rule_evidence=(
            BrooksRuleEvidence("BB-TRD-19-TREND-STRENGTH", "PASS", (1,)),
            BrooksRuleEvidence("BB-REV-15-ALWAYS-IN", "PASS", (1,)),
            BrooksRuleEvidence("BB-RNG-17-HL-BAR-COUNT", "PASS", (1,)),
        ),
    )


def test_signal_intelligence_requires_favorable_traders_equation():
    result = SignalIntelligenceService().evaluate(
        quality_candidate(), ai_score=90.0, risk_score=92.0,
        council_confidence=0.9, probability=probability(favorable=False),
    )
    assert result.approved is False
    assert result.metadata["trader_equation_favorable"] is False
    assert result.metadata["probability_calibrated"] is True
    assert result.metadata["minimum_probability_met"] is True


def test_final_gate_hard_rejects_unfavorable_traders_equation():
    service = SignalGateService()
    quality = SimpleNamespace(
        quality_grade="A", confidence=0.57,
        metadata={
            "structure_quality": 100.0, "context_quality": 83.0,
            "risk_quality": 92.0, "probability_calibrated": True,
            "probability": 0.57, "break_even_probability": 0.50,
            "trader_equation_favorable": False, "evidence_conflicts": [],
        },
    )
    result = service.evaluate(quality)
    assert result.approved is False
    assert result.metadata["trader_equation_favorable"] is False
    assert result.metadata["policy_version"] == "BROOKS_HARD_GATE_ENGINEERING_POLICY_V5_TE_REQUIRED"
    assert "TRADER_EQUATION_UNFAVORABLE" in result.metadata["failures"]

    blocked = SimpleNamespace(
        quality_grade="C", confidence=0.0,
        metadata={
            "structure_quality": 59.0, "context_quality": 59.0,
            "risk_quality": 74.0, "probability_calibrated": False,
            "trader_equation_favorable": False,
            "evidence_conflicts": ["MAJOR:test"],
        },
    )
    blocked_result = service.evaluate(blocked)
    assert blocked_result.approved is False
    failures = set(blocked_result.metadata["failures"])
    assert failures == {
        "STRUCTURE_NOT_CONFIRMED", "CONTEXT_NOT_CONFIRMED",
        "PROBABILITY_UNCALIBRATED", "RISK_NOT_CONFIRMED",
        "MAJOR_EVIDENCE_CONFLICT",
    }
    assert "TRADER_EQUATION_UNFAVORABLE" not in failures
