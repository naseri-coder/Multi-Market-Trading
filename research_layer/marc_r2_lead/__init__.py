"""MARC R2 Fresh Reversal Lead setup."""

from research_layer.marc_r2_lead.engine import backtest_frt_lead_reversal_window
from research_layer.marc_r2_lead.report import build_frt_lead_report

__all__ = ["backtest_frt_lead_reversal_window", "build_frt_lead_report"]
