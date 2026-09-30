"""Canonical Phase-2 operational pattern coverage for the Al Brooks trilogy.

Coverage is semantic, not name-driven. Some named patterns are aliases, context or
session-specific constructs and therefore must not become standalone trade candidates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CoverageRole(StrEnum):
    TRADE_CANDIDATE = "TRADE_CANDIDATE"
    OBSERVATION = "OBSERVATION"
    CONTEXT = "CONTEXT"
    ALIAS = "ALIAS"
    SESSION_REQUIRED = "SESSION_REQUIRED"


@dataclass(frozen=True, slots=True)
class PatternCoverage:
    pattern_id: str
    name: str
    source_book: str
    chapter: str
    role: CoverageRole
    implementation: str


COVERAGE: tuple[PatternCoverage, ...] = (
    PatternCoverage("REVERSAL_BAR", "Reversal Bar", "Trends", "5", CoverageRole.OBSERVATION, "signal-bar semantics in full core"),
    PatternCoverage("TWO_BAR_REVERSAL", "Two-Bar Reversal", "Trends", "5-6", CoverageRole.OBSERVATION, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("THREE_BAR_REVERSAL", "Three-Bar Reversal", "Trends", "6", CoverageRole.OBSERVATION, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("INSIDE_BAR", "Inside Bar", "Trends", "6", CoverageRole.OBSERVATION, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("II", "ii", "Trends", "6", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_candle_pattern_breakouts"),
    PatternCoverage("III", "iii", "Trends", "6", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_candle_pattern_breakouts"),
    PatternCoverage("IOI", "ioi", "Trends", "6-7", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_candle_pattern_breakouts"),
    PatternCoverage("OUTSIDE_BAR", "Outside Bar", "Trends", "7", CoverageRole.OBSERVATION, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("OO_OIO", "oo / oio", "Trends/Ranges", "7 / terms", CoverageRole.OBSERVATION, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("REVERSAL_BAR_FAILURE", "Reversal Bar Failure", "Trends", "6", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_reversal_bar_failure"),
    PatternCoverage("SHAVED_BAR", "Shaved Bar", "Trends", "6", CoverageRole.CONTEXT, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("EXHAUSTION_BAR", "Exhaustion Bar", "Trends", "6", CoverageRole.CONTEXT, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("LEDGE", "Ledge", "Trends", "terms", CoverageRole.CONTEXT, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("H1_H2_L1_L2", "High/Low 1 and 2", "Ranges", "17", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_trend_second_entry"),
    PatternCoverage("H3_L3_WEDGE_FLAG", "High/Low 3 Wedge Flag", "Ranges", "17-18", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_wedge_reversal"),
    PatternCoverage("H4_L4_COMPLEX_PULLBACK", "High/Low 4 Complex Pullback", "Ranges", "17", CoverageRole.OBSERVATION, "pattern_expansion.scan_extended_hl_recurrence_observations"),
    PatternCoverage("BREAKOUT", "Breakout", "Ranges", "1-4", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_breakout_family"),
    PatternCoverage("FAILED_BREAKOUT", "Failed Breakout", "Ranges", "5", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_breakout_family"),
    PatternCoverage("FAILED_FAILURE", "Failed Failure", "Ranges", "5", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_breakout_family"),
    PatternCoverage("BREAKOUT_PULLBACK", "Breakout Pullback/Test", "Ranges", "5", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_breakout_family"),
    PatternCoverage("GAPS", "Price / Measuring Gaps", "Ranges", "6-8", CoverageRole.CONTEXT, "pattern_expansion.scan_structure_observations"),
    PatternCoverage("TWENTY_GAP", "Twenty Gap Bar", "Ranges", "13", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_moving_average_pullback_setups"),
    PatternCoverage("FIRST_MA_GAP", "First Moving Average Gap Bar", "Ranges", "14", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_moving_average_pullback_setups"),
    PatternCoverage("SECOND_MA_GAP", "Second Moving Average Gap Bar", "Ranges", "14", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_moving_average_pullback_setups"),
    PatternCoverage("DOUBLE_TOP_BEAR_FLAG", "Double Top Bear Flag", "Ranges", "12", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_double_top_bottom"),
    PatternCoverage("DOUBLE_BOTTOM_BULL_FLAG", "Double Bottom Bull Flag", "Ranges", "12", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_double_top_bottom"),
    PatternCoverage("DUELING_LINES", "Dueling Lines", "Ranges", "19", CoverageRole.CONTEXT, "pattern_expansion.scan_structure_observations"),
    PatternCoverage("HEAD_SHOULDERS", "Head and Shoulders", "Ranges", "20", CoverageRole.ALIAS, "pattern_expansion.scan_structure_observations"),
    PatternCoverage("TRADING_RANGE", "Trading Range / Fade", "Ranges", "21", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_trading_range_fades"),
    PatternCoverage("TIGHT_TRADING_RANGE", "Tight Trading Range / Barbwire", "Ranges", "22", CoverageRole.CONTEXT, "context_classifier / final_flag"),
    PatternCoverage("TRIANGLE", "Triangle", "Ranges", "23", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_triangle_breakout"),
    PatternCoverage("WEDGE_PULLBACK", "Wedge Pullback / Three-Push Flag", "Ranges", "18", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_wedge_reversal"),
    PatternCoverage("WEDGE_REVERSAL", "Wedge Reversal", "Reversals", "5", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_wedge_reversal"),
    PatternCoverage("MICRO_WEDGE", "Micro Wedge", "Reversals", "5", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_micro_wedge"),
    PatternCoverage("MAJOR_TREND_REVERSAL", "Major Trend Reversal", "Reversals", "3", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_major_trend_reversal"),
    PatternCoverage("CLIMACTIC_REVERSAL", "Climactic Reversal", "Reversals", "4", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_climactic_reversal"),
    PatternCoverage("EXPANDING_TRIANGLE", "Expanding Triangle", "Reversals", "6", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_expanding_triangle"),
    PatternCoverage("FINAL_FLAG", "Final Flag / Micro Final Flag", "Reversals", "7", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_final_flag"),
    PatternCoverage("DOUBLE_TOP_BOTTOM_PULLBACK", "Double Top/Bottom Pullback", "Reversals", "8", CoverageRole.TRADE_CANDIDATE, "pattern_expansion.detect_double_top_bottom_pullback"),
    PatternCoverage("MICRO_DOUBLE", "Micro Double Top/Bottom", "Trends/Reversals", "6 / 3", CoverageRole.TRADE_CANDIDATE, "books_full_patterns.detect_micro_double_top_bottom"),
    PatternCoverage("PATTERN_FAILURES", "Pattern Failures", "Reversals", "9", CoverageRole.CONTEXT, "breakout/failure and reversal-bar-failure engines"),
    PatternCoverage("HUGE_VOLUME_DAILY_REVERSAL", "Huge-Volume Daily Reversal", "Reversals", "10", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("TIGHT_MICRO_CHANNEL", "Tight / Micro Channel", "Trends", "15-16", CoverageRole.CONTEXT, "advanced_context + pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("SPIKE_CHANNEL", "Spike and Channel Trend", "Trends", "21", CoverageRole.CONTEXT, "advanced_context"),
    PatternCoverage("TRENDING_RANGE", "Trending Trading Range", "Trends", "22", CoverageRole.CONTEXT, "context_classifier / structure observations"),
    PatternCoverage("SMALL_PULLBACK_TREND", "Small Pullback Trend", "Trends", "23", CoverageRole.CONTEXT, "pattern_expansion.scan_structure_observations"),
    PatternCoverage("BROAD_CHANNEL_STAIRS", "Stairs / Broad Channel", "Trends", "26", CoverageRole.CONTEXT, "pattern_expansion.scan_structure_observations"),
    PatternCoverage("SHRINKING_STAIRS", "Shrinking Stairs", "Trends", "26", CoverageRole.CONTEXT, "pattern_expansion.scan_structure_observations"),
    PatternCoverage("MEASURED_MOVE", "Measured Move", "Ranges/Trends", "7-8 / multiple", CoverageRole.CONTEXT, "advanced_context"),
    PatternCoverage("ALWAYS_IN", "Always In", "Reversals", "15", CoverageRole.CONTEXT, "context_classifier"),
    PatternCoverage("TREND_FROM_OPEN", "Trend From the Open", "Trends", "23", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
    PatternCoverage("REVERSAL_DAY", "Reversal Day", "Trends", "24", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
    PatternCoverage("TREND_RESUMPTION_DAY", "Trend Resumption Day", "Trends", "25", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
    PatternCoverage("OPENING_REVERSAL", "Opening Reversal", "Reversals", "19", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
    PatternCoverage("PREMARKET_YESTERDAY_PATTERNS", "Premarket / Yesterday Breakout Patterns", "Reversals", "17-18", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
    PatternCoverage("GAP_OPENING", "Gap Opening", "Reversals", "20", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
    PatternCoverage("SPIKE", "Spike", "Trends", "trend phase / 21", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("CHANNEL", "Trend Channel", "Trends", "trend lines and channels", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("PARABOLIC_WEDGE", "Parabolic Wedge", "Reversals", "5", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("WEDGE_TOP", "Wedge Top", "Reversals", "5", CoverageRole.ALIAS, "books_full_patterns.detect_wedge_reversal"),
    PatternCoverage("WEDGE_BOTTOM", "Wedge Bottom", "Reversals", "5", CoverageRole.ALIAS, "books_full_patterns.detect_wedge_reversal"),
    PatternCoverage("THREE_PUSH", "Three Push", "Reversals", "5", CoverageRole.ALIAS, "wedge/expanding-triangle/three-push family"),
    PatternCoverage("MEASURED_MOVE_FAILURE", "Measured Move Failure", "Reversals", "9", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("MINOR_TREND_REVERSAL", "Minor Trend Reversal", "Reversals", "9", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("TREND_RESUMPTION", "Trend Resumption", "Trends/Reversals", "general / failures", CoverageRole.CONTEXT, "pattern_expansion.scan_additional_context_observations"),
    PatternCoverage("GAP_BAR", "Moving Average Gap Bar", "Ranges", "14", CoverageRole.CONTEXT, "pattern_expansion.scan_signal_bar_observations"),
    PatternCoverage("NESTED_IOI", "Nested ioi", "Trends", "nesting + ioi", CoverageRole.TRADE_CANDIDATE, "SOURCE_INTERPRETATION: pattern_expansion.detect_candle_pattern_breakouts"),
    PatternCoverage("OPENING_SWING", "Opening Swing", "Opening-range material", "session", CoverageRole.SESSION_REQUIRED, "non-actionable without session anchor"),
)


def pattern_coverage_catalog() -> tuple[PatternCoverage, ...]:
    return COVERAGE
