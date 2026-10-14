"""DATA-A1 operator file intake: actual bytes, Stage-5 PAPER lane, no execution."""
from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import CoreEventType
from naseri_markets.data_a1_file_intake import inspect_historical_for_paper
from naseri_markets.data_a1_intake_cli import main
from naseri_markets.historical_data_loader_a1 import HistoricalDataRefused
from naseri_markets.market_data_engine_v1 import PriceBasis, VolumeSemantics

START = datetime(2026, 10, 13, 10, tzinfo=UTC)
HEADER = b"open_at,close_at,open,high,low,close,volume\n"
BAR_1 = b"2026-10-13T10:00:00Z,2026-10-13T10:15:00Z,100,102,98,101,0\n"
BAR_2 = b"2026-10-13T10:15:00Z,2026-10-13T10:30:00Z,101,104,99,103,12\n"
TICK_HEADER = b"occurred_at,bid,ask\n"
TICK_1 = b"2026-10-13T10:00:00Z,100.5,101\n"
TICK_2 = b"2026-10-13T10:00:05Z,101,102\n"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _file(tmp_path: Path, raw: bytes, ext: str = ".csv") -> Path:
    path = tmp_path / ("market-history" + ext)
    path.write_bytes(raw)
    return path


def _args(path: Path, **changes):
    opts = dict(
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        market=Market.CRYPTO, provider="operator_claimed_exchange",
        symbol="ABCUSDT", timezone="UTC", quote_currency="USDT",
        timeframe="15m", event=CoreEventType.CLOSED_CANDLE,
        price_basis=PriceBasis.TRADE,
        volume_semantics=VolumeSemantics.TRADED,
        operator_ack=True,
    )
    opts.update(changes)
    return opts


def test_actual_csv_file_readonly_quality_and_paper_input(tmp_path):
    data = HEADER + BAR_1 + BAR_2
    path = _file(tmp_path, data)
    original_stat = path.stat()
    report = inspect_historical_for_paper(path, **_args(path))
    assert report.status == "DATA_A1_FILE_VALIDATED_OFFLINE_PAPER_INPUT_ONLY"
    assert report.format == "csv"
    assert report.rows_validated == report.paper_core_inputs_validated == 2
    assert report.market == "crypto"
    assert report.symbol == "ABCUSDT"
    assert report.timeframe == "15m"
    assert report.provider_claim == "operator_claimed_exchange"
    assert report.sha256 == hashlib.sha256(data).hexdigest()
    assert report.source_ref == "hist_" + report.sha256[:40]
    assert report.first_observed_at == START + timedelta(minutes=15)
    assert report.last_observed_at == START + timedelta(minutes=30)
    assert report.first_available_at == report.first_observed_at
    assert report.last_available_at == report.last_observed_at
    assert report.lowest_observed_price == "98"
    assert report.highest_observed_price == "104"
    assert report.zero_volume_rows == 1
    assert report.widest_bid_ask_spread is None
    assert "UNVERIFIED" in report.quality_status
    assert not report.source_authenticated
    assert not report.point_in_time_feed_certified
    assert not report.exchange_calendar_verified
    assert not report.paper_strategy_executed
    assert not report.broker_order_sent
    assert not report.telegram_sent
    assert not report.worker_execution_authorized
    assert path.read_bytes() == data
    assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert sorted(x.name for x in tmp_path.iterdir()) == [path.name]


def test_csv_bid_ask_spread_and_lag_without_lookahead(tmp_path):
    raw = TICK_HEADER + TICK_1 + TICK_2
    path = _file(tmp_path, raw)
    info = inspect_historical_for_paper(
        path, **_args(path, event=CoreEventType.QUOTE_TICK,
                      price_basis=PriceBasis.BID_ASK,
                      volume_semantics=VolumeSemantics.UNKNOWN,
                      availability_lag_seconds=7),
    )
    assert info.rows_validated == info.paper_core_inputs_validated == 2
    assert info.lowest_observed_price == "100.5"
    assert info.highest_observed_price == "102"
    assert info.zero_volume_rows == 0
    assert info.widest_bid_ask_spread == "1"
    assert info.first_available_at == START + timedelta(seconds=7)
    assert info.last_available_at == START + timedelta(seconds=12)


