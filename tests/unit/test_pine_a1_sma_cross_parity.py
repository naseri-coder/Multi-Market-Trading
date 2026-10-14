"""PINE-A1 restricted translation and causal CSV/Parquet trace parity fixtures."""
from __future__ import annotations

import hashlib
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import CoreEventType, DataOrigin
from naseri_markets.historical_data_loader_a1 import HistoricalFileSpec
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition,
    PriceBasis,
    VolumeSemantics,
)
from naseri_markets.pine_a1_sma_cross_parity import (
    PineA1Refused,
    compare_pine_trace,
    parse_pine_sma_cross,
)
from naseri_markets.runtime_a6_dispatch_fence import (
    RuntimeA6Denied,
    require_worker_launch,
)

SOURCE = (
    b"//@version=5\n"
    b'indicator("SMA Cross", overlay=true)\n'
    b"fast = ta.sma(close, 2)\n"
    b"slow = ta.sma(close, 3)\n"
    b"longSignal = barstate.isconfirmed and ta.crossover(fast, slow)\n"
    b"shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)\n"
)
EXPECTED = (
    "NONE", "NONE", "NONE", "LONG", "NONE", "NONE", "NONE", "SHORT",
    "NONE", "LONG", "NONE", "SHORT",
)
PRICES = (1, 1, 1, 2, 3, 4, 2, 1, 2, 3, 4, 1)
T0 = datetime(2026, 10, 13, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _source(raw=SOURCE):
    return parse_pine_sma_cross(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _inputs(tmp_path, *, prices=PRICES, fmt="csv", signals=EXPECTED):
    header = b"open_at,close_at,open,high,low,close,volume\n"
    rows = []
    columns = {
        key: [] for key in (
            "open_at", "close_at", "open", "high", "low", "close", "volume",
        )
    }
    oracle = [b"close_at,signal\n"]
    for i, price in enumerate(prices):
        open_at = T0 + timedelta(minutes=15 * i)
        close_at = open_at + timedelta(minutes=15)
        values = [
            open_at.isoformat(), close_at.isoformat(),
            str(price), str(price + 1), str(price / 2),
            str(price), "5",
        ]
        rows.append(",".join(values).encode("ascii") + b"\n")
        for key, value in zip(columns, values, strict=True):
            columns[key].append(value)
        oracle.append((close_at.isoformat() + "," + signals[i] + "\n").encode())
    path = tmp_path / ("prices." + fmt)
    if fmt == "csv":
        path.write_bytes(header + b"".join(rows))
    else:
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")
        pq.write_table(pa.table({
            key: pa.array(values, type=pa.string())
            for key, values in columns.items()
        }), path, row_group_size=2)
    data_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    feed = FeedDefinition(
        "pine_a1_fixture_feed",
        Instrument(Market.CRYPTO, "fixture_claimed_source", "ABCUSDT", "UTC", "USDT"),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + data_digest[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120, history_limit=128,
    )
    oracle_bytes = b"".join(oracle)
    return path, dict(
        spec=HistoricalFileSpec(feed, data_digest, availability_lag_seconds=2,
                                max_rows=100),
        rule=_source(), oracle_bytes=oracle_bytes,
        expected_oracle_sha256=hashlib.sha256(oracle_bytes).hexdigest(),
        operator_ack=True,
    )


def test_source_is_a_declarative_ir_and_never_authorizes_execution():
    rule = _source()
    assert rule.pine_version == 5
    assert rule.indicator_title == "SMA Cross"
    assert rule.fast_length == 2 and rule.slow_length == 3
    assert rule.portable_rule == "PINE_A1_CONFIRMED_CLOSED_BAR_SMA_CROSS_V1"
    assert rule.input_price == "close"
    assert rule.on_bar == "barstate.isconfirmed"
    assert not rule.executable and not rule.compiled
    assert not rule.tradingview_equivalence_proven
    assert not rule.worker_execution_authorized
    v6 = SOURCE.replace(b"//@version=5", b"//@version=6")
    assert _source(v6).pine_version == 6


@pytest.mark.parametrize("fragment", [
    b"strategy(", b"request.security(", b"lookahead_on",
    b"barstate.isrealtime", b"barstate.islast", b"ta.ema(",
    b"alert(", b"strategy.entry", b"plotshape(", b"input.int(",
    b"import ", b"eval(", b"//@version=4", b"\x00",
])
def test_unsupported_or_repainting_pine_fails_closed(fragment):
    raw = SOURCE + fragment
    with pytest.raises(PineA1Refused):
        _source(raw)


@pytest.mark.parametrize("replacement", [
    b"fast = ta.sma(close, 1)",
    b"fast = ta.sma(close, 3)",
    b"fast = ta.sma(close, 201)",
    b"fast = ta.sma(open, 2)",
])
def test_invalid_fast_windows_or_source_component_rejected(replacement):
    raw = SOURCE.replace(b"fast = ta.sma(close, 2)", replacement)
    with pytest.raises(PineA1Refused):
        _source(raw)


@pytest.mark.parametrize("replacement", [
    b"shortSignal = ta.crossunder(fast, slow)",
    b"shortSignal = barstate.isconfirmed and ta.crossover(fast, slow)",
    b"shortSignal = barstate.isconfirmed and ta.crossunder(slow, fast)",
])
def test_no_unconfirmed_or_reversed_signals(replacement):
    raw = SOURCE.replace(
        b"shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)",
        replacement,
    )
    with pytest.raises(PineA1Refused):
        _source(raw)


@pytest.mark.parametrize("mutation", [
    {"fast_length": 0}, {"slow_length": 2}, {"pine_version": 7},
    {"input_price": "hl2"}, {"on_bar": "barstate.isrealtime"},
    {"executable": True}, {"compiled": True},
    {"tradingview_equivalence_proven": True},
    {"worker_execution_authorized": True},
])
def test_forged_rule_contract_denied(mutation):
    with pytest.raises(PineA1Refused, match="PINE_A1_FORGED_OR_INVALID_RULE_IR"):
        replace(_source(), **mutation)


def test_wrong_sha_size_utf8_and_bom_refused():
    with pytest.raises(PineA1Refused, match="PINE_A1_SOURCE_SHA_MISMATCH"):
        parse_pine_sma_cross(SOURCE, expected_sha256="0" * 64)
    with pytest.raises(PineA1Refused, match="PINE_A1_BOUNDED_PINNED_SOURCE_REQUIRED"):
        _source(b"x" * (16 * 1024 + 1))
    with pytest.raises(PineA1Refused, match="PINE_A1_UTF8_SOURCE_REQUIRED"):
        _source(b"\xff")
    with pytest.raises(PineA1Refused, match="PINE_A1_UNSAFE_SOURCE_ENCODING"):
        _source(b"\xef\xbb\xbf" + SOURCE)


def test_csv_hand_authored_oracle_trace_matches_without_tv_claim(tmp_path):
    path, params = _inputs(tmp_path)
    original = path.read_bytes()
    result = compare_pine_trace(path, **params)
    assert result.bars_compared == 12
    assert result.warmup_bars == 3
    assert result.long_signals == 2
    assert result.short_signals == 2
    assert result.mismatch_bars == 0
    assert result.first_mismatch_at is None
    assert result.offline_fixture_trace_matched
    assert result.status == "PINE_A1_OFFLINE_TRACE_MATCH_NOT_TV_ATTESTED"
    assert result.timeframe == "15m"
    assert result.symbol == "ABCUSDT"
    assert len(result.trace_sha256) == 64
    assert not result.actual_tradingview_source_authenticated
    assert not result.actual_tradingview_trace_authenticated
    assert not result.true_pine_runtime_equivalence_proven
    assert not result.market_source_authenticated
    assert not result.point_in_time_proven
    assert not result.paper_strategy_executed
    assert not result.paper_order_sent
    assert not result.broker_order_sent
    assert not result.telegram_sent
    assert not result.worker_execution_authorized
    assert not result.quarantine_release_authorized
    assert original == path.read_bytes()
    assert [p.name for p in tmp_path.iterdir()] == [path.name]
    assert compare_pine_trace(path, **params) == result


def test_real_parquet_row_groups_match_same_hand_authored_trace(tmp_path):
    path, opts = _inputs(tmp_path, fmt="parquet")
    report = compare_pine_trace(path, **opts)
    assert report.bars_compared == 12
    assert report.offline_fixture_trace_matched
    assert report.long_signals == report.short_signals == 2


def test_oracle_mismatch_is_a_refusal_to_claim_equivalence(tmp_path):
    bad = list(EXPECTED)
    bad[3] = "NONE"
    path, params = _inputs(tmp_path, signals=tuple(bad))
    report = compare_pine_trace(path, **params)
    assert not report.offline_fixture_trace_matched
    assert report.mismatch_bars == 1
    assert report.first_mismatch_at == T0 + timedelta(minutes=60)
    assert report.status == "PINE_A1_OFFLINE_TRACE_MISMATCH_NO_DEPLOY"
    assert not report.true_pine_runtime_equivalence_proven
    assert not report.worker_execution_authorized


@pytest.mark.parametrize("corruption", [
    b"close_at,signal\n",
    b"signal,close_at\n",
    b"close_at,signal,extra\n",
    b"close_at,signal\n2026-10-13T10:15:00Z,BUY\n",
    b"close_at,signal\n2026-10-13T10:15:00Z,NONE,EXTRA\n",
    b"\xff",
])
def test_bad_oracle_schema_and_encoding_refused(tmp_path, corruption):
    path, params = _inputs(tmp_path)
    bad = params | {
        "oracle_bytes": corruption,
        "expected_oracle_sha256": hashlib.sha256(corruption).hexdigest(),
    }
    with pytest.raises(PineA1Refused):
        compare_pine_trace(path, **bad)


def test_source_oracle_time_drift_and_duplicate_refused(tmp_path):
    path, params = _inputs(tmp_path)
    altered = params["oracle_bytes"].replace(
        b"2026-10-13T11:00:00+00:00", b"2026-10-13T12:00:00+00:00", 1,
    )
    with pytest.raises(PineA1Refused):
        compare_pine_trace(path, **(params | {
            "oracle_bytes": altered,
            "expected_oracle_sha256": hashlib.sha256(altered).hexdigest(),
        }))
    with pytest.raises(PineA1Refused, match="PINE_A1_ORACLE_SHA_MISMATCH"):
        compare_pine_trace(
            path, **(params | {"expected_oracle_sha256": "f" * 64}),
        )


def test_dataset_mutation_refused_before_success_trace(tmp_path):
    path, opts = _inputs(tmp_path)
    path.write_bytes(path.read_bytes().replace(b",3,4,1.5,3,5", b",3,4,1.5,4,5"))
    with pytest.raises(PineA1Refused, match="PINE_A1_MARKET_DATA_PREVALIDATION_REFUSED"):
        compare_pine_trace(path, **opts)


def test_wrong_environment_operator_ack_and_tick_data_refused(tmp_path, monkeypatch):
    path, opts = _inputs(tmp_path)
    with pytest.raises(PineA1Refused, match="PINE_A1_NONPRODUCTION"):
        compare_pine_trace(path, **(opts | {"operator_ack": False}))
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(PineA1Refused, match="PINE_A1_NONPRODUCTION"):
        compare_pine_trace(path, **opts)
    monkeypatch.delenv("MMT_PRODUCTION")
    feed = opts["spec"].feed
    tick_feed = FeedDefinition(
        feed.feed_id, feed.instrument, feed.timeframe,
        CoreEventType.QUOTE_TICK, DataOrigin.REPLAY, feed.source_ref,
        PriceBasis.BID_ASK, VolumeSemantics.UNKNOWN,
        max_latency_seconds=120, history_limit=128,
    )
    with pytest.raises(PineA1Refused, match="PINE_A1_EXACT_CLOSED_BAR_FEED_REQUIRED"):
        compare_pine_trace(path, **(opts | {
            "spec": HistoricalFileSpec(tick_feed, opts["spec"].expected_sha256,
                                       max_rows=100),
        }))


def test_no_network_worker_subprocess_or_a6_unlock(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("PINE_A1_MUST_NEVER_RUN_USER_CODE_OR_NETWORK")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    path, opts = _inputs(tmp_path)
    result = compare_pine_trace(path, **opts)
    assert result.offline_fixture_trace_matched
    with pytest.raises(RuntimeA6Denied):
        require_worker_launch(None, b"")
