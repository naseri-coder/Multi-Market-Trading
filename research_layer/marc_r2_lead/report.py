"""Frozen development and untouched-holdout verdict for MARC R2 LRT."""

from __future__ import annotations

from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_pure.report import build_fresh_reversal_report


def build_lead_reversal_report(
    *,
    development: tuple[BacktestWindowResult, ...],
    holdout: tuple[BacktestWindowResult, ...] | None,
    protocol: dict[str, object],
) -> dict[str, object]:
    """Reuse the unchanged FRT development/holdout gates."""
    report = build_fresh_reversal_report(
        development=development,
        holdout=holdout,
        protocol=protocol,
    )
    report["schema"] = "MARC_R2_LEAD_REVERSAL_V1"
    report["setup_version"] = "MARC_R2_LEAD_REVERSAL_V0_3"
    report["development"]["gate_source"] = "UNCHANGED_FROM_FRT_V0_1"
    if report["untouched_cross_sectional_holdout"]["verdict"]["qualified"]:
        report["untouched_cross_sectional_holdout"]["verdict"][
            "classification"
        ] = "MARC_R2_LEAD_REVERSAL_CANDIDATE"
        report["final_classification"] = "MARC_R2_LEAD_REVERSAL_CANDIDATE"
    return report
