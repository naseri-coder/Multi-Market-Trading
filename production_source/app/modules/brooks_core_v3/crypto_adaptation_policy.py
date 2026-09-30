"""Versioned engineering policy for Brooks Core v3 Phase 2 crypto adaptation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CryptoAdaptationPolicy:
    volatility_recent_bars: int = 20
    volatility_baseline_bars: int = 60
    volatility_low_ratio: Decimal = Decimal("0.65")
    volatility_high_ratio: Decimal = Decimal("1.50")
    volatility_extreme_ratio: Decimal = Decimal("2.25")

    volume_baseline_bars: int = 20
    volume_low_ratio: Decimal = Decimal("0.60")
    volume_high_ratio: Decimal = Decimal("1.50")
    volume_spike_ratio: Decimal = Decimal("2.50")

    fake_breakout_range_bars: int = 20
    fake_breakout_rejection_bars: int = 3
    fake_breakout_min_excursion_fraction: Decimal = Decimal("0.02")

    liquidity_thin_spread_bps: Decimal = Decimal("8")
    liquidity_deep_spread_bps: Decimal = Decimal("2")
    liquidity_imbalance_ratio: Decimal = Decimal("2")
    liquidity_thin_depth_ratio: Decimal = Decimal("0.05")
    liquidity_deep_depth_ratio: Decimal = Decimal("0.25")

    funding_crowded_abs_threshold: Decimal = Decimal("0.0005")
    open_interest_growth_threshold: Decimal = Decimal("0.03")

    mtf_min_resolved_timeframes: int = 2

    def __post_init__(self) -> None:
        if self.volatility_recent_bars < 5:
            raise ValueError("volatility_recent_bars must be >= 5")
        if self.volatility_baseline_bars < self.volatility_recent_bars:
            raise ValueError("volatility_baseline_bars must cover recent window")
        if self.volume_baseline_bars < 5:
            raise ValueError("volume_baseline_bars must be >= 5")
        if self.fake_breakout_range_bars < 5:
            raise ValueError("fake_breakout_range_bars must be >= 5")
        if not 1 <= self.fake_breakout_rejection_bars <= 10:
            raise ValueError("fake_breakout_rejection_bars must be within 1..10")
        ordered = (
            self.volatility_low_ratio,
            self.volatility_high_ratio,
            self.volatility_extreme_ratio,
        )
        if not Decimal("0") < ordered[0] < Decimal("1") < ordered[1] < ordered[2]:
            raise ValueError("invalid volatility ratio ordering")
        volume_ordered = (
            self.volume_low_ratio,
            self.volume_high_ratio,
            self.volume_spike_ratio,
        )
        if not (
            Decimal("0") < volume_ordered[0]
            < Decimal("1") < volume_ordered[1] < volume_ordered[2]
        ):
            raise ValueError("invalid volume ratio ordering")
        if not Decimal("0") < self.fake_breakout_min_excursion_fraction < Decimal("1"):
            raise ValueError("fake breakout excursion fraction must be between 0 and 1")
        if self.liquidity_thin_spread_bps <= self.liquidity_deep_spread_bps:
            raise ValueError("thin spread threshold must exceed deep spread threshold")
        if self.liquidity_imbalance_ratio <= Decimal("1"):
            raise ValueError("liquidity imbalance ratio must be > 1")
        if not Decimal("0") < self.liquidity_thin_depth_ratio < self.liquidity_deep_depth_ratio:
            raise ValueError("invalid depth-ratio thresholds")
        if self.funding_crowded_abs_threshold <= 0:
            raise ValueError("funding threshold must be positive")
        if self.open_interest_growth_threshold <= 0:
            raise ValueError("open-interest growth threshold must be positive")
        if self.mtf_min_resolved_timeframes < 2:
            raise ValueError("mtf_min_resolved_timeframes must be >= 2")

    @property
    def configuration_version(self) -> str:
        return (
            "brooks-core-v3-phase2-crypto-"
            f"vol{self.volatility_recent_bars}/{self.volatility_baseline_bars}-"
            f"vr{self.volatility_low_ratio}/{self.volatility_high_ratio}/"
            f"{self.volatility_extreme_ratio}-"
            f"volume{self.volume_baseline_bars}-"
            f"vrr{self.volume_low_ratio}/{self.volume_high_ratio}/{self.volume_spike_ratio}-"
            f"fake{self.fake_breakout_range_bars}/{self.fake_breakout_rejection_bars}/"
            f"{self.fake_breakout_min_excursion_fraction}-"
            f"liqSpread{self.liquidity_deep_spread_bps}/"
            f"{self.liquidity_thin_spread_bps}-"
            f"liqImb{self.liquidity_imbalance_ratio}-"
            f"liqDepth{self.liquidity_thin_depth_ratio}/"
            f"{self.liquidity_deep_depth_ratio}-"
            f"fund{self.funding_crowded_abs_threshold}-"
            f"oi{self.open_interest_growth_threshold}-mtf{self.mtf_min_resolved_timeframes}"
        )
