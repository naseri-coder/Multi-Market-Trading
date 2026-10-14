"""CERT-A1 offline evidence gate: fail-closed certification WITHOUT runtime."""
from __future__ import annotations

import hashlib
import shutil
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from naseri_markets.cert_a1_offline_candidate_review import (
    CertA1Refused,
    review_candidate,
)
from naseri_markets.core_certification_v1 import CertificationReport
from naseri_markets.data_a1_file_intake import HistoricalIntakeReport
from naseri_markets.data_runtime_paper_wire_a1 import PaperWireReview
from naseri_markets.mt_a1_offline_artifact_preflight import MetaTraderArtifactReview
from naseri_markets.pine_a1_sma_cross_parity import PineTraceReview
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)

ROOT = Path(__file__).resolve().parents[2]
PINE = (
    b"//@version=5\n"
    b'indicator("Cert SMA", overlay=true)\n'
    b"fast = ta.sma(close, 2)\n"
    b"slow = ta.sma(close, 3)\n"
    b"longSignal = barstate.isconfirmed and ta.crossover(fast, slow)\n"
    b"shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)\n"
)


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inspect(name: str, data: bytes, evidence=None, **override):
    kw = dict(
        expected_sha256=_sha(data), stage_evidence=evidence,
        operator_ack=True,
    )
    kw.update(override)
    return review_candidate(ROOT, name, data, **kw)


def _pe(suffix=".exe") -> bytes:
    data = bytearray(1024)
    data[:2] = b"MZ"
    data[0x3c:0x40] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\x00\x00"
    data[132:134] = (0x8664).to_bytes(2, "little")
    data[134:136] = (1).to_bytes(2, "little")
    data[148:150] = (240).to_bytes(2, "little")
    data[150:152] = (0x0002 | (0x2000 if suffix == ".dll" else 0)).to_bytes(2, "little")
    optional = 152
    data[optional:optional + 2] = (0x20b).to_bytes(2, "little")
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


def _elf() -> bytes:
    data = bytearray(512)
    data[:7] = b"\x7fELF\x02\x01\x01"
    data[16:18] = (3).to_bytes(2, "little")
    data[18:20] = (62).to_bytes(2, "little")
    data[20:24] = (1).to_bytes(4, "little")
    data[32:40] = (64).to_bytes(8, "little")
    data[52:54] = (64).to_bytes(2, "little")
    data[54:56] = (56).to_bytes(2, "little")
    data[56:58] = (1).to_bytes(2, "little")
    data[64:68] = (1).to_bytes(4, "little")
    data[72:80] = (0x100).to_bytes(8, "little")
    data[96:104] = (0x40).to_bytes(8, "little")
    data[104:112] = (0x40).to_bytes(8, "little")
    data[112:120] = (0x1000).to_bytes(8, "little")
    return bytes(data)


def _assert_never_approved(outcome):
    assert outcome.status == "CERT_A1_OFFLINE_REVIEW_ONLY_EXECUTION_BLOCKED"
    assert not outcome.source_provenance_independently_authenticated
    assert not outcome.review_claim_independently_authenticated
    assert not outcome.hosted_runtime_isolation_certified
    assert not outcome.actual_tradingview_equivalence_proven
    assert not outcome.binary_safe_from_malware
    assert not outcome.native_execution_authorized
    assert not outcome.worker_execution_authorized
    assert not outcome.paper_strategy_executed
    assert not outcome.paper_order_sent
    assert not outcome.broker_authorized
    assert not outcome.telegram_authorized
    assert not outcome.distribution_authorized
    assert not outcome.quarantine_release_authorized
    assert not outcome.production_recovery_authorized
    assert len(outcome.blockers) == 7
    assert "A6_UNCONDITIONAL_WORKER_EXECUTION_DENIAL_REMAINS" in outcome.blockers
    assert outcome.source_contract_files_audited == 11
    assert len(outcome.review_fingerprint_sha256) == 64


@pytest.mark.parametrize(("name", "data"), [
    ("test.exe", _pe()), ("test.dll", _pe(".dll")), ("test.so", _elf()),
])
def test_native_is_independently_reparsed_but_not_sandbox_certified(name, data):
    outcome = _inspect(name, data)
    _assert_never_approved(outcome)
    assert outcome.claim_class == "NATIVE_A1_REPARSED_HEADER_BYTES_ONLY"
    assert outcome.claim_reconciled
    assert outcome.inspection_level == "binary_magic_only"


def test_structurally_plausible_but_invalid_native_is_refused():
    raw = bytearray(_pe())
    raw[134:136] = (0xFFFF).to_bytes(2, "little")
    with pytest.raises(CertA1Refused, match="CERT_A1_NATIVE_STRUCTURE_REFUSED"):
        _inspect("test.exe", bytes(raw))


