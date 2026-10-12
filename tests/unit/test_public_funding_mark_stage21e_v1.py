"""Stage21E public funding/current-Mark evidence, no live exchange access in CI."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.public_funding_mark_stage21e_v1 import (
    FUNDING_ENDPOINT, MARK_ENDPOINT_BASE, FundingMarkRefused, FundingRequest,
    analyze_funding_and_mark, capture_public_funding_and_mark,
    parse_current_mark, parse_funding_history,
)
from naseri_markets.public_funding_mark_cli_stage21e_v1 import main
from naseri_markets.public_forward_capture_stage21c_v1 import (
    arm_forward_capture, seal_forward_capture, replay_sealed_bundle,
)
from test_public_forward_capture_stage21c_v1 import (
    SYMBOLS, T0, queries, raw_candles, raw_metadata,
)


@pytest.fixture(autouse=True)
def safe_env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _futures_fixture(tmp_path):
    bundle = tmp_path / "forward"
    def market(url):
        if url.endswith("/contracts/active"):
            return raw_metadata()
        return raw_candles(next(q for q in queries() if q.url == url))
    arm_forward_capture(
        bundle, symbols=SYMBOLS, operator_ack=True,
        transport=market, clock=lambda: T0 - timedelta(minutes=15))
    seal_forward_capture(
        bundle, requests=queries(), operator_ack=True,
        transport=market, clock=lambda: T0 + timedelta(hours=2))
    return bundle


def _public_mark_and_funding(url):
    if url.startswith(FUNDING_ENDPOINT):
        q = next(q for q in queries() if "symbol=" + q.symbol in url)
        rate = "0.0005" if q.symbol == SYMBOLS[0] else "-0.0003"
        stamp = int((q.start + (q.end - q.start)*0.85).timestamp()*1000)
        return json.dumps({"code":"200000","data":[
            {"symbol":q.symbol,"timepoint":stamp,"fundingRate":rate}
        ]}).encode()
    if url.startswith(MARK_ENDPOINT_BASE) and url.endswith("/current"):
        sym = url.removeprefix(MARK_ENDPOINT_BASE).removesuffix("/current")
        value = "101" if sym == SYMBOLS[0] else "120"
        timestamp = int((T0 + timedelta(hours=2, seconds=-2)).timestamp()*1000)
        return json.dumps({"code":"200000","data":{
            "symbol":sym, "timePoint":timestamp,
            "value":value, "indexPrice":"100"}}).encode()
    raise AssertionError("unknown URL / unexpected network operation: "+url)


def test_two_source_capture_and_readonly_funding_paper_sensitivity(tmp_path):
    bundle = _futures_fixture(tmp_path)
    paper = tmp_path / "paper"
    paper_report = replay_sealed_bundle(bundle, paper, operator_ack=True)
    assert paper_report["economic_audited_orders"] == 2
    calls = []
    def api(url):
        calls.append(url)
        return _public_mark_and_funding(url)
    evidence = capture_public_funding_and_mark(
        bundle, operator_ack=True, transport=api,
        clock=lambda: T0 + timedelta(hours=2))
    assert evidence["status"] == "PUBLIC_MARK_AND_FUNDING_ANNEX_CAPTURED_UNATTESTED"
    assert len(calls) == 4
    assert len([x for x in calls if x.startswith(FUNDING_ENDPOINT)]) == 2
    assert len([x for x in calls if x.startswith(MARK_ENDPOINT_BASE)]) == 2
    result = analyze_funding_and_mark(
        bundle, operator_ack=True, paper_path=paper / "paper.sqlite")
    assert result["funding_history_complete"] is False
    assert result["funding_applied_to_stage9_pnl"] is False
    assert result["liquidation_price_verified"] is False
    assert result["current_snapshot_is_historical_price"] is False
    assert result["paper_funding_scenario"]["audit_state"] == (
        "LOCAL_PER_CONTRACT_ECONOMICS_COHERENT_UNATTESTED")
    assert len(result["paper_funding_scenario"]["orders"]) == 2
    assert all(x["funding_scenario"] == "ENTRY_NOTIONAL_PROXY_UNATTESTED"
               for x in result["paper_funding_scenario"]["orders"])
    assert any("MARK_INDEX_DISLOCATION" in x["alerts"] for x in result["items"])
    assert all(x["liquidation_price"] is None for x in result["items"])
    assert result["live_trading_authorized"] is False
    assert result["broker_order_sent"] is False
    assert result["telegram_sent"] is False
    with pytest.raises(FundingMarkRefused, match="ANNEX_EXISTS"):
        capture_public_funding_and_mark(
            bundle, operator_ack=True, transport=api,
            clock=lambda: T0 + timedelta(hours=2))
    assert len(calls) == 4


def test_hypothetical_buffer_alert_is_not_actual_liquidation(tmp_path):
    bundle = _futures_fixture(tmp_path)
    capture_public_funding_and_mark(
        bundle, operator_ack=True, transport=_public_mark_and_funding,
        clock=lambda: T0 + timedelta(hours=2))
    report = analyze_funding_and_mark(
        bundle, operator_ack=True, hypothetical_leverage=D(50),
        hypothetical_mmr=D("0.49"))
    assert report["paper_funding_scenario"] is None
    assert all("HYPOTHETICAL_MAINTENANCE_BUFFER_NONPOSITIVE" in item["alerts"]
               for item in report["items"])
    assert all(item["historical_mark_risk"] ==
               "NOT_ASSESSED_NO_HISTORICAL_MARK_SERIES" for item in report["items"])


def test_missing_ack_and_production_cannot_call_public_get(tmp_path, monkeypatch):
    bundle = _futures_fixture(tmp_path)
    def blocked(_url):
        raise AssertionError("public GET called without authorization")
    with pytest.raises(ValueError, match="EXPLICIT_NONPRODUCTION"):
        capture_public_funding_and_mark(bundle, transport=blocked)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="EXPLICIT_NONPRODUCTION"):
        capture_public_funding_and_mark(bundle, operator_ack=True, transport=blocked)
    assert not (bundle / "stage21e.json").exists()
    assert main(["analyze", "--bundle-dir",str(bundle)]) == 2


def test_response_gaps_duplicates_future_marks_and_wrong_symbol_refused():
    req = FundingRequest(SYMBOLS[0], T0, T0 + timedelta(hours=1))
    stamp = int((T0 + timedelta(minutes=45)).timestamp()*1000)
    row = {"symbol":SYMBOLS[0],"timepoint":stamp,"fundingRate":"0.0002"}
    with pytest.raises(FundingMarkRefused, match="FUNDING_EVENT"):
        parse_funding_history(json.dumps({"code":"200000","data":[row,row]}).encode(),req)
    with pytest.raises(FundingMarkRefused, match="FUNDING_CONTRACT_MISMATCH"):
        parse_funding_history(json.dumps({"code":"200000","data":[
            dict(row,symbol="ETHUSDTM")]}).encode(),req)
    with pytest.raises(FundingMarkRefused, match="FUNDING_EVENT"):
        parse_funding_history(json.dumps({"code":"200000","data":[
            dict(row,fundingRate="0.12")]}).encode(),req)
    assert parse_funding_history(b'{"code":"200000","data":[]}',req) == ()
    received=T0 + timedelta(hours=2)
    def mark(ms, symbol=SYMBOLS[0]):
        return json.dumps({"code":"200000","data":{
            "symbol":symbol,"timePoint":ms,"value":101,"indexPrice":100}}).encode()
    with pytest.raises(FundingMarkRefused, match="STALE_OR_FUTURE"):
        parse_current_mark(mark(int((received-timedelta(minutes=1)).timestamp()*1000)),
                           SYMBOLS[0],observed_at=received)
    with pytest.raises(FundingMarkRefused, match="STALE_OR_FUTURE"):
        parse_current_mark(mark(int((received+timedelta(seconds=1)).timestamp()*1000)),
                           SYMBOLS[0],observed_at=received)
    with pytest.raises(FundingMarkRefused, match="MARK_CONTRACT_MISMATCH"):
        parse_current_mark(mark(int(received.timestamp()*1000),SYMBOLS[1]),
                           SYMBOLS[0],observed_at=received)
    with pytest.raises(FundingMarkRefused, match="DUPLICATE_MARKET_DATA_KEY"):
        parse_current_mark(
            b'{"code":"200000","data":{"symbol":"XBTUSDTM",'
            b'"symbol":"XBTUSDTM","timePoint":0,"value":1,"indexPrice":1}}',
            SYMBOLS[0],observed_at=received)


def test_tamper_mark_digest_and_symbol_refused(tmp_path):
    bundle = _futures_fixture(tmp_path)
    capture_public_funding_and_mark(
        bundle, operator_ack=True, transport=_public_mark_and_funding,
        clock=lambda: T0 + timedelta(hours=2))
    raw = bundle / "stage21e_mark_1.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(FundingMarkRefused, match="ANNEX_RAW_EVIDENCE_TAMPERED"):
        analyze_funding_and_mark(bundle,operator_ack=True)


def test_no_hidden_live_fetch_in_cli_and_sensitive_mark_checks(tmp_path, capsys):
    folder = tmp_path / "missing"
    assert main(["capture","--bundle-dir",str(folder)]) == 2
    assert "STAGE21E_PUBLIC_RISK_RESEARCH_REFUSED" in capsys.readouterr().err
    assert not folder.exists()
    req = FundingRequest(SYMBOLS[0], T0, T0 + timedelta(minutes=20))
    assert req.url.startswith(FUNDING_ENDPOINT)
    assert "symbol=XBTUSDTM" in req.url
