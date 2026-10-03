from types import SimpleNamespace as NS

import pytest
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
)
from app.modules.signal_intelligence.cold_start_policy import (
    COLD_START_LABEL,
    CONFIGURATION_TAG,
    POLICY_VERSION,
    evaluate_cold_start_fallback,
    persistence_metadata,
)


def objects(
    *,
    policy=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    statistics=BROOKS_HP_STATISTICS_CONTRACT_ID,
    readiness="UNBOOTSTRAPPED",
    calibrated=False,
    failures=("REALIZED_R_EVIDENCE_NOT_FAVORABLE",),
    structure=80,
    context=80,
    entry=100,
    risk=90,
    certainty=0.85,
    conflicts=(),
    compatible=0,
):
    probability = NS(
        outcome_policy_id=policy,
        statistics_contract_id=statistics,
        readiness_state=readiness,
        calibrated=calibrated,
        compatible_case_count=compatible,
        required_sample_size=20,
    )
    quality = NS(
        metadata={
            "structure_quality": structure,
            "context_quality": context,
            "entry_quality": entry,
            "risk_quality": risk,
            "brooks_certainty": certainty,
            "evidence_conflicts": conflicts,
        }
    )
    gate = NS(metadata={"failures": failures})
    return probability, quality, gate


def decide(**kwargs):
    object_keys = {
        "policy",
        "statistics",
        "readiness",
        "calibrated",
        "failures",
        "structure",
        "context",
        "entry",
        "risk",
        "certainty",
        "conflicts",
        "compatible",
    }
    object_args = {key: kwargs.pop(key) for key in list(kwargs) if key in object_keys}
    probability, quality, gate = objects(**object_args)
    args = dict(
        probability=probability,
        signal_quality=quality,
        final_gate=gate,
        ai_approved=True,
        risk_approved=True,
        geometry_valid=True,
        structural_valid=True,
        absolute_brooks_veto=False,
        closed_native_compatible_count=0,
    )
    args.update(kwargs)
    return evaluate_cold_start_fallback(**args), probability


@pytest.mark.parametrize("readiness", ["UNBOOTSTRAPPED", "MATURING"])
def test_strong_current_cold_start_can_substitute_only_realized_r_gate(readiness):
    decision, probability = decide(readiness=readiness)
    assert decision.approved
    assert decision.label == COLD_START_LABEL
    assert decision.policy_version == POLICY_VERSION
    assert decision.configuration_tag == CONFIGURATION_TAG
    metadata = persistence_metadata(decision, probability)
    assert metadata["statistically_calibrated_at_admission"] is False
    assert metadata["hp_readiness_state_at_admission"] == readiness
    assert "calibration_status_at_admission" not in metadata


@pytest.mark.parametrize(
    "readiness",
    [
        "CALIBRATED_FAVORABLE",
        "CALIBRATED_UNFAVORABLE",
        "STATISTICAL_ASSESSMENT_INVALID",
        None,
        "UNKNOWN",
    ],
)
def test_non_cold_readiness_never_uses_fallback(readiness):
    decision, _ = decide(readiness=readiness)
    assert not decision.approved
    assert decision.reason == "NOT_COLD_START_READINESS"


@pytest.mark.parametrize("policy", [None, "LEGACY_LATEST_TERMINAL_EVENT_V1", "UNKNOWN"])
def test_missing_legacy_or_unknown_policy_fails_closed(policy):
    decision, _ = decide(policy=policy)
    assert decision.reason == "NOT_COLD_START_POLICY"


@pytest.mark.parametrize("statistics", [None, "wrong-contract"])
def test_missing_or_mismatched_statistics_contract_fails_closed(statistics):
    decision, _ = decide(statistics=statistics)
    assert decision.reason == "STATISTICS_CONTRACT_MISMATCH"


@pytest.mark.parametrize("readiness", ["UNBOOTSTRAPPED", "MATURING"])
def test_contradictory_calibrated_flag_fails_closed(readiness):
    decision, _ = decide(readiness=readiness, calibrated=True)
    assert decision.reason == "COLD_START_ASSESSMENT_INCONSISTENT"


