"""Frozen selector and untouched-holdout verdict for MARC R2 exit repair."""

from __future__ import annotations

from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_search.report import summarize_windows


def _passes_dev(summary: dict[str, object]) -> bool:
    o=summary["overall"]; b=o["base"]; s=o["stress"]
    return bool(
        o["trades"] >= 750
        and b["expectancy_r"] is not None and b["expectancy_r"] > 0
        and b["profit_factor"] is not None and b["profit_factor"] > 1.05
        and s["expectancy_r"] is not None and s["expectancy_r"] > 0
        and s["profit_factor"] is not None and s["profit_factor"] > 1.0
    )


def select_variant(summaries: dict[str, dict[str, object]]) -> str | None:
    eligible=[
        (name,summary) for name,summary in summaries.items()
        if name!="R1_BASELINE" and _passes_dev(summary)
    ]
    if not eligible:
        return None
    eligible.sort(
        key=lambda item:(
            item[1]["overall"]["stress"]["expectancy_r"],
            item[1]["overall"]["base"]["expectancy_r"],
            item[0],
        ),
        reverse=True,
    )
    return eligible[0][0]


def _holdout(summary: dict[str, object]) -> dict[str, object]:
    o=summary["overall"]; b=o["base"]; s=o["stress"]; tf=summary["by_timeframe"]
    checks={
        "trades_at_least_500":o["trades"]>=500,
        "base_expectancy_positive":b["expectancy_r"] is not None and b["expectancy_r"]>0,
        "base_pf_at_least_1_10":b["profit_factor"] is not None and b["profit_factor"]>=1.10,
        "stress_expectancy_positive":s["expectancy_r"] is not None and s["expectancy_r"]>0,
        "stress_pf_at_least_1_03":s["profit_factor"] is not None and s["profit_factor"]>=1.03,
        "positive_streams_at_least_6_of_10":summary["stream_count"]>=10 and summary["positive_base_streams"]>=6,
        "both_timeframes_positive_base":all(
            k in tf and tf[k]["base"]["expectancy_r"] is not None and tf[k]["base"]["expectancy_r"]>0
            for k in ("15m","30m")
        ),
    }
    qualified=all(checks.values())
    return {
        "qualified":qualified,
        "classification":"MARC_R2_PURE_SETUP_CANDIDATE" if qualified else "MARC_R2_HOLDOUT_NOT_CONFIRMED",
        "checks":checks,
        "failed_checks":[k for k,v in checks.items() if not v],
        "runtime_approval":"DENIED_RESEARCH_ONLY",
    }


def build_repair_report(
    *,
    development: dict[str, tuple[BacktestWindowResult,...]],
    selected_variant: str | None,
    holdout: tuple[BacktestWindowResult,...] | None,
    protocol: dict[str,object],
) -> dict[str,object]:
    summaries={k:summarize_windows(v) for k,v in sorted(development.items())}
    if select_variant(summaries)!=selected_variant:
        raise RuntimeError("selected repair variant violates frozen selector")
    hold_summary=None
    verdict={
        "qualified":False,
        "classification":"NO_DEVELOPMENT_VARIANT_PASSED",
        "checks":{},
        "failed_checks":["development_gate"],
        "runtime_approval":"DENIED_RESEARCH_ONLY",
    }
    if selected_variant is not None:
        if holdout is None:
            raise ValueError("selected repair variant requires holdout")
        hold_summary=summarize_windows(holdout)
        verdict=_holdout(hold_summary)
    return {
        "schema":"MARC_R2_EXIT_REPAIR_V1",
        "protocol":protocol,
        "development":{"summaries":summaries,"selected_variant":selected_variant},
        "untouched_cross_sectional_holdout":{"summary":hold_summary,"verdict":verdict},
        "final_classification":verdict["classification"],
        "runtime_approval":"DENIED_RESEARCH_ONLY",
    }
