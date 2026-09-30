"""Known implementation blockers that must not be silently converted into Brooks rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Phase7Blocker:
    hypothesis_id: str
    name: str
    source_pages: tuple[int, ...]
    reason: str


BLOCKERS = (
    Phase7Blocker(
        "EH-001",
        "Deterministic Trend-Bar Threshold",
        (9, 39),
        "Body/tail numeric threshold is not defined by the reviewed source.",
    ),
    Phase7Blocker(
        "EH-002",
        "Deterministic Swing Confirmation",
        (127,),
        "A causal non-repainting swing confirmation algorithm is not defined.",
    ),
    Phase7Blocker(
        "EH-003",
        "Support/Resistance Zone Construction",
        (6, 56, 126),
        "Zone width, merge, touch, recency, break and flip rules are unspecified.",
    ),
    Phase7Blocker(
        "EH-004",
        "Always-In Flip Algorithm",
        (28, 29),
        "The exact causal flip bar/condition is not defined.",
    ),
    Phase7Blocker(
        "EH-005",
        "Momentum Strength Metric",
        (129, 130),
        "No deterministic numeric momentum metric is specified.",
    ),
    Phase7Blocker(
        "EH-006",
        "H1/H2/L1/L2 Leg Counting Edge Cases",
        (11, 12),
        "Inside/outside/equal-high/equal-low/reset behavior is unresolved.",
    ),
    Phase7Blocker(
        "EH-007",
        "Successful Breakout Follow-Through Threshold",
        (97, 100, 105, 106),
        "Minimum continuation distance and bar count are unspecified.",
    ),
)
