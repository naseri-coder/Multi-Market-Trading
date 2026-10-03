"""Pre-production Cold Start integration harness.

Not imported by production runtime. It exercises the real Signal Intelligence and
Final Gate first, then permits the frozen qualitative fallback to substitute only
for PROBABILITY_UNCALIBRATED.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.cold_start_policy import (
    ColdStartDecision, evaluate_cold_start_fallback, persistence_metadata,
)
from app.modules.signal_intelligence.service import SignalIntelligenceService

@dataclass(frozen=True, slots=True)
class OfflineColdStartIntegrationResult:
    signal_quality: Any
    final_gate: Any
    cold_start: ColdStartDecision
    effective_approved: bool
    admission_metadata: dict[str, object]

def evaluate_offline_cold_start_integration(
    *, candidate: Any, probability: Any, ai_score: float, risk_score: float,
    council_confidence: float, ai_approved: bool, risk_approved: bool,
    geometry_valid: bool, structural_valid: bool, absolute_brooks_veto: bool,
    closed_native_compatible_count: int,
) -> OfflineColdStartIntegrationResult:
    quality = SignalIntelligenceService().evaluate(
        candidate, ai_score=ai_score, risk_score=risk_score,
        council_confidence=council_confidence, probability=probability,
    )
    gate = SignalGateService().evaluate(quality)
    cold = evaluate_cold_start_fallback(
        probability=probability, signal_quality=quality, final_gate=gate,
        ai_approved=ai_approved, risk_approved=risk_approved,
        geometry_valid=geometry_valid, structural_valid=structural_valid,
        absolute_brooks_veto=absolute_brooks_veto,
        closed_native_compatible_count=closed_native_compatible_count,
    )
    effective = bool(gate.approved or cold.approved)
    metadata = persistence_metadata(cold, probability) if cold.approved else {}
    return OfflineColdStartIntegrationResult(quality, gate, cold, effective, metadata)
