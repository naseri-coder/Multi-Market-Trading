"""Stage-12 historical Point-in-Time gate over the existing DATA-A1 loader."""
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
from naseri_markets.historical_pit_quality_stage12_v1 import (
    HistoricalPitRefused,
    inspect_historical_pit_archive,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, PriceBasis, VolumeSemantics,
)

START = datetime(2026, 10, 13, 10, tzinfo=UTC)
HEADER = b"open_at,close_at,open,high,low,close,volume\n"
ROW1 = b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,100,105,99,102,0\n"
ROW2 = b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,102,106,101,103,8\n"


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def scenario(tmp_path, *, raw=HEADER + ROW1 + ROW2, lag=5, **changes):
    path = tmp_path / "one_crypto_source.csv"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    feed = FeedDefinition(
        "stage12_crypto_history", Instrument(
            Market.CRYPTO, "fixture_venue", "BTCUSDT", "UTC", "USDT",
        ),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + digest[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120,
    )
    spec = HistoricalFileSpec(feed, digest, lag)
    receipt = {
        "schema_version": 1,
        "dataset_sha256": digest,
        "feed_id": feed.feed_id,
        "market": "crypto",
        "provider_claim": "fixture_venue",
        "symbol": "BTCUSDT",
        "timezone": "UTC",
        "quote_currency": "USDT",
        "timeframe": "15m",
        "event": "closed_candle",
        "price_basis": "trade",
        "volume_semantics": "traded",
        "contract_kind": "linear_perpetual",
        "session_policy": "continuous_utc_operator_assertion",
        "capture_method": "operator_supplied_archive",
        "availability_lag_seconds": lag,
        "expected_rows": 2,
        "window_start_utc": "2026-10-13T10:00:00Z",
        "window_end_utc": "2026-10-13T10:30:00Z",
        "retrieved_at_utc": "2026-10-13T10:31:00Z",
    }
    receipt.update(changes)
    return path, spec, receipt


def encode(receipt):
    payload = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()
    return payload, hashlib.sha256(payload).hexdigest()


def run(path, spec, receipt, *, asof=None, pin=None, ack=True):
    payload, digest = encode(receipt)
    return inspect_historical_pit_archive(
        path, spec, receipt_bytes=payload,
        trusted_receipt_sha256=digest if pin is None else pin,
        as_of_utc=asof or datetime(2026, 10, 13, 10, 32, tzinfo=UTC),
        operator_ack=ack,
    )


def test_pinned_archive_asof_and_evidence_digest_are_deterministic(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    source = path.read_bytes()
    one = run(path, spec, receipt)
    two = run(path, spec, receipt)
    assert one == two
    assert one.rows_validated == 2
    assert one.zero_volume_rows == 1
    assert one.duration_minutes == 30
    assert one.max_claimed_availability_lag_seconds == 5
    assert one.dataset_sha256 == hashlib.sha256(source).hexdigest()
    assert len(one.receipt_sha256) == len(one.evidence_sha256) == 64
    assert one.result == "OFFLINE_PIT_LOCAL_CAUSALITY_PASS_SOURCE_UNATTESTED"
    assert path.read_bytes() == source
    for field in (
        "provider_authenticated", "acquisition_clock_independently_attested",
        "exchange_calendar_independently_verified",
        "contract_economics_verified", "historical_revisions_excluded",
        "point_in_time_market_truth_certified", "strategy_executed",
        "backtest_run", "profit_edge_proven", "broker_orders_authorized",
        "live_trading_authorized", "telegram_sent",
    ):
        assert getattr(one, field) is False


def test_receipt_pin_must_be_external_and_exact(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    with pytest.raises(HistoricalPitRefused, match="PIT_RECEIPT_PIN_MISMATCH"):
        run(path, spec, receipt, pin="a" * 64)
    for bogus in ("x", "", None, 123):
        payload, _digest = encode(receipt)
        with pytest.raises(HistoricalPitRefused, match="PIT_BOUND_RECEIPT"):
            inspect_historical_pit_archive(
                path, spec, receipt_bytes=payload,
                trusted_receipt_sha256=bogus,
                as_of_utc=START + timedelta(hours=1),
                operator_ack=True,
            )


@pytest.mark.parametrize(("change", "refusal"), [
    ({"provider_claim": "another_venue"}, "IDENTITY_MISMATCH"),
    ({"symbol": "ETHUSDT"}, "IDENTITY_MISMATCH"),
    ({"contract_kind": "inverse_perpetual"}, "UNVERIFIED_POLICY"),
    ({"capture_method": "provider_signed_receipt"}, "UNVERIFIED_POLICY"),
    ({"session_policy": "unverified"}, "UNVERIFIED_POLICY"),
    ({"availability_lag_seconds": 0}, "IDENTITY_MISMATCH"),
    ({"expected_rows": 3}, "WINDOW_OR_ACQUISITION"),
    ({"expected_rows": True}, "UNVERIFIED_POLICY"),
    ({"window_start_utc": "2026-10-13T10:01:00Z"}, "WINDOW_OR_ACQUISITION"),
    ({"window_end_utc": "2026-10-13T10:45:00Z"}, "WINDOW_OR_ACQUISITION"),
    ({"retrieved_at_utc": "2026-10-13T10:29:59Z"}, "WINDOW_OR_ACQUISITION"),
    ({"retrieved_at_utc": "2026-10-13T11:30:00Z"}, "WINDOW_OR_ACQUISITION"),
    ({"retrieved_at_utc": "2026-10-13T10:31:00"}, "CANONICAL_UTC"),
    ({"window_start_utc": "2026-10-13T13:00:00+03:00"}, "CANONICAL_UTC"),
])
def test_adversarial_claims_fail_before_acceptance(tmp_path, change, refusal):
    path, spec, receipt = scenario(tmp_path, **change)
    with pytest.raises(HistoricalPitRefused, match=refusal):
        run(path, spec, receipt)


def test_archive_received_after_decision_asof_is_unavailable(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    with pytest.raises(HistoricalPitRefused, match="WINDOW_OR_ACQUISITION"):
        run(path, spec, receipt, asof=START + timedelta(minutes=30, seconds=30))


def test_backdated_row_beyond_declared_archive_window_refused(tmp_path):
    raw = HEADER + ROW1 + (
        b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,"
        b"102,106,101,103,8\n"
    ) + (
        b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,"
        b"103,108,102,104,9\n"
    )
    path, spec, receipt = scenario(tmp_path, raw=raw)
    with pytest.raises(HistoricalPitRefused, match="EXPECTED_SAMPLE_COUNT"):
        run(path, spec, receipt)


def test_gaps_and_wrong_ohlc_use_existing_data_a1_guards(tmp_path):
    wrong = HEADER + ROW1 + (
        b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,"
        b"102,106,101,103,8\n"
    )
    path, spec, receipt = scenario(tmp_path, raw=wrong)
    with pytest.raises(HistoricalDataRefused, match="UNVERIFIED_BAR_GAP"):
        run(path, spec, receipt)
    bad = HEADER + ROW1.replace(b",100,105,99,102,0", b",100,105,108,102,0") + ROW2
    path, spec, receipt = scenario(tmp_path, raw=bad)
    with pytest.raises(HistoricalDataRefused, match="INVALID_MARKET_SAMPLE"):
        run(path, spec, receipt)


def test_receipt_duplicate_keys_and_float_and_unknown_fields(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    payload, _ = encode(receipt)
    for malformed in (
        payload.replace(b'"expected_rows":2', b'"expected_rows":2,"expected_rows":2'),
        payload.replace(b'"expected_rows":2', b'"expected_rows":2.0'),
        payload.replace(b'"expected_rows":2', b'"expected_rows":NaN'),
        payload.replace(b'"expected_rows":2', b'"unexpected":1,"expected_rows":2'),
    ):
        with pytest.raises(HistoricalPitRefused):
            inspect_historical_pit_archive(
                path, spec, receipt_bytes=malformed,
                trusted_receipt_sha256=hashlib.sha256(malformed).hexdigest(),
                as_of_utc=START + timedelta(hours=1), operator_ack=True,
            )


def test_unaligned_closed_candles_refused_even_if_contiguous(tmp_path):
    row1 = b"2026-10-13T10:01:00Z,2026-10-13T10:16:00Z,100,105,99,102,0\n"
    row2 = b"2026-10-13T10:16:00Z,2026-10-13T10:31:00Z,102,106,101,103,8\n"
    path, spec, receipt = scenario(
        tmp_path, raw=HEADER+row1+row2,
        window_start_utc="2026-10-13T10:01:00Z",
        window_end_utc="2026-10-13T10:31:00Z",
        retrieved_at_utc="2026-10-13T10:32:00Z",
    )
    with pytest.raises(HistoricalPitRefused, match="UNALIGNED"):
        run(path, spec, receipt)


def test_tampered_csv_refused_by_original_loader(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    path.write_bytes(HEADER + ROW1 + ROW2 + b"\n")
    with pytest.raises(HistoricalDataRefused, match="SOURCE_HASH_MISMATCH"):
        run(path, spec, receipt)


def test_no_network_no_orders_and_explicit_nonproduction_ack(tmp_path, monkeypatch):
    path, spec, receipt = scenario(tmp_path)
    with pytest.raises(HistoricalPitRefused, match="NONPRODUCTION_ACK"):
        run(path, spec, receipt, ack=False)
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(HistoricalPitRefused, match="NONPRODUCTION_ACK"):
        run(path, spec, receipt)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(HistoricalPitRefused, match="NONPRODUCTION_ACK"):
        run(path, spec, receipt)


def test_symlink_and_relative_path_do_not_bypass_file_boundary(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    alias = tmp_path / "linked.csv"
    alias.symlink_to(path)
    with pytest.raises(HistoricalPitRefused, match="NON_SYMLINK"):
        run(alias, spec, receipt)
    with pytest.raises(HistoricalPitRefused, match="NON_SYMLINK"):
        run(Path("file.csv"), spec, receipt)


def test_forex_tick_mark_and_lookahead_are_not_silently_supported(tmp_path):
    path, spec, receipt = scenario(tmp_path)
    base = spec.feed
    for market, event, basis, volume in (
        (Market.FOREX, base.event, base.price_basis, base.volume_semantics),
        (Market.CRYPTO, CoreEventType.QUOTE_TICK, PriceBasis.BID_ASK,
         VolumeSemantics.UNKNOWN),
        (Market.CRYPTO, base.event, PriceBasis.MARK, base.volume_semantics),
    ):
        adjusted = FeedDefinition(
            base.feed_id, Instrument(
                market, base.instrument.provider, base.instrument.symbol,
                "UTC", base.instrument.quote_currency,
            ),
            base.timeframe, event, base.origin, base.source_ref, basis, volume,
            max_latency_seconds=120,
        )
        with pytest.raises(HistoricalPitRefused, match="CRYPTO_TRADE_CANDLES"):
            run(path, HistoricalFileSpec(adjusted, spec.expected_sha256, 5), receipt)
