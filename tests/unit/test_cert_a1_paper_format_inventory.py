"""CERT-A1 cross-format PAPER coverage: no real trading or Worker activity."""
from __future__ import annotations

import hashlib
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from naseri_markets.cert_a1_paper_format_inventory import (
    CandidateSubmission,
    CertA1InventoryRefused,
    review_paper_format_inventory,
)
from naseri_markets.data_runtime_paper_wire_a1 import PaperWireReview
from naseri_markets.pine_a1_sma_cross_parity import PineTraceReview
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)
from naseri_markets.universal_artifact_intake_v1 import supported_extensions

ROOT = Path(__file__).resolve().parents[2]
PINE = (
    b"//@version=5\n"
    b'indicator("Cert SMA", overlay=true)\n'
    b"fast = ta.sma(close, 2)\n"
    b"slow = ta.sma(close, 3)\n"
    b"longSignal = barstate.isconfirmed and ta.crossover(fast, slow)\n"
    b"shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)\n"
)
NOW = datetime(2026, 10, 14, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _item(name: str, data: bytes, evidence=None):
    return CandidateSubmission(name, data, _sha(data), evidence)


def _pe() -> bytes:
    # A minimal structural PE image. This is NOT an executable test payload.
    data = bytearray(1024)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\x00\x00"
    data[132:134] = (0x8664).to_bytes(2, "little")
    data[134:136] = (1).to_bytes(2, "little")
    data[148:150] = (240).to_bytes(2, "little")
    data[150:152] = (0x0002).to_bytes(2, "little")
    optional = 152
    data[optional:optional + 2] = (0x20B).to_bytes(2, "little")
    data[optional + 32:optional + 36] = (0x1000).to_bytes(4, "little")
    data[optional + 36:optional + 40] = (0x200).to_bytes(4, "little")
    data[optional + 56:optional + 60] = (0x2000).to_bytes(4, "little")
    data[optional + 60:optional + 64] = (0x200).to_bytes(4, "little")
    section = optional + 240
    data[section:section + 5] = b".text"
    data[section + 8:section + 12] = (0x100).to_bytes(4, "little")
    data[section + 12:section + 16] = (0x1000).to_bytes(4, "little")
    data[section + 16:section + 20] = (0x200).to_bytes(4, "little")
    data[section + 20:section + 24] = (0x200).to_bytes(4, "little")
    return bytes(data)


def _claim_js(raw: bytes) -> PaperWireReview:
    return PaperWireReview(
        source_sha256="b" * 64, source_ref="fixture_only",
        artifact_sha256=_sha(raw), language="javascript",
        symbol="ABCUSDT", timeframe="15m", core_id="demo",
        binding_id="binding", validated_rows=4, warmup_rows=2,
        frames_prepared=2, peak_frame_bytes=120,
        transcript_sha256="a" * 64,
        first_ready_observed_at=NOW, last_ready_observed_at=NOW,
    )


def _claim_pine() -> PineTraceReview:
    return PineTraceReview(
        source_sha256=_sha(PINE), historical_sha256="a" * 64,
        oracle_sha256="b" * 64, symbol="ABCUSDT", timeframe="15m",
        price_basis="trade", bars_compared=24, warmup_bars=3,
        long_signals=2, short_signals=2, mismatch_bars=0,
        first_mismatch_at=None, trace_sha256="c" * 64,
        status="PINE_A1_OFFLINE_TRACE_MATCH_NOT_TV_ATTESTED",
        offline_fixture_trace_matched=True,
    )


def _collection():
    javascript = b"export const evaluate = x => x;\n"
    return (
        _item("layout.json", b'{"schema":1}'),
        _item("rule.pine", PINE, _claim_pine()),
        _item("worker.js", javascript, _claim_js(javascript)),
        _item("sample.exe", _pe()),
    )


def _review(items=None, **changes):
    return review_paper_format_inventory(
        ROOT, _collection() if items is None else items,
        operator_ack=True, **changes,
    )


def test_registry_declares_all_current_formats_and_all_are_nonexecuting():
    expected = frozenset({
        ".py", ".js", ".ts", ".wasm", ".csv", ".parquet",
        ".mq4", ".mq5", ".ex5", ".pine", ".dll", ".exe", ".so",
        ".zip", ".json",
    })
    assert frozenset(supported_extensions()) == expected
    report = _review()
    assert report.expected_format_count == len(expected) == 15
    assert report.submitted_format_count == 4
    assert set(report.missing_extensions) == expected - {
        ".json", ".pine", ".js", ".exe",
    }
    assert report.matching_unattested_stage_claims == 2
    assert report.missing_stage_claims == 2
    assert len(report.fingerprint_sha256) == 64
    assert report.status == "CERT_A1_PAPER_COVERAGE_INVENTORY_ONLY_ALL_EXECUTION_DENIED"
    assert not report.independent_market_history_authenticated
    assert not report.independent_runtime_host_attested
    assert not report.independent_stage_receipts_authenticated
    assert not report.all_formats_paper_executable
    assert not report.paper_strategy_executed
    assert not report.paper_order_sent
    assert not report.native_execution_authorized
    assert not report.worker_execution_authorized
    assert not report.broker_authorized
    assert not report.telegram_authorized
    assert not report.quarantine_release_authorized
    assert not report.production_release_authorized
    for entry in report.present:
        assert not entry.stage_claim_authenticated
        assert not entry.market_provenance_authenticated
        assert not entry.paper_strategy_executed
        assert not entry.native_or_worker_executed
        assert not entry.broker_order_sent
        assert not entry.telegram_sent
        assert not entry.quarantine_release_authorized
    by_ext = {r.extension: r for r in report.present}
    assert by_ext[".js"].paper_capability == "PAPER_WIRE_FRAMES_CLAIM_ONLY"
    assert by_ext[".js"].stage_claim_reconciled
    assert by_ext[".pine"].paper_capability == "STATIC_RULE_AND_ORACLE_CLAIM_ONLY"
    assert by_ext[".exe"].paper_capability == "NATIVE_HEADER_REPARSED_NO_NATIVE_LOAD"
    assert not by_ext[".exe"].stage_claim_present
    assert by_ext[".json"].paper_capability == "DECLARATION_STRUCTURE_ONLY"


def test_inventory_order_is_canonical_and_keeps_same_fingerprint():
    a = _collection()
    r1 = _review(a)
    r2 = _review(tuple(reversed(a)))
    assert r1 == r2
    assert tuple(x.extension for x in r1.present) == tuple(
        sorted(x.extension for x in r1.present)
    )


def test_complete_inventory_cannot_be_falsely_claimed_from_subset():
    with pytest.raises(CertA1InventoryRefused, match="FULL_FORMAT_INVENTORY_INCOMPLETE"):
        _review(require_all_formats=True)


def test_no_report_on_empty_or_unbounded_submissions():
    with pytest.raises(CertA1InventoryRefused, match="BOUNDED_CANDIDATE"):
        _review(())
    with pytest.raises(CertA1InventoryRefused, match="BOUNDED_CANDIDATE"):
        _review(_collection() * 5)


@pytest.mark.parametrize("candidates", [
    (_item("x.json", b'{"x":1}'), _item("Y.JSON", b'{"x":2}')),
    (_item("x.json", b'{"x":1}'), _item("y.json", b'{"x":2}')),
    (_item("x.json", b'{"x":1}'), _item("y.js", b'{"x":1}')),
])
def test_duplicate_suffix_casefold_filename_or_digest_refused(candidates):
    with pytest.raises(CertA1InventoryRefused, match="AMBIGUOUS_OR_DUPLICATE"):
        _review(candidates)


@pytest.mark.parametrize("filename", ["../unsafe.json", "z.exe/evil", "unknown.txt"])
def test_unsafe_or_unsupported_source_refused(filename):
    with pytest.raises(CertA1InventoryRefused):
        _review((_item(filename, b'{"value":1}'),))


def test_unmodified_valid_bytes_required_no_evidence_forgery():
    item = _item("schema.json", b'{"value":1}')
    bad = replace(item, sha256="f" * 64)
    with pytest.raises(CertA1InventoryRefused, match="CANDIDATE_REVIEW_REFUSED"):
        _review((bad,))


def test_claimed_frames_not_execution_even_when_sha_matches():
    source = b"export const evaluate = x => x;\n"
    input_candidate = _item("worker.js", source, _claim_js(source))
    ok = _review((input_candidate,))
    assert ok.matching_unattested_stage_claims == 1
    assert not ok.paper_strategy_executed
    assert not ok.present[0].stage_claim_authenticated
    with pytest.raises(CertA1InventoryRefused, match="CANDIDATE_REVIEW_REFUSED"):
        _review((replace(input_candidate, stage_evidence=replace(
            input_candidate.stage_evidence, worker_executed=True,
        )),))


def test_forged_pine_parity_and_unapproved_strategies_fail():
    artifact = _item("rule.pine", PINE, _claim_pine())
    with pytest.raises(CertA1InventoryRefused, match="CANDIDATE_REVIEW_REFUSED"):
        _review((replace(artifact, stage_evidence=replace(
            artifact.stage_evidence, actual_tradingview_trace_authenticated=True,
        )),))
    with pytest.raises(CertA1InventoryRefused, match="CANDIDATE_REVIEW_REFUSED"):
        _review((_item("other.pine", b"//@version=5\nstrategy('orders')"),))


def test_invalid_native_binary_not_promoted_by_claimed_filename():
    with pytest.raises(CertA1InventoryRefused, match="CANDIDATE_REVIEW_REFUSED"):
        _review((_item("payload.exe", b"MZ"),))


def test_production_missing_ack_and_unsafe_candidate_type_rejected(monkeypatch):
    with pytest.raises(CertA1InventoryRefused, match="NONPRODUCTION_ACK_REQUIRED"):
        review_paper_format_inventory(ROOT, _collection())
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CertA1InventoryRefused, match="NONPRODUCTION_ACK_REQUIRED"):
        _review()
    monkeypatch.delenv("MMT_PRODUCTION")
    with pytest.raises(CertA1InventoryRefused, match="EXACT_CANDIDATE_REQUIRED"):
        _review((object(),))


def test_no_network_or_native_launch_and_a6_always_denies(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("CERT_A1_MUST_NOT_EXECUTE_EXTERNAL_PROCESS")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    report = _review()
    assert not report.worker_execution_authorized
    assert not report.paper_order_sent
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
