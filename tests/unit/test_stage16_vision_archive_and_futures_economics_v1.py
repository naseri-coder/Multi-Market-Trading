"""Stage16: actual standard-library ZIP, checksum, DATA-A1 and modeled futures cashflows."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from naseri_markets.binance_vision_archive_stage16_v1 import (
    VisionArchiveRefused, prepare_vision_monthly_um_15m,
    select_reviewed_brooks_window,
)
from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import CoreEventType, DataOrigin
from naseri_markets.futures_economic_scenario_stage16_v1 import (
    FundingMarkScenario, FuturesScenarioRefused,
    model_linear_usdm_research_scenario,
)
from naseri_markets.historical_data_loader_a1 import HistoricalFileSpec
from naseri_markets.historical_pit_quality_stage12_v1 import (
    inspect_historical_pit_archive,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, PriceBasis, VolumeSemantics,
)
from naseri_markets.real_brooks_historical_stage15_v1 import (
    review_real_brooks_history,
)


@pytest.fixture(autouse=True)
def safety_env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def zip_fixture(*, month=9, year=2026, mutate=None, name=None, header=False):
    first = datetime(year, month, 1, tzinfo=UTC)
    last = (datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12
            else datetime(year, month + 1, 1, tzinfo=UTC))
    count = int((last-first).total_seconds() / 900)
    rows = []
    if header:
        rows.append("open time,open,high,low,close,volume,close time,"
                    "quote asset volume,number of trades,taker buy base,"
                    "taker buy quote,ignore")
    for i in range(count):
        opened = int(first.timestamp()) * 1000 + i * 900000
        fields = [str(opened), "100", "101", "99", "100", "10",
                  str(opened + 899999), "1000", "10", "4", "400", "0"]
        if mutate and i == mutate[0]:
            fields[mutate[1]] = mutate[2]
        rows.append(",".join(fields))
    raw = ("\n".join(rows) + "\n").encode()
    filename = name or f"BTCUSDT-15m-{year}-{month:02d}.zip"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename[:-4]+".csv", raw)
    blob = out.getvalue()
    chk = (hashlib.sha256(blob).hexdigest() + "  " + filename + "\n").encode()
    return blob, chk, count


def run_archive(blob, chk, *, month=9, year=2026, ack=True):
    return prepare_vision_monthly_um_15m(
        blob, chk, expected_zip_sha256=hashlib.sha256(blob).hexdigest(),
        expected_checksum_sha256=hashlib.sha256(chk).hexdigest(),
        year=year, month=month,
        retrieved_at_utc=datetime(2026, 10, 3, 9, tzinfo=UTC),
        operator_ack=ack,
    )


def make_spec(csv_sha):
    feed = FeedDefinition(
        "stage16_binance_vision_um_btcusdt",
        Instrument(Market.CRYPTO, "binance_replay", "BTCUSDT", "UTC", "USDT"),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + csv_sha[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120,
    )
    return HistoricalFileSpec(feed, csv_sha, 5)


def test_offline_archive_checksum_whole_month_and_stage12_pit(tmp_path):
    blob, check, expected = zip_fixture()
    prepared = run_archive(blob, check)
    assert prepared.count == expected == 2880
    assert prepared.csv_sha256 == hashlib.sha256(prepared.canonical_csv_bytes).hexdigest()
    assert prepared.receipt_sha256 == hashlib.sha256(prepared.stage12_receipt_bytes).hexdigest()
    assert prepared.canonical_csv_bytes.startswith(
        b"open_at,close_at,open,high,low,close,volume\n"
    )
    assert prepared.first_open_utc == "2026-09-01T00:00:00Z"
    assert prepared.last_close_utc == "2026-10-01T00:00:00Z"
    assert "/futures/um/monthly/" in prepared.official_url_claim
    assert not prepared.independent_source_authenticated
    assert not prepared.independent_retrieval_clock_attested
    assert not prepared.economic_backtest_run
    assert not prepared.trading_authorized
    full = tmp_path / "complete-month.csv"
    full.write_bytes(prepared.canonical_csv_bytes)
    report = inspect_historical_pit_archive(
        full, make_spec(prepared.csv_sha256),
        receipt_bytes=prepared.stage12_receipt_bytes,
        trusted_receipt_sha256=prepared.receipt_sha256,
        as_of_utc=datetime(2026, 10, 3, 10, tzinfo=UTC),
        operator_ack=True,
    )
    assert report.rows_validated == expected
    assert not report.provider_authenticated
    assert not report.point_in_time_market_truth_certified
    assert full.read_bytes() == prepared.canonical_csv_bytes


def test_brooks_bounded_window_preserves_lineage_and_runs_real_engine(tmp_path):
    blob, check, _ = zip_fixture()
    prepared = run_archive(blob, check)
    cut = select_reviewed_brooks_window(
        prepared, start_bar_index=0, count=72, operator_ack=True,
    )
    assert cut.parent_monthly_csv_sha256 == prepared.csv_sha256
    assert cut.parent_official_zip_sha256 == prepared.zip_sha256
    assert cut.count == 72
    assert cut.start_bar_index == 0
    assert not cut.selected_without_seeing_outcomes_attested
    trimmed = tmp_path / "reviewed-72-bars.csv"
    trimmed.write_bytes(cut.canonical_csv_bytes)
    report = inspect_historical_pit_archive(
        trimmed, make_spec(cut.csv_sha256),
        receipt_bytes=cut.stage12_receipt_bytes,
        trusted_receipt_sha256=cut.receipt_sha256,
        as_of_utc=datetime(2026, 10, 3, 10, tzinfo=UTC),
        operator_ack=True,
    )
    assert report.rows_validated == 72
    # This is the actual frozen Brooks V5 engine, not an isolated fake signal.
    root = __import__("pathlib").Path.cwd() / "production_source"
    output = review_real_brooks_history(
        trimmed, make_spec(cut.csv_sha256),
        receipt_bytes=cut.stage12_receipt_bytes,
        trusted_receipt_sha256=cut.receipt_sha256,
        archive_as_of_utc=datetime(2026, 10, 3, 10, tzinfo=UTC),
        legacy_source=root,
        evaluation_cutoffs_utc=(
            datetime(2026, 9, 1, 15, tzinfo=UTC),
            datetime(2026, 9, 1, 18, tzinfo=UTC),
        ),
        operator_ack=True,
    )
    assert output["actual_brooks_engine_evaluated"]
    assert output["evaluation_count"] == 2
    assert not output["actual_exchange_data_authenticated"]
    assert not output["economic_pnl_calculated"]
    assert not output["trading_edge_proven"]
    assert not (tmp_path / "brooks_stage10_paper.sqlite").exists()


def test_archive_full_month_with_approved_header_is_supported():
    blob, check, _ = zip_fixture(header=True)
    x = run_archive(blob, check)
    assert x.count == 2880


@pytest.mark.parametrize("mutation,code", [
    ((3, 0, "bad"), "INVALID_EXCHANGE_INTEGER"),
    ((3, 0, "1788221700000"), "GRID_OR_CLOSE"),
    ((3, 6, "1788221700000"), "GRID_OR_CLOSE"),
    ((3, 1, "NaN"), "NONCANONICAL_EXCHANGE_DECIMAL"),
    ((3, 2, "95"), "OHLC_INCONSISTENCY"),
    ((3, 9, "11"), "OHLC_INCONSISTENCY"),
    ((3, 8, "-1"), "INVALID_EXCHANGE_INTEGER"),
])
def test_kline_header_clock_quantity_and_ohlc_fail_closed(mutation, code):
    blob, check, _ = zip_fixture(mutate=mutation)
    with pytest.raises(VisionArchiveRefused, match=code):
        run_archive(blob, check)


def test_pinned_checksum_and_archive_mismatch_refused():
    blob, chk, _ = zip_fixture()
    with pytest.raises(VisionArchiveRefused, match="CHECKSUM_PIN_MISMATCH"):
        prepare_vision_monthly_um_15m(
            blob, chk, expected_zip_sha256="0"*64,
            expected_checksum_sha256=hashlib.sha256(chk).hexdigest(),
            year=2026, month=9,
            retrieved_at_utc=datetime(2026, 10, 3, tzinfo=UTC),
            operator_ack=True,
        )
    forged = b"0"*64 + chk[64:]
    with pytest.raises(VisionArchiveRefused, match="CHECKSUM_PIN_MISMATCH"):
        run_archive(blob, forged)


def test_bad_archive_member_and_cut_window_are_never_silent():
    blob, chk, count = zip_fixture(name="traversal.zip")
    assert count == 2880
    with pytest.raises(VisionArchiveRefused, match="OFFICIAL_NAMED_CHECKSUM"):
        run_archive(blob, chk)
    good_blob, good_chk, _ = zip_fixture()
    prepared = run_archive(good_blob, good_chk)
    for start, size in ((0, 59), (0, 513), (2870, 72), (-1, 72), (True, 72)):
        with pytest.raises(VisionArchiveRefused, match="STAGE15_WINDOW_BOUNDS"):
            select_reviewed_brooks_window(
                prepared, start_bar_index=start, count=size, operator_ack=True,
            )
    with pytest.raises(VisionArchiveRefused, match="PARENT_MONTHLY_CSV_DRIFT"):
        select_reviewed_brooks_window(
            replace(prepared, canonical_csv_bytes=prepared.canonical_csv_bytes+b"x"),
            start_bar_index=0, count=72, operator_ack=True,
        )


def test_no_archive_network_calls_or_production_bypass(monkeypatch):
    blob, check, _ = zip_fixture()
    with pytest.raises(VisionArchiveRefused, match="NONPRODUCTION"):
        run_archive(blob, check, ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(VisionArchiveRefused, match="NONPRODUCTION"):
        run_archive(blob, check)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(VisionArchiveRefused, match="NONPRODUCTION"):
        run_archive(blob, check)


def economics():
    return {
        "schema_version": 1, "provider_claim": "binance_usdm_operator_claim",
        "symbol": "BTCUSDT", "contract_kind": "linear_perpetual",
        "settle_currency": "USDT", "base_units_per_contract": "1",
        "price_tick": "0.1", "quantity_step": "0.001",
        "taker_fee_fraction": "0.001", "worst_slippage_fraction": "0.002",
        "maintenance_margin_fraction": "0.05",
        "source_metadata_sha256": "a"*64,
    }


def encoded_economics(data=None):
    blob = json.dumps(economics() if data is None else data,
                      sort_keys=True, separators=(",", ":")).encode()
    return blob, hashlib.sha256(blob).hexdigest()


def model(*, data=None, events=None, side="long", ack=True):
    payload, sha = encoded_economics(data)
    return model_linear_usdm_research_scenario(
        payload, expected_metadata_sha256=sha,
        side=side, quantity_contracts="1.000", entry_price="100.0",
        exit_price="110.0",
        entry_at=datetime(2026, 9, 1, tzinfo=UTC),
        exit_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        funding_mark_events=(
            FundingMarkScenario(
                datetime(2026, 9, 1, 8, tzinfo=UTC), "0.001", "105",
            ),
        ) if events is None else events,
        operator_ack=ack,
    )


def test_explicit_notional_quote_cashflows_and_funding_sign():
    long = model()
    short = model(side="short")
    assert D(long["gross_quote"]) == D("10")
    assert D(long["taker_fees_quote"]) == D("0.21")
    assert D(long["adverse_slippage_quote"]) == D("0.42")
    assert D(long["funding_cashflow_quote"]) == D("-0.105")
    assert D(long["net_scenario_quote"]) == D("9.265")
    assert D(short["gross_quote"]) == D("-10")
    assert D(short["funding_cashflow_quote"]) == D("0.105")
    assert long["evidence_sha256"] == model()["evidence_sha256"]
    for flag in ("funding_history_completeness_attested",
                 "historical_mark_prices_authenticated",
                 "contract_metadata_authenticated",
                 "liquidation_margin_model_complete",
                 "connected_to_real_brooks_trades",
                 "backtest_profitability_proven",
                 "live_trading_authorized"):
        assert long[flag] is False


@pytest.mark.parametrize("field,bad", [
    ("price_tick", "0"), ("quantity_step", "NaN"),
    ("taker_fee_fraction", "1"), ("worst_slippage_fraction", "-1"),
    ("provider_claim", "kucoin"), ("settle_currency", "BTC"),
])
def test_economic_metadata_scope_and_unsafe_values_refused(field, bad):
    with pytest.raises(FuturesScenarioRefused):
        model(data={**economics(), field: bad})


def test_pinned_economic_data_and_funding_order_integrity():
    base, sha = encoded_economics()
    with pytest.raises(FuturesScenarioRefused, match="METADATA_DIGEST_DRIFT"):
        model_linear_usdm_research_scenario(
            base, expected_metadata_sha256="b"*64,
            side="long", quantity_contracts="1", entry_price="100",
            exit_price="110",
            entry_at=datetime(2026, 9, 1, tzinfo=UTC),
            exit_at=datetime(2026, 9, 2, tzinfo=UTC),
            funding_mark_events=(), operator_ack=True,
        )
    duplicated = (
        FundingMarkScenario(datetime(2026, 9, 1, 8, tzinfo=UTC), "0.001", "105"),
    ) * 2
    with pytest.raises(FuturesScenarioRefused, match="FUNDING_ORDER"):
        model(events=duplicated)


def test_economics_rejects_production_and_no_ack(monkeypatch):
    with pytest.raises(FuturesScenarioRefused, match="RESEARCH_ACK"):
        model(ack=False)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(FuturesScenarioRefused, match="RESEARCH_ACK"):
        model()
