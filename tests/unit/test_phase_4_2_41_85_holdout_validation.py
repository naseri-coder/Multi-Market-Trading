import hashlib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
)
from app.modules.signal_intelligence.cold_start_policy import (
    COLD_START_LABEL,
    CONFIGURATION_TAG,
    EXIT_CLOSED_NATIVE_COMPATIBLE,
    POLICY_VERSION,
    evaluate_cold_start_fallback,
    persistence_metadata,
)
from app.modules.signal_intelligence.cold_start_reporting import (
    include_in_calibrated_at_admission_reporting,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "production_source/app/modules/signal_intelligence/cold_start_policy.py"
HISTORICAL_HOLDOUT = ROOT / "tests/fixtures/phase_4_2_41_85_independent_holdout.json"
HISTORICAL_HOLDOUT_SHA = "84b2c851e9ef0d5bcf59407c15c428353909c6d1260e742bda0172235b9aa7d2"
HISTORICAL_V1_POLICY_SHA = "6d5b1e24b0d7a7dd2c0a6752abeb7be480a3c59d35f41ba043d71fd66ec1be91"


def strong_objects(*, readiness="UNBOOTSTRAPPED", failures=("REALIZED_R_EVIDENCE_NOT_FAVORABLE",)):
    probability = NS(
        calibrated=False,
        outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        statistics_contract_id=BROOKS_HP_STATISTICS_CONTRACT_ID,
        readiness_state=readiness,
        compatible_case_count=0,
        required_sample_size=20,
    )
    quality = NS(
        metadata={
            "structure_quality": 90,
            "context_quality": 90,
            "entry_quality": 100,
            "risk_quality": 90,
            "brooks_certainty": 0.9,
            "evidence_conflicts": (),
        }
    )
    gate = NS(metadata={"failures": failures})
    return probability, quality, gate


def evaluate_case(*, readiness="UNBOOTSTRAPPED", count=0, **overrides):
    probability, quality, gate = strong_objects(readiness=readiness)
    args = dict(
        probability=probability,
        signal_quality=quality,
        final_gate=gate,
        ai_approved=True,
        risk_approved=True,
        geometry_valid=True,
        structural_valid=True,
        absolute_brooks_veto=False,
        closed_native_compatible_count=count,
    )
    args.update(overrides)
    decision = evaluate_cold_start_fallback(**args)
    return decision, probability


def test_historical_holdout_bytes_remain_immutable_reference():
    assert HISTORICAL_HOLDOUT.is_file()
    assert hashlib.sha256(HISTORICAL_HOLDOUT.read_bytes()).hexdigest() == HISTORICAL_HOLDOUT_SHA


def test_current_policy_identity_and_hash_are_generated_from_current_bytes():
    current_hash = hashlib.sha256(POLICY.read_bytes()).hexdigest()
    assert POLICY_VERSION == "COLD_START_QUALITATIVE_POLICY_V2"
    assert CONFIGURATION_TAG.startswith("coldq2-hp-realized-r-")
    assert current_hash != HISTORICAL_V1_POLICY_SHA
    assert len(current_hash) == 64


def test_exit20_transition_is_monotonic_and_never_reactivates():
    assert evaluate_case(count=19)[0].approved
    for count in (EXIT_CLOSED_NATIVE_COMPATIBLE, 21, 100):
        decision, _ = evaluate_case(count=count)
        assert decision.approved is False
        assert decision.reason == "COLD_START_EXIT_THRESHOLD_REACHED"


@pytest.mark.parametrize("readiness,expected", [("UNBOOTSTRAPPED", True), ("MATURING", True),
                                                ("CALIBRATED_UNFAVORABLE", False),
                                                ("STATISTICAL_ASSESSMENT_INVALID", False)])
def test_synthetic_holdout_contains_non_vacuous_accept_and_reject_cases(readiness, expected):
    decision, probability = evaluate_case(readiness=readiness)
    assert decision.approved is expected
    if expected:
        metadata = persistence_metadata(decision, probability)
        assert metadata["admission_gate"] == COLD_START_LABEL
        assert metadata["cold_start_policy_version"] == POLICY_VERSION
        assert metadata["cold_start_configuration_tag"] == CONFIGURATION_TAG
        assert metadata["statistically_calibrated_at_admission"] is False
        assert metadata["hp_outcome_policy_id_at_admission"] == (
            BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
        )
        assert metadata["hp_statistics_contract_id_at_admission"] == BROOKS_HP_STATISTICS_CONTRACT_ID
        assert metadata["hp_readiness_state_at_admission"] == readiness
        assert "calibration_status_at_admission" not in metadata
        assert include_in_calibrated_at_admission_reporting(metadata) is False


@pytest.mark.parametrize(
    "override",
    [
        {"ai_approved": False},
        {"risk_approved": False},
        {"geometry_valid": False},
        {"structural_valid": False},
        {"absolute_brooks_veto": True},
    ],
)
def test_synthetic_holdout_rejections_remain_guarded(override):
    decision, _ = evaluate_case(**override)
    assert decision.approved is False


def test_unlabeled_metadata_remains_reportable_by_existing_reporting_contract():
    assert include_in_calibrated_at_admission_reporting({}) is True
