"""Archive-safe 88C extended holdout contracts using current synthetic inputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.modules.brooks_core.engine_contract import TargetPlanLifecycle
from app.modules.risk_engine.service import RiskEngineService

from research_layer.current_risk_contract import read_current_risk
from research_layer.phase_4_2_41_88d.contract import *
from research_layer.phase_4_2_41_88d.statistics import evaluate

ROOT = Path(__file__).resolve().parents[2]


def candidate(identity="candidate", at="2026-01-10T00:00:00+00:00"):
    return {
        "candidate_identity": identity,
        "candidate_timestamp": at,
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "direction": "LONG",
        "setup_type": "FAILED_BREAKOUT_LONG",
        "engine_version": ENGINE,
        "rule_set_version": RULES,
        "configuration_version": CONFIGURATION,
        "exchange": "binance",
        "market_type": "futures",
        "management_version": MGMT,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "risk_semantic_model": RISK_SEMANTIC_MODEL,
        "runner_policy": RUNNER_POLICY,
        "statistics_contract_version": STAT,
    }


def history_rows(count, *, prefix="h", start=datetime(2026, 1, 1, tzinfo=UTC)):
    base = candidate()
    rows = []
    for index in range(count):
        terminal = start + timedelta(hours=index)
        realized = Decimal("1.0") if index % 3 else Decimal("-0.35")
        rows.append(
            {
                **{key: base[key] for key in COHORT_FIELDS},
                "candidate_identity": f"{prefix}{index:03d}",
                "candidate_timestamp": (terminal - timedelta(minutes=30)).isoformat(),
                "terminal_timestamp": terminal.isoformat(),
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "direction": "LONG",
                "setup_type": "FAILED_BREAKOUT_LONG",
                "realized_r": str(realized),
            }
        )
    return rows


def current_risk_candidate(monkeypatch):
    context = SimpleNamespace(regime="BULL_TREND", channel_quality="UNRESOLVED")
    monkeypatch.setattr(
        "app.modules.risk_engine.calculator.build_market_context", lambda _: context
    )
    monkeypatch.setattr(
        "research_layer.current_risk_contract.build_market_context", lambda _: context
    )
    return SimpleNamespace(
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("99"),
        targets=(Decimal("100.5"), Decimal("103")),
        target_plan_lifecycle=TargetPlanLifecycle("synthetic-plan", "TREND_TRADE", "LONG", 0),
        snapshot=SimpleNamespace(
            candles=(SimpleNamespace(high=Decimal("99.5"), low=Decimal("98.5")),)
        ),
        rule_ids=(),
        rule_evidence=(),
        setup_type="SYNTHETIC",
        reversal_outcome_context=None,
    )


def test_extended_holdout_remains_identity_disjoint():
    base = {row["candidate_identity"] for row in history_rows(20, prefix="b-")}
    extension = {row["candidate_identity"] for row in history_rows(25, prefix="c-")}
    assert base.isdisjoint(extension)


def test_extended_holdout_has_complete_terminal_lineage():
    rows = history_rows(25, prefix="c-")
    for row in rows:
        assert datetime.fromisoformat(row["candidate_timestamp"]) < datetime.fromisoformat(
            row["terminal_timestamp"]
        )
        assert row["realized_r"] is not None


def test_current_cohort_identity_has_all_fail_closed_fields():
    row = candidate()
    assert tuple(key for key in COHORT_FIELDS if key not in row) == ()
    assert row["configuration_version"] == CONFIGURATION
    assert row["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert row["risk_semantic_model"] == RISK_SEMANTIC_MODEL
    assert row["runner_policy"] == RUNNER_POLICY


def test_extended_pool_keeps_all_compatible_cases_without_truncation():
    result = evaluate(candidate(), history_rows(25, prefix="c-"))
    assert result["compatible_n"] == 25
    assert len(result["history_case_ids"]) == 25
    assert result["max_neighbors_truncation_used"] is False
    assert result["legacy_similarity_used_for_admission"] is False


def test_future_or_equal_terminal_time_is_excluded():
    at = datetime(2026, 1, 10, tzinfo=UTC)
    rows = history_rows(20, start=at - timedelta(hours=19))
    rows[-1]["terminal_timestamp"] = at.isoformat()
    result = evaluate(candidate(at=at.isoformat()), rows)
    assert rows[-1]["candidate_identity"] not in result["history_case_ids"]


def test_bootstrap_is_deterministic_for_same_current_contract():
    rows = history_rows(20, prefix="det-")
    first = evaluate(candidate(), rows)
    second = evaluate(candidate(), rows)
    assert first["bootstrap_t_lower95"] == second["bootstrap_t_lower95"]
    assert first["bootstrap_t_upper95"] == second["bootstrap_t_upper95"]
    assert first["bootstrap_diagnostics"]["seed"] == second["bootstrap_diagnostics"]["seed"]


def test_statistical_admission_uses_bootstrap_lower_bound_not_wilson():
    result = evaluate(candidate(), history_rows(20, prefix="policy-"))
    assert result["trader_equation_controls_admission"] is False
    assert (result["status"] == "FAVORABLE") == (result["bootstrap_t_lower95"] > 0)


def test_current_plan_parity_rejects_mutated_allocation(monkeypatch):
    current = current_risk_candidate(monkeypatch)
    risk = RiskEngineService().evaluate(current)
    risk.metadata["risk_semantic_breakdown"]["plan_reward"]["target_contributions"][1][
        "allocation_fraction"
    ] = "1"
    with pytest.raises(ValueError, match="CURRENT_RISK_PLAN_MISMATCH"):
        read_current_risk(current, assessment=risk)
