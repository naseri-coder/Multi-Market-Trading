from types import SimpleNamespace as NS

import pytest

from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
)
from app.modules.signal_intelligence.cold_start_integration import (
    evaluate_offline_cold_start_integration,
)
from app.modules.signal_intelligence.probability import ProbabilityAssessment


def probability(
    *,
    readiness="UNBOOTSTRAPPED",
    calibrated=False,
    policy=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    statistics=BROOKS_HP_STATISTICS_CONTRACT_ID,
):
    return ProbabilityAssessment(
        calibrated=calibrated,
        probability=None,
        empirical_win_rate=None,
        lower_bound=None,
        upper_bound=None,
        historical_reliability=0,
        sample_size=0,
        wins=0,
        losses=0,
        scope="NONE",
        break_even_probability=None,
        expected_value_r=None,
        trader_equation_favorable=False,
        compatible_case_count=0,
        required_sample_size=20,
        outcome_policy_id=policy,
        statistics_contract_id=statistics,
        readiness_state=readiness,
        economic_required_n=20,
    )


def candidate():
    return NS(snapshot=None, rule_evidence=(), setup_type="TEST", direction="LONG")


def strong_score():
    return NS(
        final_score=90,
        brooks_certainty=0.95,
        structure_quality=90,
        context_quality=90,
        entry_quality=100,
        risk_quality=90,
        conflicts=(),
        unclassified_rule_ids=(),
    )


def run(**kwargs):
    defaults = dict(
        candidate=candidate(),
        probability=probability(),
        ai_score=95,
        risk_score=90,
        council_confidence=0.9,
        ai_approved=True,
        risk_approved=True,
        geometry_valid=True,
        structural_valid=True,
        absolute_brooks_veto=False,
        closed_native_compatible_count=0,
    )
    defaults.update(kwargs)
    return evaluate_offline_cold_start_integration(**defaults)


@pytest.fixture(autouse=True)
def deterministic_quality(monkeypatch):
    from app.modules.signal_intelligence import service as signal_service

    monkeypatch.setattr(signal_service, "score_candidate", lambda *a, **k: strong_score())


@pytest.mark.parametrize("readiness", ["UNBOOTSTRAPPED", "MATURING"])
def test_real_si_and_gate_allow_only_current_cold_start_substitution(readiness):
    result = run(probability=probability(readiness=readiness))
    assert result.final_gate.approved is False
    assert result.final_gate.metadata["failures"] == ("REALIZED_R_EVIDENCE_NOT_FAVORABLE",)
    assert result.cold_start.approved is True
    assert result.effective_approved is True
    assert result.admission_metadata["hp_readiness_state_at_admission"] == readiness
    assert result.admission_metadata["statistically_calibrated_at_admission"] is False


@pytest.mark.parametrize(
    "readiness",
    ["CALIBRATED_UNFAVORABLE", "STATISTICAL_ASSESSMENT_INVALID"],
)
def test_unfavorable_or_invalid_current_readiness_cannot_fallback(readiness):
    result = run(probability=probability(readiness=readiness))
    assert "REALIZED_R_EVIDENCE_NOT_FAVORABLE" in result.final_gate.metadata["failures"]
    assert result.cold_start.approved is False
    assert result.cold_start.reason == "NOT_COLD_START_READINESS"
    assert result.effective_approved is False


def test_normal_favorable_realized_r_path_uses_final_gate_not_fallback():
    result = run(probability=probability(readiness="CALIBRATED_FAVORABLE", calibrated=True))
    assert result.final_gate.approved is True
    assert result.cold_start.approved is False
    assert result.cold_start.reason == "NOT_COLD_START_READINESS"
    assert result.effective_approved is True
    assert result.admission_metadata == {}


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("ai_approved", False, "AI_REJECTED"),
        ("risk_approved", False, "RISK_REJECTED"),
        ("geometry_valid", False, "INVALID_GEOMETRY"),
        ("structural_valid", False, "STRUCTURAL_INVALIDATION"),
        ("absolute_brooks_veto", True, "ABSOLUTE_BROOKS_VETO"),
    ],
)
def test_hard_guards_survive_real_si_and_gate(field, value, reason):
    result = run(**{field: value})
    assert result.cold_start.approved is False
    assert result.cold_start.reason == reason
    assert result.effective_approved is False


@pytest.mark.parametrize(
    "probability_value,reason",
    [
        (probability(policy="LEGACY_LATEST_TERMINAL_EVENT_V1"), "NOT_COLD_START_POLICY"),
        (probability(policy="UNKNOWN"), "NOT_COLD_START_POLICY"),
        (probability(statistics="wrong"), "STATISTICS_CONTRACT_MISMATCH"),
        (probability(readiness="UNKNOWN"), "NOT_COLD_START_READINESS"),
    ],
)
def test_unknown_or_mismatched_current_identity_fails_closed(probability_value, reason):
    result = run(probability=probability_value)
    assert result.cold_start.approved is False
    assert result.cold_start.reason == reason