def test_actual_parquet_row_groups_are_decoded_and_paper_delivered(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    values = {
        "open_at": ["2026-10-13T10:00:00Z", "2026-10-13T10:15:00Z"],
        "close_at": ["2026-10-13T10:15:00Z", "2026-10-13T10:30:00Z"],
        "open": ["100", "101"], "high": ["102", "104"],
        "low": ["98", "99"], "close": ["101", "103"], "volume": ["0", "12"],
    }
    path = tmp_path / "market-history.parquet"
    pq.write_table(pa.table({
        name: pa.array(val, type=pa.string()) for name, val in values.items()
    }), path, row_group_size=1)
    snapshot = path.read_bytes()
    report = inspect_historical_for_paper(path, **_args(path))
    assert report.format == "parquet"
    assert report.rows_validated == 2
    assert report.paper_core_inputs_validated == 2
    assert report.zero_volume_rows == 1
    assert path.read_bytes() == snapshot


def test_large_csv_is_streamed_without_unbounded_core_history(tmp_path):
    rows = [HEADER]
    when = START
    for number in range(260):
        end = when + timedelta(minutes=15)
        rows.append(
            f"{when.isoformat()},{end.isoformat()},100,101,99,100,{number}\n".encode()
        )
        when = end
    path = _file(tmp_path, b"".join(rows))
    report = inspect_historical_for_paper(path, **_args(path))
    assert report.rows_validated == report.paper_core_inputs_validated == 260
    assert report.zero_volume_rows == 1


@pytest.mark.parametrize(("raw", "reason"), [
    (HEADER + BAR_1 + BAR_1, "OUT_OF_ORDER_OR_DUPLICATE_TIME"),
    (HEADER + BAR_1 + b"2026-10-13T10:30:00Z,2026-10-13T10:45:00Z,101,104,99,103,12\n",
     "UNVERIFIED_BAR_GAP_OR_OVERLAP"),
    (HEADER + BAR_1.replace(b",100,102,98,101,0", b",100,102,105,101,0"),
     "INVALID_MARKET_SAMPLE"),
    (HEADER + BAR_1.replace(b",100,102,98,101,0", b",100,102,98,101,NaN"),
     "INVALID_NUMERIC_VALUE"),
    (HEADER + BAR_1.replace(b",100,102,98,101,0", b",100,102,98,101,=1+2"),
     "INVALID_NUMERIC_VALUE"),
    (HEADER.replace(b"open_at,close_at", b"close_at,open_at") + BAR_1,
     "CSV_EXACT_COLUMN_ORDER_REQUIRED"),
])
def test_adversarial_history_never_creates_paper_delivery(tmp_path, raw, reason):
    path = _file(tmp_path, raw)
    with pytest.raises(HistoricalDataRefused, match=reason):
        inspect_historical_for_paper(path, **_args(path))


def test_sha_mismatch_blocks_before_decoding(tmp_path):
    path = _file(tmp_path, HEADER + BAR_1)
    with pytest.raises(HistoricalDataRefused, match="SOURCE_HASH_MISMATCH"):
        inspect_historical_for_paper(path, **_args(path, sha256="f" * 64))


def test_max_rows_and_bad_lag_denied(tmp_path):
    path = _file(tmp_path, HEADER + BAR_1 + BAR_2)
    with pytest.raises(HistoricalDataRefused, match="ROW_LIMIT_EXCEEDED"):
        inspect_historical_for_paper(path, **_args(path, max_rows=1))
    with pytest.raises(HistoricalDataRefused, match="INVALID_REPLAY_AVAILABILITY_LAG"):
        inspect_historical_for_paper(path, **_args(path, availability_lag_seconds=121))


def test_relative_file_path_or_symlink_denied(tmp_path):
    path = _file(tmp_path, HEADER + BAR_1)
    with pytest.raises(HistoricalDataRefused, match="DATA_A1_ABSOLUTE_FILE_PATH_REQUIRED"):
        inspect_historical_for_paper(Path("history.csv"), **_args(path))
    alias = tmp_path / "alias.csv"
    alias.symlink_to(path)
    with pytest.raises(HistoricalDataRefused, match="INVALID_FILE_TYPE_OR_SIZE"):
        inspect_historical_for_paper(alias, **_args(path))


def test_no_ack_no_nonproduction_no_production_bypass(tmp_path, monkeypatch):
    path = _file(tmp_path, HEADER + BAR_1)
    with pytest.raises(HistoricalDataRefused, match="ACK_REQUIRED"):
        inspect_historical_for_paper(path, **_args(path, operator_ack=False))
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(HistoricalDataRefused, match="ACK_REQUIRED"):
        inspect_historical_for_paper(path, **_args(path))
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(HistoricalDataRefused, match="ACK_REQUIRED"):
        inspect_historical_for_paper(path, **_args(path))


def _cli_args(path):
    return [
        "--file", str(path),
        "--sha256", hashlib.sha256(path.read_bytes()).hexdigest(),
        "--market", "crypto", "--provider", "operator_claimed_exchange",
        "--symbol", "ABCUSDT", "--timezone", "UTC",
        "--quote-currency", "USDT", "--timeframe", "15m",
        "--event", "closed_candle", "--price-basis", "trade",
        "--volume-semantics", "traded", "--ack-offline-paper-only",
    ]


def test_operator_cli_prints_only_quality_report_not_rows(tmp_path, capsys):
    path = _file(tmp_path, HEADER + BAR_1 + BAR_2)
    assert main(_cli_args(path)) == 0
    out = capsys.readouterr()
    obj = json.loads(out.out)
    assert out.err == ""
    assert obj["paper_core_inputs_validated"] == 2
    assert obj["source_authenticated"] is False
    assert "10:15:00+00:00" in obj["first_observed_at"]
    assert str(path) not in out.out
    assert "open_at,close_at" not in out.out


def test_operator_cli_refuses_invalid_file_without_data_leak(tmp_path, capsys):
    path = _file(tmp_path, HEADER + BAR_1)
    args = _cli_args(path)
    args[args.index("--sha256") + 1] = "0" * 64
    assert main(args) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "DATA_A1_LOCAL_INTAKE_REFUSED" in output.err
    assert str(path) not in output.err


def test_no_subprocess_no_network_and_no_strategy_launch(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("DATA_A1_MUST_NOT_LAUNCH_NETWORK_OR_WORKER")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    path = _file(tmp_path, HEADER + BAR_1 + BAR_2)
    report = inspect_historical_for_paper(path, **_args(path))
    assert report.paper_core_inputs_validated == 2
    assert not report.paper_strategy_executed
    assert not report.broker_order_sent
