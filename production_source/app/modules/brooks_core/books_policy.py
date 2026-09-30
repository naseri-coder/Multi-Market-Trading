"""Versioned engineering policy for the book-grounded Brooks engine v2.

The books provide qualitative rules and examples. Any numeric threshold below that is
not directly quoted from Brooks is explicitly an engineering policy and is encoded in
``configuration_version``. Autonomous trade decisions remain disabled by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BrooksBooksPolicy:
    # Existing causal swing infrastructure. Brooks supports swing structure, but not
    # this numeric confirmation algorithm.
    swing_left_bars: int = 2
    swing_right_bars: int = 2

    # Context windows. Engineering choices used to quantify Brooks' qualitative ideas.
    context_window_bars: int = 40
    recent_window_bars: int = 20
    breakout_lookback_bars: int = 10
    pullback_window_bars: int = 24
    tight_range_window_bars: int = 6

    # Strong trend-bar proxy. Engineering thresholds for Brooks' body/tail/close ideas.
    strong_bar_min_body_fraction: Decimal = Decimal("0.60")
    strong_bar_close_extreme_fraction: Decimal = Decimal("0.25")
    always_in_min_consecutive_strong_bars: int = 2

    # Trend/range quantification. These are not Brooks-authored numeric cutoffs.
    min_directional_bar_fraction: Decimal = Decimal("0.55")
    min_recent_adjusted_displacement: Decimal = Decimal("0.12")
    min_recent_close_path_efficiency: Decimal = Decimal("0.04")
    min_ema_side_fraction: Decimal = Decimal("0.55")
    range_min_body_overlap_rate: Decimal = Decimal("0.60")
    range_max_abs_adjusted_displacement: Decimal = Decimal("0.18")
    tight_range_min_overlap_rate: Decimal = Decimal("0.70")
    tight_range_min_small_body_fraction: Decimal = Decimal("0.35")
    small_body_max_fraction: Decimal = Decimal("0.35")

    # Book 1 / Chapter 2 relative bar interpretation. Brooks explicitly compares
    # body size with roughly the prior five or 10 bars; the exact deterministic
    # lookback and minimum "series" length remain visible engineering policy.
    chapter2_relative_body_lookback_bars: int = 10
    chapter2_trending_doji_min_bars: int = 3

    # Source-style execution geometry. The books define the qualitative stop
    # decision tree; the ratio thresholds below are explicit engineering policy.
    entry_buffer_fraction: Decimal = Decimal("0.0001")

    # Legacy v2 fields retained for compatibility with the narrow books engine.
    stop_buffer_fraction_of_signal_range: Decimal = Decimal("0.02")
    atr_period: int = 14
    atr_stop_buffer_multiple: Decimal = Decimal("0.40")

    # Chapter-29 stop regime classification around the recent market's normal
    # bar size. 0.50/2.00 are engineering thresholds, not Brooks-authored values.
    stop_recent_range_period: int = 20
    normal_signal_range_min_ratio: Decimal = Decimal("0.50")
    normal_signal_range_max_ratio: Decimal = Decimal("2.00")
    large_signal_money_management_risk_fraction: Decimal = Decimal("0.70")
    small_signal_standard_stop_multiple: Decimal = Decimal("1.00")
    # V5 engineering translations of STOP-001..007 and TGT-001..003.
    # Buffers and minimum room scale with recent bars; they are not book-authored numbers.
    stop_volatility_buffer_multiple: Decimal = Decimal("0.10")
    minimum_structural_reward_range_multiple: Decimal = Decimal("0.50")
    structural_target_limit: int = 2

    # Binance USD-M Futures PRICE_FILTER tick metadata for the active production
    # symbol set. These are exchange metadata, not Brooks thresholds. Unknown
    # symbols fail closed instead of approximating one tick from decimal formatting.
    futures_tick_sizes: tuple[tuple[str, Decimal], ...] = (
        ("BTCUSDT", Decimal("0.10")),
        ("ETHUSDT", Decimal("0.01")),
        ("BNBUSDT", Decimal("0.010")),
        ("XRPUSDT", Decimal("0.0001")),
        ("SOLUSDT", Decimal("0.0100")),
        ("TRXUSDT", Decimal("0.00001")),
        ("ZECUSDT", Decimal("0.01")),
        ("HYPEUSDT", Decimal("0.00100")),
        ("DOGEUSDT", Decimal("0.000010")),
        ("XMRUSDT", Decimal("0.01")),
        ("LINKUSDT", Decimal("0.001")),
        ("ADAUSDT", Decimal("0.00010")),
        ("XLMUSDT", Decimal("0.00001")),
        ("UNIUSDT", Decimal("0.0010")),
        ("NEARUSDT", Decimal("0.0010")),
        ("BCHUSDT", Decimal("0.01")),
        ("AVAXUSDT", Decimal("0.0010")),
        ("LTCUSDT", Decimal("0.01")),
        ("CCUSDT", Decimal("0.0000100")),
        ("GRAMUSDT", Decimal("0.001000")),
        ("HBARUSDT", Decimal("0.00001")),
        ("SUIUSDT", Decimal("0.000100")),
        ("MUSDT", Decimal("0.0001000")),
        ("1000SHIBUSDT", Decimal("0.000001")),
        ("TAOUSDT", Decimal("0.01")),
    )

    target_r_multiples: tuple[Decimal, ...] = (Decimal("1"), Decimal("2"))

    # The books do not specify a single universal target for every H2/L2. R targets
    # remain engineering-only and are inactive unless decisions are explicitly enabled.
    enable_trade_decisions: bool = False

    def __post_init__(self) -> None:
        if self.swing_left_bars < 1 or self.swing_right_bars < 1:
            raise ValueError("swing confirmation bars must be >= 1")
        if self.context_window_bars < 20:
            raise ValueError("context_window_bars must be >= 20")
        if not 4 <= self.tight_range_window_bars <= self.context_window_bars:
            raise ValueError("invalid tight_range_window_bars")
        if not 4 <= self.recent_window_bars <= self.context_window_bars:
            raise ValueError("invalid recent_window_bars")
        if self.pullback_window_bars < 6:
            raise ValueError("pullback_window_bars must be >= 6")
        if not 5 <= self.chapter2_relative_body_lookback_bars <= 10:
            raise ValueError(
                "chapter2_relative_body_lookback_bars must stay within source guide 5..10"
            )
        if self.chapter2_trending_doji_min_bars < 2:
            raise ValueError("chapter2_trending_doji_min_bars must be >= 2")
        if self.always_in_min_consecutive_strong_bars < 2:
            raise ValueError("always_in_min_consecutive_strong_bars must be >= 2")
        fraction_fields = (
            self.strong_bar_min_body_fraction,
            self.strong_bar_close_extreme_fraction,
            self.min_directional_bar_fraction,
            self.min_recent_close_path_efficiency,
            self.min_ema_side_fraction,
            self.range_min_body_overlap_rate,
            self.range_max_abs_adjusted_displacement,
            self.tight_range_min_overlap_rate,
            self.tight_range_min_small_body_fraction,
            self.small_body_max_fraction,
            self.stop_buffer_fraction_of_signal_range,
        )
        if any(value < 0 or value > 1 for value in fraction_fields):
            raise ValueError("fraction policies must be between 0 and 1")
        if self.min_recent_adjusted_displacement < 0:
            raise ValueError("min_recent_adjusted_displacement must be non-negative")
        if self.entry_buffer_fraction < 0:
            raise ValueError("entry_buffer_fraction cannot be negative")
        if self.atr_period < 14:
            raise ValueError("atr_period must be at least 14")
        if self.atr_stop_buffer_multiple <= 0:
            raise ValueError("atr_stop_buffer_multiple must be positive")
        if not 14 <= self.stop_recent_range_period <= 20:
            raise ValueError("stop_recent_range_period must be between 14 and 20")
        if not Decimal("0") < self.normal_signal_range_min_ratio < Decimal("1"):
            raise ValueError("normal_signal_range_min_ratio must be between 0 and 1")
        if self.normal_signal_range_max_ratio <= Decimal("1"):
            raise ValueError("normal_signal_range_max_ratio must be greater than 1")
        if self.normal_signal_range_min_ratio >= self.normal_signal_range_max_ratio:
            raise ValueError("normal signal range ratio ordering is invalid")
        if not Decimal("0.30") <= self.large_signal_money_management_risk_fraction <= Decimal("0.70"):
            raise ValueError("large-signal money-management risk fraction must be 0.30..0.70")
        if self.small_signal_standard_stop_multiple <= 0:
            raise ValueError("small-signal standard stop multiple must be positive")
        if not Decimal("0") < self.stop_volatility_buffer_multiple <= Decimal("0.50"):
            raise ValueError("stop volatility buffer multiple must be 0..0.50")
        if self.minimum_structural_reward_range_multiple <= 0:
            raise ValueError("minimum structural reward multiple must be positive")
        if not 1 <= self.structural_target_limit <= 3:
            raise ValueError("structural_target_limit must be 1..3")
        if not self.futures_tick_sizes or any(size <= 0 for _, size in self.futures_tick_sizes):
            raise ValueError("futures tick sizes must be positive")
        if len({symbol for symbol, _ in self.futures_tick_sizes}) != len(self.futures_tick_sizes):
            raise ValueError("futures tick-size symbols must be unique")
        if not self.target_r_multiples or any(x <= 0 for x in self.target_r_multiples):
            raise ValueError("target R multiples must be positive")

    def tick_size_for_symbol(self, symbol: str) -> Decimal:
        normalized = symbol.strip().upper()
        for configured_symbol, tick_size in self.futures_tick_sizes:
            if configured_symbol == normalized:
                return tick_size
        raise ValueError(f"missing Binance Futures tick-size metadata for {normalized}")

    @property
    def configuration_version(self) -> str:
        targets = "-".join(str(x) for x in self.target_r_multiples)
        ticks = ".".join(f"{symbol}:{size}" for symbol, size in self.futures_tick_sizes)
        return (
            "books-v2-eng-"
            f"swingL{self.swing_left_bars}R{self.swing_right_bars}-"
            f"ctx{self.context_window_bars}-recent{self.recent_window_bars}-"
            f"pb{self.pullback_window_bars}-tr{self.tight_range_window_bars}-"
            f"strongBody{self.strong_bar_min_body_fraction}-"
            f"closeExt{self.strong_bar_close_extreme_fraction}-"
            f"ai{self.always_in_min_consecutive_strong_bars}-"
            f"dir{self.min_directional_bar_fraction}-"
            f"disp{self.min_recent_adjusted_displacement}-"
            f"eff{self.min_recent_close_path_efficiency}-"
            f"ema{self.min_ema_side_fraction}-"
            f"rangeOverlap{self.range_min_body_overlap_rate}-"
            f"rangeDisp{self.range_max_abs_adjusted_displacement}-"
            f"tightOverlap{self.tight_range_min_overlap_rate}-"
            f"tightSmall{self.tight_range_min_small_body_fraction}-"
            f"ch2body{self.chapter2_relative_body_lookback_bars}-"
            f"ch2doji{self.chapter2_trending_doji_min_bars}-"
            f"entry{self.entry_buffer_fraction}-"
            f"stopbuf{self.stop_buffer_fraction_of_signal_range}-"
            f"atr{self.atr_period}x{self.atr_stop_buffer_multiple}-"
            f"ch29range{self.stop_recent_range_period}-"
            f"normal{self.normal_signal_range_min_ratio}:{self.normal_signal_range_max_ratio}-"
            f"largeMM{self.large_signal_money_management_risk_fraction}-"
            f"smallSTD{self.small_signal_standard_stop_multiple}-"
            f"stopVolBuf{self.stop_volatility_buffer_multiple}-"
            f"minStructReward{self.minimum_structural_reward_range_multiple}-"
            f"structTargets{self.structural_target_limit}-"
            f"ticks[{ticks}]-"
            f"targets{targets}-exec{int(self.enable_trade_decisions)}"
        )
