"""Brooks Core v3 phase-1 Foundation pipeline.

This module intentionally produces descriptive state only.  It does not create signal
rows, delivery records, chart files, risk scores, quality scores, or Telegram output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.brooks_core_v3.entities import (
    ContextModel,
    EvidenceItem,
    EvidenceRegistry,
    FoundationSnapshot,
    MarketState,
    NarrativeModel,
)
from app.modules.brooks_core_v3.enums import (
    AlwaysIn,
    EvidenceStatus,
    FoundationLayer,
    MarketRegime,
)
from app.modules.brooks_core_v3.source_catalog import RuleReference, get_rule_reference
from app.modules.market_data.entities import MarketSnapshot

_CONTEXT_RULE_ID = "BB-TRD-19-TREND-STRENGTH"
_ALWAYS_IN_RULE_ID = "BB-REV-15-ALWAYS-IN"
_TWO_REASONS_RULE_ID = "BB-RNG-26-TWO-REASONS"


def _status_for_resolved(value: str) -> EvidenceStatus:
    return EvidenceStatus.AMBIGUOUS if value in {"AMBIGUOUS", "UNRESOLVED"} else EvidenceStatus.PASS


def _coerce_regime(value: str) -> MarketRegime:
    try:
        return MarketRegime(value)
    except ValueError as exc:
        raise ValueError(f"unsupported Brooks regime: {value}") from exc


def _coerce_always_in(value: str) -> AlwaysIn:
    try:
        return AlwaysIn(value)
    except ValueError as exc:
        raise ValueError(f"unsupported Brooks Always-In value: {value}") from exc


def _evidence_item(
    ref: RuleReference,
    *,
    status: EvidenceStatus,
    layer: FoundationLayer,
    rationale: str,
    measurements: tuple[tuple[str, str], ...],
) -> EvidenceItem:
    return EvidenceItem(
        rule_id=ref.rule_id,
        status=status,
        source_book=ref.source_book,
        source_pages=ref.source_pages,
        taxonomy=ref.taxonomy,
        layer=layer,
        rationale=rationale,
        measurements=measurements,
    )


@dataclass(frozen=True, slots=True)
class BrooksCoreV3FoundationBuilder:
    policy: BrooksBooksPolicy = field(default_factory=BrooksBooksPolicy)

    def build_market_state(self, snapshot: MarketSnapshot) -> MarketState:
        context = assess_books_context(snapshot, policy=self.policy)
        registry = self._evidence_from_context(context)
        return MarketState(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            exchange=snapshot.exchange,
            market_type=snapshot.market_type,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            last_closed_index=len(snapshot.candles) - 1,
            regime=_coerce_regime(context.regime),
            always_in=_coerce_always_in(context.always_in),
            structure_direction=context.structure_direction,
            breakout_direction=_coerce_always_in(context.breakout_direction),
            evidence=registry,
        )

    def build_context_model(
        self,
        *,
        snapshot: MarketSnapshot,
        market_state: MarketState,
    ) -> ContextModel:
        context = assess_books_context(snapshot, policy=self.policy)
        supporting_reasons = (
            f"regime={context.regime}",
            f"always_in={context.always_in}",
            f"structure_direction={context.structure_direction}",
            f"breakout_direction={context.breakout_direction}",
            f"context_reason={context.reason}",
        )
        blockers = (
            "phase1_descriptive_only_no_trade_decision",
            "phase1_no_signal_runtime_or_telegram_wiring",
        )
        return ContextModel(
            market_state=market_state,
            primary_context=context.reason,
            supporting_reasons=supporting_reasons,
            blockers=blockers,
            evidence=market_state.evidence.with_item(
                _evidence_item(
                    get_rule_reference(_TWO_REASONS_RULE_ID),
                    status=EvidenceStatus.NOT_APPLICABLE,
                    layer=FoundationLayer.CONTEXT_MODEL,
                    rationale=(
                        "Phase 1 has no trade candidate; "
                        "the two-reason invariant is registered only."
                    ),
                    measurements=(("candidate_created", "false"),),
                )
            ),
        )

    def build_narrative_model(self, context: ContextModel) -> NarrativeModel:
        state = context.market_state
        return NarrativeModel(
            context=context,
            title=f"Brooks Core v3 foundation: {state.symbol} {state.timeframe}",
            summary="Market context was normalized without generating production output.",
            bullets=(
                f"regime={state.regime.value}",
                f"always_in={state.always_in.value}",
                f"snapshot_id={state.snapshot_id}",
                "production_behavior_unchanged=true",
            ),
            evidence=context.evidence,
        )

    def evaluate_foundation(self, snapshot: MarketSnapshot) -> FoundationSnapshot:
        market_state = self.build_market_state(snapshot)
        context = self.build_context_model(snapshot=snapshot, market_state=market_state)
        narrative = self.build_narrative_model(context)
        self.validate_evidence_registry(narrative.evidence)
        return FoundationSnapshot(
            market_state=market_state,
            context_model=context,
            narrative_model=narrative,
        )

    def validate_evidence_registry(self, registry: EvidenceRegistry) -> None:
        unknown: list[str] = []
        for rule_id in registry.rule_ids:
            try:
                get_rule_reference(rule_id)
            except KeyError:
                unknown.append(rule_id)
        if unknown:
            raise ValueError(f"unknown evidence rule ids: {tuple(unknown)}")

    def _evidence_from_context(self, context) -> EvidenceRegistry:
        metrics = context.metrics
        items = (
            _evidence_item(
                get_rule_reference(_CONTEXT_RULE_ID),
                status=_status_for_resolved(context.regime),
                layer=FoundationLayer.MARKET_STATE,
                rationale=context.reason,
                measurements=(
                    ("regime", context.regime),
                    ("structure_direction", context.structure_direction),
                    ("directional_bar_fraction", str(metrics.directional_bar_fraction)),
                    ("bar_overlap_rate", str(metrics.bar_overlap_rate)),
                    ("adjusted_displacement", str(metrics.adjusted_displacement)),
                ),
            ),
            _evidence_item(
                get_rule_reference(_ALWAYS_IN_RULE_ID),
                status=_status_for_resolved(context.always_in),
                layer=FoundationLayer.MARKET_STATE,
                rationale=(
                    "Always-In direction copied from the canonical "
                    "closed-bar context classifier."
                ),
                measurements=(
                    ("always_in", context.always_in),
                    ("breakout_direction", context.breakout_direction),
                    ("breakout_streak", str(context.breakout_streak)),
                ),
            ),
        )
        return EvidenceRegistry(items=items)
