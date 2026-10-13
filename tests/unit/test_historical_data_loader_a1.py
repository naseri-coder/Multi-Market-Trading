"""DATA-A1 genuine CSV and Parquet decoding, strict replay/identity checks."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import CoreBinding, CoreEventType, DataOrigin
from naseri_markets.historical_data_loader_a1 import (
    HistoricalDataRefused,
    HistoricalFileSpec,
    validate_historical_file,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition,
    OfflineMarketDataEngine,
    PacketStatus,
    PriceBasis,
    VolumeSemantics,
)

BEGIN = datetime(2026, 10, 13, 10, tzinfo=UTC)


def _bar_csv() -> bytes:
    return (
        b"open_at,close_at,open,high,low,close,volume\n"
        b"2026-10-13T10:00:00+00:00,2026-10-13T10:15:00+00:00,100,102,98,100,10\n"
        b"2026-10-13T10:15:00+00:00,2026-10-13T10:30:00+00:00,100,108,99,106,12\n"
    )


def _feed(data: bytes, *, event=CoreEventType.CLOSED_CANDLE,
          market=Market.CRYPTO, basis=PriceBasis.TRADE,
          volume=VolumeSemantics.TRADED) -> FeedDefinition:
    return FeedDefinition(
        "csv_replay_1",
        Instrument(market, "operator_declared_source", "ABCUSD", "UTC", "USD"),
        "15m", event, DataOrigin.REPLAY,
        "hist_" + hashlib.sha256(data).hexdigest()[:40],
        basis if event is CoreEventType.CLOSED_CANDLE else PriceBasis.BID_ASK,
        volume if event is CoreEventType.CLOSED_CANDLE else VolumeSemantics.UNKNOWN,
    )


def _source(tmp_path: Path, raw: bytes, ext: str = ".csv") -> Path:
    path = tmp_path / ("history" + ext)
    path.write_bytes(raw)
    return path


def _spec(raw: bytes, **kwargs) -> HistoricalFileSpec:
    return HistoricalFileSpec(_feed(raw, **kwargs), hashlib.sha256(raw).hexdigest())


def test_csv_genuine_decode_into_stage5_closed_market_events(tmp_path: Path) -> None:
    raw = _bar_csv()
    f = _source(tmp_path, raw)
    spec = _spec(raw)
    approval = validate_historical_file(f, spec)
    report = approval.report
    assert report.rows_validated == 2
    assert report.first_observed_at == BEGIN + timedelta(minutes=15)
    assert report.last_observed_at == BEGIN + timedelta(minutes=30)
    assert report.sha256 == hashlib.sha256(raw).hexdigest()
    assert report.origin is DataOrigin.REPLAY
    assert not report.provider_authenticated
    assert not report.forward_ready
    assert not report.strategy_executed
    assert not report.telegram_sent
    assert not report.broker_order_sent
    engine = OfflineMarketDataEngine(enabled=True)
    engine.register_feed(spec.feed)
    fixture = OfflineContractFixture()
    binding = CoreBinding("instance_1", "binding_1", spec.feed.instrument, "15m")
    engine.subscribe(spec.feed.feed_id, fixture.manifest, binding)
    events = [engine.ingest(packet) for packet in approval.packets()]
    assert events[0].status is PacketStatus.WARMING
    assert events[1].status is PacketStatus.ACCEPTED
    assert len(events[1].deliveries) == 1
    event = events[1].deliveries[0].event
    assert event.origin is DataOrigin.REPLAY
    assert event.candles[-1].close == D(106)
    assert event.candles[-1].volume == D(12)


def test_csv_ticks_have_bid_and_ask_without_bar_gap_rule(tmp_path: Path) -> None:
    raw = (
        b"occurred_at,bid,ask\n"
        b"2026-10-13T10:00:00+00:00,100,101\n"
        b"2026-10-13T10:00:02+00:00,100.5,101.25\n"
    )
    spec = _spec(raw, event=CoreEventType.QUOTE_TICK)
    approval = validate_historical_file(_source(tmp_path, raw), spec)
    packets = list(approval.packets())
    assert len(packets) == 2
    assert packets[0].tick.bid == D(100)
    assert packets[1].tick.ask == D("101.25")
    assert packets[0].candle is None
    assert packets[1].observed_at == BEGIN + timedelta(seconds=2)


def test_forex_tick_volume_not_traded_volume(tmp_path: Path) -> None:
    raw = (
        b"open_at,close_at,open,high,low,close,tick_volume\n"
        b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,1.1,1.2,1.0,1.15,72\n"
    )
    spec = _spec(raw, market=Market.FOREX, basis=PriceBasis.BID,
                 volume=VolumeSemantics.TICK_COUNT)
    p = list(validate_historical_file(_source(tmp_path, raw), spec).packets())
    assert p[0].candle.volume == D(72)
    assert spec.feed.volume_semantics is VolumeSemantics.TICK_COUNT


@pytest.mark.parametrize(("payload", "reason"), [
    (_bar_csv().replace(
        b"2026-10-13T10:15:00+00:00,2026-10-13T10:30:00+00:00,100,108",
        b"2026-10-13T10:20:00+00:00,2026-10-13T10:30:00+00:00,100,108"),
     "BAR_TIMEFRAME_MISMATCH"),
    (_bar_csv().replace(b"2026-10-13T10:15:00+00:00,100,108",
                        b"2026-10-13T10:15:00+00:00,100,108")
     .replace(b"2026-10-13T10:30:00+00:00,100,108",
              b"2026-10-13T10:45:00+00:00,100,108"),
     "BAR_TIMEFRAME_MISMATCH"),
    (_bar_csv().replace(b"2026-10-13T10:15:00+00:00,100,108",
                        b"2026-10-13T10:15:00+00:00,100,108")
     .replace(b",100,108,99,106,12", b",100,108,99,106,-1"),
     "INVALID_NUMERIC_VALUE"),
    (_bar_csv().replace(b"100,102,98,100,10", b"100,102,105,100,10"),
     "INVALID_MARKET_SAMPLE"),
    (_bar_csv().replace(b"10:00:00+00:00", b"10:00:00"),
     "EXPLICIT_TIMEZONE_REQUIRED"),
    (_bar_csv().replace(b"open_at,close_at", b"close_at,open_at"),
     "CSV_EXACT_COLUMN_ORDER_REQUIRED"),
    (_bar_csv().replace(b"100,108,99,106,12", b"100,108,99,106"),
     "CSV_ROW_SHAPE_MISMATCH"),
])
def test_malformed_csv_refused_without_approval(tmp_path: Path,
                                                 payload: bytes, reason: str) -> None:
    with pytest.raises(HistoricalDataRefused, match=reason):
        validate_historical_file(_source(tmp_path, payload), _spec(payload))


def test_duplicate_timestamp_and_unverified_session_gap_refused(tmp_path: Path) -> None:
    raw = _bar_csv()
    first = raw.splitlines(keepends=True)
    duplicate = first[0] + first[1] + first[1]
    with pytest.raises(HistoricalDataRefused, match="OUT_OF_ORDER_OR_DUPLICATE_TIME"):
        validate_historical_file(_source(tmp_path, duplicate), _spec(duplicate))
    gap = (
        first[0] + first[1]
        + b"2026-10-13T10:30:00+00:00,2026-10-13T10:45:00+00:00,100,108,99,106,12\n"
    )
    with pytest.raises(HistoricalDataRefused, match="UNVERIFIED_BAR_GAP_OR_OVERLAP"):
        validate_historical_file(_source(tmp_path, gap), _spec(gap))


def test_sha256_pin_required_and_mutation_revokes_replay(tmp_path: Path) -> None:
    raw = _bar_csv()
    file = _source(tmp_path, raw)
    wrong = hashlib.sha256(b"not the file").hexdigest()
    with pytest.raises(HistoricalDataRefused, match="SOURCE_HASH_MISMATCH"):
        validate_historical_file(file, HistoricalFileSpec(
            _feed(b"not the file"), wrong))
    approved = validate_historical_file(file, _spec(raw))
    file.write_bytes(raw + b"\n")
    with pytest.raises(HistoricalDataRefused, match="FILE_CHANGED_SINCE_PREFLIGHT"):
        list(approved.packets())


def test_no_symlinks_and_no_unsupported_extensions(tmp_path: Path) -> None:
    raw = _bar_csv()
    real = _source(tmp_path, raw)
    sym = tmp_path / "linked.csv"
    sym.symlink_to(real)
    with pytest.raises(HistoricalDataRefused, match="INVALID_FILE_TYPE_OR_SIZE"):
        validate_historical_file(sym, _spec(raw))
    other = tmp_path / "bad.exe"
    other.write_bytes(raw)
    with pytest.raises(HistoricalDataRefused, match="CSV_OR_PARQUET_ONLY"):
        validate_historical_file(other, _spec(raw))


def test_replay_source_claim_not_silently_accepted(tmp_path: Path) -> None:
    raw = _bar_csv()
    feed = _feed(raw)
    forged_feed = FeedDefinition(
        feed.feed_id, feed.instrument, feed.timeframe, feed.event,
        feed.origin, "pretend_authenticated_provider", feed.price_basis,
        feed.volume_semantics)
    with pytest.raises(HistoricalDataRefused, match="SOURCE_REF_MUST_MATCH_FILE_DIGEST"):
        HistoricalFileSpec(forged_feed, hashlib.sha256(raw).hexdigest())


def test_maximum_rows_fail_closed(tmp_path: Path) -> None:
    raw = _bar_csv()
    with pytest.raises(HistoricalDataRefused, match="ROW_LIMIT_EXCEEDED"):
        validate_historical_file(_source(tmp_path, raw), HistoricalFileSpec(
            _feed(raw), hashlib.sha256(raw).hexdigest(), max_rows=1))


def _write_real_parquet(tmp_path: Path, *, tick: bool = False) -> tuple[Path, bytes]:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    values = {
        "open_at": ["2026-10-13T10:00:00Z", "2026-10-13T10:15:00Z"],
        "close_at": ["2026-10-13T10:15:00Z", "2026-10-13T10:30:00Z"],
        "open": ["100", "100"],
        "high": ["102", "108"],
        "low": ["98", "99"],
        "close": ["100", "106"],
        "volume": ["10", "12"],
    } if not tick else {
        "occurred_at": ["2026-10-13T10:00:00Z", "2026-10-13T10:00:02Z"],
        "bid": ["100", "101"], "ask": ["101", "102"],
    }
    table = pa.table({
        key: pa.array(value, type=pa.string()) for key, value in values.items()
    })
    path = tmp_path / "history.parquet"
    pq.write_table(table, path, row_group_size=1)
    return path, path.read_bytes()


def test_real_parquet_row_groups_decode_and_match_csv_semantics(tmp_path: Path) -> None:
    path, raw = _write_real_parquet(tmp_path)
    approved = validate_historical_file(path, _spec(raw))
    assert approved.report.rows_validated == 2
    assert approved.report.format == "parquet"
    packets = list(approved.packets())
    assert [p.candle.close for p in packets] == [D(100), D(106)]


def test_real_parquet_tick_decoding(tmp_path: Path) -> None:
    path, raw = _write_real_parquet(tmp_path, tick=True)
    approved = validate_historical_file(
        path, _spec(raw, event=CoreEventType.QUOTE_TICK))
    assert [p.tick.ask for p in approved.packets()] == [D(101), D(102)]


def test_parquet_rejects_wrong_data_shape(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "wrong.parquet"
    pq.write_table(pa.table({"unsafe": ["1"]}), path)
    raw = path.read_bytes()
    with pytest.raises(HistoricalDataRefused, match="PARQUET_EXACT_SCHEMA_REQUIRED"):
        validate_historical_file(path, _spec(raw))


def test_parquet_missing_dependency_fails_closed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "fake.parquet"
    path.write_bytes(b"PAR1some-unverified-binary-footerPAR1")
    # This refusal holds regardless of PyArrow availability: bad bytes never become data.
    with pytest.raises(HistoricalDataRefused):
        validate_historical_file(path, _spec(path.read_bytes()))
