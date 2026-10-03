from __future__ import annotations

import importlib.util
import json
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.modules.market_data.entities import Candle
from research_layer.phase_4_2_41_88d.contract import *
from research_layer.phase_4_2_41_88d.lifecycle import advance, new_state
from research_layer.phase_4_2_41_88d.statistics import evaluate
from research_layer.phase_4_2_41_88d.store import ShadowStore

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/legacy/research_layer/phase_4_2_41_88d/live_shadow.py.txt"


def fixture():
    return json.loads((ROOT / "tests/fixtures/research/synthetic_manifest.json").read_text())


def candle(m, o, h, l, c):
    t = datetime(2026, 1, 1, 0, m, tzinfo=UTC)
    return Candle(t, t + timedelta(seconds=59), D(str(o)), D(str(h)), D(str(l)), D(str(c)), D("1"))


def cand(plan=None):
    management = plan or {
        "policy_version": MGMT,
        "context_class": "REVERSAL_OR_TRANSITION",
        "initial_stop_loss": "90",
        "initial_risk": "10",
        "target_exit_fractions": {"1": "0.5", "2": "0.5"},
        "runner_fraction": "0",
        "breakeven_mode": "AFTER_PARTIAL",
        "source_rule_ids": ["X"],
    }
    return {
        "candidate_identity": "c1",
        "candidate_timestamp": "2026-01-01T00:00:00+00:00",
        "snapshot_captured_at": "2025-12-31T23:59:59+00:00",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "direction": "LONG",
        "setup_type": "FAILED_BREAKOUT_LONG",
        "entry": "100",
        "initial_stop": "90",
        "targets": ["110", "120"],
        "management_plan": management,
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
        "source_frozen_contract_sha": CONTRACT_SHA,
    }


def test_contract_and_initialization_frozen():
    assert_contract()
    init = fixture()["88f_initialization"]
    assert len(init["cases"]) == 72
    assert len({row["candidate_identity"] for row in init["cases"]}) == 72
    assert init["source_role"] == "MODEL_DEVELOPMENT_INITIALIZATION"
    assert init["excluded_sources"]["phase_88e_interrupted_forward"] == 0


def test_offline_reproduction_uses_current_synthetic_invariants_only():
    parity = fixture()["current_plan_parity"]
    assert parity["kind"] == "CURRENT_PLAN_ALLOCATION_INVARIANTS"
    assert parity["historical_counts_are_provenance_only"] is True
    assert all(row["pass"] for row in parity["detailed_synthetic_checks"])


def test_version_mismatch_fails_closed():
    candidate = cand()
    history = []
    for i in range(25):
        history.append({
            **{key: candidate[key] for key in COHORT_FIELDS},
            "candidate_identity": f"h{i}",
            "candidate_timestamp": "2025-12-01T00:00:00+00:00",
            "terminal_timestamp": "2025-12-02T00:00:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "LONG",
            "setup_type": "FAILED_BREAKOUT_LONG",
            "realized_r": "1",
        })
    history[0]["statistics_contract_version"] = "WRONG"
    assert evaluate(candidate, history)["compatible_n"] == 24
    for row in history:
        row["statistics_contract_version"] = "WRONG"
    assert evaluate(candidate, history)["status"] == "INSUFFICIENT_HISTORY"


def test_initial_stop_realized_r():
    c = cand()
    state = advance(c, new_state(c), [candle(1, 99, 101, 99, 100), candle(2, 100, 101, 89, 90)], [])
    assert state["terminal_reason"] == "INITIAL_STOP_HIT"
    assert D(state["realized_r"]) == D("-1")


def test_partial_then_breakeven_realized_r():
    c = cand()
    state = advance(
        c, new_state(c),
        [candle(1, 99, 101, 99, 100), candle(2, 105, 111, 101, 108), candle(3, 103, 105, 99, 100)],
        [],
    )
    assert state["terminal_reason"] == "BREAKEVEN"
    assert D(state["realized_r"]) == D("0.5")


def test_staged_completion_realized_r():
    c = cand()
    state = advance(
        c, new_state(c),
        [candle(1, 99, 101, 99, 100), candle(2, 105, 111, 101, 108), candle(3, 115, 121, 111, 120)],
        [],
    )
    assert state["terminal_reason"] == "TARGET_STAGED_COMPLETION"
    assert D(state["realized_r"]) == D("1.5")


def test_runner_reversal_realized_r():
    plan = {
        "policy_version": MGMT,
        "context_class": "STRONG_TREND",
        "initial_stop_loss": "90",
        "initial_risk": "10",
        "target_exit_fractions": {"1": "0.5", "2": "0"},
        "runner_fraction": "0.5",
        "breakeven_mode": "STRUCTURE_ONLY",
        "source_rule_ids": ["X"],
    }
    c = cand(plan)
    evidence = [
        {
            "candidate_identity": "c1",
            "approved_at": "2026-01-01T00:00:00+00:00",
            "candle_closed_at": "2025-12-31T23:59:59+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "LONG",
            "always_in": "LONG",
        },
        {
            "candidate_identity": "opp",
            "approved_at": "2026-01-01T00:02:30+00:00",
            "candle_closed_at": "2026-01-01T00:02:30+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "SHORT",
            "always_in": "SHORT",
        },
    ]
    state = advance(
        c, new_state(c),
        [candle(1, 99, 101, 99, 100), candle(2, 105, 111, 101, 108), candle(3, 107, 109, 104, 105)],
        evidence,
    )
    assert state["terminal_reason"] == "RUNNER_REVERSAL"
    assert D(state["realized_r"]) == D("0.75")


def test_ambiguity_excluded():
    c = cand()
    state = advance(c, new_state(c), [candle(1, 99, 111, 89, 100)], [])
    assert state["status"] == "AMBIGUOUS"
    assert state["realized_r"] is None


def test_store_decision_immutable_and_isolated():
    with tempfile.TemporaryDirectory() as td:
        store = ShadowStore(Path(td) / "shadow.sqlite")
        c = cand()
        store.add_candidate(c, {"status": "UNFAVORABLE"}, new_state(c))
        store.add_candidate(c, {"status": "FAVORABLE"}, new_state(c))
        assert store.candidates()[0][1]["status"] == "UNFAVORABLE"
        store.close()


def test_no_production_writer_imports_or_publication():
    raw = ARCHIVE.read_text().lower()
    assert "original sha256: b86371185450d9d51e4349bca4244f592ef131e1aa53ed720b343dfe0750192d" in raw
    forbidden = (
        "from app.db", "import app.db", "app.modules.signal_intelligence",
        "app.modules.signal_gate", "app.modules.operations.telegram",
        "app.modules.signals.repository", "app.modules.signals.service",
    )
    assert not any(item in raw for item in forbidden)
    assert ".send_message(" not in raw and ".publish(" not in raw
    assert ARCHIVE.suffixes == [".py", ".txt"]
    assert importlib.util.find_spec("research_layer.phase_4_2_41_88d.live_shadow") is None


def test_section_c_frozen_parity_all_pass():
    parity = fixture()["current_plan_parity"]
    expected = {"exact14": 14, "holdout67": 67, "bootstrap86": 86}
    assert sum(row["expected_rows"] for row in parity["groups"].values()) == 167
    for name, count in expected.items():
        assert parity["groups"][name]["expected_rows"] == count
        assert parity["groups"][name]["passed_rows"] == count
    assert all(row["pass"] and all(row["checks"].values()) for row in parity["detailed_synthetic_checks"])
