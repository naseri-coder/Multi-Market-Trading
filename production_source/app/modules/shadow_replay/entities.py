"""Immutable Phase 8 shadow-replay contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.modules.brooks_core.engine_contract import BrooksEngineResult

ShadowClassification = Literal[
    "H2",
    "L2",
    "AMBIGUOUS",
    "BLOCKED",
    "NO_SIGNAL",
]


def classify_engine_result(result: BrooksEngineResult) -> ShadowClassification:
    """Classify an evaluation without changing the strategy decision.

    H2/L2 detection is carried in setup_type while Phase 7C autonomous decisions
    remain disabled. AMBIGUOUS uses structured rule evidence. BLOCKED is derived
    from the existing fail-closed EH-006 reasoning until the core exposes a
    dedicated structured blocker field.
    """
    if result.setup_type == "H2_CONFIRMED":
        return "H2"
    if result.setup_type == "L2_CONFIRMED":
        return "L2"
    if any(item.status == "AMBIGUOUS" for item in result.rule_evidence):
        return "AMBIGUOUS"
    if any(
        "EH-006" in reason or "fail-closed" in reason.lower()
        for reason in result.reasoning
    ):
        return "BLOCKED"
    return "NO_SIGNAL"


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    sequence: int
    snapshot_id: str
    snapshot_hash: str
    captured_at: datetime
    window_first_open: datetime
    window_last_close: datetime
    classification: ShadowClassification
    decision: str
    setup_type: str | None
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    engine_version: str
    rule_set_version: str
    configuration_version: str


@dataclass(frozen=True, slots=True)
class ShadowReplayMetrics:
    evaluated_snapshots: int
    h2_count: int
    l2_count: int
    ambiguous_count: int
    blocked_count: int
    no_signal_count: int
    detections_per_1000_snapshots: float

    @classmethod
    def from_observations(
        cls,
        observations: tuple[ShadowObservation, ...],
    ) -> "ShadowReplayMetrics":
        counts = {
            "H2": 0,
            "L2": 0,
            "AMBIGUOUS": 0,
            "BLOCKED": 0,
            "NO_SIGNAL": 0,
        }
        for item in observations:
            counts[item.classification] += 1

        total = len(observations)
        detections = counts["H2"] + counts["L2"]
        rate = 0.0 if total == 0 else round((detections * 1000.0) / total, 6)

        return cls(
            evaluated_snapshots=total,
            h2_count=counts["H2"],
            l2_count=counts["L2"],
            ambiguous_count=counts["AMBIGUOUS"],
            blocked_count=counts["BLOCKED"],
            no_signal_count=counts["NO_SIGNAL"],
            detections_per_1000_snapshots=rate,
        )


@dataclass(frozen=True, slots=True)
class ShadowReplayReport:
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    window_size: int
    source_candle_count: int
    observations: tuple[ShadowObservation, ...]
    metrics: ShadowReplayMetrics
