"""Paper runtime contracts independent from exchange implementations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.brooks_core.engine_contract import ReversalOutcomeContext, StopSourceIdentity, TargetPlanLifecycle, TargetSourceIdentity
from app.modules.market_data.entities import MarketSnapshot

TRADEABLE_DIRECTIONS = {"LONG", "SHORT"}


@dataclass(frozen=True, slots=True)
class PaperSignalCandidate:
    source_signal_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    targets: tuple[Decimal, ...]
    exchange: str
    market_type: str
    setup_type: str | None
    market_snapshot_id: str
    market_snapshot_hash: str
    engine_version: str
    rule_set_version: str
    configuration_version: str
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    rule_evidence: tuple[BrooksRuleEvidence, ...]
    chart_path: str
    snapshot: MarketSnapshot
    target_source_identities: tuple[TargetSourceIdentity, ...] = ()
    stop_source_identity: StopSourceIdentity | None = None
    target_plan_lifecycle: TargetPlanLifecycle | None = None
    reversal_outcome_context: ReversalOutcomeContext | None = None
    semantic_cohort_id: str | None = None

    def __post_init__(self) -> None:
        if self.direction not in TRADEABLE_DIRECTIONS:
            raise ValueError("PaperSignalCandidate must be LONG or SHORT")
        for name in (
            "source_signal_id",
            "symbol",
            "timeframe",
            "exchange",
            "market_type",
            "market_snapshot_id",
            "market_snapshot_hash",
            "engine_version",
            "rule_set_version",
            "configuration_version",
            "chart_path",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        # WAVE_17 identity is carried as approved Core evidence, but the Paper
        # candidate remains intentionally replaceable for downstream geometry
        # verification/rejection tests. BrooksEngineResult/BrooksCoreDecision
        # enforce source-identity consistency at the approval boundary.


@dataclass(frozen=True, slots=True)
class PaperPublishPayload:
    signal_id: int
    symbol: str
    timeframe: str
    direction: str
    setup_type: str | None
    entry_price: Decimal
    stop_loss: Decimal
    targets: tuple[Decimal, ...]
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    market_snapshot_id: str
    market_snapshot_hash: str
    chart_path: str


@dataclass(frozen=True, slots=True)
class PaperRunResult:
    signal_id: int
    signal_created: bool
    delivery_status: str
    external_message_id: str | None
