"""Stage21D: per-instrument risk, fees, exact quote-PnL and tamper fences."""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.paper_contract_audit_stage21d_v1 import (
    ContractAuditRefused, audit_paper_contract_economics,
)
from naseri_markets.paper_contract_economics_stage21d_v1 import (
    ContractEconomicsRefused, PaperContractEconomics,
)
from naseri_markets.public_forward_capture_stage21c_v1 import (
    ForwardCaptureRefused, arm_forward_capture, replay_sealed_bundle,
    seal_forward_capture,
)
from test_public_forward_capture_stage21c_v1 import (
    SYMBOLS, T0, queries, raw_candles, raw_metadata,
)


def contract(symbol="XBTUSDTM", multiplier="0.001",
             step="1", taker="0.0006", slip="0.003"):
    return PaperContractEconomics(
        "kucoin_futures", symbol, D(multiplier), D(step), D("0.1"),
        D(taker), D("0.0002"), D(slip), "e" * 64)


def test_per_instrument_economic_formulas_differ_and_are_exact():
    xbt = contract()
    eth = contract(symbol="ETHUSDTM", multiplier="0.01", step="2",
                   taker="0.001", slip="0.002")
    xbt.validate_order(D(2), D(100), D(95))
    eth.validate_order(D(2), D(100), D(95))
    assert xbt.notional(D(2), D(100)) == D("0.2")
    assert eth.notional(D(2), D(100)) == D("2")
    assert xbt.reserved_risk(D(2), D(100), D(95)) == (
        D(2) * D("0.001") * (D(5) + D(100) * D("0.0006")
                              + D(100) * D("0.0036")))
    assert eth.reserved_risk(D(2), D(100), D(105)) == (
        D(2) * D("0.01") * (D(5) + D(100) * D("0.001")
                             + D(105) * D("0.003")))
    long_gross, long_fee = xbt.modeled_exit(
        quantity=D(2), entry=D(100), exit_price=D(110), direction="long")
    short_gross, short_fee = eth.modeled_exit(
        quantity=D(2), entry=D(100), exit_price=D(90), direction="short")
    assert long_gross == D("0.02")
    assert long_fee == D(2) * D("0.001") * (
        D(100) * D("0.0006") + D(110) * D("0.0006")
        + D(110) * D("0.003"))
    assert short_gross == D("0.2")
    assert short_fee == D(2) * D("0.01") * (
        D(100) * D("0.001") + D(90) * D("0.001")
        + D(100) * D("0.002"))
    assert xbt.digest != eth.digest
    assert PaperContractEconomics.from_wire(xbt.wire()) == xbt


@pytest.mark.parametrize("override", [
    {"quantity_step": D("0.1")}, {"contract_multiplier": D(0)},
    {"taker_fee_fraction": D("Infinity")}, {"worst_slippage_fraction": D(1)},
    {"settle_currency": "BTC"}, {"provider": "unknown"},
])
def test_bad_contract_policy_refused(override):
    params = contract().wire()
    for k, v in override.items():
        params[k] = v
    with pytest.raises((ContractEconomicsRefused, ValueError)):
        PaperContractEconomics(**{
            **{k: D(v) if k in (
                "contract_multiplier", "quantity_step", "price_tick",
                "taker_fee_fraction", "maker_fee_fraction",
                "worst_slippage_fraction") else v for k, v in params.items()}
        })


def _pilot(tmp_path, *, raw=None):
    bundle = tmp_path / "bundle"
    def transport(url):
        if url.endswith("/contracts/active"):
            return raw or raw_metadata()
        return raw_candles(next(q for q in queries() if q.url == url))
    arm_forward_capture(
        bundle, symbols=SYMBOLS, operator_ack=True,
        transport=transport, clock=lambda: T0 - timedelta(minutes=15))
    seal_forward_capture(
        bundle, requests=queries(), operator_ack=True,
        transport=transport, clock=lambda: T0 + timedelta(hours=2))
    return bundle


