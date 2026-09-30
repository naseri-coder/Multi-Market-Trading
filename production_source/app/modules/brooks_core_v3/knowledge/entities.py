"""Pure immutable contracts for the Brooks knowledge layer.

The knowledge layer describes price action only. It never emits a trade decision,
order instruction, risk plan, quality grade, or publication instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal


class KnowledgeCategory(StrEnum):
    STRUCTURE = "STRUCTURE"
    CONTEXT = "CONTEXT"
    TREND = "TREND"
    RANGE = "RANGE"
    CHANNEL = "CHANNEL"
    PRESSURE = "PRESSURE"
    TRAP = "TRAP"
    ENTRY = "ENTRY"
    FAILURE = "FAILURE"
    PROBABILITY = "PROBABILITY"
    EVIDENCE = "EVIDENCE"


class Bias(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNRESOLVED = "UNRESOLVED"


class FindingState(StrEnum):
    DETECTED = "DETECTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


class SourceTaxonomy(StrEnum):
    SOURCE_RULE = "SOURCE_RULE"
    SOURCE_INTERPRETATION = "SOURCE_INTERPRETATION"
    ENGINEERING_INFRASTRUCTURE = "ENGINEERING_INFRASTRUCTURE"
    SESSION_REQUIRED = "SESSION_REQUIRED"




@dataclass(frozen=True, slots=True)
class SessionAnchor:
    """Explicit market session anchor required for opening-range concepts."""
    open_time: datetime
    label: str = "SESSION"

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None:
            raise ValueError("session open_time must be timezone-aware")
        if not self.label.strip():
            raise ValueError("session label is required")

class ProbabilityBand(StrEnum):
    HIGHER = "HIGHER"
    BALANCED = "BALANCED"
    LOWER = "LOWER"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class RuleOrigin:
    rule_id: str
    concept: str
    source_book: str
    chapter: str
    pages: tuple[int, ...]
    taxonomy: SourceTaxonomy
    note: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.concept.strip():
            raise ValueError("rule_id and concept are required")


@dataclass(frozen=True, slots=True)
class KnowledgeFinding:
    rule_id: str
    concept: str
    category: KnowledgeCategory
    state: FindingState
    bias: Bias
    bar_index: int
    source: RuleOrigin
    evidence: tuple[tuple[str, str], ...] = ()
    probability_band: ProbabilityBand | None = None

    def __post_init__(self) -> None:
        if self.bar_index < 0:
            raise ValueError("bar_index must be non-negative")
        if self.rule_id != self.source.rule_id:
            raise ValueError("finding rule_id must match source rule_id")


@dataclass(frozen=True, slots=True)
class BrooksKnowledgeSnapshot:
    snapshot_id: str
    snapshot_hash: str
    detected_structures: tuple[KnowledgeFinding, ...]
    detected_context: tuple[KnowledgeFinding, ...]
    detected_trend: tuple[KnowledgeFinding, ...]
    detected_range: tuple[KnowledgeFinding, ...]
    detected_channel: tuple[KnowledgeFinding, ...]
    detected_pressure: tuple[KnowledgeFinding, ...]
    detected_traps: tuple[KnowledgeFinding, ...]
    detected_entries: tuple[KnowledgeFinding, ...]
    detected_failures: tuple[KnowledgeFinding, ...]
    detected_probabilities: tuple[KnowledgeFinding, ...]
    detected_evidence: tuple[KnowledgeFinding, ...]

    @property
    def all_findings(self) -> tuple[KnowledgeFinding, ...]:
        return (
            *self.detected_structures,
            *self.detected_context,
            *self.detected_trend,
            *self.detected_range,
            *self.detected_channel,
            *self.detected_pressure,
            *self.detected_traps,
            *self.detected_entries,
            *self.detected_failures,
            *self.detected_probabilities,
            *self.detected_evidence,
        )
