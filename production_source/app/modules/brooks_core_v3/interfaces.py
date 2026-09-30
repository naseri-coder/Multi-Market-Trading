"""Shared Brooks Core v3 phase-1 pipeline contracts."""

from __future__ import annotations

from typing import Protocol

from app.modules.brooks_core_v3.entities import (
    ContextModel,
    EvidenceRegistry,
    FoundationSnapshot,
    MarketState,
    NarrativeModel,
)
from app.modules.market_data.entities import MarketSnapshot


class MarketStateBuilder(Protocol):
    def build_market_state(self, snapshot: MarketSnapshot) -> MarketState: ...


class ContextModelBuilder(Protocol):
    def build_context_model(
        self,
        *,
        snapshot: MarketSnapshot,
        market_state: MarketState,
    ) -> ContextModel: ...


class NarrativeModelBuilder(Protocol):
    def build_narrative_model(self, context: ContextModel) -> NarrativeModel: ...


class EvidenceValidator(Protocol):
    def validate_evidence_registry(self, registry: EvidenceRegistry) -> None: ...


class FoundationPipeline(Protocol):
    def evaluate_foundation(self, snapshot: MarketSnapshot) -> FoundationSnapshot: ...
