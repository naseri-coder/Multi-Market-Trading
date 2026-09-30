"""Pure Brooks source registry for the Knowledge Layer.

This module contains source/provenance only and imports no runtime decision layer.
"""
from __future__ import annotations

from .entities import RuleOrigin, SourceTaxonomy

_RAW: dict[str, tuple[str, tuple[int, ...], str, str]] = {
    'BB-REV-03-MAJOR-TREND-REVERSAL': ('Trading Price Action Reversals', (70, 95, 97), 'Major Trend Reversal', '03'),
    'BB-REV-03-REVERSAL-MATURITY': ('Trading Price Action Reversals', (111, 112, 113), 'Rev 03 Reversal Maturity', '03'),
    'BB-REV-04-CLIMACTIC-REVERSAL': ('Trading Price Action Reversals', (139, 140), 'Climactic Reversal', '04'),
    'BB-REV-05-MICRO-WEDGE': ('Trading Price Action Reversals', (151, 158, 159, 168, 176, 179, 180), 'Micro Wedge', '05'),
    'BB-REV-05-PARABOLIC-WEDGE': ('Trading Price Action Reversals', (152, 153, 170, 174), 'Parabolic Wedge', '05'),
    'BB-REV-05-WEDGE-THREE-PUSH': ('Trading Price Action Reversals', (19, 25), 'Wedge / Three-Push Reversal', '05'),
    'BB-REV-06-EXPANDING-TRIANGLE': ('Trading Price Action Reversals', (181, 182, 183), 'Expanding Triangle', '06'),
    'BB-REV-07-FINAL-FLAG': ('Trading Price Action Reversals', (80, 83, 189), 'Final Flag', '07'),
    'BB-REV-08-DOUBLE-BOTTOM-PULLBACK': ('Trading Price Action Reversals', (217, 218, 219), 'Double Bottom Pullback', '08'),
    'BB-REV-08-DOUBLE-TOP-PULLBACK': ('Trading Price Action Reversals', (217, 218, 224), 'Double Top Pullback', '08'),
    'BB-REV-09-FAILURES': ('Trading Price Action Reversals', (225, 226, 227), 'Pattern Failure', '09'),
    'BB-REV-09-MEASURED-MOVE-FAILURE': ('Trading Price Action Reversals', (225, 226), 'Measured Move Failure', '09'),
    'BB-REV-09-MINOR-REVERSAL': ('Trading Price Action Reversals', (226, 227), 'Minor Trend Reversal', '09'),
    'BB-REV-10-HUGE-VOLUME-DAILY': ('Trading Price Action Reversals', (257, 262), 'Rev 10 Huge Volume Daily', '10'),
    'BB-REV-15-ALWAYS-IN': ('Trading Price Action Reversals', (321, 322), 'Always In', '15'),
    'BB-REV-19-OPENING-REVERSAL': ('Trading Price Action Reversals', (373, 393), 'Opening Reversal', '19'),
    'BB-REV-20-GAP-OPENING': ('Trading Price Action Reversals', (395, 399), 'Gap Opening', '20'),
    'BB-REV-DOUBLE-TOP-BOTTOM': ('Trading Price Action Reversals', (86, 217), 'Double Top / Double Bottom', '8 / reversal patterns'),
    'BB-REV-MICRO-DOUBLE-TOP-BOTTOM': ('Trading Price Action Trends / Reversals', (106, 88), 'Micro Double Top / Bottom', '3 / signal-bar variations'),
    'BB-RNG-02-BREAKOUT-FOLLOWTHROUGH': ('Trading Price Action Trading Ranges', (39, 40, 41), 'Breakout Strength and Follow-Through', '02'),
    'BB-RNG-05-BREAKOUT-PULLBACK': ('Trading Price Action Trading Ranges', (30, 31, 34), 'Breakout Pullback', '05'),
    'BB-RNG-05-FAILED-BREAKOUT': ('Trading Price Action Trading Ranges', (30, 34, 48), 'Failed Breakout', '05'),
    'BB-RNG-05-FAILED-FAILURE': ('Trading Price Action Trading Ranges', (12, 30, 34), 'Failed Failure', '05'),
    'BB-RNG-06-GAPS': ('Trading Price Action Trading Ranges', (6, 7, 8), 'Rng 06 Gaps', '06'),
    'BB-RNG-12-DOUBLE-BOTTOM-BULL-FLAG': ('Trading Price Action Trading Ranges', (95, 96), 'Double Bottom Bull Flag', '12'),
    'BB-RNG-12-DOUBLE-TOP-BEAR-FLAG': ('Trading Price Action Trading Ranges', (95, 96), 'Double Top Bear Flag', '12'),
    'BB-RNG-13-TWENTY-GAP': ('Trading Price Action Trading Ranges', (100, 101), 'Twenty Gap Bar', '13'),
    'BB-RNG-14-FIRST-MA-GAP': ('Trading Price Action Trading Ranges', (102, 103), 'First Moving Average Gap Bar', '14'),
    'BB-RNG-14-GAP-BAR': ('Trading Price Action Trading Ranges', (102, 103, 104), 'Moving Average Gap Bar', '14'),
    'BB-RNG-17-H2L2-TREND-CONTEXT': ('Trading Price Action Trading Ranges', (108, 109), 'Rng 17 H2L2 Trend Context', '17'),
    'BB-RNG-17-HL-BAR-COUNT': ('Trading Price Action Trading Ranges', (29, 108, 109), 'High/Low Bar Counting', '17'),
    'BB-RNG-18-WEDGE-PULLBACK': ('Trading Price Action Trading Ranges', (4,), 'Wedge Pullback', '18'),
    'BB-RNG-19-DUELING-LINES': ('Trading Price Action Trading Ranges', (129, 130), 'Rng 19 Dueling Lines', '19'),
    'BB-RNG-20-HEAD-SHOULDERS-AS-RANGE': ('Trading Price Action Trading Ranges', (131, 132), 'Rng 20 Head Shoulders As Range', '20'),
    'BB-RNG-21-BUY-LOW-SELL-HIGH': ('Trading Price Action Trading Ranges', (134, 147), 'Trading Range Location', '21'),
    'BB-RNG-22-TIGHT-RANGE': ('Trading Price Action Trading Ranges', (48, 147), 'Tight Trading Range / Barbwire', '22'),
    'BB-RNG-23-TRIANGLE': ('Trading Price Action Trading Ranges', (147, 148), 'Triangle', '23'),
    'BB-RNG-26-TWO-REASONS': ('Trading Price Action Trading Ranges', (187, 188, 189), 'Rng 26 Two Reasons', '26'),
    'BB-RNG-29-SIGNAL-BAR-STOP': ('Trading Price Action Trading Ranges', (202, 203, 204), 'Rng 29 Signal Bar Stop', '29'),
    'BB-RNG-CTX-TREND-VS-RANGE': ('Trading Price Action Trading Ranges', (108, 109, 113), 'Rng Ctx Trend Vs Range', '17 / range context'),
    'BB-TRD-04-CANDLE-PATTERNS': ('Trading Price Action Trends', (83, 84, 85), 'Trd 04 Candle Patterns', '04'),
    'BB-TRD-05-THREE-BAR-REVERSAL': ('Trading Price Action Trends', (104,), 'Trd 05 Three Bar Reversal', '05'),
    'BB-TRD-05-TWO-BAR-REVERSAL': ('Trading Price Action Trends', (102, 103, 104), 'Trd 05 Two Bar Reversal', '05'),
    'BB-TRD-06-BREAKOUT-MODE': ('Trading Price Action Trends', (105, 106), 'Trd 06 Breakout Mode', '06'),
    'BB-TRD-06-EXHAUSTION-BAR': ('Trading Price Action Trends', (106, 115, 116), 'Trd 06 Exhaustion Bar', '06'),
    'BB-TRD-06-II-III': ('Trading Price Action Trends', (105, 106), 'ii / iii', '06'),
    'BB-TRD-06-IOI': ('Trading Price Action Trends', (105, 161), 'ioi', '06'),
    'BB-TRD-06-LEDGE': ('Trading Price Action Trends', (18,), 'Trd 06 Ledge', '06'),
    'BB-TRD-06-REVERSAL-BAR-FAILURE': ('Trading Price Action Trends', (106,), 'Trd 06 Reversal Bar Failure', '06'),
    'BB-TRD-06-SHAVED-BAR': ('Trading Price Action Trends', (106, 152, 153), 'Trd 06 Shaved Bar', '06'),
    'BB-TRD-07-OUTSIDE-BAR': ('Trading Price Action Trends', (155, 161), 'Outside Bar', '07'),
    'BB-TRD-16-MICRO-CHANNEL': ('Trading Price Action Trends', (249, 260), 'Micro Channel', '16'),
    'BB-TRD-19-TREND-STRENGTH': ('Trading Price Action Trends', (337, 338, 339), 'Signs of Strength in a Trend', '19'),
    'BB-TRD-22-TRENDING-RANGE': ('Trading Price Action Trends', (359, 382), 'Trending Trading Range', '22'),
    'BB-TRD-23-SMALL-PULLBACK-TREND': ('Trading Price Action Trends', (383, 401), 'Trd 23 Small Pullback Trend', '23'),
    'BB-TRD-23-TREND-FROM-OPEN': ('Trading Price Action Trends', (383, 401), 'Trend From Open', '23'),
    'BB-TRD-24-REVERSAL-DAY': ('Trading Price Action Trends', (415, 420), 'Reversal Day', '24'),
    'BB-TRD-25-TREND-RESUMPTION-DAY': ('Trading Price Action Trends', (423, 430), 'Trend Resumption Day', '25'),
    'BB-TRD-26-STAIRS-BROAD-CHANNEL': ('Trading Price Action Trends', (431, 436), 'Stairs / Broad Channel', '26'),
    'BB-TRD-CHANNEL': ('Trading Price Action Trends', (195, 207, 209, 248), 'Channel', '13-16'),
    'BB-TRD-MEASURED-MOVE': ('Trading Price Action Trends', (102, 165, 170, 172), 'Measured Move', 'multiple'),
    'BB-TRD-OPENING-REVERSAL': ('Trading Price Action Trends', (19, 149, 431), 'Trd Opening Reversal', 'cross-chapter'),
    'BB-TRD-SPIKE': ('Trading Price Action Trends', (279, 280, 281, 325, 358), 'Spike', '21 / breakout discussions'),
    'BB-TRD-SPIKE-CHANNEL': ('Trading Price Action Trends', (250, 258, 284), 'Spike and Channel', '21'),
    'BB-TRD-TIGHT-CHANNEL': ('Trading Price Action Trends', (24, 250, 258, 279), 'Tight Channel', '15-16'),
    'BB-TRD-TREND-RESUMPTION': ('Trading Price Action Trends', (319, 321, 423, 430), 'Trend Resumption', 'cross-chapter'),
}

