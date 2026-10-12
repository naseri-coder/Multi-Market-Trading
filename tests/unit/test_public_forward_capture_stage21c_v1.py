"""Stage21C offline fixtures: true forward chronology, 0 network calls in CI."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.kucoin_futures_replay_stage21_v1 import FuturesKlineRequest
from naseri_markets.public_forward_capture_stage21c_v1 import (
    ForwardCaptureRefused, arm_forward_capture, inspect_public_contract_geometry,
    replay_sealed_bundle, seal_forward_capture, verify_capture_bundle,
)
from naseri_markets.public_forward_capture_cli_stage21c_v1 import main

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
SYMBOLS = ("XBTUSDTM", "ETHUSDTM")


def raw_metadata(*, bad=None):
    rows = [
        {"symbol": symbol, "type": "FFWCSX", "quoteCurrency": "USDT",
         "settleCurrency": "USDT", "expireDate": None, "status": "Open",
         "tickSize": "0.1", "lotSize": 1,
         "multiplier": ("0.001" if symbol == SYMBOLS[0] else "0.01"),
         "makerFeeRate": "0.0002", "takerFeeRate": "0.0006",
         "isInverse": False, "isQuanto": True}
        for symbol in SYMBOLS
    ]
    if bad:
        rows[0][bad[0]] = bad[1]
    return json.dumps({"code": "200000", "data": rows}).encode()


def queries():
    return (
        FuturesKlineRequest(SYMBOLS[0], "15m", T0,
                            T0 + timedelta(minutes=60)),
        FuturesKlineRequest(SYMBOLS[1], "5m", T0,
                            T0 + timedelta(minutes=20)),
    )


def raw_candles(query):
    dt = query.end - query.start
    minutes = int(dt.total_seconds() // 60 // 4)
    tstep = timedelta(minutes=minutes)
    bars = (
        (100, 102, 98, 100, 10, 1000),
        (100, 108, 99, 106, 10, 1000),
        (107, 108, 104, 107, 10, 1000),
        (107, 114, 104, 113, 10, 1000),
    )
    rows = [[int((T0 + n * tstep).timestamp() * 1000), *bar]
            for n, bar in enumerate(bars)]
    return json.dumps({"code": "200000", "data": rows}).encode()


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def test_forward_metadata_two_gets_later_and_paper_audit(tmp_path):
    dest = tmp_path / "armed"
    called = []
    def api(url):
        called.append(url)
        if url.endswith("/contracts/active"):
            return raw_metadata()
        for q in queries():
            if url == q.url:
                return raw_candles(q)
        raise AssertionError("unexpected URL")

    armed_at = T0 - timedelta(minutes=15)
    armed = arm_forward_capture(
        dest, symbols=SYMBOLS, operator_ack=True, transport=api,
        clock=lambda: armed_at)
    assert len(called) == 1
    assert armed["capture_mode"] == "INJECTED_TEST_TRANSPORT"
    assert (dest / "contracts.json").stat().st_mode & 0o077 == 0
    geometry = armed["contract_geometry"]
    assert {g["symbol"] for g in geometry} == set(SYMBOLS)
    assert geometry[0]["base_units_per_contract"] == "0.001"
    assert geometry[1]["base_units_per_contract"] == "0.01"
    with pytest.raises(ForwardCaptureRefused, match="FORWARD_BARS_NOT_CLOSED"):
        seal_forward_capture(dest, requests=queries(), operator_ack=True,
                             transport=api, clock=lambda: T0 + timedelta(minutes=16))
    assert len(called) == 1
    seal = seal_forward_capture(
        dest, requests=queries(), operator_ack=True, transport=api,
        clock=lambda: T0 + timedelta(hours=2))
    assert len(called) == 3
    assert seal["status"] == "SEALED_COMPLETE_PUBLIC_RESPONSE_BUNDLE"
    assert seal["real_contract_pnl_calibrated"] is False
    assert verify_capture_bundle(dest)[0]["capture_mode"] == "INJECTED_TEST_TRANSPORT"
    report = replay_sealed_bundle(dest, tmp_path / "paper", operator_ack=True)
    assert report["completed_jobs"] == 2
    assert report["exact_effects"] == 4
    assert report["integrity_verdict"] == "PASS"
    assert report["source_transport_origin"] == "INJECTED_TEST_TRANSPORT"
    assert report["contract_economics_gate"] == "BLOCKED_PER_INSTRUMENT_MULTIPLIER_NOT_APPLIED"
    assert report["real_exchange_contract_pnl_verified"] is False
    assert report["broker_order_sent"] is False
    assert report["telegram_sent"] is False
    assert report["data_capture_before_candle_window"] is True
    assert all(x["data_origin"] == "replay" for x in report["datasets"])
    with pytest.raises(ForwardCaptureRefused, match="CAPTURE_ALREADY_SEALED"):
        seal_forward_capture(dest, requests=queries(), operator_ack=True,
                             transport=api, clock=lambda: T0 + timedelta(hours=2))
    assert len(called) == 3


def test_no_network_without_ack_or_in_production(tmp_path, monkeypatch):
    folder = tmp_path / "blocked"
    def no_network(_url):
        raise AssertionError("network must not be accessed")
    with pytest.raises(ForwardCaptureRefused, match="EXPLICIT_NONPRODUCTION"):
        arm_forward_capture(folder, symbols=SYMBOLS, transport=no_network)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ForwardCaptureRefused, match="EXPLICIT_NONPRODUCTION"):
        arm_forward_capture(folder, symbols=SYMBOLS,
                            operator_ack=True, transport=no_network)
    assert not folder.exists()


@pytest.mark.parametrize("bad", [
    ("multiplier", None), ("multiplier", 0),
    ("lotSize", 0), ("lotSize", "0.5"),
    ("isInverse", True), ("isQuanto", None),
    ("settleCurrency", "BTC"), ("quoteCurrency", "BTC"),
    ("status", "Closed"), ("expireDate", 123456),
    ("makerFeeRate", -0.1),
])
def test_unsafe_contract_metadata_rejected(bad):
    with pytest.raises((ForwardCaptureRefused, ValueError)):
        inspect_public_contract_geometry(raw_metadata(bad=bad), SYMBOLS)


def test_never_retrofit_historic_metadata_or_fake_candle_completeness(tmp_path):
    folder = tmp_path / "armed"
    def api(url):
        return raw_metadata() if url.endswith("/contracts/active") else raw_candles(
            next(q for q in queries() if q.url == url))
    arm_forward_capture(folder, symbols=SYMBOLS, operator_ack=True,
                        transport=api, clock=lambda: T0 + timedelta(minutes=1))
    with pytest.raises(ForwardCaptureRefused, match="HISTORIC_LOOKBACK"):
        seal_forward_capture(folder, requests=queries(), operator_ack=True,
                             transport=api, clock=lambda: T0 + timedelta(hours=2))
    assert not (folder / "first.json").exists()


def test_bytes_tampered_sealed_bundle_refused_before_paper_db(tmp_path):
    folder = tmp_path / "armed"
    def api(url):
        if url.endswith("/contracts/active"):
            return raw_metadata()
        return raw_candles(next(q for q in queries() if q.url == url))
    arm_forward_capture(
        folder, symbols=SYMBOLS, operator_ack=True, transport=api,
        clock=lambda: T0 - timedelta(minutes=1))
    seal_forward_capture(
        folder, requests=queries(), operator_ack=True, transport=api,
        clock=lambda: T0 + timedelta(hours=2))
    candle_path = folder / "first.json"
    candle_path.write_bytes(candle_path.read_bytes() + b" ")
    output = tmp_path / "paper"
    with pytest.raises(ForwardCaptureRefused, match="CANDLE_EVIDENCE_DIGEST_CONFLICT"):
        replay_sealed_bundle(folder, output, operator_ack=True)
    assert not output.exists()


def test_cli_gates_before_network_or_local_file_use(tmp_path, capsys):
    folder = tmp_path / "never"
    assert main(["arm", "--bundle-dir", str(folder),
                 "--first-symbol", SYMBOLS[0], "--second-symbol", SYMBOLS[1]]) == 2
    assert not folder.exists()
    assert "STAGE21C_NONPRODUCTION_REFUSED" in capsys.readouterr().err
