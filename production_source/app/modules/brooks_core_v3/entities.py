"""Immutable Foundation entities for Brooks Core v3 phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.brooks_core_v3.enums import (
    AlwaysIn,
    EvidenceStatus,
    FoundationLayer,
    MarketRegime,
    RuleTaxonomy,
    SourceBook,
)
from app.modules.brooks_core_v3.source_catalog import CATALOG_VERSION

MetricValue = tuple[str, str]


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    rule_id: str
    status: EvidenceStatus
    source_book: SourceBook
    source_pages: tuple[int, ...]
    taxonomy: RuleTaxonomy
    layer: FoundationLayer
    rationale: str
    measurements: tuple[MetricValue, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id.startswith("BB-"):
            raise ValueError("rule_id must be a Brooks source rule id")
        if not self.source_pages or any(page <= 0 for page in self.source_pages):
            raise ValueError("source_pages must be positive and non-empty")
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        for key, value in self.measurements:
            if not key.strip() or not value.strip():
                raise ValueError("measurement key/value cannot be blank")


@dataclass(frozen=True, slots=True)
class EvidenceRegistry:
    items: tuple[EvidenceItem, ...]
    catalog_version: str = CATALOG_VERSION

    def __post_init__(self) -> None:
        if not self.catalog_version.strip():
            raise ValueError("catalog_version is required")
        duplicate_keys: set[tuple[str, FoundationLayer]] = set()
        for item in self.items:
            key = (item.rule_id, item.layer)
            if key in duplicate_keys:
                raise ValueError("duplicate evidence item for rule/layer")
            duplicate_keys.add(key)

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.rule_id for item in self.items))

    def for_layer(self, layer: FoundationLayer) -> tuple[EvidenceItem, ...]:
        return tuple(item for item in self.items if item.layer == layer)

    def with_item(self, item: EvidenceItem) -> EvidenceRegistry:
        return EvidenceRegistry(items=(*self.items, item), catalog_version=self.catalog_version)


@dataclass(frozen=True, slots=True)
class MarketState:
    symbol: str
    timeframe: str
    exchange: str
    market_type: str
    snapshot_id: str
    snapshot_hash: str
    last_closed_index: int
    regime: MarketRegime
    always_in: AlwaysIn
    structure_direction: str
    breakout_direction: AlwaysIn
    evidence: EvidenceRegistry = field(default_factory=lambda: EvidenceRegistry(items=()))

    def __post_init__(self) -> None:
        for value in (self.symbol, self.timeframe, self.exchange, self.market_type):
            if not value.strip():
                raise ValueError("market identifiers cannot be blank")
        if len(self.snapshot_hash) != 64:
            raise ValueError("snapshot_hash must be a sha256 hex digest")
        if self.last_closed_index < 0:
            raise ValueError("last_closed_index must be non-negative")


@dataclass(frozen=True, slots=True)
class ContextModel:
    market_state: MarketState
    primary_context: str
    supporting_reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence: EvidenceRegistry

    def __post_init__(self) -> None:
        if not self.primary_context.strip():
            raise ValueError("primary_context is required")
        if not self.supporting_reasons:
            raise ValueError("ContextModel needs at least one supporting reason")
        if any(not reason.strip() for reason in self.supporting_reasons):
            raise ValueError("supporting reasons cannot be blank")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("blockers cannot be blank")


@dataclass(frozen=True, slots=True)
class NarrativeModel:
    context: ContextModel
    title: str
    summary: str
    bullets: tuple[str, ...]
    evidence: EvidenceRegistry

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("narrative title and summary are required")
        if not self.bullets:
            raise ValueError("narrative bullets are required")
        if any(not bullet.strip() for bullet in self.bullets):
            raise ValueError("narrative bullets cannot be blank")


@dataclass(frozen=True, slots=True)
class FoundationSnapshot:
    market_state: MarketState
    context_model: ContextModel
    narrative_model: NarrativeModel

    @property
    def evidence(self) -> EvidenceRegistry:
        return self.narrative_model.evidence

