from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
)
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
    ProbabilityAssessment,
    _finite_sample_one_sided_bootstrap_support,
)
from app.modules.signal_intelligence.service import SignalIntelligenceService


def candidate():
    return SimpleNamespace(
        setup_type="BREAKOUT_LONG",
        timeframe="15m",
        direction="LONG",
        symbol="BTCUSDT",
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
        entry_price=100,
        stop_loss=99,
        targets=(102,),
        rule_evidence=(),
    )


def case(index, realized_r):
    return HistoricalCase(
        signal_id=index,
        setup_type="BREAKOUT_LONG",
        timeframe="15m",
        direction="LONG",
        structure_quality=80,
        context_quality=80,
        entry_quality=80,
        risk_feature=60,
        outcome=index % 2,
        rule_ids=(),
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
        generation_mode="LIVE",
        economic_opportunity_id=f"opp-{index}",
        symbol="BTCUSDT",
        realized_r=realized_r,
        payoff_input_fingerprint=f"fingerprint-{index}-{realized_r}",
        outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    )


def test_realized_r_requires_twenty_valid_cases_even_when_exact_is_ready():
    result = HistoricalProbabilityEngine(tuple(case(i, 0.2 + i / 100) for i in range(8))).assess(
        candidate()
    )
    assert result.readiness_state == "MATURING"
    assert result.structural_scope == "SETUP_TIMEFRAME"
    assert result.structural_required_n == 8
    assert result.economic_required_n == 20
    assert result.calibrated is False
    assert result.outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    assert result.statistics_contract_id == BROOKS_HP_STATISTICS_CONTRACT_ID


def test_realized_r_stable_positive_history_is_favorable_and_deterministic():
    rows = tuple(case(i, 0.2 + (i % 5) / 100) for i in range(20))
    first = HistoricalProbabilityEngine(rows).assess(candidate())
    second = HistoricalProbabilityEngine(rows).assess(candidate())
    assert first.readiness_state == "CALIBRATED_FAVORABLE"
    assert first.ci95_lower_r > 0
    assert first == second
    assert first.outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    assert first.statistics_contract_id == BROOKS_HP_STATISTICS_CONTRACT_ID
    assert first.break_even_probability == pytest.approx(1 / 3, abs=1e-6)
    assert first.expected_value_r == pytest.approx(3 * first.lower_bound - 1, abs=3e-6)
    assert first.trader_equation_favorable is False
    assert first.mean_realized_r > 0


def quality(state, *, legacy_probability=0.0):
    return SimpleNamespace(
        quality_grade="A",
        confidence=0.5,
        metadata={
            "structure_quality": 90,
            "context_quality": 90,
            "risk_quality": 90,
            "evidence_conflicts": (),
            "hp_outcome_policy_id": BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
            "hp_readiness_state": state,
            "hp_ci95_lower_r": 0.1,
            "probability_calibrated": False,
            "probability": legacy_probability,
            "break_even_probability": 0.9,
            "trader_equation_favorable": False,
        },
    )


def test_final_gate_uses_realized_r_policy_not_legacy_probability():
    decision = SignalGateService().evaluate(quality("CALIBRATED_FAVORABLE"))
    assert decision.approved is True
    assert "PROBABILITY_BELOW_BREAK_EVEN" not in decision.metadata["failures"]


def test_final_gate_fails_closed_when_realized_r_is_not_favorable():
    decision = SignalGateService().evaluate(
        quality("CALIBRATED_UNFAVORABLE", legacy_probability=1.0)
    )
    assert decision.approved is False
    assert decision.metadata["failures"] == ("REALIZED_R_EVIDENCE_NOT_FAVORABLE",)



def score_fixture():
    return SimpleNamespace(
        final_score=95.0,
        conflicts=(),
        structure_quality=90.0,
        context_quality=90.0,
        risk_quality=90.0,
        entry_quality=90.0,
        brooks_certainty=0.95,
        unclassified_rule_ids=(),
    )


def evaluate_si(assessment: ProbabilityAssessment):
    with patch(
        "app.modules.signal_intelligence.service.score_candidate",
        return_value=score_fixture(),
    ):
        return SignalIntelligenceService().evaluate(
            candidate(),
            ai_score=95.0,
            risk_score=95.0,
            council_confidence=0.9,
            probability=assessment,
        )


def positive_assessment():
    rows = tuple(case(i, 0.2 + (i % 5) / 100) for i in range(20))
    return HistoricalProbabilityEngine(rows).assess(candidate())


def negative_assessment():
    rows = tuple(case(i, -0.2 - (i % 5) / 100) for i in range(20))
    return HistoricalProbabilityEngine(rows).assess(candidate())


