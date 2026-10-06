"""Frozen MARC v0.1 baseline policy.

The values in this module are engineering hypotheses for validation, not claims
of profitability. They are intentionally versioned and should not be optimized
before the frozen baseline has been evaluated out of sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MARCPolicy:
    """MA 7/25/99 regime-reclaim baseline configuration."""

    fast_period: int = 7
    medium_period: int = 25
    regime_period: int = 99
    atr_period: int = 14
    persistence_bars: int = 2
    ma99_band_atr: Decimal = Decimal("0.10")
    chop_lookback: int = 20
    max_crosses_in_chop_window: int = 2
    compression_min_spread_atr: Decimal = Decimal("0.25")
    max_entry_extension_atr: Decimal = Decimal("1.50")
    structure_lookback: int = 5
    structure_buffer_atr: Decimal = Decimal("0.20")
    ma_stop_buffer_atr: Decimal = Decimal("0.50")
    max_initial_risk_atr: Decimal = Decimal("1.80")
    risk_fraction: Decimal = Decimal("0.005")
    tp1_r: Decimal = Decimal("1")
    tp2_r: Decimal = Decimal("2")
    chandelier_length: int = 22
    chandelier_atr_period: int = 22
    chandelier_multiplier: Decimal = Decimal("3")

    def __post_init__(self) -> None:
        integer_fields = (
            self.fast_period,
            self.medium_period,
            self.regime_period,
            self.atr_period,
            self.persistence_bars,
            self.chop_lookback,
            self.max_crosses_in_chop_window,
            self.structure_lookback,
            self.chandelier_length,
            self.chandelier_atr_period,
        )
        if any(value <= 0 for value in integer_fields):
            raise ValueError("MARC integer policy values must be positive")
        if not self.fast_period < self.medium_period < self.regime_period:
            raise ValueError("MARC MA periods must satisfy fast < medium < regime")
        decimal_fields = (
            self.ma99_band_atr,
            self.compression_min_spread_atr,
            self.max_entry_extension_atr,
            self.structure_buffer_atr,
            self.ma_stop_buffer_atr,
            self.max_initial_risk_atr,
            self.risk_fraction,
            self.tp1_r,
            self.tp2_r,
            self.chandelier_multiplier,
        )
        if any(value <= 0 for value in decimal_fields):
            raise ValueError("MARC decimal policy values must be positive")
        if self.risk_fraction >= 1:
            raise ValueError("risk_fraction must be less than one")

    @property
    def minimum_indicator_bars(self) -> int:
        """Minimum closed bars needed before all baseline indicators can exist."""
        return max(self.regime_period, self.atr_period + 1)

    def cross_validity_bars(self, timeframe: str) -> int:
        """Return frozen v0.1 cross validity for the supported intraday frames."""
        if timeframe == "15m":
            return 12
        if timeframe == "30m":
            return 8
        raise ValueError("MARC v0.1 supports only 15m and 30m")
