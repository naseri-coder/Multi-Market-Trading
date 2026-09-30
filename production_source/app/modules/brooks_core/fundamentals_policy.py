"""Engineering policy for the PDF-grounded Brooks fundamentals core.

IMPORTANT:
- EMA(20), H2/L2 concepts, context, HH/HL and LH/LL structure are source-grounded.
- Numeric swing confirmation, entry buffer, stop construction and R-multiple targets are
  engineering choices because the reviewed 150-slide PDF does not define exact values.
- Autonomous trade decisions are disabled by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FundamentalsExecutionPolicy:
    swing_left_bars: int = 2
    swing_right_bars: int = 2
    pullback_window_bars: int = 20
    entry_buffer_fraction: Decimal = Decimal("0.0001")
    stop_buffer_fraction_of_signal_range: Decimal = Decimal("0.10")
    target_r_multiples: tuple[Decimal, ...] = (
        Decimal("1"),
        Decimal("2"),
    )
    enable_trade_decisions: bool = False

    def __post_init__(self) -> None:
        if self.swing_left_bars < 1 or self.swing_right_bars < 1:
            raise ValueError("swing confirmation bars must be >= 1")
        if self.pullback_window_bars < 4:
            raise ValueError("pullback_window_bars must be >= 4")
        if self.entry_buffer_fraction < 0:
            raise ValueError("entry_buffer_fraction cannot be negative")
        if not Decimal("0") <= self.stop_buffer_fraction_of_signal_range <= Decimal("1"):
            raise ValueError("stop buffer fraction must be between 0 and 1")
        if not self.target_r_multiples:
            raise ValueError("at least one target R multiple is required")
        if any(value <= 0 for value in self.target_r_multiples):
            raise ValueError("target R multiples must be positive")

    @property
    def configuration_version(self) -> str:
        targets = "-".join(str(x) for x in self.target_r_multiples)
        return (
            "phase7c-eng-"
            f"swingL{self.swing_left_bars}R{self.swing_right_bars}-"
            f"pb{self.pullback_window_bars}-"
            f"entry{self.entry_buffer_fraction}-"
            f"stopbuf{self.stop_buffer_fraction_of_signal_range}-"
            f"targets{targets}-"
            f"exec{int(self.enable_trade_decisions)}"
        )
