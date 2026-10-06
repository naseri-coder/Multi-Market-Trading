"""MARC R2 Fresh Reversal Transition research setup."""

from research_layer.marc_r2_pure.engine import backtest_fresh_reversal_window
from research_layer.marc_r2_pure.report import build_fresh_reversal_report

__all__ = ["backtest_fresh_reversal_window", "build_fresh_reversal_report"]
