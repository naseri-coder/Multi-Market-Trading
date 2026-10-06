"""MARC R2 trade-management repair experiments."""

from research_layer.marc_r2_repair.engine import (
    RepairVariant,
    backtest_repair_variant_window,
)
from research_layer.marc_r2_repair.report import build_repair_report

__all__ = [
    "RepairVariant",
    "backtest_repair_variant_window",
    "build_repair_report",
]
