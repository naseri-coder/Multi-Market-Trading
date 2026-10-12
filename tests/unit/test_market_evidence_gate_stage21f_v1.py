"""Stage21F: provenance, completeness blockers and second-observation fail closed."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from naseri_markets.market_evidence_gate_stage21f_v1 import (
    EvidenceGateRefused, evaluate_market_evidence_gate,
    recapture_funding_for_comparison,
)
from naseri_markets.market_evidence_gate_cli_stage21f_v1 import main
from naseri_markets.public_funding_mark_stage21e_v1 import (
    FUNDING_ENDPOINT, capture_public_funding_and_mark,
)
from naseri_markets.public_forward_capture_stage21c_v1 import replay_sealed_bundle
from test_public_funding_mark_stage21e_v1 import (
    T0, _futures_fixture, _public_mark_and_funding,
)


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _ready(tmp_path):
    folder = _futures_fixture(tmp_path)
    capture_public_funding_and_mark(
        folder, operator_ack=True, transport=_public_mark_and_funding,
        clock=lambda: T0 + timedelta(hours=2))
    return folder


def _again(folder, transport=_public_mark_and_funding):
    return recapture_funding_for_comparison(
        folder, operator_ack=True, transport=transport,
        clock=lambda: T0 + timedelta(hours=2, minutes=1))


def test_two_explicit_same_provider_gets_then_readonly_gate_paper(tmp_path):
    folder = _ready(tmp_path)
    paper_path = tmp_path / "paper" / "paper.sqlite"
    paper_report = replay_sealed_bundle(
        folder, paper_path.parent, operator_ack=True)
    assert paper_report["economic_audited_orders"] == 2
    with pytest.raises(EvidenceGateRefused, match="EXPLICIT_FUNDING_RECHECK_REQUIRED"):
        evaluate_market_evidence_gate(folder, operator_ack=True)
    first = evaluate_market_evidence_gate(
        folder, operator_ack=True, require_recheck=False)
    assert first["funding_repeatability"] == "NOT_TESTED"
    assert first["strategy_profitability_verified"] is False
    calls = []
    def compare(url):
        calls.append(url)
        return _public_mark_and_funding(url)
    response = _again(folder, transport=compare)
    assert len(calls) == 2
    assert all(u.startswith(FUNDING_ENDPOINT) for u in calls)
    assert response["state"] == "SAME_PROVIDER_RECAPTURE_MATCHED_NOT_INDEPENDENT_SOURCE"
    outcome = evaluate_market_evidence_gate(
        folder, operator_ack=True, paper_path=paper_path)
    assert outcome["local_hash_and_schema_consistency"] == "PASS_LOCAL_ONLY"
    assert outcome["funding_repeatability"] == (
        "MATCHED_SAME_PROVIDER_NOT_SOURCE_INDEPENDENT")
    assert outcome["paper_journal_checked"] is True
    assert outcome["paper_journal_local_integrity"] == (
        "LOCAL_PER_CONTRACT_ECONOMICS_COHERENT_UNATTESTED")
    assert outcome["closed_order_scenarios"] == 2
    assert outcome["performance_evidence_gate"] == (
        "BLOCKED_MISSING_MARK_FUNDING_EXECUTION_PROOF")
    assert outcome["independent_feed_verification"] == "ABSENT"
    assert outcome["historical_mark_coverage"] == "ABSENT_CURRENT_MARK_ONLY"
    assert outcome["funding_completeness"] == (
        "UNVERIFIABLE_FROM_PUBLIC_RESPONSE_ALONE")
    assert outcome["publication_authorized"] is False
    assert outcome["live_trading_authorized"] is False
    assert outcome["strategy_profitability_verified"] is False
    assert all(row["funding_event_completeness"] == "UNKNOWN_NOT_ZERO"
               and row["historical_mark_samples_inside_window"] == 0
               and row["funding_events_reproducible_same_source"] is True
               for row in outcome["symbols"])
    assert outcome["broker_order_sent"] is False
    assert outcome["telegram_sent"] is False
    with pytest.raises(EvidenceGateRefused, match="RECHECK_EXISTS_OR_PARTIAL"):
        _again(folder)
    assert len(calls) == 2


def test_first_empty_funding_repeatable_still_unknown_not_zero(tmp_path):
    folder = _ready(tmp_path)
    # Can't replace original Stage21E file: hash-bound annex is immutable.
    # Explicit same-provider repeat with both fixtures unchanged is allowed;
    # empty history itself can never prove that funding did not occur.
    result = _again(folder)
    assert all(count == 1 for count in result["events"])
    outcome = evaluate_market_evidence_gate(folder, operator_ack=True)
    assert all(row["funding_interval_schedule_verified"] is False
               for row in outcome["symbols"])
    assert outcome["historical_liquidation_risk_verified"] is False


def test_disagreeing_second_response_refused_without_writes(tmp_path):
    folder = _ready(tmp_path)
    def disagree(url):
        original = _public_mark_and_funding(url)
        obj = json.loads(original)
        obj["data"][0]["fundingRate"] = "0.0011"
        return json.dumps(obj).encode()
    with pytest.raises(EvidenceGateRefused, match="RECHECK_FUNDING_CONTENT_CONFLICT"):
        _again(folder, transport=disagree)
    assert not (folder / "stage21f_recheck.json").exists()
    assert not (folder / "stage21f_funding_0.json").exists()
    assert not (folder / "stage21f_funding_1.json").exists()


def test_manual_mutation_of_recheck_response_blocks_gate(tmp_path):
    folder = _ready(tmp_path)
    _again(folder)
    changed = folder / "stage21f_funding_1.json"
    changed.write_bytes(changed.read_bytes() + b" ")
    with pytest.raises(EvidenceGateRefused, match="FUNDING_RECHECK_SOURCE_OR_DIGEST_DRIFT"):
        evaluate_market_evidence_gate(folder, operator_ack=True)


def test_no_network_when_not_authorized_or_production(tmp_path, monkeypatch):
    folder = _ready(tmp_path)
    def forbidden(_url):
        raise AssertionError("unexpected network access")
    with pytest.raises(ValueError, match="EXPLICIT_NONPRODUCTION"):
        recapture_funding_for_comparison(folder, transport=forbidden)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="EXPLICIT_NONPRODUCTION"):
        recapture_funding_for_comparison(
            folder, operator_ack=True, transport=forbidden)
    with pytest.raises(ValueError, match="EXPLICIT_NONPRODUCTION"):
        evaluate_market_evidence_gate(folder, operator_ack=True)
    assert main(["audit", "--bundle-dir", str(folder)]) == 2
    assert not (folder / "stage21f_recheck.json").exists()


def test_cli_no_capture_without_explicit_ack(tmp_path, capsys):
    folder = _ready(tmp_path)
    assert main(["corroborate", "--bundle-dir", str(folder)]) == 2
    assert "STAGE21F_RESEARCH_EVIDENCE_REFUSED" in capsys.readouterr().err
    assert not (folder / "stage21f_funding_0.json").exists()
