"""Pre-registered causal MARC R2 setup search."""

from research_layer.marc_r2_search.engine import (
    R2Variant,
    backtest_r2_variant_window,
)
from research_layer.marc_r2_search.report import (
    build_causal_search_report,
    summarize_windows,
)

__all__ = [
    "R2Variant",
    "backtest_r2_variant_window",
    "build_causal_search_report",
    "summarize_windows",
]