def test_pine_strict_subset_without_oracle_never_certified():
    r = _inspect("test.pine", PINE)
    assert not r.claim_reconciled
    _assert_never_approved(r)
    assert "STAGE_EVIDENCE_MISSING" in r.blockers
    assert _inspect("test.pine", PINE).review_fingerprint_sha256 == r.review_fingerprint_sha256


def test_generic_pine_script_must_fail_closed():
    raw = b"//@version=5\nstrategy('unreviewed')\n"
    with pytest.raises(CertA1Refused, match="CERT_A1_PINE_STRICT_SUBSET_REQUIRED"):
        _inspect("test.pine", raw)


def test_claimed_pine_oracle_is_not_tradingview_attestation():
    claim = PineTraceReview(
        source_sha256=_sha(PINE), historical_sha256="a" * 64,
        oracle_sha256="b" * 64, symbol="ABCUSDT", timeframe="15m",
        price_basis="trade", bars_compared=24, warmup_bars=3,
        long_signals=2, short_signals=2, mismatch_bars=0,
        first_mismatch_at=None, trace_sha256="f" * 64,
        status="PINE_A1_OFFLINE_TRACE_MATCH_NOT_TV_ATTESTED",
        offline_fixture_trace_matched=True,
    )
    outcome = _inspect("test.pine", PINE, claim)
    assert outcome.claim_reconciled
    assert outcome.claim_class == "PINE_A1_OFFLINE_TRACE_OPERATOR_CLAIM"
    _assert_never_approved(outcome)
    with pytest.raises(CertA1Refused, match="CERT_A1_UNTRUSTED_CLAIM_GRANTS_AUTHORITY"):
        _inspect("test.pine", PINE, replace(claim, true_pine_runtime_equivalence_proven=True))
    with pytest.raises(CertA1Refused, match="CERT_A1_PINE_PARITY_CLAIM_INCONSISTENT"):
        _inspect("test.pine", PINE, replace(claim, mismatch_bars=1))


def test_metatrader_artifact_operator_claim_not_terminal_identity():
    raw = b"void OnTick() { }\n"
    report = MetaTraderArtifactReview(
        sha256=_sha(raw), size_bytes=len(raw), platform="MT5",
        artifact_kind="MQL5_SOURCE", declared_market="forex",
        declared_symbol="EURUSD", declared_timeframe="M15",
        data_a1_timeframe="15m", provider_claim="operator_demo",
        source_lines=1, source_encoding="UTF-8",
    )
    outcome = _inspect("strategy.mq5", raw, report)
    assert outcome.claim_class == "MT_A1_OPERATOR_FILE_REVIEW_UNATTESTED"
    _assert_never_approved(outcome)
    with pytest.raises(CertA1Refused, match="CERT_A1_MT_CLAIM_INCONSISTENT"):
        _inspect("strategy.mq5", raw, replace(report, platform="MT4"))
    with pytest.raises(CertA1Refused, match="CERT_A1_UNTRUSTED_CLAIM_GRANTS_AUTHORITY"):
        _inspect("strategy.mq5", raw, replace(report, real_terminal_connected=True))


def test_data_a1_claim_is_only_local_review_and_must_match_sha():
    raw = b"time,price\n1,100\n"
    now = datetime(2026, 10, 14, tzinfo=UTC)
    report = HistoricalIntakeReport(
        status="DATA_A1_FILE_VALIDATED_OFFLINE_PAPER_INPUT_ONLY",
        format="csv", market="crypto", provider_claim="fixture",
        symbol="ABCUSDT", timezone="UTC", quote_currency="USDT",
        timeframe="15m", price_basis="trade", volume_semantics="traded",
        sha256=_sha(raw), feed_id="fixture", source_ref="claim_fixture",
        rows_validated=1, paper_core_inputs_validated=1,
        first_observed_at=now, last_observed_at=now,
        first_available_at=now, last_available_at=now,
        lowest_observed_price="100", highest_observed_price="100",
        zero_volume_rows=0, widest_bid_ask_spread=None,
    )
    outcome = _inspect("history.csv", raw, report)
    assert outcome.claim_reconciled
    _assert_never_approved(outcome)
    with pytest.raises(CertA1Refused, match="CERT_A1_HISTORICAL_CLAIM_INCONSISTENT"):
        _inspect("history.csv", raw, replace(report, rows_validated=2))
    with pytest.raises(CertA1Refused, match="CERT_A1_UNTRUSTED_CLAIM_GRANTS_AUTHORITY"):
        _inspect("history.csv", raw, replace(report, source_authenticated=True))


