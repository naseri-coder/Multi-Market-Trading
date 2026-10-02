"""Offline-safe Cold Start admission policy for native V5/V6 cohorts.

This module is not wired into production publication.  It may substitute only
for the missing calibrated-probability gate while compatible native history is
insufficient; every other Brooks/AI/Risk/Final-Gate failure remains binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COLD_START_STATUS = "COLD_START_INSUFFICIENT_COMPATIBLE_HISTORY"
COLD_START_LABEL = "COLD_START_QUALITATIVE_GATE"
POLICY_VERSION = "COLD_START_QUALITATIVE_POLICY_V1"
CONFIGURATION_TAG = "coldq1-s75-c75-e90-r85-bc0.80-exit20"
EXIT_CLOSED_NATIVE_COMPATIBLE = 20
MIN_STRUCTURE = 75.0
MIN_CONTEXT = 75.0
MIN_ENTRY = 90.0
MIN_RISK = 85.0
MIN_BROOKS_CERTAINTY = 0.80

@dataclass(frozen=True, slots=True)
class ColdStartDecision:
    approved: bool
    reason: str
    label: str | None
    policy_version: str = POLICY_VERSION
    configuration_tag: str = CONFIGURATION_TAG

def evaluate_cold_start_fallback(
    *, probability: Any, signal_quality: Any, final_gate: Any,
    ai_approved: bool, risk_approved: bool, geometry_valid: bool,
    structural_valid: bool, absolute_brooks_veto: bool,
    closed_native_compatible_count: int,
) -> ColdStartDecision:
    if getattr(probability, "calibration_status", None) != COLD_START_STATUS:
        return ColdStartDecision(False, "NOT_COLD_START_STATUS", None)
    if closed_native_compatible_count >= EXIT_CLOSED_NATIVE_COMPATIBLE:
        return ColdStartDecision(False, "COLD_START_EXIT_THRESHOLD_REACHED", None)
    guards = (
        (ai_approved, "AI_REJECTED"), (risk_approved, "RISK_REJECTED"),
        (geometry_valid, "INVALID_GEOMETRY"), (structural_valid, "STRUCTURAL_INVALIDATION"),
        (not absolute_brooks_veto, "ABSOLUTE_BROOKS_VETO"),
    )
    for allowed, reason in guards:
        if not allowed:
            return ColdStartDecision(False, reason, None)
    metadata = dict(getattr(signal_quality, "metadata", {}) or {})
    conflicts = tuple(str(x) for x in metadata.get("evidence_conflicts", ()) or ())
    if any(item.startswith("MAJOR:") for item in conflicts):
        return ColdStartDecision(False, "MAJOR_EVIDENCE_CONFLICT", None)
    failures = tuple((getattr(final_gate, "metadata", {}) or {}).get("failures", ()) or ())
    unrelated = tuple(x for x in failures if x != "PROBABILITY_UNCALIBRATED")
    if unrelated:
        return ColdStartDecision(False, "UNRELATED_FINAL_GATE_FAILURE:" + ",".join(unrelated), None)
    if "PROBABILITY_UNCALIBRATED" not in failures:
        return ColdStartDecision(False, "NO_COLD_START_GATE_TO_SUBSTITUTE", None)
    checks = (
        (float(metadata.get("structure_quality", 0) or 0) >= MIN_STRUCTURE, "STRUCTURE_BELOW_COLD_START_THRESHOLD"),
        (float(metadata.get("context_quality", 0) or 0) >= MIN_CONTEXT, "CONTEXT_BELOW_COLD_START_THRESHOLD"),
        (float(metadata.get("entry_quality", 0) or 0) >= MIN_ENTRY, "ENTRY_BELOW_COLD_START_THRESHOLD"),
        (float(metadata.get("risk_quality", 0) or 0) >= MIN_RISK, "RISK_BELOW_COLD_START_THRESHOLD"),
        (float(metadata.get("brooks_certainty", 0) or 0) >= MIN_BROOKS_CERTAINTY, "BROOKS_CERTAINTY_BELOW_COLD_START_THRESHOLD"),
    )
    for passed, reason in checks:
        if not passed:
            return ColdStartDecision(False, reason, None)
    return ColdStartDecision(True, "QUALITATIVE_EVIDENCE_STRONG_WITH_STATISTICS_UNAVAILABLE", COLD_START_LABEL)

def persistence_metadata(decision: ColdStartDecision, probability: Any) -> dict[str, object]:
    """JSONB-ready marker; no database write is performed here."""
    return {
        "admission_gate": decision.label,
        "cold_start_policy_version": decision.policy_version,
        "cold_start_configuration_tag": decision.configuration_tag,
        "statistically_calibrated_at_admission": False,
        "calibration_status_at_admission": getattr(probability, "calibration_status", None),
        "compatible_case_count_at_admission": getattr(probability, "compatible_case_count", None),
        "required_sample_size_at_admission": getattr(probability, "required_sample_size", None),
    }