def invalid_assessment():
    rows = tuple(case(i, 0.2) for i in range(20))
    return HistoricalProbabilityEngine(rows).assess(candidate())


def maturing_assessment():
    rows = tuple(case(i, 0.2 + i / 100) for i in range(8))
    return HistoricalProbabilityEngine(rows).assess(candidate())


def unbootstrapped_assessment():
    return HistoricalProbabilityEngine(()).assess(candidate())


def legacy_case(index: int, outcome: int):
    return HistoricalCase(
        signal_id=index,
        setup_type="BREAKOUT_LONG",
        timeframe="15m",
        direction="LONG",
        structure_quality=80,
        context_quality=80,
        entry_quality=80,
        risk_feature=60,
        outcome=outcome,
        rule_ids=(),
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
        generation_mode="LIVE",
        economic_opportunity_id=f"legacy-opp-{index}",
        symbol="BTCUSDT",
    )


def legacy_assessment(outcomes):
    rows = tuple(legacy_case(i, outcome) for i, outcome in enumerate(outcomes))
    return HistoricalProbabilityEngine(rows).assess(candidate())


def test_unbootstrapped_realized_r_policy_id_is_explicit():
    result = unbootstrapped_assessment()
    assert result.readiness_state == "UNBOOTSTRAPPED"
    assert result.outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    assert result.statistics_contract_id == BROOKS_HP_STATISTICS_CONTRACT_ID


def test_calibrated_unfavorable_realized_r_policy_id_is_explicit():
    result = negative_assessment()
    assert result.readiness_state == "CALIBRATED_UNFAVORABLE"
    assert result.outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    assert result.statistics_contract_id == BROOKS_HP_STATISTICS_CONTRACT_ID


def test_statistical_invalid_realized_r_policy_id_is_explicit():
    result = invalid_assessment()
    assert result.readiness_state == "STATISTICAL_ASSESSMENT_INVALID"
    assert result.outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    assert result.statistics_contract_id == BROOKS_HP_STATISTICS_CONTRACT_ID


def test_engine_realized_r_policy_reaches_signal_intelligence_without_manual_id():
    assessment = positive_assessment()
    result = evaluate_si(assessment)
    assert (
        result.metadata["hp_outcome_policy_id"]
        == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    )
    assert result.metadata["hp_readiness_state"] == "CALIBRATED_FAVORABLE"
    assert result.metadata["hp_policy_routing_status"] == "REALIZED_R_POLICY"
    assert result.approved is True


def test_realized_r_approval_ignores_legacy_trader_equation_and_break_even_gate():
    assessment = positive_assessment()
    assert assessment.trader_equation_favorable is False
    result = evaluate_si(assessment)
    assert result.metadata["minimum_probability_met"] is False
    assert result.metadata["trader_equation_favorable"] is False
    assert result.approved is True


def test_realized_r_unfavorable_and_maturing_fail_economic_condition():
    unfavorable = evaluate_si(negative_assessment())
    maturing = evaluate_si(maturing_assessment())
    assert unfavorable.approved is False
    assert unfavorable.metadata["hp_readiness_state"] == "CALIBRATED_UNFAVORABLE"
    assert maturing.approved is False
    assert maturing.metadata["hp_readiness_state"] == "MATURING"


def test_missing_or_invalid_realized_r_readiness_fails_closed():
    base = positive_assessment()
    missing = evaluate_si(replace(base, readiness_state=None))
    invalid = evaluate_si(replace(base, readiness_state="NOT_A_VALID_STATE"))
    assert missing.approved is False
    assert invalid.approved is False


def test_unknown_explicit_policy_fails_closed_in_signal_intelligence():
    assessment = replace(
        positive_assessment(),
        outcome_policy_id="UNRECOGNIZED_HP_POLICY_V1",
    )
    result = evaluate_si(assessment)
    assert result.approved is False
    assert result.metadata["hp_policy_routing_status"] == "UNKNOWN_POLICY_FAIL_CLOSED"
    assert result.metadata["hp_policy_rejection_reason"] == "UNKNOWN_HP_OUTCOME_POLICY"


def test_unknown_explicit_policy_fails_closed_in_final_gate():
    result = evaluate_si(
        replace(positive_assessment(), outcome_policy_id="UNRECOGNIZED_HP_POLICY_V1")
    )
    gate = SignalGateService().evaluate(result)
    assert gate.approved is False
    assert "HP_OUTCOME_POLICY_UNRECOGNIZED" in gate.metadata["failures"]


