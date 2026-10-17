"""Synthetic Stage21F future stream. NO real future market feed is contacted."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest

from naseri_markets import brooks_forward_http_intake_stage21f_v1 as intake

BASE = datetime(2026, 10, 20, tzinfo=UTC)
MS = int(BASE.timestamp() * 1000)
STEP = 900000
ROOT = Path(__file__).resolve().parents[2]
SIGNED_PLAN = (
    ROOT / "docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json"
).read_bytes()


@pytest.fixture(autouse=True)
def research(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def bars(start=0, count=2):
    rows = []
    for i in range(start, start + count):
        t = MS + i * STEP
        rows.append([
            t, "100", "104", "99", "102", "5", t + STEP - 1,
            "500", 12, "2", "200", "0",
        ])
    return json.dumps(rows, separators=(",", ":")).encode("ascii")


def kw(start=0, count=2, *, at=None, body=None):
    src = bars(start, count) if body is None else body
    first = MS + start * STEP
    observed = at or BASE + timedelta(minutes=15 * (start + count), seconds=5)
    url = (
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT"
        f"&interval=15m&startTime={first}&limit={count}"
    )
    return {
        "plan_bytes": SIGNED_PLAN,
        "plan_sha256": intake._PLAN_SHA,
        "timestamp_response_der": b"synthetic-tsr-not-an-external-witness",
        "timestamp_response_sha256": intake._STAMP_SHA,
        "trusted_ca_pem": b"synthetic-ca-not-a-trust-anchor",
        "trusted_ca_sha256": intake._CA_SHA,
        "tsa_signer_certificate_pem": b"synthetic-signer-not-real",
        "tsa_signer_certificate_sha256": intake._SIGNER_SHA,
        "original_http_response_body": src,
        "original_http_response_sha256": hashlib.sha256(src).hexdigest(),
        "request_url": url,
        "http_response_status": 200,
        "http_content_type": "application/json",
        "untrusted_http_date": format_datetime(observed, usegmt=True),
        "operator_observed_at_utc": observed,
        "operator_ack": True,
        "capture_claim": "SYNTHETIC_OFFLINE_TEST_ONLY",
    }


def admit(monkeypatch, **params):
    def pretend_signature(**kwargs):
        assert kwargs["plan_bytes"] == SIGNED_PLAN
        assert kwargs["timestamp_response_sha256"] == intake._STAMP_SHA
        return {
            "cryptographic_tsa_signature_and_imprint_valid": True,
            "plan_sha256": intake._PLAN_SHA,
            "signed_timestamp_utc": "2026-10-16T01:36:00+00:00",
        }
    monkeypatch.setattr(intake, "_verified_external_plan", pretend_signature)
    return intake.stage21f_admit_offline_binance_response(**params)


def test_exact_original_plan_from_repository_is_notarized_digest():
    assert hashlib.sha256(SIGNED_PLAN).hexdigest() == intake._PLAN_SHA
    assert json.loads(SIGNED_PLAN)["study_start_utc"] == "2026-10-20T00:00:00Z"


def test_two_synthetic_batches_convert_and_chain_without_oos_claim(monkeypatch):
    report, csv, receipt = admit(monkeypatch, **kw())
    assert csv.splitlines() == [
        b"open_at,close_at,open,high,low,close,volume",
        b"2026-10-20T00:00:00Z,2026-10-20T00:15:00Z,100,104,99,102,5",
        b"2026-10-20T00:15:00Z,2026-10-20T00:30:00Z,100,104,99,102,5",
    ]
    assert report["number_of_closed_bars"] == 2
    assert report["stage21c_sequence"] == 1
    assert report["canonical_15m_csv_sha256"] == hashlib.sha256(csv).hexdigest()
    chain = json.loads(receipt)
    assert chain["receipt_sha256"] == report["stage21c_receipt_sha256"]
    assert report["stage21c_receipt_sha256"] == hashlib.sha256(
        json.dumps(
            {key: value for key, value in chain.items() if key != "receipt_sha256"},
            sort_keys=True, separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    assert report["actual_issuer_signed_price_message_verified"] is False
    assert report["independent_capture_clock_verified"] is False
    assert report["future_market_data_prospectively_verified"] is False
    assert report["verified_out_of_sample_profitability"] is False
    assert report["connected_paper_authorized"] is False
    next_report, _, next_receipt = admit(
        monkeypatch, **{**kw(2, 2), "previous_stage21c_receipt_bytes": receipt},
    )
    assert next_report["stage21c_sequence"] == 2
    assert next_report["previous_stage21c_receipt_sha256"] == report[
        "stage21c_receipt_sha256"
    ]
    assert next_receipt != receipt


@pytest.mark.parametrize("mutation,identifier", [
    ({"request_url": "https://evil.invalid/api"}, "READONLY_REQUEST_URL"),
    ({"http_response_status": 403}, "UNVERIFIED_PUBLIC_JSON"),
    ({"http_content_type": "text/html"}, "UNVERIFIED_PUBLIC_JSON"),
    ({"original_http_response_sha256": "0"*64}, "DIGEST_MISMATCH"),
    ({"capture_claim": "EXCHANGE_AUTHENTICATED_SIGNED"}, "UNVERIFIED_PUBLIC_JSON"),
])
def test_source_claim_url_or_response_pin_refused(monkeypatch, mutation, identifier):
    with pytest.raises(intake.Stage21IntakeRefused, match=identifier):
        admit(monkeypatch, **{**kw(), **mutation})


def test_future_unclosed_and_stale_observation_refused(monkeypatch):
    too_early = BASE + timedelta(minutes=30, seconds=4)
    with pytest.raises(intake.Stage21IntakeRefused, match="FRESH_CLOSED"):
        admit(monkeypatch, **kw(at=too_early))
    too_late = BASE + timedelta(minutes=41)
    with pytest.raises(intake.Stage21IntakeRefused, match="FRESH_CLOSED"):
        admit(monkeypatch, **kw(at=too_late))


def test_retrospective_2024_bars_are_not_accepted_into_2026_future_plan(monkeypatch):
    raw = json.loads(bars(0, 2))
    historical_start = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    delta = MS - historical_start
    for row in raw:
        row[0] -= delta
        row[6] -= delta
    params = kw(at=BASE + timedelta(minutes=31), body=json.dumps(raw).encode())
    params["request_url"] = (
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT"
        f"&interval=15m&startTime={historical_start}&limit=2"
    )
    with pytest.raises(intake.Stage21IntakeRefused, match="FRESH_CLOSED"):
        admit(monkeypatch, **params)


def test_gap_duplicate_or_unsorted_kline_refused(monkeypatch):
    for entries in (
        [json.loads(bars(0, 1))[0], json.loads(bars(0, 1))[0]],
        [json.loads(bars(0, 1))[0], json.loads(bars(2, 1))[0]],
        [json.loads(bars(1, 1))[0], json.loads(bars(0, 1))[0]],
    ):
        data = json.dumps(entries).encode("ascii")
        with pytest.raises(intake.Stage21IntakeRefused, match="GRID_GAP"):
            admit(monkeypatch, **kw(body=data))


def test_bad_kline_data_rejected_before_stage21c(monkeypatch):
    source = json.loads(bars())
    for index, bad in ((1, "-1"), (3, "105"), (5, "NaN"),
                       (8, "noninteger"), (11, "reserved")):
        candidate = json.loads(bars())
        candidate[0][index] = bad
        data = json.dumps(candidate).encode("ascii")
        with pytest.raises(intake.Stage21IntakeRefused):
            admit(monkeypatch, **kw(body=data))


def test_operator_http_date_is_rejected_on_five_minute_drift(monkeypatch):
    params = kw()
    params["untrusted_http_date"] = format_datetime(
        BASE + timedelta(minutes=20), usegmt=True,
    )
    with pytest.raises(intake.Stage21IntakeRefused, match="HTTP_DATE"):
        admit(monkeypatch, **params)


def test_first_batch_must_begin_at_frozen_study_start(monkeypatch):
    with pytest.raises(intake.Stage21IntakeRefused, match="STAGE21C_CHAIN"):
        admit(monkeypatch, **kw(1, 2))


def test_second_batch_cannot_skip_missing_candles(monkeypatch):
    _, _, receipt = admit(monkeypatch, **kw())
    with pytest.raises(intake.Stage21IntakeRefused, match="STAGE21C_CHAIN"):
        admit(monkeypatch, **{**kw(3, 1),
                              "previous_stage21c_receipt_bytes": receipt})


def test_tampering_signed_plan_and_fake_timestamp_refused_before_untrusted_input():
    params = kw()
    params["plan_bytes"] = SIGNED_PLAN + b" "
    with pytest.raises(intake.Stage21IntakeRefused, match="ORIGINAL_FROZEN_PLAN"):
        intake.stage21f_admit_offline_binance_response(**params)
    params = kw()
    params["timestamp_response_sha256"] = "0" * 64
    with pytest.raises(intake.Stage21IntakeRefused, match="NOTARIZED_PLAN"):
        intake.stage21f_admit_offline_binance_response(**params)


def test_witness_is_actually_called_without_synthetic_monkeypatch(monkeypatch):
    data = kw()
    with pytest.raises(intake.Stage21IntakeRefused, match="EXTERNAL_SIGNATURE"):
        intake.stage21f_admit_offline_binance_response(**data)


def test_prod_and_absent_ack_refused_before_any_witness_check(monkeypatch):
    params = kw()
    params["operator_ack"] = False
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        intake.stage21f_admit_offline_binance_response(**params)
    params["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        intake.stage21f_admit_offline_binance_response(**params)


def test_reject_noncanonical_body_and_oversized_batch():
    for raw in (
        b'{"klines":[]}',
        b'[[1,2], [3,4]]',
        b'[[NaN]]',
        b"[" + b"[]" * 100 + b"]",
    ):
        with pytest.raises(intake.Stage21IntakeRefused):
            intake._original_data_to_canonical(raw)
    with pytest.raises(intake.Stage21IntakeRefused, match="BOUNDED"):
        intake._original_data_to_canonical(b"X" * 160001)
