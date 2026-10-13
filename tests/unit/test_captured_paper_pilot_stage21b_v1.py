"""Stage 21B full real-schema-format (not genuine real-origin) PAPER tests."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Market
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin, ProviderSnapshot,
)
from naseri_markets.kucoin_futures_replay_stage21_v1 import FuturesKlineRequest
from naseri_markets.captured_paper_pilot_stage21b_v1 import (
    CapturedPaperRefused, run_captured_paper_pilot,
)

T0 = datetime(2026, 10, 12, 10, tzinfo=UTC)
SYMBOLS = ("XBTUSDTM", "ETHUSDTM")
PERIODS = ("15m", "5m")
MINUTES = {"15m": 15, "5m": 5}


def snapshot(*, stale=False):
    at = T0 - (timedelta(days=3) if stale else timedelta())
    records = tuple(InstrumentMetadata(
        "kucoin_futures", Market.CRYPTO, symbol, "UTC", "USDT",
        D("0.01"), MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
        ListingStatus.OPEN, at, "PERPETUAL") for symbol in SYMBOLS)
    return ProviderSnapshot(
        "kucoin_futures", MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
        at, records, "b" * 64)


def fixtures(*, no_entry=False, no_touch=False, ambiguous=False):
    result = []
    for symbol, period in zip(SYMBOLS, PERIODS):
        delta = timedelta(minutes=MINUTES[period])
        query = FuturesKlineRequest(symbol, period, T0, T0 + delta * 4)
        bars = [
            [100, 102, 98, 100, 10, 1000],
            [100, 108, 99, 106, 10, 1000],
            [107, 108, 104, 107, 10, 1000],
            [107, 114, 104, 113, 10, 1000],
        ]
        if no_entry:
            bars = [[100, 101, 99, 100, 10, 1000]] * 4
        elif no_touch:
            bars[2] = [110, 111, 109, 110, 10, 1000]
            bars[3] = [110, 111, 109, 110, 10, 1000]
        elif ambiguous:
            bars[2] = [107, 115, 98, 107, 10, 1000]
        rows = [[int((T0 + i * delta).timestamp() * 1000), *bar]
                for i, bar in enumerate(bars)]
        data = json.dumps({"code": "200000", "data": rows}).encode()
        result.append((query, data))
    return tuple(result)


def pilot(tmp_path, *, datasets=None, dry_run_signals=True, **kwargs):
    return run_captured_paper_pilot(
        tmp_path / "stage21b", datasets=fixtures() if datasets is None else datasets,
        provider_snapshot=snapshot(), observed_at=T0 + timedelta(hours=2),
        operator_ack=True, dry_run_signals=dry_run_signals, **kwargs)


def test_two_symbol_true_replay_stage19_intents_fill_target_restart_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    report = pilot(tmp_path)
    assert report["mode"] == "STAGE21B_UNATTESTED_PUBLIC_FORMAT_OFFLINE_PAPER"
    assert report["core"] == "fixture.contract.check"
    assert report["completed_jobs"] == 2
    assert report["exact_effects"] == 6
    assert report["integrity_verdict"] == "PASS"
    assert report["release_verdict"] == "BLOCKED_NONPRODUCTION_UNATTESTED"
    assert report["restarted_and_reconciled"] is True
    assert {x["symbol"] for x in report["datasets"]} == set(SYMBOLS)
    assert all(x["status"] == "CLOSED" for x in report["datasets"])
    assert all(x["data_origin"] == "replay" for x in report["datasets"])
    assert all(x["fill_model"] == "MODELED_LIMIT_TOUCH" for x in report["datasets"])
    assert {x["timeframe"] for x in report["datasets"]} == set(PERIODS)
    assert all(x["source_ref"].startswith("kucoin_futures_") for x in report["datasets"])
    assert D(report["modeled_realized_net_total"]) > 0
    assert all(report[key] is False for key in (
        "telegram_sent", "broker_order_sent", "provider_origin_independently_attested",
        "real_network_used", "provider_contract_size_verified",
        "real_futures_pnl_proven", "profitability_proven",
        "live_trading_enabled", "public_release_authorized",
        "brooks_core_api_integrated"))
    with sqlite3.connect(tmp_path / "stage21b" / "effects.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM effect19_intents").fetchone()[0] == 6
        assert db.execute("SELECT COUNT(*) FROM effect19_intents WHERE state='RECORDED'").fetchone()[0] == 6
    with pytest.raises(CapturedPaperRefused, match="NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED"):
        pilot(tmp_path)


@pytest.mark.parametrize("case,reason", [
    ("no_touch", "NOT_TOUCHED"),
    ("ambiguous", "INTRABAR_UNRESOLVED"),
])
def test_unfillable_and_intrabar_ambiguous_never_become_winners(tmp_path, monkeypatch, case, reason):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    report = pilot(tmp_path, datasets=fixtures(**{case: True}))
    assert report["completed_jobs"] == 2
    assert report["exact_effects"] == 6
    assert all(x["status"] == "CANCELED" for x in report["datasets"])
    assert all(x["fill_model"] == reason for x in report["datasets"])
    assert D(report["modeled_realized_net_total"]) == 0


def test_no_setup_does_not_invent_trades_or_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    report = pilot(tmp_path, datasets=fixtures(no_entry=True))
    assert report["completed_jobs"] == 0
    assert report["exact_effects"] == 0
    assert all(x["status"] == "NO_ELIGIBLE_ENTRY" for x in report["datasets"])
    assert report["integrity_verdict"] == "BLOCKED"
    assert report["integrity_blockers"] == ["NO_EVALUATED_OUTPUT_EVIDENCE"]
    assert report["effect_evidence_verdict"] == "NO_EFFECT_INTENTS_NOT_STAGE19_ATTESTED"
    assert report["no_output_cross_stage_unattested"] is True


def test_paper_and_signal_modes_are_independent(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    report = pilot(tmp_path, dry_run_signals=False)
    assert report["completed_jobs"] == 2
    assert report["exact_effects"] == 4
    assert {r["status"] for r in report["datasets"]} == {"CLOSED"}
    with sqlite3.connect(tmp_path / "stage21b" / "signals.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM offline_signal_states").fetchone()[0] == 0


def test_safety_gates_no_state_created(tmp_path, monkeypatch):
    path = tmp_path / "denied"
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    with pytest.raises(CapturedPaperRefused, match="EXPLICIT_NONPRODUCTION"):
        run_captured_paper_pilot(
            path, datasets=fixtures(), provider_snapshot=snapshot(),
            observed_at=T0+timedelta(hours=2), operator_ack=True)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CapturedPaperRefused, match="EXPLICIT_NONPRODUCTION"):
        run_captured_paper_pilot(
            path, datasets=fixtures(), provider_snapshot=snapshot(),
            observed_at=T0+timedelta(hours=2), operator_ack=True)
    monkeypatch.delenv("MMT_PRODUCTION")
    with pytest.raises(CapturedPaperRefused, match="REVIEWED_HISTORIC_METADATA"):
        run_captured_paper_pilot(
            path, datasets=fixtures(), provider_snapshot=snapshot(stale=True),
            observed_at=T0+timedelta(hours=2), operator_ack=True)
    with pytest.raises(CapturedPaperRefused, match="TWO_DISTINCT"):
        run_captured_paper_pilot(
            path, datasets=(fixtures()[0], fixtures()[0]),
            provider_snapshot=snapshot(),
            observed_at=T0+timedelta(hours=2), operator_ack=True)
    assert not path.exists()