def test_realized_r_mean_is_not_copied_into_legacy_expected_value_r():
    result = positive_assessment()
    assert result.mean_realized_r > 0
    assert result.expected_value_r == pytest.approx(3 * result.lower_bound - 1, abs=3e-6)
    assert result.expected_value_r != pytest.approx(result.mean_realized_r)


def test_realized_r_favorability_is_not_copied_into_legacy_trader_equation():
    result = positive_assessment()
    assert result.readiness_state == "CALIBRATED_FAVORABLE"
    assert result.ci95_lower_r > 0
    assert result.trader_equation_favorable is False


def test_probability_metadata_retains_event_probability_not_positive_fraction():
    assessment = positive_assessment()
    result = evaluate_si(assessment)
    assert assessment.positive_fraction_wilson_lower is not None
    assert result.metadata["probability"] == assessment.probability
    assert result.metadata["probability"] != assessment.positive_fraction_wilson_lower
    assert result.metadata["hp_event_metrics_role"] == "DIAGNOSTIC_ONLY"


def test_probability_calibrated_is_not_alias_for_realized_r_readiness():
    assessment = invalid_assessment()
    assert assessment.readiness_state == "STATISTICAL_ASSESSMENT_INVALID"
    result = evaluate_si(assessment)
    assert result.metadata["probability_calibrated"] is True
    assert result.approved is False


def test_maturing_event_probability_metadata_is_unavailable_not_realized_alias():
    result = evaluate_si(maturing_assessment())
    assert result.metadata["hp_readiness_state"] == "MATURING"
    assert result.metadata["probability_calibrated"] is None
    assert result.metadata["probability"] is None
    assert result.metadata["minimum_probability_met"] is None


def test_cold_start_maturing_routes_to_realized_r_final_gate_failure():
    result = evaluate_si(maturing_assessment())
    gate = SignalGateService().evaluate(result)
    assert (
        result.metadata["hp_outcome_policy_id"]
        == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    )
    assert gate.metadata["failures"] == ("REALIZED_R_EVIDENCE_NOT_FAVORABLE",)


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    (
        ("structure_quality", 0, "STRUCTURE_NOT_CONFIRMED"),
        ("context_quality", 0, "CONTEXT_NOT_CONFIRMED"),
        ("risk_quality", 0, "RISK_NOT_CONFIRMED"),
    ),
)
def test_realized_r_final_gate_preserves_non_hp_gates(field, value, failure):
    item = quality("CALIBRATED_FAVORABLE")
    item.metadata[field] = value
    decision = SignalGateService().evaluate(item)
    assert decision.approved is False
    assert failure in decision.metadata["failures"]


def test_realized_r_final_gate_preserves_major_conflict_gate():
    item = quality("CALIBRATED_FAVORABLE")
    item.metadata["evidence_conflicts"] = ("MAJOR:test",)
    decision = SignalGateService().evaluate(item)
    assert decision.approved is False
    assert "MAJOR_EVIDENCE_CONFLICT" in decision.metadata["failures"]


def test_legacy_expected_value_r_keeps_checkpoint_091_numeric_semantics():
    result = legacy_assessment([1] * 10 + [0] * 10)
    assert result.outcome_policy_id == "LEGACY_LATEST_TERMINAL_EVENT_V1"
    assert result.statistics_contract_id is None
    assert result.break_even_probability == pytest.approx(1 / 3, abs=1e-6)
    expected = 3 * result.lower_bound - 1
    assert result.expected_value_r == pytest.approx(expected, abs=3e-6)


def test_legacy_trader_equation_favorable_comes_from_legacy_equation():
    result = legacy_assessment([1] * 10 + [0] * 10)
    assert result.expected_value_r < 0
    assert result.trader_equation_favorable is False
    winning = legacy_assessment([1] * 20)
    assert winning.expected_value_r > 0
    assert winning.trader_equation_favorable is True


def test_legacy_signal_intelligence_gating_is_preserved():
    winning = legacy_assessment([1] * 20)
    approved = evaluate_si(winning)
    assert approved.approved is True
    assert approved.metadata["hp_policy_routing_status"] == "LEGACY_POLICY"
    assert approved.metadata["hp_event_metrics_role"] == "LEGACY_GATE"

    te_rejected = evaluate_si(replace(winning, trader_equation_favorable=False))
    assert te_rejected.approved is False

    probability_rejected = evaluate_si(legacy_assessment([1] * 10 + [0] * 10))
    assert probability_rejected.approved is False


