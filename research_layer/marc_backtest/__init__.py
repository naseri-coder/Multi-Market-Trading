"""MARC research-only backtest and out-of-sample validation helpers."""

from research_layer.marc_backtest.engine import BacktestConfig, backtest_window
from research_layer.marc_backtest.entities import BacktestTrade, TradeFill
from research_layer.marc_backtest.report import build_validation_report

__all__ = [
    "BacktestConfig",
    "BacktestTrade",
    "TradeFill",
    "backtest_window",
    "build_validation_report",
]
