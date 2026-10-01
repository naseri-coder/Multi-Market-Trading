"""Versioned policy for the Brooks trilogy full-core engine v3.

Source-derived counts are kept when Brooks is explicit (for example a breakout
pullback of roughly one to five bars, three pushes for a wedge, and two reasons for a
trade).  Values Brooks does not define numerically are marked as engineering policy and
are included in the configuration version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.brooks_core.books_policy import BrooksBooksPolicy


@dataclass(frozen=True, slots=True)
class BrooksFullCorePolicy:
    context: BrooksBooksPolicy = field(default_factory=BrooksBooksPolicy)

    # Source-style windows / counts.
    breakout_pullback_max_bars: int = 5  # Brooks: "one to about five bars".
    wedge_push_count: int = 3
    min_trade_reasons: int = 2
    major_trend_line_anchor_spacing_bars: int = 10  # Brooks: major TL typically >=10 bars apart.

    # Engineering policies needed to make qualitative rules deterministic.
    breakout_scan_bars: int = 12
    range_window_bars: int = 40
    range_extreme_zone_fraction: Decimal = Decimal("0.25")
    double_test_tolerance_fraction_of_recent_range: Decimal = Decimal("0.12")
    wedge_lookback_bars: int = 45
    mtr_lookback_bars: int = 50
    # V5 engineering witnesses for MTR-001..003; Brooks gives no OHLC constants.
    mtr_second_reversal_min_range_multiple: Decimal = Decimal("0.50")
    mtr_retest_max_bars: int = 12
    barbwire_veto_window_bars: int = 6
    climax_lookback_bars: int = 4
    climax_min_strong_bars: int = 2
    climax_range_multiple_of_recent_median: Decimal = Decimal("1.50")
    final_flag_window_bars: int = 6
    final_flag_max_span_fraction_of_recent_range: Decimal = Decimal("0.35")
    final_flag_min_trend_span_multiple: Decimal = Decimal("6.0")
    tight_channel_window_bars: int = 8
    spike_channel_scan_bars: int = 16
    micro_double_tolerance_fraction_of_median_range: Decimal = Decimal("0.25")

    # Execution remains a separate switch.  The detector is fully functional while
    # returning NO_SIGNAL so production wiring does not change merely by installing it.
    enable_trade_decisions: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.breakout_pullback_max_bars <= 5:
            raise ValueError("breakout_pullback_max_bars must stay within source-style 1..5")
        if self.wedge_push_count != 3:
            raise ValueError("wedge_push_count must remain 3 for Brooks wedge/three-push semantics")
        if self.min_trade_reasons < 2:
            raise ValueError("Brooks core requires at least two reasons")
        if self.major_trend_line_anchor_spacing_bars < 10:
            raise ValueError("major trend-line anchor spacing must be >= 10 bars")
        if self.range_window_bars < 20:
            raise ValueError("range_window_bars must be >= 20")
        if self.breakout_scan_bars < 3:
            raise ValueError("breakout_scan_bars must be >= 3")
        fractions = (
            self.range_extreme_zone_fraction,
            self.double_test_tolerance_fraction_of_recent_range,
            self.final_flag_max_span_fraction_of_recent_range,
            self.micro_double_tolerance_fraction_of_median_range,
        )
        if any(x <= 0 or x >= 1 for x in fractions):
            raise ValueError("fraction policies must be between 0 and 1")
        if (
            self.tight_channel_window_bars < 4
            or self.spike_channel_scan_bars < self.tight_channel_window_bars
        ):
            raise ValueError("invalid tight/spike channel windows")
        if self.climax_range_multiple_of_recent_median <= 1:
            raise ValueError("climax range multiple must be > 1")
        if self.final_flag_min_trend_span_multiple <= 1:
            raise ValueError("final-flag trend span multiple must be > 1")
        if self.mtr_second_reversal_min_range_multiple <= 0:
            raise ValueError("MTR second-reversal displacement must be positive")
        if self.mtr_retest_max_bars < 2:
            raise ValueError("MTR retest window must be >= 2")
        if self.barbwire_veto_window_bars < 4:
            raise ValueError("barbwire veto window must be >= 4")

    @property
    def configuration_version(self) -> str:
        return (
            "books-full-v3-"
            f"ctx[{self.context.configuration_version}]-"
            f"bp{self.breakout_pullback_max_bars}-"
            f"bscan{self.breakout_scan_bars}-"
            f"rng{self.range_window_bars}z{self.range_extreme_zone_fraction}-"
            f"dbl{self.double_test_tolerance_fraction_of_recent_range}-"
            f"wedge{self.wedge_push_count}lb{self.wedge_lookback_bars}-"
            f"mtr{self.mtr_lookback_bars}tl{self.major_trend_line_anchor_spacing_bars}-"
            f"mtr2r{self.mtr_second_reversal_min_range_multiple}rt{self.mtr_retest_max_bars}-"
            f"bw{self.barbwire_veto_window_bars}-"
            f"clx{self.climax_lookback_bars}x{self.climax_range_multiple_of_recent_median}-"
            f"ff{self.final_flag_window_bars}x{self.final_flag_max_span_fraction_of_recent_range}"
            f"late{self.final_flag_min_trend_span_multiple}-"
            f"tc{self.tight_channel_window_bars}-sc{self.spike_channel_scan_bars}-"
            f"md{self.micro_double_tolerance_fraction_of_median_range}-"
            f"reasons{self.min_trade_reasons}-exec{int(self.enable_trade_decisions)}"
        )