def test_external_exit_counter_is_independent_and_monotonic():
    assert decide(closed_native_compatible_count=19, compatible=100)[0].approved
    for count in (20, 21, 100):
        decision, _ = decide(closed_native_compatible_count=count, compatible=0)
        assert not decision.approved
        assert decision.reason == "COLD_START_EXIT_THRESHOLD_REACHED"


@pytest.mark.parametrize(
    "name,value,reason",
    [
        ("ai_approved", False, "AI_REJECTED"),
        ("risk_approved", False, "RISK_REJECTED"),
        ("geometry_valid", False, "INVALID_GEOMETRY"),
        ("structural_valid", False, "STRUCTURAL_INVALIDATION"),
        ("absolute_brooks_veto", True, "ABSOLUTE_BROOKS_VETO"),
    ],
)
def test_hard_guards_are_never_overridden(name, value, reason):
    decision, _ = decide(**{name: value})
    assert not decision.approved
    assert decision.reason == reason


def test_major_conflict_is_never_overridden():
    decision, _ = decide(conflicts=("MAJOR:X:opposition",))
    assert decision.reason == "MAJOR_EVIDENCE_CONFLICT"


def test_additional_final_gate_failure_is_never_overridden_in_order():
    decision, _ = decide(
        failures=(
            "REALIZED_R_EVIDENCE_NOT_FAVORABLE",
            "STRUCTURE_NOT_CONFIRMED",
            "RISK_NOT_CONFIRMED",
        )
    )
    assert decision.reason == (
        "UNRELATED_FINAL_GATE_FAILURE:STRUCTURE_NOT_CONFIRMED,RISK_NOT_CONFIRMED"
    )


def test_missing_realized_r_gate_failure_cannot_fallback():
    decision, _ = decide(failures=())
    assert decision.reason == "NO_COLD_START_GATE_TO_SUBSTITUTE"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("structure", 74.99, "STRUCTURE_BELOW_COLD_START_THRESHOLD"),
        ("context", 74.99, "CONTEXT_BELOW_COLD_START_THRESHOLD"),
        ("entry", 89.99, "ENTRY_BELOW_COLD_START_THRESHOLD"),
        ("risk", 84.99, "RISK_BELOW_COLD_START_THRESHOLD"),
        ("certainty", 0.7999, "BROOKS_CERTAINTY_BELOW_COLD_START_THRESHOLD"),
    ],
)
def test_conservative_thresholds_fail_closed(field, value, reason):
    decision, _ = decide(**{field: value})
    assert decision.reason == reason


@pytest.mark.parametrize("bad", [None, "bad", float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize(
    "field,reason",
    [
        ("structure", "STRUCTURE_BELOW_COLD_START_THRESHOLD"),
        ("context", "CONTEXT_BELOW_COLD_START_THRESHOLD"),
        ("entry", "ENTRY_BELOW_COLD_START_THRESHOLD"),
        ("risk", "RISK_BELOW_COLD_START_THRESHOLD"),
        ("certainty", "BROOKS_CERTAINTY_BELOW_COLD_START_THRESHOLD"),
    ],
)
def test_missing_nonfinite_or_nonnumeric_quality_fails_closed(field, reason, bad):
    decision, _ = decide(**{field: bad})
    assert decision.reason == reason


def test_persistence_metadata_uses_only_current_hp_schema():
    decision, probability = decide(readiness="MATURING", compatible=7)
    metadata = persistence_metadata(decision, probability)
    assert metadata == {
        "admission_gate": COLD_START_LABEL,
        "cold_start_policy_version": POLICY_VERSION,
        "cold_start_configuration_tag": CONFIGURATION_TAG,
        "statistically_calibrated_at_admission": False,
        "compatible_case_count_at_admission": 7,
        "required_sample_size_at_admission": 20,
        "hp_outcome_policy_id_at_admission": BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        "hp_statistics_contract_id_at_admission": BROOKS_HP_STATISTICS_CONTRACT_ID,
        "hp_readiness_state_at_admission": "MATURING",
    }
