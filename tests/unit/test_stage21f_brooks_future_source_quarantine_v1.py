"""Stage21F synthetic future-price admission, with a MOCKED signed-token verifier.

The independent RFC3161 cryptographic verification itself is exhaustively
tested with genuine OpenSSL signatures in Stage21D; these tests do NOT prove
a real future Binance provider feed was captured.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import brooks_future_kline_admission_stage21f_v1 as gate

START = datetime(2026, 10, 20, tzinfo=UTC)
END = datetime(2026, 11, 3, tzinfo=UTC)
STEP = timedelta(minutes=15)
_PLAN = (Path(gate.__file__).resolve().parents[1] /
         "docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json")
_TSR = b"demonstration-token"  # Never substitutes for genuine SHA-pinned bytes


@pytest.fixture(autouse=True)
def research(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(
        gate, "verify_brooks_rfc3161_precommitment",
        lambda **_kw: {
            "cryptographic_tsa_signature_and_imprint_valid": True,
            "independent_tsa_provider_assessed": False,
            "paper_mode_authorized": False,
            "signed_timestamp_utc": "2026-10-16T01:36:00+00:00",
        },
    )


def bars(index=0, count=2):
    out = []
    for n in range(index, index+count):
        open_ms = int((START+STEP*n).timestamp()*1000)
        out.append([
            open_ms, "100", "102", "98", "101", "10",
            open_ms+899999, "1000", 5, "4", "400", "0",
        ])
    return out


def kwargs(index=0, count=2, received=None, previous=None):
    started = START+STEP*index
    uri=(f"https://fapi.binance.com/fapi/v1/klines?interval=15m&limit={count}"
         f"&startTime={int(started.timestamp()*1000)}&symbol=BTCUSDT")
    return dict(
        exact_frozen_plan=_PLAN.read_bytes(),
        original_tsr_der=_TSR,
        original_ca_pem=b"test-ca",
        original_tsa_signer_pem=b"test-signer",
        original_provider_body_bytes=json.dumps(bars(index,count),
                                                separators=(",",":")).encode(),
        declared_request_url=uri, declared_http_status=200,
        declared_tls_verified=True,
        operator_received_at_utc=received or (started+STEP*count+timedelta(seconds=10)),
        previous_stage21c_receipt_bytes=previous,
        operator_ack=True,
    )


@pytest.fixture
def pinned(monkeypatch):
    # Only transport-byte identity checks mocked. No independent provenance
    # or trust is ever asserted. Stage21D tests exercise the real token.
    kw=kwargs()
    monkeypatch.setattr(gate,"_CANONICAL_TOKEN_SHA",
                        hashlib.sha256(kw["original_tsr_der"]).hexdigest())
    monkeypatch.setattr(gate,"_CANONICAL_CA_SHA",
                        hashlib.sha256(kw["original_ca_pem"]).hexdigest())
    monkeypatch.setattr(gate,"_CANONICAL_SIGNER_SHA",
                        hashlib.sha256(kw["original_tsa_signer_pem"]).hexdigest())
    return kw


def test_exact_canonical_stage21e_plan_is_pinned_and_unmodified():
    assert hashlib.sha256(_PLAN.read_bytes()).hexdigest() == (
        "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
    )
    plan=json.loads(_PLAN.read_bytes())
    assert plan["study_start_utc"]=="2026-10-20T00:00:00Z"
    assert plan["study_end_utc"]=="2026-11-03T00:00:00Z"
    assert plan["paper_market_access"] is False


def test_first_and_second_quarantined_receipts_are_sequential(pinned):
    first, norm=gate.stage21f_admit_future_kline_batch_to_quarantine(**pinned)
    assert first["candle_count"]==2
    assert norm.splitlines()[0]==b"open_at,close_at,open,high,low,close,volume"
    assert first["verdict"]=="LOCAL_QUARANTINE_ONLY_UNATTESTED_FUTURE_SOURCE"
    assert first["source_origin_independently_attested"] is False
    assert first["tsa_independence_policy_approved"] is False
    assert first["capture_time_independently_attested"] is False
    assert first["actual_trades_filled"] is False
    assert first["oos_performance_verified"] is False
    assert first["connected_paper_enabled"] is False
    assert first["live_trading_authorized"] is False
    assert first["production_modified"] is False
    prev=gate._canon(first["stage21c_receipt"])
    kw=kwargs(index=2,count=2,previous=prev)
    second,_=gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    assert second["stage21c_receipt"]["sequence"]==2
    assert second["stage21c_receipt"]["previous_receipt_sha256"]==(
        first["stage21c_receipt_sha256"]
    )
    assert second["original_provider_response_bytes_sha256"]!=(
        first["original_provider_response_bytes_sha256"]
    )


def test_missing_second_bar_and_duplicates_refused(pinned):
    kw=dict(pinned)
    original=json.loads(kw["original_provider_body_bytes"])
    original[1][0]+=900000
    kw["original_provider_body_bytes"]=json.dumps(original).encode()
    with pytest.raises(gate.Stage21AdmissionRefused,match="GRID"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    original=json.loads(pinned["original_provider_body_bytes"])
    original[1]=original[0]
    kw["original_provider_body_bytes"]=json.dumps(original).encode()
    with pytest.raises(gate.Stage21AdmissionRefused,match="GRID"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_unclosed_and_too_early_future_data_blocked(pinned):
    kw=dict(pinned)
    kw["operator_received_at_utc"]=START+timedelta(minutes=29)
    with pytest.raises(gate.Stage21AdmissionRefused,match="CUSTODY"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw["operator_received_at_utc"]=START-timedelta(days=1)
    with pytest.raises(gate.Stage21AdmissionRefused,match="CAPTURE_OUTSIDE"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_operator_authenticity_claim_cannot_become_true_proof(pinned):
    kw=dict(pinned)
    kw["declared_tls_verified"]=False
    with pytest.raises(gate.Stage21AdmissionRefused,match="HTTPS"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw=dict(pinned)
    kw["declared_request_url"]=kw["declared_request_url"].replace(
        "fapi.binance.com","forged.invalid",
    )
    with pytest.raises(gate.Stage21AdmissionRefused,match="HTTPS"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw=dict(pinned)
    kw["declared_request_url"]=kw["declared_request_url"]+"&time=latest"
    with pytest.raises(gate.Stage21AdmissionRefused,match="QUERY_DRIFT"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_wrong_tsa_or_plan_pin_fail_before_crypto_or_data(pinned):
    kw=dict(pinned)
    kw["original_tsr_der"]=b"forged"
    with pytest.raises(gate.Stage21AdmissionRefused,match="WITNESS"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw=dict(pinned)
    kw["exact_frozen_plan"]=kw["exact_frozen_plan"]+b" "
    with pytest.raises(gate.Stage21AdmissionRefused,match="ORIGINAL_SIGNED_PLAN"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_forged_prior_receipt_and_wrong_count_blocked(pinned):
    first,_=gate.stage21f_admit_future_kline_batch_to_quarantine(**pinned)
    prior=dict(first["stage21c_receipt"])
    prior["last_close_utc"]="2026-10-23T00:00:00Z"
    kw=kwargs(index=2,previous=gate._canon(prior))
    with pytest.raises(gate.Stage21AdmissionRefused,match="CUSTODY"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw=dict(pinned)
    kw["original_provider_body_bytes"]=b"[]"
    with pytest.raises(gate.Stage21AdmissionRefused,match="96"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_bad_price_unexpected_shape_and_quote_length_refused(pinned):
    for value in ("0", "-1", "nan"):
        kw=dict(pinned)
        data=json.loads(kw["original_provider_body_bytes"])
        data[0][1]=value
        kw["original_provider_body_bytes"]=json.dumps(data).encode()
        with pytest.raises(gate.Stage21AdmissionRefused,match="CUSTODY"):
            gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw=dict(pinned)
    data=json.loads(kw["original_provider_body_bytes"])
    data[1].pop()
    kw["original_provider_body_bytes"]=json.dumps(data).encode()
    with pytest.raises(gate.Stage21AdmissionRefused,match="SHAPE"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_absence_operator_permission_and_production_never_touch_worker(pinned,monkeypatch):
    kw=dict(pinned)
    kw["operator_ack"]=False
    with pytest.raises(ValueError,match="NONPRODUCTION"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)
    kw["operator_ack"]=True
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(ValueError,match="NONPRODUCTION"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_real_future_window_end_is_enforced(pinned):
    kw=kwargs(index=int((END-START)/STEP)-1,count=2)
    with pytest.raises(gate.Stage21AdmissionRefused,match="CUSTODY"):
        gate.stage21f_admit_future_kline_batch_to_quarantine(**kw)


def test_capture_cannot_claim_a_forward_trade(pinned):
    report,_=gate.stage21f_admit_future_kline_batch_to_quarantine(**pinned)
    assert report["actual_trades_filled"] is False
    assert report["connected_paper_enabled"] is False
    assert "net_profit" not in report
