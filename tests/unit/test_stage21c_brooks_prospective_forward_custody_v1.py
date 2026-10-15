"""Stage21C Brooks forward preregistration tests: SYNTHETIC future data only."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.brooks_prospective_forward_custody_stage21c_v1 import (
    BrooksProspectivePlan, Stage21ForwardRefused,
    freeze_brooks_prospective_plan, review_brooks_forward_candle_receipt,
)
from naseri_markets.brooks_replay import LEGACY_MANIFEST_SHA256

CREATED = datetime(2026, 12, 31, tzinfo=UTC)
START = datetime(2027, 1, 2, tzinfo=UTC)
END = datetime(2027, 1, 12, tzinfo=UTC)
BAR = timedelta(minutes=15)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def plan():
    return BrooksProspectivePlan(
        protocol="STAGE21C_BROOKS_PROSPECTIVE_PRECOMMIT_PROTOCOL_V1",
        strategy_manifest_sha256=LEGACY_MANIFEST_SHA256,
        bridge_source_sha256="a" * 64,
        economics_assumptions_sha256="b" * 64,
        study_start_utc=iso(START),
        study_end_utc=iso(END),
        operator_created_utc=iso(CREATED),
    )


def frozen(p=None):
    return freeze_brooks_prospective_plan(
        plan() if p is None else p,
        operator_recorded_at_utc=CREATED + timedelta(minutes=1),
        operator_ack=True,
    )


def candles(index=0, count=4):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(("open_at", "close_at", "open", "high", "low", "close", "volume"))
    for n in range(index, index + count):
        writer.writerow((iso(START+BAR*n), iso(START+BAR*(n+1)),
                         "100", "101", "99", "100", "10"))
    return buf.getvalue().encode("ascii")


def receive(raw, *, prior=None, at=None, plan_override=None, origin=None):
    body, digest = frozen(plan_override)
    return review_brooks_forward_candle_receipt(
        plan_bytes=body, plan_sha256=digest,
        original_capture_csv_bytes=raw,
        operator_recorded_at_utc=at or START+timedelta(hours=2),
        capture_origin=origin or "SYNTHETIC_OFFLINE_TEST_ONLY",
        previous_receipt_bytes=prior,
        operator_ack=True,
    )


def test_seal_exact_study_precommitted_before_begin_and_fixed_policy():
    data, digest = frozen()
    assert hashlib.sha256(data).hexdigest() == digest
    report = json.loads(data)
    assert report["paper_market_access"] is False
    assert report["strategy_manifest_sha256"] == LEGACY_MANIFEST_SHA256
    assert report["study_start_utc"] == iso(START)
    assert report["study_end_utc"] == iso(END)
    assert data == frozen()[0]


def test_local_first_and_second_receipts_form_hash_chain_and_never_certify_oos():
    first, h1 = receive(candles(0, 4))
    second, h2 = receive(
        candles(4, 4), prior=first, at=START+timedelta(hours=3),
    )
    r1, r2 = json.loads(first), json.loads(second)
    assert r1["sequence"] == 1 and r2["sequence"] == 2
    assert r1["previous_receipt_sha256"] == frozen()[1]
    assert r2["previous_receipt_sha256"] == h1
    assert r2["first_open_utc"] == iso(START+timedelta(hours=1))
    assert r2["last_close_utc"] == iso(START+timedelta(hours=2))
    assert h2 == hashlib.sha256(json.dumps(
        {k:v for k,v in r2.items() if k != "receipt_sha256"},
        sort_keys=True,separators=(",", ":")
    ).encode()).hexdigest()
    assert r2["independent_timestamp_attested"] is False
    assert r2["precommitment_witness_verified"] is False
    assert r2["provider_signature_verified"] is False
    assert r2["verified_prospective_oos"] is False
    assert r2["forward_paper_enabled"] is False
    assert r2["live_trading_authorized"] is False


@pytest.mark.parametrize("wrong", [
    {"strategy_manifest_sha256": "0"*64},
    {"paper_market_access": True},
    {"symbol": "ETHUSDT"},
    {"warmup_closed_bars": 59},
    {"max_forward_bars_per_receipt": 512},
    {"same_bar_stop_target_policy": "TAKE_TARGET_FIRST"},
    {"funding_gap_policy": "BACKFILL_ZERO"},
    {"study_start_utc": "2026-12-31T12:00:00Z"},
    {"study_end_utc": "2027-01-04T00:00:00Z"},
    {"study_end_utc": "2027-05-30T00:00:00Z"},
    {"study_start_utc": "2027-01-02T00:05:00Z"},
])
def test_invalid_study_geometry_and_rule_drift_block(wrong):
    with pytest.raises(Stage21ForwardRefused):
        frozen(replace(plan(), **wrong))


def test_receipt_start_rejects_backfill_or_skipped_first_bar():
    with pytest.raises(Stage21ForwardRefused, match="SEQUENCE"):
        receive(candles(1, 2))


def test_receipt_missing_candle_and_out_of_order_is_refused():
    content = candles(0, 4).decode()
    rows = content.splitlines()
    with pytest.raises(Stage21ForwardRefused, match="SEQUENCE"):
        receive(("\n".join(rows[:2]+rows[3:])+"\n").encode())
    with pytest.raises(Stage21ForwardRefused, match="SEQUENCE"):
        receive(("\n".join([rows[0],rows[2],rows[1],*rows[3:]])+"\n").encode())


def test_future_report_rejected_until_close_plus_data_availability_lag():
    with pytest.raises(Stage21ForwardRefused, match="NOT_YET_CLOSED"):
        receive(candles(0, 4), at=START+timedelta(minutes=59))
    with pytest.raises(Stage21ForwardRefused, match="NOT_YET_CLOSED"):
        receive(candles(0, 4), at=START+timedelta(hours=1,seconds=4))
    receive(candles(0, 4), at=START+timedelta(hours=1,seconds=5))


def test_tamper_prior_receipt_and_reordering_refused():
    first,_ = receive(candles(0, 4))
    doc = json.loads(first)
    doc["last_close_utc"] = iso(START+timedelta(hours=10))
    fake = json.dumps(doc).encode()
    with pytest.raises(Stage21ForwardRefused, match="PRIOR_CHAIN"):
        receive(candles(4,4), prior=fake)


def test_wrong_prior_plan_and_gap_refused():
    first,_ = receive(candles(0, 4))
    with pytest.raises(Stage21ForwardRefused, match="SEQUENCE"):
        receive(candles(8, 4), prior=first)


def test_plan_sha_source_csv_tamper_refused():
    plan_bytes, pin = frozen()
    with pytest.raises(Stage21ForwardRefused, match="PLAN_BYTES_OR_PIN"):
        review_brooks_forward_candle_receipt(
            plan_bytes=plan_bytes, plan_sha256="a"*64,
            original_capture_csv_bytes=candles(),
            operator_recorded_at_utc=START+timedelta(hours=2),
            capture_origin="SYNTHETIC_OFFLINE_TEST_ONLY", operator_ack=True,
        )
    with pytest.raises(Stage21ForwardRefused, match="PRICE"):
        receive(candles().replace(b",99,100,10", b",garbage,100,10"))


def test_no_missing_provider_authentication_claim():
    report,_ = receive(
        candles(), origin="OPERATOR_SUPPLIED_PUBLIC_SOURCE_UNVERIFIED",
    )
    assert json.loads(report)["source_claim"] == "OPERATOR_SUPPLIED_PUBLIC_SOURCE_UNVERIFIED"
    with pytest.raises(Stage21ForwardRefused, match="UNVERIFIED_SOURCE"):
        receive(candles(), origin="EXCHANGE_SIGNED_AND_WITNESSED")


def test_duplicate_json_plan_disallowed():
    data,pin = frozen()
    duplicate=data.replace(b'"market":"binance_usdm"',b'"market":"binance_usdm","market":"binance_usdm"')
    with pytest.raises(Stage21ForwardRefused, match="DUPLICATE"):
        review_brooks_forward_candle_receipt(
            plan_bytes=duplicate, plan_sha256=hashlib.sha256(duplicate).hexdigest(),
            original_capture_csv_bytes=candles(),
            operator_recorded_at_utc=START+timedelta(hours=2),
            capture_origin="SYNTHETIC_OFFLINE_TEST_ONLY",
            operator_ack=True,
        )


def test_no_production_activation_even_for_wellformed_payload(monkeypatch):
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage21ForwardRefused, match="NONPRODUCTION"):
        frozen()
    data,pin = None,None
    with pytest.raises(Stage21ForwardRefused, match="NONPRODUCTION"):
        receive(candles())


def test_clock_must_not_be_backdated_and_utc_awareness_required():
    with pytest.raises(Stage21ForwardRefused, match="REGISTRATION"):
        freeze_brooks_prospective_plan(
            plan(), operator_recorded_at_utc=CREATED-timedelta(hours=1),
            operator_ack=True,
        )
    with pytest.raises(Stage21ForwardRefused, match="CLOCK"):
        freeze_brooks_prospective_plan(
            plan(), operator_recorded_at_utc=CREATED.replace(tzinfo=None),
            operator_ack=True,
        )


def test_candle_quantity_and_header_bounds():
    with pytest.raises(Stage21ForwardRefused, match="ROWS"):
        receive(candles(0, 97))
    with pytest.raises(Stage21ForwardRefused, match="SCHEMA"):
        receive(candles().replace(b"open_at,close_at",b"event_time,close_at"))
