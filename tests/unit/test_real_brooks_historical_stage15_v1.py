"""Stage-15 real Brooks worker on synthetic, fully pinned historical archives."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import CoreEventType, DataOrigin
from naseri_markets.historical_data_loader_a1 import (
    HistoricalDataRefused, HistoricalFileSpec,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, PriceBasis, VolumeSemantics,
)
from naseri_markets.real_brooks_historical_stage15_v1 import (
    Stage15Refused, _review, review_real_brooks_history,
)

LEGACY = Path.cwd() / "production_source"
BEGIN = datetime(2026, 1, 1, tzinfo=UTC)
BAR = timedelta(minutes=15)


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _wire(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("ascii")


def parts(tmp_path, *, count=72, provider="binance_replay",
          symbol="BTCUSDT", contract="linear_perpetual"):
    path = tmp_path / "historical_ohlcv.csv"
    header = "open_at,close_at,open,high,low,close,volume\n"
    lines = [header]
    for index in range(count):
        t0 = BEGIN + BAR * index
        t1 = t0 + BAR
        # Matches flat synthetic scenario in actual public Brooks V5 integration.
        lines.append(
            f"{t0.isoformat()},{t1.isoformat()},100,101,99,100,10\n"
        )
    raw = "".join(lines).encode()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    feed = FeedDefinition(
        "stage15_reviewed_brooks", Instrument(
            Market.CRYPTO, provider, symbol, "UTC", "USDT",
        ),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + digest[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120,
    )
    spec = HistoricalFileSpec(feed, digest, 5)
    end = BEGIN + BAR * count
    receipt = {
        "schema_version": 1, "dataset_sha256": digest,
        "feed_id": feed.feed_id, "market": "crypto",
        "provider_claim": provider, "symbol": symbol,
        "timezone": "UTC", "quote_currency": "USDT",
        "timeframe": "15m", "event": "closed_candle",
        "price_basis": "trade", "volume_semantics": "traded",
        "contract_kind": contract,
        "session_policy": "continuous_utc_operator_assertion",
        "capture_method": "operator_supplied_archive",
        "availability_lag_seconds": 5, "expected_rows": count,
        "window_start_utc": BEGIN.isoformat(),
        "window_end_utc": end.isoformat(),
        "retrieved_at_utc": (end + timedelta(minutes=1)).isoformat(),
    }
    text = _wire(receipt)
    return path, spec, text, hashlib.sha256(text).hexdigest(), end


def evaluate(data, *, cuts=None, source=None, ack=True):
    path, spec, text, digest, end = data
    return review_real_brooks_history(
        path, spec, receipt_bytes=text, trusted_receipt_sha256=digest,
        archive_as_of_utc=end + timedelta(minutes=2),
        legacy_source=LEGACY if source is None else source,
        evaluation_cutoffs_utc=(
            BEGIN + BAR*60, BEGIN + BAR*72,
        ) if cuts is None else cuts,
        timeout_seconds=30, operator_ack=ack,
    )


def test_frozen_actual_v5_engine_sees_only_closed_window_and_no_order(tmp_path):
    assert LEGACY.is_dir()
    dataset = parts(tmp_path)
    old = dataset[0].read_bytes()
    report = evaluate(dataset)
    assert report["actual_brooks_engine_evaluated"] is True
    assert report["evaluation_count"] == 2
    assert report["evaluation_cutoffs_utc"] == [
        (BEGIN + BAR*60).isoformat(), (BEGIN + BAR*72).isoformat(),
    ]
    assert [x["visible_history_bar_count"] for x in report["evaluations"]] == [60, 72]
    assert all(x["engine_version"] ==
               "brooks-trilogy-full-core-v5-context-structural"
               for x in report["evaluations"])
    assert all(x["decision"] in ("NO_SIGNAL", "LONG", "SHORT")
               for x in report["evaluations"])
    assert all(len(x["snapshot_sha256"]) == 64
               and len(x["decision_evidence_sha256"]) == 64
               for x in report["evaluations"])
    assert report["source_manifest_sha256"] == (
        "1a15f9d4b40b07c05186d27f694f9ce71cd007dd5047a35b25b6811f9bc67335"
    )
    assert report["dataset_sha256"] == hashlib.sha256(old).hexdigest()
    assert report["verdict"] == "REAL_CORE_EXECUTED_SOURCE_AND_ECONOMICS_UNVERIFIED"
    for key in (
        "actual_exchange_data_authenticated",
        "independent_archival_time_attested",
        "venue_contract_economics_verified",
        "actual_live_strategy_signal_parity_certified",
        "parametric_strategy_variants_evaluated",
        "walk_forward_backtest_run", "economic_pnl_calculated",
        "trading_edge_proven", "research_release_authorized",
        "broker_orders_authorized", "telegram_sent", "production_modified",
    ):
        assert report[key] is False
    assert not (tmp_path / "brooks_stage10_paper.sqlite").exists()
    assert not (tmp_path / "engine_control.sqlite").exists()
    assert dataset[0].read_bytes() == old
    repeated = evaluate(dataset)
    assert repeated == report


def test_wrong_cutoffs_rejected_without_worker(tmp_path, monkeypatch):
    from naseri_markets import real_brooks_historical_stage15_v1 as mod
    dataset = parts(tmp_path)
    def no_worker(*_args, **_kwargs):
        raise AssertionError("worker should not run")
    monkeypatch.setattr(mod, "_worker", no_worker)
    for cuts in (
        (), (BEGIN + BAR*59,), (BEGIN + BAR*60, BEGIN + BAR*60),
        (BEGIN + BAR*72, BEGIN + BAR*60),
        (BEGIN + BAR*60 + timedelta(seconds=1),),
        (BEGIN + BAR*60,) * 4,
        (datetime(2026, 1, 1),),
    ):
        with pytest.raises(Stage15Refused, match="CUTOFF"):
            evaluate(dataset, cuts=cuts)


@pytest.mark.parametrize("opts,expected", [
    ({"provider": "operator_spoof"}, "INSTRUMENT_FENCE"),
    ({"symbol": "ETHUSDT"}, "INSTRUMENT_FENCE"),
    ({"contract": "spot"}, "CONTRACT_CLAIM"),
])
def test_unapproved_feed_or_contract_is_not_an_actual_brooks_test(
    tmp_path, opts, expected, monkeypatch,
):
    from naseri_markets import real_brooks_historical_stage15_v1 as mod
    monkeypatch.setattr(mod, "_worker",
                        lambda *_a, **_k: pytest.fail("worker reached"))
    with pytest.raises(Stage15Refused, match=expected):
        evaluate(parts(tmp_path, **opts))


def test_bad_utc_archive_or_file_digest_never_starts_real_worker(tmp_path, monkeypatch):
    from naseri_markets import real_brooks_historical_stage15_v1 as mod
    monkeypatch.setattr(mod, "_worker",
                        lambda *_a, **_k: pytest.fail("worker reached"))
    item = parts(tmp_path)
    item[0].write_bytes(item[0].read_bytes().replace(b",100,101,99,100,10",
                                                     b",100,102,99,100,10"))
    with pytest.raises(HistoricalDataRefused, match="HASH|SOURCE"):
        evaluate(item)


def test_operator_optin_required_and_production_denied(tmp_path, monkeypatch):
    dataset = parts(tmp_path)
    with pytest.raises(Stage15Refused, match="OPERATOR_APPROVAL"):
        evaluate(dataset, ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage15Refused, match="OPERATOR_APPROVAL"):
        evaluate(dataset)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(Stage15Refused, match="OPERATOR_APPROVAL"):
        evaluate(dataset)


def test_wrong_frozen_source_refused_without_evaluation(tmp_path, monkeypatch):
    from naseri_markets import real_brooks_historical_stage15_v1 as mod
    monkeypatch.setattr(mod, "_worker",
                        lambda *_a, **_k: pytest.fail("worker reached"))
    with pytest.raises(ValueError, match="BROOKS_FROZEN_SOURCE_REQUIRED"):
        evaluate(parts(tmp_path), source=tmp_path / "nonexistent")


def test_bounded_risk_geometry_refusal_for_forged_worker_result():
    context = {
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_replay", "exchange": "binance",
        "market_type": "futures", "symbol": "BTCUSDT",
        "quote_currency": "USDT", "timezone": "UTC",
        "timeframe": "15m",
        "candles": [{
            "open_time": (BEGIN + BAR*i).isoformat(),
            "close_time": (BEGIN + BAR*(i+1)).isoformat(),
            "open": "100", "high": "101", "low": "99",
            "close": "100", "volume": "10",
        } for i in range(60)],
    }
    from naseri_markets.brooks_replay import (
        canonical_snapshot_identity, parse_candle_replay,
    )
    data, _, bars = parse_candle_replay(_wire(context))
    key, sha = canonical_snapshot_identity(data, bars)
    base = {
        "snapshot_id": key, "snapshot_hash": sha,
        "engine_version": "brooks-trilogy-full-core-v5-context-structural",
        "rule_set_version": "brooks-v6", "configuration_version": "policy-1",
        "rule_ids": [], "decision": "LONG", "entry": "100", "stop": "101",
        "targets": ["105"], "setup_type": "TEST_INJECTION",
    }
    with pytest.raises(Stage15Refused, match="GEOMETRY"):
        _review(context, base, "a" * 64)
    no_signal = {**base, "decision": "NO_SIGNAL", "entry": None,
                 "stop": None, "targets": [], "setup_type": None}
    assert _review(context, no_signal, "a"*64)["decision"] == "NO_SIGNAL"
    wrong = {**no_signal, "snapshot_hash": "f"*64}
    with pytest.raises(Stage15Refused, match="SNAPSHOT"):
        _review(context, wrong, "a"*64)