def test_javascript_claim_never_grants_worker_execution():
    raw = b"export const evaluate = x => x;\n"
    now = datetime(2026, 10, 14, tzinfo=UTC)
    report = PaperWireReview(
        source_sha256="b" * 64, source_ref="fixture",
        artifact_sha256=_sha(raw), language="javascript",
        symbol="ABCUSDT", timeframe="15m", core_id="demo",
        binding_id="binding", validated_rows=1, warmup_rows=0,
        frames_prepared=1, peak_frame_bytes=120,
        transcript_sha256="a" * 64,
        first_ready_observed_at=now, last_ready_observed_at=now,
    )
    outcome = _inspect("test.js", raw, report)
    assert outcome.claim_reconciled
    _assert_never_approved(outcome)
    with pytest.raises(CertA1Refused, match="CERT_A1_WIRE_EVIDENCE_NOT_CONSISTENT"):
        _inspect("test.js", raw, replace(report, language="python"))
    with pytest.raises(CertA1Refused, match="CERT_A1_UNTRUSTED_CLAIM_GRANTS_AUTHORITY"):
        _inspect("test.js", raw, replace(report, worker_executed=True))


def test_stage14_sdk_claims_alone_cannot_authorize_public_distribution():
    raw = b"PK\x03\x04not a canonical bundle"
    fake = CertificationReport(
        artifact_sha256=_sha(raw), source_sha256="b" * 64,
        core_id="fake", core_version="1", publisher_key_id=None,
        checks=(), blockers=("EXTERNAL",),
    )
    with pytest.raises(CertA1Refused, match="CERT_A1_FORMAT_INTAKE_REFUSED"):
        _inspect("test.zip", raw, fake)


@pytest.mark.parametrize("name", ["test.txt", "../evil.so", "folder/test.js"])
def test_unsupported_or_unsafe_source_names(name):
    with pytest.raises(CertA1Refused, match="CERT_A1_FORMAT_INTAKE_REFUSED"):
        _inspect(name, b"hello")


def test_immutable_sha_exact_bytes_required():
    raw = b'{"version":1}'
    outcome = _inspect("test.json", raw)
    _assert_never_approved(outcome)
    with pytest.raises(CertA1Refused, match="CERT_A1_SOURCE_SHA256_MISMATCH"):
        _inspect("test.json", raw, expected_sha256="f" * 64)
    with pytest.raises(CertA1Refused, match="CERT_A1_EXACT_SOURCE_SHA256_REQUIRED"):
        _inspect("test.json", raw, expected_sha256="A" * 64)


def test_unexpected_or_wrong_stage_claim_refused():
    raw = _pe()
    with pytest.raises(CertA1Refused, match="CERT_A1_NATIVE_EXTERNAL_CLAIM_UNSUPPORTED"):
        _inspect("test.exe", raw, object())
    with pytest.raises(CertA1Refused, match="CERT_A1_UNEXPECTED_STAGE_CLAIM"):
        _inspect("test.json", b'{"x":1}', object())


def test_production_or_missing_ack_refuses_even_structural_report(monkeypatch):
    raw = b'{"a":1}'
    with pytest.raises(CertA1Refused, match="CERT_A1_EXPLICIT_NONPRODUCTION"):
        _inspect("test.json", raw, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CertA1Refused, match="CERT_A1_EXPLICIT_NONPRODUCTION"):
        _inspect("test.json", raw)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(CertA1Refused, match="CERT_A1_EXPLICIT_NONPRODUCTION"):
        _inspect("test.json", raw)


def test_unaudited_root_or_mutated_a6_denial_is_refused(tmp_path):
    with pytest.raises(CertA1Refused, match="CERT_A1_A6_SOURCE_CONTRACT_NOT_VERIFIED"):
        review_candidate(
            tmp_path, "test.json", b'{"x":1}',
            expected_sha256=_sha(b'{"x":1}'), operator_ack=True,
        )
    original = ROOT / "naseri_markets/runtime_a6_dispatch_fence.py"
    target = tmp_path / "audited"
    for rel in (
        *(__import__("naseri_markets.runtime_a13_security_contract_audit",
                     fromlist=["_MODULES"])._MODULES),
        "naseri_markets/multilang_runtime_a1.py",
        "deploy/runtime_a2/Dockerfile",
    ):
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dest)
    fence = target / "naseri_markets/runtime_a6_dispatch_fence.py"
    text = fence.read_text()
    assert "raise RuntimeA6Denied" in text
    fence.write_text(text.replace(
        'raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")',
        "return None", 1,
    ))
    assert original.is_file()
    with pytest.raises(CertA1Refused, match="CERT_A1_A6_SOURCE_CONTRACT_NOT_VERIFIED"):
        review_candidate(
            target, "test.json", b'{"x":1}',
            expected_sha256=_sha(b'{"x":1}'), operator_ack=True,
        )


def test_no_network_or_process_and_runtime_a6_always_refuses(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("CERT_A1_MUST_NOT_RUN_USER_CODE_OR_OPEN_NETWORK")
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(socket, "socket", denied)
    report = _inspect("test.json", b'{"x":1}')
    assert not report.worker_execution_authorized
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
