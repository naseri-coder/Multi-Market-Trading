"""Frozen development and untouched-holdout verdict for MARC R2 FRT."""

from __future__ import annotations

from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_search.report import summarize_windows


def _development_passes(summary: dict[str, object]) -> bool:
    overall = summary["overall"]
    base = overall["base"]
    stress = overall["stress"]
    return bool(
        overall["trades"] >= 300
        and base["expectancy_r"] is not None
        and base["expectancy_r"] > 0.05
        and base["profit_factor"] is not None
        and base["profit_factor"] >= 1.10
        and stress["expectancy_r"] is not None
        and stress["expectancy_r"] > 0
        and stress["profit_factor"] is not None
        and stress["profit_factor"] >= 1.03
        and summary["stream_count"] >= 5
        and summary["positive_base_streams"] >= 4
    )


def _holdout_verdict(summary: dict[str, object]) -> dict[str, object]:
    overall = summary["overall"]
    base = overall["base"]
    stress = overall["stress"]
    checks = {
        "trades_at_least_200": overall["trades"] >= 200,
        "base_expectancy_positive": (
            base["expectancy_r"] is not None and base["expectancy_r"] > 0
        ),
        "base_profit_factor_at_least_1_10": (
            base["profit_factor"] is not None and base["profit_factor"] >= 1.10
        ),
        "stress_expectancy_positive": (
            stress["expectancy_r"] is not None and stress["expectancy_r"] > 0
        ),
        "stress_profit_factor_at_least_1_03": (
            stress["profit_factor"] is not None and stress["profit_factor"] >= 1.03
        ),
        "positive_base_streams_at_least_4_of_5": (
            summary["stream_count"] >= 5 and summary["positive_base_streams"] >= 4
        ),
    }
    qualified = all(checks.values())
    return {
        "qualified": qualified,
        "classification": (
            "MARC_R2_FRESH_REVERSAL_CANDIDATE"
            if qualified
            else "MARC_R2_FRESH_REVERSAL_NOT_CONFIRMED"
        ),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }


def build_fresh_reversal_report(
    *,
    development: tuple[BacktestWindowResult, ...],
    holdout: tuple[BacktestWindowResult, ...] | None,
    protocol: dict[str, object],
) -> dict[str, object]:
    dev = summarize_windows(development)
    dev_pass = _development_passes(dev)
    if dev_pass and holdout is None:
        raise ValueError("passing development result requires untouched holdout")
    if not dev_pass and holdout is not None:
        raise ValueError("holdout must not be fetched when development fails")

    hold_summary = None
    verdict = {
        "qualified": False,
        "classification": "MARC_R2_FRESH_REVERSAL_DEVELOPMENT_FAILED",
        "checks": {},
        "failed_checks": ["development_gate"],
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }
    if holdout is not None:
        hold_summary = summarize_windows(holdout)
        verdict = _holdout_verdict(hold_summary)

    return {
        "schema": "MARC_R2_FRESH_REVERSAL_V1",
        "protocol": protocol,
        "development": {
            "summary": dev,
            "passed": dev_pass,
            "gate": {
                "minimum_trades": 300,
                "base_expectancy_r": ">0.05",
                "base_profit_factor": ">=1.10",
                "stress_expectancy_r": ">0",
                "stress_profit_factor": ">=1.03",
                "positive_base_streams": ">=4 of 5",
            },
        },
        "untouched_cross_sectional_holdout": {
            "summary": hold_summary,
            "verdict": verdict,
        },
        "final_classification": verdict["classification"],
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }
