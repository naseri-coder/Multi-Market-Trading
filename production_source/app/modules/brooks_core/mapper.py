from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.market_data.entities import MarketSnapshot
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.signal_automation.entities import FINAL_BROOKS_HP_SEMANTIC_COHORT_ID

def to_paper_candidate(
    *,
    snapshot: MarketSnapshot,
    decision: BrooksCoreDecision,
) -> PaperSignalCandidate | None:
    if decision.market_snapshot_id != snapshot.snapshot_id:
        raise ValueError("Brooks decision snapshot_id mismatch")
    if decision.market_snapshot_hash != snapshot.snapshot_hash:
        raise ValueError("Brooks decision snapshot_hash mismatch")
    if decision.decision == "NO_SIGNAL":
        return None

    return PaperSignalCandidate(
        snapshot=snapshot,
        source_signal_id=decision.source_signal_id or "",
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        direction=decision.decision,
        entry_price=decision.entry_price,
        stop_loss=decision.stop_loss,
        targets=decision.targets,
        exchange=snapshot.exchange,
        market_type=snapshot.market_type,
        setup_type=decision.setup_type,
        market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash,
        engine_version=decision.engine_version,
        rule_set_version=decision.rule_set_version,
        configuration_version=decision.configuration_version,
        reasoning=decision.reasoning,
        rule_ids=decision.rule_ids,
        failed_rules=decision.failed_rules,
        rule_evidence=decision.rule_evidence,
        chart_path=decision.chart_path or "",
        target_source_identities=decision.target_source_identities,
        stop_source_identity=decision.stop_source_identity,
        target_plan_lifecycle=decision.target_plan_lifecycle,
        reversal_outcome_context=decision.reversal_outcome_context,
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    )
