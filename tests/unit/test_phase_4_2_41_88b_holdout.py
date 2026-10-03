"""Archive-safe 88B holdout contracts using current synthetic inputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.modules.brooks_core.engine_contract import TargetPlanLifecycle
from app.modules.risk_engine.service import RiskEngineService

from research_layer.current_risk_contract import read_current_risk
from research_layer.phase_4_2_41_88d.contract import (
    ARTIFACT_SCHEMA_VERSION,
    COHORT_FIELDS,
    CONFIGURATION,
    ENGINE,
    MGMT,
    RISK_SEMANTIC_MODEL,
    RULES,
    RUNNER_POLICY,
    STAT,
)
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


def test_current_contract_identity_is_explicit_and_no_legacy_risk_suffix():
    row = candidate()
    assert row["configuration_version"] == CONFIGURATION
    assert row["artifact_schema_version"] == "brooks-research-current-risk-v1"
    assert row["risk_semantic_model"] == "PLAN_WEIGHTED_PRETRADE"
    assert row["runner_policy"] == "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE"
    assert "riskrr[" not in row["configuration_version"]


def test_synthetic_holdout_is_disjoint_from_development_initialization():
    data = json.loads((ROOT / "tests/fixtures/research/synthetic_manifest.json").read_text())
    development = {row["candidate_identity"] for row in data["88f_initialization"]["cases"]}
    holdout = {row["candidate_identity"] for row in history_rows(20, prefix="holdout-b-")}
    assert development.isdisjoint(holdout)


def test_causality_uses_only_terminal_cases_strictly_before_admission():
    rows = history_rows(20)
    admission = datetime(2026, 1, 10, tzinfo=UTC)
    result = evaluate(candidate(at=admission.isoformat()), rows)
    selected = {
        row["candidate_identity"]
        for row in rows
        if datetime.fromisoformat(row["terminal_timestamp"]) < admission
    }
    assert set(result["history_case_ids"]) == selected


def test_version_mismatch_fails_closed_without_neighbor_substitution():
    rows = history_rows(20)
    rows[0]["runner_policy"] = "WRONG"
    result = evaluate(candidate(), rows)
    assert result["compatible_n"] == 19
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["legacy_similarity_used_for_admission"] is False
    assert result["max_neighbors_truncation_used"] is False


def test_realized_r_reconstruction_uses_full_initial_risk():
    entry = Decimal("100")
    stop = Decimal("90")
    target = Decimal("110")
    fraction = Decimal("0.5")
    terminal = Decimal("100")
    initial_risk = abs(entry - stop)
    realized = fraction * ((target - entry) / initial_risk)
    realized += (Decimal("1") - fraction) * ((terminal - entry) / initial_risk)
    assert realized == Decimal("0.5")


def test_sample_floor_and_complete_compatible_pool():
    insufficient = evaluate(candidate(), history_rows(19))
    assert insufficient["status"] == "INSUFFICIENT_HISTORY"
    result = evaluate(candidate(), history_rows(20))
    assert result["compatible_n"] == 20
    assert len(result["history_case_ids"]) == 20
    assert len(result["history_realized_r"]) == 20
    assert result["status"] in {"FAVORABLE", "UNFAVORABLE"}


def test_wilson_and_trader_equation_are_telemetry_only():
    result = evaluate(candidate(), history_rows(20))
    assert result["wilson"]["n"] == 20
    assert result["trader_equation_controls_admission"] is False
    assert result["legacy_similarity_used_for_admission"] is False


def test_current_plan_parity_uses_public_plan_invariants(monkeypatch):
    current = current_risk_candidate(monkeypatch)
    risk = RiskEngineService().evaluate(current)
    view = read_current_risk(current, assessment=risk, need_trade_plan=True)
    assert all(view["invariants"].values())
    assert view["plan_breakdown"]["runner_objective"] is None
    assert view["plan_breakdown"]["weighted_runner_r"] == "0"
    assert view["plan_rr"] == Decimal("1.5")
