"""Frozen development and untouched-holdout verdict for MARC R2 FRT v0.2."""

from __future__ import annotations

from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_pure.report import (
    _development_passes,
    build_fresh_reversal_report,
)


def build_frt_v2_report(
    *,
    development: tuple[BacktestWindowResult, ...],
    holdout: tuple[BacktestWindowResult, ...] | None,
    protocol: dict[str, object],
) -> dict[str, object]:
    """Reuse the frozen FRT gate while versioning the setup/report separately."""
    report = build_fresh_reversal_report(
        development=development,
        holdout=holdout,
        protocol=protocol,
    )
    report["schema"] = "MARC_R2_FRT_EXECUTION_V2"
    report["setup_version"] = "MARC_R2_FRT_EXECUTION_V0_2"
    report["development"]["gate_source"] = "UNCHANGED_FROM_FRT_V0_1"
    return report


__all__ = ["_development_passes", "build_frt_v2_report"]
