from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from research_layer.phase_4_2_41_88e.contract import *
from research_layer.phase_4_2_41_88e.statistics import evaluate

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/legacy/research_layer/phase_4_2_41_88e/live_shadow.py.txt"


def fixture():
    return json.loads((ROOT / "tests/fixtures/research/synthetic_manifest.json").read_text())


def archived_source():
    raw = ARCHIVE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "d90134653bc6ea317b98ffc4f75ed86b281f526f5d05ed364d165f9b38ebd3c4"
    )
    text = raw.decode()
    assert (
        "Original SHA256: 4fa03bb9fc2ac42046a2dd971955f9c472cda4b72116459b77dfdf400c68b34c" in text
    )
    return text


def current_candidate():
    return {
        "candidate_identity": "synthetic-current",
        "candidate_timestamp": "2026-01-03T00:00:00+00:00",
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


def test_statistics_contract_unchanged_and_module_hash_same_as_88d():
    assert_contract()
    assert (ROOT / "research_layer/phase_4_2_41_88e/statistics.py").read_bytes() == (
        ROOT / "research_layer/phase_4_2_41_88d/statistics.py"
    ).read_bytes()


def test_no_production_writers_or_publication_imports():
    src = archived_source().lower()
    forbidden = (
        "from app.db",
        "import app.db",
        "app.modules.signal_intelligence",
        "app.modules.signal_gate",
        "app.modules.operations.telegram",
        "app.modules.signals.repository",
        "app.modules.signals.service",
    )
    assert not any(item in src for item in forbidden)
    assert ".send_message(" not in src and ".publish(" not in src
    assert ARCHIVE.suffixes == [".py", ".txt"]
    assert importlib.util.find_spec("research_layer.phase_4_2_41_88e.live_shadow") is None


def test_shadow_uses_manifest_start_cutover_and_minute_aligned_fetch():
    src = archived_source()
    assert "cutover_at=self.start" in src
    assert "one_minute_query_start(floor)" in src
    assert "floor-timedelta(seconds=1)" not in src


def test_version_mismatch_remains_fail_closed():
    candidate = current_candidate()
    history = []
    for i in range(20):
        history.append(
            {
                **{key: candidate[key] for key in COHORT_FIELDS},
                "candidate_identity": f"h{i}",
                "candidate_timestamp": "2026-01-01T00:00:00+00:00",
                "terminal_timestamp": "2026-01-02T00:00:00+00:00",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "direction": "LONG",
                "setup_type": "FAILED_BREAKOUT_LONG",
                "realized_r": "1",
            }
        )
    history[0]["statistics_contract_version"] = "WRONG"
    result = evaluate(candidate, history)
    assert result["compatible_n"] == 19
    assert result["status"] == "INSUFFICIENT_HISTORY"


def test_current_synthetic_parity_schema_replaces_historical_result_claims():
    data = fixture()
    contract = data["current_risk_contract"]
    assert contract["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert contract["risk_semantic_model"] == RISK_SEMANTIC_MODEL
    assert contract["runner_policy"] == RUNNER_POLICY
    assert contract["statistics_contract_version"] == STAT
    assert data["current_plan_parity"]["historical_counts_are_provenance_only"] is True


def test_current_plan_parity_cardinality_and_all_pass():
    parity = fixture()["current_plan_parity"]
    expected = {"exact14": 14, "holdout67": 67, "bootstrap86": 86}
    for name, count in expected.items():
        assert parity["groups"][name] == {"expected_rows": count, "passed_rows": count}
    rows = parity["detailed_synthetic_checks"]
    assert rows
    assert all(row["pass"] for row in rows)
    assert all(all(row["checks"].values()) for row in rows)


def test_original_88e_source_is_inert_and_matches_provenance():
    data = fixture()["archive_provenance"]["phase88e"]
    assert data["role"] == "HISTORICAL_REFERENCE_ONLY"
    assert data["original_source_sha256"] in archived_source()
    assert not (ROOT / "research_layer/phase_4_2_41_88e/live_shadow.py").exists()


def test_operational_interruption_remains_historical_provenance_only():
    data = fixture()["archive_provenance"]["phase88e"]
    assert data["experiment_status"] == "OPERATIONALLY_INTERRUPTED_NOT_ECONOMICALLY_USABLE"
    assert data["economic_analysis_performed"] is False
    assert data["replacement_initialization_eligible"] is False
