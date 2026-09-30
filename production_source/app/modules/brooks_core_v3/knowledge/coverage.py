"""Canonical operational Brooks concept coverage for Knowledge Layer v1."""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class KnowledgeConceptCoverage:
    concept: str
    rule_ids: tuple[str, ...]
    status: str

COVERAGE: tuple[KnowledgeConceptCoverage, ...] = (
    KnowledgeConceptCoverage('Always In', ('BB-REV-15-ALWAYS-IN',), 'ACTIVE'),
    KnowledgeConceptCoverage('Spike', ('BB-TRD-SPIKE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Spike & Channel', ('BB-TRD-SPIKE-CHANNEL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Channel', ('BB-TRD-CHANNEL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Broad Channel', ('BB-TRD-26-STAIRS-BROAD-CHANNEL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Tight Channel', ('BB-TRD-TIGHT-CHANNEL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Trading Range', ('BB-RNG-CTX-TREND-VS-RANGE', 'BB-RNG-21-BUY-LOW-SELL-HIGH'), 'ACTIVE'),
    KnowledgeConceptCoverage('Breakout', ('BB-RNG-02-BREAKOUT-FOLLOWTHROUGH',), 'ACTIVE'),
    KnowledgeConceptCoverage('Successful Breakout', ('BB-RNG-02-SUCCESSFUL-BREAKOUT',), 'ACTIVE'),
    KnowledgeConceptCoverage('Failed Breakout', ('BB-RNG-05-FAILED-BREAKOUT',), 'ACTIVE'),
    KnowledgeConceptCoverage('Failed Failure', ('BB-RNG-05-FAILED-FAILURE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Breakout Pullback', ('BB-RNG-05-BREAKOUT-PULLBACK',), 'ACTIVE'),
    KnowledgeConceptCoverage('Measured Move', ('BB-TRD-MEASURED-MOVE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Measured Move Failure', ('BB-REV-09-MEASURED-MOVE-FAILURE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Final Flag', ('BB-REV-07-FINAL-FLAG',), 'ACTIVE'),
    KnowledgeConceptCoverage('Final Flag Failure', ('BB-REV-07-FINAL-FLAG-FAILURE',), 'ACTIVE'),
    KnowledgeConceptCoverage('High 1 / H1', ('BB-RNG-17-HL-BAR-COUNT',), 'ACTIVE'),
    KnowledgeConceptCoverage('High 2 / H2', ('BB-RNG-17-HL-BAR-COUNT', 'BB-RNG-17-H2L2-TREND-CONTEXT'), 'ACTIVE'),
    KnowledgeConceptCoverage('High 3 / H3', ('BB-RNG-17-HL-BAR-COUNT', 'BB-RNG-18-WEDGE-PULLBACK'), 'ACTIVE'),
    KnowledgeConceptCoverage('Low 1 / L1', ('BB-RNG-17-HL-BAR-COUNT',), 'ACTIVE'),
    KnowledgeConceptCoverage('Low 2 / L2', ('BB-RNG-17-HL-BAR-COUNT', 'BB-RNG-17-H2L2-TREND-CONTEXT'), 'ACTIVE'),
    KnowledgeConceptCoverage('Low 3 / L3', ('BB-RNG-17-HL-BAR-COUNT', 'BB-RNG-18-WEDGE-PULLBACK'), 'ACTIVE'),
    KnowledgeConceptCoverage('H4 / L4 complex pullback', ('BB-RNG-17-HL-BAR-COUNT', 'BB-REV-09-FAILURES'), 'ACTIVE'),
    KnowledgeConceptCoverage('Micro Double Top', ('BB-REV-MICRO-DOUBLE-TOP-BOTTOM',), 'ACTIVE'),
    KnowledgeConceptCoverage('Micro Double Bottom', ('BB-REV-MICRO-DOUBLE-TOP-BOTTOM',), 'ACTIVE'),
    KnowledgeConceptCoverage('Double Top', ('BB-REV-DOUBLE-TOP-BOTTOM',), 'ACTIVE'),
    KnowledgeConceptCoverage('Double Bottom', ('BB-REV-DOUBLE-TOP-BOTTOM',), 'ACTIVE'),
    KnowledgeConceptCoverage('Double Top Bear Flag', ('BB-RNG-12-DOUBLE-TOP-BEAR-FLAG',), 'ACTIVE'),
    KnowledgeConceptCoverage('Double Bottom Bull Flag', ('BB-RNG-12-DOUBLE-BOTTOM-BULL-FLAG',), 'ACTIVE'),
    KnowledgeConceptCoverage('Double Top/Bottom Pullback', ('BB-REV-08-DOUBLE-TOP-PULLBACK', 'BB-REV-08-DOUBLE-BOTTOM-PULLBACK'), 'ACTIVE'),
    KnowledgeConceptCoverage('Wedge', ('BB-REV-05-WEDGE-THREE-PUSH',), 'ACTIVE'),
    KnowledgeConceptCoverage('Micro Wedge', ('BB-REV-05-MICRO-WEDGE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Parabolic Wedge', ('BB-REV-05-PARABOLIC-WEDGE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Three Push', ('BB-REV-05-WEDGE-THREE-PUSH',), 'ACTIVE'),
    KnowledgeConceptCoverage('Expanding Triangle', ('BB-REV-06-EXPANDING-TRIANGLE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Triangle', ('BB-RNG-23-TRIANGLE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Opening Reversal', ('BB-REV-19-OPENING-REVERSAL',), 'SESSION_REQUIRED'),
    KnowledgeConceptCoverage('Opening Swing', ('BB-REV-19-OPENING-SWING',), 'SESSION_REQUIRED'),
    KnowledgeConceptCoverage('Major Trend Reversal', ('BB-REV-03-MAJOR-TREND-REVERSAL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Minor Trend Reversal', ('BB-REV-09-MINOR-REVERSAL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Trend Resumption', ('BB-TRD-TREND-RESUMPTION',), 'ACTIVE'),
    KnowledgeConceptCoverage('Climax / Climactic Reversal', ('BB-REV-04-CLIMACTIC-REVERSAL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Exhaustion', ('BB-TRD-06-EXHAUSTION-BAR',), 'ACTIVE'),
    KnowledgeConceptCoverage('Inside Bar', ('BB-TRD-04-CANDLE-PATTERNS',), 'ACTIVE'),
    KnowledgeConceptCoverage('Outside Bar', ('BB-TRD-07-OUTSIDE-BAR',), 'ACTIVE'),
    KnowledgeConceptCoverage('IOI', ('BB-TRD-06-IOI',), 'ACTIVE'),
    KnowledgeConceptCoverage('II / III', ('BB-TRD-06-II-III',), 'ACTIVE'),
    KnowledgeConceptCoverage('OO / OIO', ('BB-TRD-07-OUTSIDE-BAR',), 'ACTIVE'),
    KnowledgeConceptCoverage('Nested IOI', ('BB-TRD-06-NESTED-IOI',), 'ACTIVE_INTERPRETATION'),
    KnowledgeConceptCoverage('Gap Bar', ('BB-RNG-14-GAP-BAR',), 'ACTIVE'),
    KnowledgeConceptCoverage('Twenty Gap Bar', ('BB-RNG-13-TWENTY-GAP',), 'ACTIVE'),
    KnowledgeConceptCoverage('First MA Gap Bar', ('BB-RNG-14-FIRST-MA-GAP',), 'ACTIVE'),
    KnowledgeConceptCoverage('Nested Trading Range', ('BB-RNG-02-NESTED-TRADING-RANGE',), 'ACTIVE_INTERPRETATION'),
    KnowledgeConceptCoverage('Always In Failure', ('BB-REV-15-ALWAYS-IN-FAILURE',), 'ACTIVE_INTERPRETATION'),
    KnowledgeConceptCoverage('Reversal Bar Failure', ('BB-TRD-06-REVERSAL-BAR-FAILURE', 'BB-REV-09-FAILURES'), 'ACTIVE'),
    KnowledgeConceptCoverage('Tight Trading Range / Barbwire', ('BB-RNG-22-TIGHT-RANGE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Micro Channel', ('BB-TRD-16-MICRO-CHANNEL',), 'ACTIVE'),
    KnowledgeConceptCoverage('Trending Trading Range', ('BB-TRD-22-TRENDING-RANGE',), 'ACTIVE'),
    KnowledgeConceptCoverage('Small Pullback Trend', ('BB-TRD-23-SMALL-PULLBACK-TREND',), 'ACTIVE'),
    KnowledgeConceptCoverage('Dueling Lines', ('BB-RNG-19-DUELING-LINES',), 'ACTIVE'),
    KnowledgeConceptCoverage('Pattern Failures', ('BB-REV-09-FAILURES',), 'ACTIVE'),
    KnowledgeConceptCoverage('Huge Volume Daily Reversal', ('BB-REV-10-HUGE-VOLUME-DAILY',), 'ACTIVE'),
)

def all_concepts() -> tuple[KnowledgeConceptCoverage, ...]:
    return COVERAGE
