"""CERT-A2 direct pinned file/Pine replays, never runnable strategies."""
from __future__ import annotations

import hashlib
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.cert_a2_direct_paper_replay import (
    CertA2Refused,
    reverify_paper_evidence,
)
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import CoreEventType, DataOrigin
from naseri_markets.data_a1_file_intake import inspect_historical_for_paper
from naseri_markets.historical_data_loader_a1 import HistoricalFileSpec
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition,
    PriceBasis,
    VolumeSemantics,
)
from naseri_markets.pine_a1_sma_cross_parity import (
    compare_pine_trace,
    parse_pine_sma_cross,
)
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 10, 13, 10, tzinfo=UTC)
PINE = (
    b"//@version=6\n"
    b'indicator("SMA Research", overlay=true)\n'
    b"fast = ta.sma(close, 2)\n"
    b"slow = ta.sma(close, 3)\n"
    b"longSignal = barstate.isconfirmed and ta.crossover(fast, slow)\n"
    b"shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)\n"
)
PRICES = (1, 1, 1, 2, 3, 4, 2, 1, 2, 3, 4, 1)
SIGNALS = (
    "NONE", "NONE", "NONE", "LONG", "NONE", "NONE", "NONE", "SHORT",
    "NONE", "LONG", "NONE", "SHORT",
)


