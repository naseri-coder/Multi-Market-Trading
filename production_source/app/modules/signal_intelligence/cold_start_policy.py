"""Offline-safe Cold Start admission policy for current realized-R cohorts.

This module is not wired into production publication. It may substitute only for
an unavailable current realized-R evidence gate while compatible native history
is insufficient; every other Brooks/AI/Risk/Final-Gate failure remains binding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
)

COLD_START_LABEL = "COLD_START_QUALITATIVE_GATE"
POLICY_VERSION = "COLD_START_QUALITATIVE_POLICY_V2"
CONFIGURATION_TAG = "coldq2-hp-realized-r-unbootstrapped-maturing-s75-c75-e90-r85-bc0.80-exit20"
EXIT_CLOSED_NATIVE_COMPATIBLE = 20
ALLOWED_READINESS_STATES = frozenset({"UNBOOTSTRAPPED", "MATURING"})
MIN_STRUCTURE = 75.0
MIN_CONTEXT = 75.0
MIN_ENTRY = 90.0
MIN_RISK = 85.0
MIN_BROOKS_CERTAINTY = 0.80
_REALIZED_R_GATE_FAILURE = "REALIZED_R_EVIDENCE_NOT_FAVORABLE"


@dataclass(frozen=True, slots=True)
class ColdStartDecision:
    approved: bool
    reason: str
    label: str | None
    policy_version: str = POLICY_VERSION
    configuration_tag: str = CONFIGURATION_TAG


def _meets_threshold(metadata: dict[str, object], key: str, minimum: float) -> bool:
    try:
        value = float(metadata.get(key))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(value) and value >= minimum


def evaluate_cold_start_fallback(
    *,
    probability: Any,
    signal_quality: Any,
    final_gate: Any,
    ai_approved: bool,
    risk_approved: bool,
    geometry_valid: bool,
    structural_valid: bool,
    absolute_brooks_veto: bool,
    closed_native_compatible_count: int,
) -> ColdStartDecision:
    if (
        getattr(probability, "outcome_policy_id", None)
        != BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
    ):
        return ColdStartDecision(False, "NOT_COLD_START_POLICY", None)
    if getattr(probability, "statistics_contract_id", None) != BROOKS_HP_STATISTICS_CONTRACT_ID:
        return ColdStartDecision(False, "STATISTICS_CONTRACT_MISMATCH", None)

    readiness = getattr(probability, "readiness_state", None)
    if readiness not in ALLOWED_READINESS_STATES:
        return ColdStartDecision(False, "NOT_COLD_START_READINESS", None)
    if getattr(probability, "calibrated", None) is True:
        return ColdStartDecision(False, "COLD_START_ASSESSMENT_INCONSISTENT", None)

    if closed_native_compatible_count >= EXIT_CLOSED_NATIVE_COMPATIBLE:
        return ColdStartDecision(False, "COLD_START_EXIT_THRESHOLD_REACHED", None)

    guards = (
        (ai_approved, "AI_REJECTED"),
        (risk_approved, "RISK_REJECTED"),
        (geometry_valid, "INVALID_GEOMETRY"),
        (structural_valid, "STRUCTURAL_INVALIDATION"),
        (not absolute_brooks_veto, "ABSOLUTE_BROOKS_VETO"),
    )
    for allowed, reason in guards:
        if not allowed:
            return ColdStartDecision(False, reason, None)

    metadata = dict(getattr(signal_quality, "metadata", {}) or {})
    conflicts = tuple(str(item) for item in metadata.get("evidence_conflicts", ()) or ())
    if any(item.startswith("MAJOR:") for item in conflicts):
        return ColdStartDecision(False, "MAJOR_EVIDENCE_CONFLICT", None)

    failures = tuple((getattr(final_gate, "metadata", {}) or {}).get("failures", ()) or ())
    unrelated = tuple(item for item in failures if item != _REALIZED_R_GATE_FAILURE)
    if unrelated:
        return ColdStartDecision(
            False,
            "UNRELATED_FINAL_GATE_FAILURE:" + ",".join(unrelated),
            None,
        )
    if _REALIZED_R_GATE_FAILURE not in failures:
        return ColdStartDecision(False, "NO_COLD_START_GATE_TO_SUBSTITUTE", None)

    checks = (
        (
            _meets_threshold(metadata, "structure_quality", MIN_STRUCTURE),
            "STRUCTURE_BELOW_COLD_START_THRESHOLD",
        ),
        (
            _meets_threshold(metadata, "context_quality", MIN_CONTEXT),
            "CONTEXT_BELOW_COLD_START_THRESHOLD",
        ),
        (
            _meets_threshold(metadata, "entry_quality", MIN_ENTRY),
            "ENTRY_BELOW_COLD_START_THRESHOLD",
        ),
        (
            _meets_threshold(metadata, "risk_quality", MIN_RISK),
            "RISK_BELOW_COLD_START_THRESHOLD",
        ),
        (
            _meets_threshold(metadata, "brooks_certainty", MIN_BROOKS_CERTAINTY),
            "BROOKS_CERTAINTY_BELOW_COLD_START_THRESHOLD",
        ),
    )
    for passed, reason in checks:
        if not passed:
            return ColdStartDecision(False, reason, None)

    return ColdStartDecision(
        True,
        "QUALITATIVE_EVIDENCE_STRONG_WITH_STATISTICS_UNAVAILABLE",
        COLD_START_LABEL,
    )


def persistence_metadata(
    decision: ColdStartDecision,
    probability: Any,
) -> dict[str, object]:
    """Return JSONB-ready current-contract admission metadata; perform no write."""
    return {
        "admission_gate": decision.label,
        "cold_start_policy_version": decision.policy_version,
        "cold_start_configuration_tag": decision.configuration_tag,
        "statistically_calibrated_at_admission": False,
        "compatible_case_count_at_admission": getattr(probability, "compatible_case_count", None),
        "required_sample_size_at_admission": getattr(probability, "required_sample_size", None),
        "hp_outcome_policy_id_at_admission": getattr(probability, "outcome_policy_id", None),
        "hp_statistics_contract_id_at_admission": getattr(
            probability, "statistics_contract_id", None
        ),
        "hp_readiness_state_at_admission": getattr(probability, "readiness_state", None),
    }