def test_stage21d_both_symbols_replay_with_correct_units_and_evidence(
        tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    bundle = _pilot(tmp_path)
    report = replay_sealed_bundle(bundle, tmp_path / "paper", operator_ack=True)
    assert report["completed_jobs"] == 2
    assert report["economic_audited_orders"] == 2
    assert report["modeled_per_contract_economics_applied"] is True
    assert report["contract_quantity_per_symbol"] == "1"
    assert report["contract_economics_gate"] == "MODELED_PER_INSTRUMENT_APPLIED_UNATTESTED"
    assert report["real_exchange_contract_pnl_verified"] is False
    assert report["broker_order_sent"] is False
    assert report["telegram_sent"] is False
    assert len(report["per_instrument_economics_digests"]) == 2
    report_by_symbol = {r["symbol"]: r for r in report["datasets"]}
    assert report_by_symbol[SYMBOLS[0]]["per_instrument_economics_digest"] != (
        report_by_symbol[SYMBOLS[1]]["per_instrument_economics_digest"])
    assert all(r["status"] == "CLOSED" and r["data_origin"] == "replay"
               for r in report["datasets"])
    assert all(r["contract_units"] == "1" for r in report["datasets"])
    ledger = tmp_path / "paper" / "paper.sqlite"
    with sqlite3.connect(ledger) as db:
        rows = db.execute("SELECT r.risk,r.notional,e.policy FROM "
                          "paper_risk_reservations r "
                          "JOIN paper_order_economics e ON r.order_id=e.order_id").fetchall()
        assert len(rows) == 2
        by_symbol = {json.loads(p)["symbol"]: (D(risk), D(notional))
                     for risk, notional, p in rows}
        assert by_symbol[SYMBOLS[0]][1] != by_symbol[SYMBOLS[1]][1]
        assert db.execute("SELECT COUNT(*) FROM paper_stage9_exits").fetchone()[0] == 2
    assert audit_paper_contract_economics(
        ledger, expected=tuple(PaperContractEconomics.from_public(
            __import__("naseri_markets.public_forward_capture_stage21c_v1",
                       fromlist=["PublicContractGeometry"]).PublicContractGeometry(**g),
            metadata_sha256=report["reviewed_metadata_raw_sha256"],
            origin="INJECTED_TEST_CONTRACT_FIXTURE")
            for g in report["contract_geometry"]),
        expected_orders=2).orders == 2
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE paper_stage9_exits SET net='999' WHERE rowid=("
                   "SELECT MIN(rowid) FROM paper_stage9_exits)")
        db.commit()
    with pytest.raises(ContractAuditRefused, match="REALIZED_EXIT_PNL_DRIFT"):
        audit_paper_contract_economics(
            ledger, expected=tuple(PaperContractEconomics.from_public(
                __import__("naseri_markets.public_forward_capture_stage21c_v1",
                           fromlist=["PublicContractGeometry"]).PublicContractGeometry(**g),
                metadata_sha256=report["reviewed_metadata_raw_sha256"],
                origin="INJECTED_TEST_CONTRACT_FIXTURE")
                for g in report["contract_geometry"]),
            expected_orders=2)


def test_invalid_contract_lot_early_fail_without_paper_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    bundle = _pilot(tmp_path, raw=raw_metadata(bad=("lotSize", 2)))
    with pytest.raises(ForwardCaptureRefused, match="CONTRACT_LOT_STEP_MISMATCH"):
        replay_sealed_bundle(bundle, tmp_path / "never", operator_ack=True)
    assert not (tmp_path / "never").exists()


def test_nonproduction_fence_rejects_without_internet(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    bundle = _pilot(tmp_path)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ForwardCaptureRefused, match="EXPLICIT_NONPRODUCTION"):
        replay_sealed_bundle(bundle, tmp_path / "never", operator_ack=True)
    assert not (tmp_path / "never").exists()
