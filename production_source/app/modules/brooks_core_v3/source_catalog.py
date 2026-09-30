"""Immutable source catalog for Brooks Core v3 phase 1.

Only the three user-provided primary Al Brooks books are represented here.  The catalog
is data, not a strategy, and does not alter the existing production runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.brooks_core_v3.enums import RuleTaxonomy, SourceBook

CATALOG_VERSION = "brooks-core-v3-phase1-source-catalog-v1"


@dataclass(frozen=True, slots=True)
class RuleReference:
    rule_id: str
    family: str
    source_book: SourceBook
    source_pages: tuple[int, ...]
    taxonomy: RuleTaxonomy
    statement: str

    def __post_init__(self) -> None:
        if not self.rule_id.startswith("BB-"):
            raise ValueError("Brooks Core v3 rule ids must start with BB-")
        if not self.family.strip():
            raise ValueError("family is required")
        if not self.statement.strip():
            raise ValueError("statement is required")
        if not self.source_pages or any(page <= 0 for page in self.source_pages):
            raise ValueError("source_pages must be positive and non-empty")


_CANONICAL_RULES: tuple[RuleReference, ...] = (
    RuleReference(
        "BB-TRD-19-TREND-STRENGTH",
        "trend context",
        SourceBook.TRENDS,
        (337, 338, 339),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Trend strength is multi-factor and must not be reduced to a single score.",
    ),
    RuleReference(
        "BB-RNG-17-HL-BAR-COUNT",
        "H1/H2/L1/L2",
        SourceBook.RANGES,
        (29, 108, 109),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "H1/H2 and L1/L2 are bar-counting events in context.",
    ),
    RuleReference(
        "BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",
        "breakout",
        SourceBook.RANGES,
        (39, 40, 41),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "A breakout needs strength, urgency, and follow-through.",
    ),
    RuleReference(
        "BB-RNG-05-BREAKOUT-PULLBACK",
        "breakout pullback",
        SourceBook.RANGES,
        (30, 31, 34),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "A breakout pullback is a small pullback after a breakout.",
    ),
    RuleReference(
        "BB-RNG-05-FAILED-BREAKOUT",
        "failed breakout",
        SourceBook.RANGES,
        (30, 34, 48),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "A failed breakout returns back inside the breakout area.",
    ),
    RuleReference(
        "BB-RNG-05-FAILED-FAILURE",
        "failed failure",
        SourceBook.RANGES,
        (12, 30, 34),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "A second signal can resume the original breakout direction.",
    ),
    RuleReference(
        "BB-RNG-21-BUY-LOW-SELL-HIGH",
        "trading range fade",
        SourceBook.RANGES,
        (134, 147),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Trading ranges are two-sided: buy low and sell high.",
    ),
    RuleReference(
        "BB-RNG-22-TIGHT-RANGE",
        "tight range",
        SourceBook.RANGES,
        (48, 147),
        RuleTaxonomy.ENGINEERING_POLICY,
        "Tight ranges need explicit overlap and compactness policy.",
    ),
    RuleReference(
        "BB-RNG-26-TWO-REASONS",
        "confluence",
        SourceBook.RANGES,
        (187, 188, 189),
        RuleTaxonomy.SOURCE_RULE,
        "A trade candidate must have at least two independent reasons.",
    ),
    RuleReference(
        "BB-REV-03-MAJOR-TREND-REVERSAL",
        "major trend reversal",
        SourceBook.REVERSALS,
        (70, 95, 97),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Major trend reversal needs a break of the old trend and a test.",
    ),
    RuleReference(
        "BB-REV-04-CLIMACTIC-REVERSAL",
        "climactic reversal",
        SourceBook.REVERSALS,
        (139, 140),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "A climax must be followed by sharp opposite price action.",
    ),
    RuleReference(
        "BB-REV-05-WEDGE-THREE-PUSH",
        "wedge reversal",
        SourceBook.REVERSALS,
        (19, 25),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Wedges are three-push patterns and need not be geometrically perfect.",
    ),
    RuleReference(
        "BB-REV-07-FINAL-FLAG",
        "final flag",
        SourceBook.REVERSALS,
        (80, 83, 189),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Final flags are late two-sided flags whose breakout can reverse trend.",
    ),
    RuleReference(
        "BB-REV-DOUBLE-TOP-BOTTOM",
        "double top/bottom",
        SourceBook.REVERSALS,
        (86, 217),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Double top and bottom tests require a tolerance policy.",
    ),
    RuleReference(
        "BB-REV-15-ALWAYS-IN",
        "always-in context",
        SourceBook.REVERSALS,
        (321, 322),
        RuleTaxonomy.SOURCE_INTERPRETATION,
        "Always-In represents the side traders would choose if forced to hold.",
    ),
)


def brooks_rule_catalog() -> tuple[RuleReference, ...]:
    return _CANONICAL_RULES


def rule_ids() -> tuple[str, ...]:
    return tuple(item.rule_id for item in _CANONICAL_RULES)


def get_rule_reference(rule_id: str) -> RuleReference:
    for item in _CANONICAL_RULES:
        if item.rule_id == rule_id:
            return item
    raise KeyError(f"unknown Brooks Core v3 rule id: {rule_id}")