# First-class knowledge semantics that were implicit or missing in the legacy candidate engine.
_EXTRA: tuple[RuleOrigin, ...] = (
    RuleOrigin('BB-RNG-02-SUCCESSFUL-BREAKOUT', 'Successful Breakout', 'Trading Price Action Trading Ranges', '2', (39, 40, 41), SourceTaxonomy.SOURCE_RULE, 'Strong breakout plus follow-through; successful breakouts function as spikes.'),
    RuleOrigin('BB-RNG-02-NESTED-TRADING-RANGE', 'Small Trading Range Within Larger Trading Range', 'Trading Price Action Trading Ranges', 'breakout context', (39, 40, 41), SourceTaxonomy.SOURCE_INTERPRETATION, 'Brooks explicitly distinguishes a breakout of a small range inside a larger range from a breakout into a new trend.'),
    RuleOrigin('BB-REV-07-FINAL-FLAG-FAILURE', 'Failed Final Flag', 'Trading Price Action Reversals', '7', (197, 198, 206, 207), SourceTaxonomy.SOURCE_RULE, 'A triggered final-flag reversal that fails can become trend resumption / breakout pullback.'),
    RuleOrigin('BB-REV-15-ALWAYS-IN-FAILURE', 'Failed Always-In Flip Attempt', 'Trading Price Action Reversals', '15', (295, 296, 297, 301), SourceTaxonomy.SOURCE_INTERPRETATION, 'An opposite spike without sufficient follow-through does not necessarily flip the prior Always-In state.'),
    RuleOrigin('BB-TRD-06-NESTED-IOI', 'Nested ioi', 'Trading Price Action Trends', '6 / pattern nesting', (105, 106, 161), SourceTaxonomy.SOURCE_INTERPRETATION, 'Combination of Brooks ioi and pattern-nesting concepts; not claimed as a separate Brooks-named rule.'),
    RuleOrigin('BB-REV-19-OPENING-SWING', 'Opening Swing', 'Trading Price Action Reversals', '19 / opening range', (373, 379, 393), SourceTaxonomy.SESSION_REQUIRED, 'Requires an explicit session/open anchor; unavailable in a generic 24/7 crypto snapshot.'),
)

REGISTRY: dict[str, RuleOrigin] = {
    rid: RuleOrigin(rid, concept, book, chapter, pages, SourceTaxonomy.SOURCE_RULE)
    for rid, (book, pages, concept, chapter) in _RAW.items()
}
REGISTRY.update({item.rule_id: item for item in _EXTRA})

def rule_origin(rule_id: str) -> RuleOrigin:
    return REGISTRY[rule_id]

def all_rule_origins() -> tuple[RuleOrigin, ...]:
    return tuple(REGISTRY[key] for key in sorted(REGISTRY))
