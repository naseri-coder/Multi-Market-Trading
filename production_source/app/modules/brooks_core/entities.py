"""Typed output expected from the actual Brooks analysis core."""

from dataclasses import dataclass
from decimal import Decimal
from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.brooks_core.engine_contract import ReversalOutcomeContext, StopSourceIdentity, TargetPlanLifecycle, TargetSourceIdentity

@dataclass(frozen=True, slots=True)
class BrooksCoreDecision:
    decision: str
    source_signal_id: str | None
    entry_price: Decimal | None
    stop_loss: Decimal | None
    targets: tuple[Decimal, ...]
    setup_type: str | None
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    rule_evidence: tuple[BrooksRuleEvidence, ...]
    engine_version: str
    rule_set_version: str
    configuration_version: str
    market_snapshot_id: str
    market_snapshot_hash: str
    chart_path: str | None
    target_source_identities: tuple[TargetSourceIdentity, ...] = ()
    stop_source_identity: StopSourceIdentity | None = None
    target_plan_lifecycle: TargetPlanLifecycle | None = None
    reversal_outcome_context: ReversalOutcomeContext | None = None

    def __post_init__(self) -> None:
        if self.decision not in {"LONG", "SHORT", "NO_SIGNAL"}:
            raise ValueError("invalid Brooks decision")
        if self.decision == "NO_SIGNAL":
            if (
                self.target_source_identities
                or self.stop_source_identity is not None
                or self.target_plan_lifecycle is not None
                or self.reversal_outcome_context is not None
            ):
                raise ValueError("NO_SIGNAL cannot carry target/stop execution identity")
            return
        if self.source_signal_id is None or self.entry_price is None or self.stop_loss is None:
            raise ValueError("tradeable Brooks decision is incomplete")
        if not self.targets:
            raise ValueError("tradeable Brooks decision needs a target")
        if not self.chart_path:
            raise ValueError("tradeable Brooks decision needs chart_path")
        if self.target_source_identities:
            if len(self.target_source_identities) != len(self.targets):
                raise ValueError("target identity count must match targets")
            for number, (price, identity) in enumerate(
                zip(self.targets, self.target_source_identities), start=1
            ):
                if identity.target_number != number or identity.target_price != price:
                    raise ValueError("target identity must preserve target number/price")
        if self.stop_source_identity is not None and self.stop_source_identity.stop_price != self.stop_loss:
            raise ValueError("stop identity must preserve stop price")
        if self.target_plan_lifecycle is not None and self.target_plan_lifecycle.direction != self.decision:
            raise ValueError("target-plan direction must preserve decision direction")
        if self.reversal_outcome_context is not None:
            if self.reversal_outcome_context.direction != self.decision:
                raise ValueError("reversal-outcome direction must preserve decision direction")
            if self.target_plan_lifecycle is None:
                raise ValueError("reversal outcome requires target-plan lifecycle")
