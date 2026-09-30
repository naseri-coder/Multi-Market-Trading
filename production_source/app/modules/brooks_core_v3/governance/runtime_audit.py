"""Read-only governance mirror for the deployed legacy/full-core signal pipeline."""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.brooks_core_v3.knowledge.source_registry import REGISTRY


@dataclass(frozen=True, slots=True)
class RuntimeGovernanceAudit:
    market_snapshot_id: str
    setup_type: str
    direction: str
    mapped_rule_ids: tuple[str, ...]
    unmapped_rule_ids: tuple[str, ...]
    status: str
    blockers: tuple[str, ...]

    @property
    def publication_allowed(self) -> bool:
        return False


class BrooksRuntimeGovernanceAuditor:
    """Observe current decisions without changing or vetoing them."""

    def assess(
        self,
        *,
        candidate: object,
        council_approved: bool,
        risk_approved: bool,
        probability_calibrated: bool,
        trader_equation_favorable: bool,
        quality_approved: bool,
        gate_approved: bool,
    ) -> RuntimeGovernanceAudit:
        rule_ids = tuple(dict.fromkeys(tuple(getattr(candidate, "rule_ids", ()) or ())))
        mapped = tuple(rule_id for rule_id in rule_ids if rule_id in REGISTRY)
        unmapped = tuple(rule_id for rule_id in rule_ids if rule_id not in REGISTRY)
        blockers: list[str] = []
        if unmapped:
            blockers.append("unmapped_brooks_rules")
        for label, value in (
            ("council", council_approved),
            ("risk", risk_approved),
            ("probability_calibrated", probability_calibrated),
            ("traders_equation", trader_equation_favorable),
            ("quality", quality_approved),
            ("gate", gate_approved),
        ):
            if not value:
                blockers.append(f"observed_{label}_not_passed")
        blockers.extend((
            "runtime_governance_shadow_only",
            "runtime_governance_cannot_change_gate_result",
            "runtime_governance_no_publication",
        ))
        status = "OBSERVED_PASS" if not unmapped and gate_approved else "OBSERVED_BLOCKED"
        return RuntimeGovernanceAudit(
            market_snapshot_id=str(candidate.market_snapshot_id),
            setup_type=str(getattr(candidate, "setup_type", None) or "UNKNOWN"),
            direction=str(getattr(candidate, "direction", "UNKNOWN")),
            mapped_rule_ids=mapped,
            unmapped_rule_ids=unmapped,
            status=status,
            blockers=tuple(dict.fromkeys(blockers)),
        )
