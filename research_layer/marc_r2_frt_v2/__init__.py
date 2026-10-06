"""MARC R2 Fresh Reversal Transition v0.2 with execution viability."""

from research_layer.marc_r2_frt_v2.engine import (
    FRT_MAX_STRESS_DRAG_R,
    backtest_frt_execution_viable_window,
)
from research_layer.marc_r2_frt_v2.report import build_frt_v2_report

__all__ = [
    "FRT_MAX_STRESS_DRAG_R",
    "backtest_frt_execution_viable_window",
    "build_frt_v2_report",
]