@pytest.fixture(autouse=True)
def _nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _dataset(tmp_path, *, format="csv", signals=SIGNALS):
    values = {
        field: [] for field in (
            "open_at", "close_at", "open", "high", "low", "close", "volume",
        )
    }
    oracle = [b"close_at,signal\n"]
    for index, price in enumerate(PRICES):
        open_at = T0 + timedelta(minutes=15 * index)
        close_at = open_at + timedelta(minutes=15)
        row = [
            open_at.isoformat(), close_at.isoformat(),
            str(price), str(price + 1), str(price / 2),
            str(price), "7",
        ]
        for field, value in zip(values, row, strict=True):
            values[field].append(value)
        oracle.append((close_at.isoformat() + "," + signals[index] + "\n").encode())
    path = tmp_path / ("candles." + format)
    if format == "csv":
        header = ",".join(values).encode() + b"\n"
        rows = [
            ",".join(values[field][i] for field in values).encode() + b"\n"
            for i in range(len(PRICES))
        ]
        path.write_bytes(header + b"".join(rows))
    else:
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")
        pq.write_table(pa.table({
            k: pa.array(v, type=pa.string()) for k, v in values.items()
        }), path, row_group_size=3)
    digest = _sha(path.read_bytes())
    feed = FeedDefinition(
        "data_a1_" + digest[:32],
        Instrument(Market.CRYPTO, "declared_fixture", "ABCUSDT", "UTC", "USDT"),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + digest[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120, history_limit=128,
    )
    spec = HistoricalFileSpec(
        feed, digest, availability_lag_seconds=2, max_rows=100,
    )
    return path, spec, b"".join(oracle)


def _direct(path, spec, **overrides):
    kw = {
        "spec": spec,
        "operator_ack": True,
    }
    kw.update(overrides)
    return reverify_paper_evidence(ROOT, path, **kw)


def _with_pine(oracle):
    return {
        "pine_source": PINE,
        "pine_source_sha256": _sha(PINE),
        "pine_oracle": oracle,
        "pine_oracle_sha256": _sha(oracle),
    }


def _old_data(path, spec):
    return inspect_historical_for_paper(
        path, sha256=spec.expected_sha256,
        market=spec.feed.instrument.market,
        provider=spec.feed.instrument.provider,
        symbol=spec.feed.instrument.symbol,
        timezone=spec.feed.instrument.timezone,
        quote_currency=spec.feed.instrument.quote_currency,
        timeframe=spec.feed.timeframe,
        event=spec.feed.event,
        price_basis=spec.feed.price_basis,
        volume_semantics=spec.feed.volume_semantics,
        availability_lag_seconds=spec.availability_lag_seconds,
        max_rows=spec.max_rows, operator_ack=True,
    )


def _old_pine(path, spec, oracle):
    rule = parse_pine_sma_cross(PINE, expected_sha256=_sha(PINE))
    return compare_pine_trace(
        path, spec=spec, rule=rule, oracle_bytes=oracle,
        expected_oracle_sha256=_sha(oracle), operator_ack=True,
    )


@pytest.mark.parametrize("format", ["csv", "parquet"])
def test_direct_causal_data_replay_is_not_execution(tmp_path, format):
    path, spec, _ = _dataset(tmp_path, format=format)
    report = _direct(path, spec)
    assert report.dataset_sha256 == spec.expected_sha256
    assert report.dataset_format == format
    assert report.claimed_provider == "declared_fixture"
    assert report.data_rows_replayed == len(PRICES)
    assert report.data_core_inputs_prepared == len(PRICES)
    assert report.status == "CERT_A2_DIRECT_REPLAY_REPRODUCED_ONLY_ALL_EXECUTION_DENIED"
    assert not report.data_prior_claim_checked
    assert not report.pine_prior_claim_checked
    assert not report.independent_market_source_authenticated
    assert not report.independent_stage_evidence_authenticated
    assert not report.real_tradingview_parity_proven
    assert not report.real_terminal_or_sandbox_attested
    assert not report.paper_strategy_executed
    assert not report.paper_order_sent
    assert not report.broker_authorized
    assert not report.telegram_authorized
    assert not report.worker_execution_authorized
    assert not report.quarantine_release_authorized
    assert not report.production_release_authorized
    assert report.pine_source_sha256 is None


@pytest.mark.parametrize("format", ["csv", "parquet"])
def test_direct_pine_recompute_with_original_claims(tmp_path, format):
    path, spec, oracle = _dataset(tmp_path, format=format)
    options = _with_pine(oracle)
    previous_data = _old_data(path, spec)
    previous_pine = _old_pine(path, spec, oracle)
    report = _direct(
        path, spec, prior_data_claim=previous_data,
        prior_pine_claim=previous_pine, **options,
    )
    assert report.pine_bars_compared == len(PRICES)
    assert report.pine_long_signals == 2
    assert report.pine_short_signals == 2
    assert report.data_prior_claim_checked
    assert report.pine_prior_claim_checked
    assert report.pine_source_sha256 == _sha(PINE)
    assert report.pine_oracle_sha256 == _sha(oracle)
    assert len(report.pine_trace_sha256) == 64
    assert len(report.report_fingerprint_sha256) == 64
    assert report == _direct(
        path, spec, prior_data_claim=previous_data,
        prior_pine_claim=previous_pine, **options,
    )
    assert not report.real_tradingview_parity_proven
    assert not report.worker_execution_authorized


@pytest.mark.parametrize("change", [
    {"rows_validated": 1},
    {"paper_core_inputs_validated": 900},
    {"symbol": "OTHERUSDT"},
    {"source_authenticated": True},
    {"broker_order_sent": True},
    {"first_available_at": T0},
])
def test_forged_data_claim_must_match_full_recomputed_report(tmp_path, change):
    path, spec, _ = _dataset(tmp_path)
    prior = replace(_old_data(path, spec), **change)
    with pytest.raises(CertA2Refused, match="CERT_A2_DATA_CLAIM_DIFFERS_FROM_REPLAY"):
        _direct(path, spec, prior_data_claim=prior)


@pytest.mark.parametrize("change", [
    {"mismatch_bars": 5},
    {"trace_sha256": "0" * 64},
    {"actual_tradingview_trace_authenticated": True},
    {"broker_order_sent": True},
    {"long_signals": 100},
])
def test_forged_pine_claim_must_match_new_recomputed_trace(tmp_path, change):
    path, spec, oracle = _dataset(tmp_path)
    previous = replace(_old_pine(path, spec, oracle), **change)
    with pytest.raises(CertA2Refused, match="CERT_A2_PINE_CLAIM_DIFFERS_FROM_REPLAY"):
        _direct(path, spec, prior_pine_claim=previous, **_with_pine(oracle))


def test_wrong_data_digest_and_mutated_file_rejected(tmp_path):
    path, spec, _ = _dataset(tmp_path)
    path.write_bytes(path.read_bytes().replace(b",2,3,1.0,2,7", b",2,3,1.0,3,7"))
    with pytest.raises(CertA2Refused, match="CERT_A2_ACTUAL_DATA_REPLAY_FAILED"):
        _direct(path, spec)


def test_forged_oracle_signal_mismatch_not_a_certificate(tmp_path):
    wrong = list(SIGNALS)
    wrong[3] = "NONE"
    path, spec, oracle = _dataset(tmp_path, signals=tuple(wrong))
    with pytest.raises(CertA2Refused, match="CERT_A2_PINE_TRACE_DISAGREEMENT"):
        _direct(path, spec, **_with_pine(oracle))


def test_bad_pine_source_digest_refused(tmp_path):
    path, spec, oracle = _dataset(tmp_path)
    with pytest.raises(CertA2Refused, match="CERT_A2_ACTUAL_PINE_TRACE_FAILED"):
        _direct(path, spec, **(_with_pine(oracle) | {"pine_source_sha256": "f" * 64}))


@pytest.mark.parametrize("key", [
    "pine_source", "pine_source_sha256", "pine_oracle", "pine_oracle_sha256",
])
def test_partial_pine_oracle_bundle_rejected(tmp_path, key):
    path, spec, oracle = _dataset(tmp_path)
    bundle = _with_pine(oracle)
    del bundle[key]
    with pytest.raises(CertA2Refused, match="CERT_A2_INCOMPLETE_PINE_REFERENCE"):
        _direct(path, spec, **bundle)


def test_prior_pine_claim_without_source_bundle_rejected(tmp_path):
    path, spec, oracle = _dataset(tmp_path)
    with pytest.raises(CertA2Refused, match="CERT_A2_INCOMPLETE_PINE_REFERENCE"):
        _direct(path, spec, prior_pine_claim=_old_pine(path, spec, oracle))


def test_replay_refuses_production_missing_operator_and_bad_limits(tmp_path, monkeypatch):
    path, spec, _ = _dataset(tmp_path)
    with pytest.raises(CertA2Refused, match="CERT_A2_EXPLICIT_NONPRODUCTION"):
        _direct(path, spec, operator_ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(CertA2Refused, match="CERT_A2_EXPLICIT_NONPRODUCTION"):
        _direct(path, spec)
    monkeypatch.delenv("MMT_PRODUCTION")
    with pytest.raises(CertA2Refused, match="CERT_A2_EXACT_PINNED_FILE_SPEC"):
        _direct(path, replace(spec, max_rows=10_001))


def test_no_broker_network_subprocess_or_a6_execution(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("CERT_A2_MUST_NOT_RUN_PROCESS_OR_NETWORK")
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(socket, "socket", denied)
    path, spec, oracle = _dataset(tmp_path)
    report = _direct(path, spec, **_with_pine(oracle))
    assert report.pine_bars_compared == len(PRICES)
    assert not report.worker_execution_authorized
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
