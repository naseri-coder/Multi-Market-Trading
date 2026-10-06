"""MARC R2 Lead Reversal Transition research setup."""

from research_layer.marc_r2_lead.engine import (
    backtest_lead_reversal_window,
)
from research_layer.marc_r2_lead.report import build_lead_reversal_report

__all__ = [
    "backtest_lead_reversal_window",
    "build_lead_reversal_report",
]