def test_legacy_final_gate_path_remains_probability_and_te_gated():
    legacy_quality = quality("IGNORED")
    legacy_quality.metadata.pop("hp_outcome_policy_id")
    legacy_quality.metadata["probability_calibrated"] = True
    legacy_quality.metadata["probability"] = 0.2
    legacy_quality.metadata["break_even_probability"] = 0.5
    legacy_quality.metadata["trader_equation_favorable"] = False
    decision = SignalGateService().evaluate(legacy_quality)
    assert decision.approved is False
    assert "PROBABILITY_BELOW_BREAK_EVEN" in decision.metadata["failures"]
    assert "TRADER_EQUATION_UNFAVORABLE" in decision.metadata["failures"]


def test_realized_r_statistical_confidence_exact_finite_sample_formula():
    confidence, p_value, k, valid = _finite_sample_one_sided_bootstrap_support(
        1.0,
        np.asarray([-2.0, 0.0, 1.0, 1.5, 3.0], dtype=np.float64),
    )
    assert valid == 5
    assert k == 3
    assert p_value == pytest.approx((3 + 1) / (5 + 1))
    assert confidence == pytest.approx(1 - (4 / 6))


def test_realized_r_statistical_confidence_ties_count_in_upper_tail():
    confidence, p_value, k, valid = _finite_sample_one_sided_bootstrap_support(
        1.0,
        np.asarray([0.5, 1.0, 1.0], dtype=np.float64),
    )
    assert valid == 3
    assert k == 2
    assert p_value == pytest.approx(3 / 4)
    assert confidence == pytest.approx(1 / 4)


def test_realized_r_statistical_confidence_never_reports_one_from_finite_sample():
    confidence, p_value, k, valid = _finite_sample_one_sided_bootstrap_support(
        10.0,
        np.asarray([-2.0, 0.0, 1.0], dtype=np.float64),
    )
    assert valid == 3
    assert k == 0
    assert p_value == pytest.approx(1 / 4)
    assert confidence == pytest.approx(3 / 4)
    assert confidence < 1.0


def test_realized_r_statistical_confidence_full_upper_tail_is_zero():
    confidence, p_value, k, valid = _finite_sample_one_sided_bootstrap_support(
        -10.0,
        np.asarray([-2.0, 0.0, 1.0], dtype=np.float64),
    )
    assert valid == 3
    assert k == valid
    assert p_value == 1.0
    assert confidence == 0.0


def test_realized_r_statistical_confidence_is_event_independent():
    rows = tuple(case(i, 0.15 + (i % 7) / 100) for i in range(20))
    event_losses = tuple(replace(row, outcome=0) for row in rows)
    event_wins = tuple(replace(row, outcome=1) for row in rows)
    losses = HistoricalProbabilityEngine(event_losses).assess(candidate())
    wins = HistoricalProbabilityEngine(event_wins).assess(candidate())
    assert losses.probability != wins.probability
    assert (
        losses.realized_r_statistical_confidence
        == wins.realized_r_statistical_confidence
    )


def test_realized_r_statistical_confidence_is_deterministic_and_bounded():
    first = positive_assessment()
    second = positive_assessment()
    assert first.realized_r_statistical_confidence is not None
    assert first.realized_r_statistical_confidence == second.realized_r_statistical_confidence
    assert 0.0 <= first.realized_r_statistical_confidence < 1.0


def test_invalid_realized_r_statistics_do_not_fabricate_confidence():
    result = invalid_assessment()
    assert result.readiness_state == "STATISTICAL_ASSESSMENT_INVALID"
    assert result.realized_r_statistical_confidence is None


def test_maturing_realized_r_does_not_fabricate_statistical_confidence():
    result = maturing_assessment()
    assert result.readiness_state == "MATURING"
    assert result.realized_r_statistical_confidence is None


def test_insufficient_valid_bootstrap_fraction_has_no_statistical_confidence():
    rows = tuple(
        case(i, 1.0 if i == 0 else 0.0)
        for i in range(20)
    )
    result = HistoricalProbabilityEngine(rows).assess(candidate())
    assert result.readiness_state == "STATISTICAL_ASSESSMENT_INVALID"
    assert result.bootstrap_valid_fraction < 0.95
    assert result.realized_r_statistical_confidence is None


def test_realized_r_statistical_confidence_is_metadata_only_not_publication_gate():
    assessment = positive_assessment()
    original = evaluate_si(assessment)
    changed = evaluate_si(
        replace(assessment, realized_r_statistical_confidence=0.0)
    )
    assert original.approved is True
    assert changed.approved is True
    assert (
        original.metadata["hp_realized_r_statistical_confidence"]
        != changed.metadata["hp_realized_r_statistical_confidence"]
    )
