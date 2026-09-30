from __future__ import annotations

from typing import Any

from app.modules.signal_gate.entities import SignalGateDecision


class SignalGateService:
    """Hard Brooks final gate: Structure + Context + Probability + Risk."""

    MIN_STRUCTURE_QUALITY = 60.0
    MIN_CONTEXT_QUALITY = 60.0
    MIN_RISK_QUALITY = 75.0
    # V5: Trader's Equation is a hard pre-publication contract (BOOKS_NOTES_V5 TE-001..003).
    POLICY_VERSION = "BROOKS_HARD_GATE_ENGINEERING_POLICY_V5_TE_REQUIRED"

    def evaluate(self, signal_quality: Any) -> SignalGateDecision:
        metadata = dict(getattr(signal_quality, "metadata", {}) or {})
        grade = str(getattr(signal_quality, "quality_grade", "UNKNOWN"))
        confidence = float(getattr(signal_quality, "confidence", 0.0))
        structure = float(metadata.get("structure_quality", 0.0) or 0.0)
        context = float(metadata.get("context_quality", 0.0) or 0.0)
        risk = float(metadata.get("risk_quality", 0.0) or 0.0)
        calibrated = bool(metadata.get("probability_calibrated", False))
        favorable = bool(metadata.get("trader_equation_favorable", False))
        outcome_policy_id = metadata.get("hp_outcome_policy_id")
        realized_r_policy = outcome_policy_id == "BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1"
        legacy_policy = outcome_policy_id in {None, "LEGACY_LATEST_TERMINAL_EVENT_V1"}
        unknown_policy = not (realized_r_policy or legacy_policy)
        readiness_state = metadata.get("hp_readiness_state")
        conflicts = tuple(str(x) for x in metadata.get("evidence_conflicts", ()) or ())
        major_conflict = any(item.startswith("MAJOR:") for item in conflicts)

        failures: list[str] = []
        if structure < self.MIN_STRUCTURE_QUALITY:
            failures.append("STRUCTURE_NOT_CONFIRMED")
        if context < self.MIN_CONTEXT_QUALITY:
            failures.append("CONTEXT_NOT_CONFIRMED")
        break_even = metadata.get("break_even_probability")
        probability = metadata.get("probability")
        if realized_r_policy:
            if readiness_state != "CALIBRATED_FAVORABLE":
                failures.append("REALIZED_R_EVIDENCE_NOT_FAVORABLE")
        elif unknown_policy:
            failures.append("HP_OUTCOME_POLICY_UNRECOGNIZED")
        else:
            if not calibrated:
                failures.append("PROBABILITY_UNCALIBRATED")
            if calibrated and (
                break_even is None or probability is None or float(probability) < float(break_even)
            ):
                failures.append("PROBABILITY_BELOW_BREAK_EVEN")
            if calibrated and not favorable:
                failures.append("TRADER_EQUATION_UNFAVORABLE")
        if risk < self.MIN_RISK_QUALITY:
            failures.append("RISK_NOT_CONFIRMED")
        if major_conflict:
            failures.append("MAJOR_EVIDENCE_CONFLICT")

        gate_metadata = {
            "policy_version": self.POLICY_VERSION,
            "policy_semantics": "ENGINEERING_GATE_POLICY_NOT_BROOKS_NUMERIC_RULE",
            "structure_quality": structure,
            "context_quality": context,
            "risk_quality": risk,
            "probability": probability,
            "break_even_probability": break_even,
            "probability_scope": metadata.get("probability_scope"),
            "trader_equation_favorable": favorable,
            "hp_outcome_policy_id": outcome_policy_id,
            "hp_readiness_state": readiness_state,
            "hp_ci95_lower_r": metadata.get("hp_ci95_lower_r"),
            "hp_ci95_upper_r": metadata.get("hp_ci95_upper_r"),
            "hp_mean_realized_r": metadata.get("hp_mean_realized_r"),
            "minimum_structure_quality": self.MIN_STRUCTURE_QUALITY,
            "minimum_context_quality": self.MIN_CONTEXT_QUALITY,
            "minimum_risk_quality": self.MIN_RISK_QUALITY,
            "failures": tuple(failures),
        }
        if failures:
            return SignalGateDecision(
                approved=False,
                reason="Final Brooks gate rejected: " + ",".join(failures),
                quality_grade=grade,
                confidence=confidence,
                metadata=gate_metadata,
            )
        return SignalGateDecision(
            approved=True,
            reason=(
                "Structure, context, conservative realized-R evidence, and risk confirmed."
                if realized_r_policy
                else (
                    "Structure, context, probability above break-even, "
                    "favorable Trader equation, and risk confirmed."
                )
            ),
            quality_grade=grade,
            confidence=confidence,
            metadata=gate_metadata,
        )
