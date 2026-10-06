"""MARC research backtest causality and execution-assumption tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.modules.market_data.entities import Candle
from app.modules.marc_core.entities import MARCCandidate
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.data import (
    fetch_binance_futures_klines,
    resample_15m_to_30m,
)
from research_layer.marc_backtest.engine import (
    BacktestConfig,
    _simulate_trade,
)
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_backtest.report import build_validation_report

D = Decimal
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    index: int,
    *,
    open_price: str,
    high: str,
    low: str,
    close: str,
) -> Candle:
    start = BASE + timedelta(minutes=15 * index)
    return Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15) - timedelta(milliseconds=1),
        open=D(open_price),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D("1"),
    )


def _candidate(
    *,
    direction: str = "LONG",
    entry: str = "100",
    stop: str = "90",
    tp1: str = "110",
    tp2: str = "120",
) -> MARCCandidate:
    return MARCCandidate(
        source_signal_id="marc-test",
        symbol="BTCUSDT",
        timeframe="15m",
        direction=direction,
        entry_price=D(entry),
        stop_loss=D(stop),
        targets=(D(tp1), D(tp2)),
        exchange="binance",
        market_type="futures",
        setup_type="MARC_R1_MA99_REGIME_RECLAIM",
        market_snapshot_id="snapshot",
        market_snapshot_hash="hash",
        engine_version="marc-core-v0.1.0",
        rule_set_version="marc-r1-v0.1",
        configuration_version="marc-baseline-v0.1",
        confirmation_close_time=BASE,
        ma99=D("100"),
        atr14=D("10"),
        initial_risk_atr=D("1"),
        risk_fraction=D("0.005"),
        exit_model="TP1_1R_TP2_2R_RUNNER_CHANDELIER_22_3ATR",
        reasoning=("test",),
    )


def test_resample_15m_to_30m_is_utc_aligned_and_deterministic():
    source = (
        _candle(0, open_price="100", high="102", low="99", close="101"),
        _candle(1, open_price="101", high="103", low="100", close="102"),
        _candle(2, open_price="102", high="104", low="101", close="103"),
        _candle(3, open_price="103", high="105", low="102", close="104"),
    )

    result = resample_15m_to_30m(source)

    assert len(result) == 2
    assert result[0].open == D("100")
    assert result[0].high == D("103")
    assert result[0].low == D("99")
    assert result[0].close == D("102")
    assert result[0].volume == D("2")
    assert result[1].open_time.minute == 30


def test_same_bar_stop_and_target_is_resolved_stop_first():
    candles = (
        _candle(0, open_price="100", high="112", low="89", close="100"),
    )
    trade, exit_index = _simulate_trade(
        candles=candles,
        atr22=(None,),
        candidate=_candidate(),
        entry_index=0,
        last_index=0,
        config=BacktestConfig(),
        policy=MARCPolicy(),
    )

    assert exit_index == 0
    assert trade.terminal_reason == "STOP_FIRST_AMBIGUOUS"
    assert trade.gross_r == -1.0
    assert trade.tp1_hit is False


def test_hybrid_exit_uses_25_25_50_tranches_and_window_end_runner():
    candles = (
        _candle(0, open_price="100", high="111", low="95", close="109"),
        _candle(1, open_price="109", high="121", low="105", close="119"),
        _candle(2, open_price="119", high="126", low="115", close="125"),
    )
    trade, _ = _simulate_trade(
        candles=candles,
        atr22=(None, None, None),
        candidate=_candidate(),
        entry_index=0,
        last_index=2,
        config=BacktestConfig(),
        policy=MARCPolicy(),
    )

    assert [fill.reason for fill in trade.fills] == ["TP1", "TP2", "WINDOW_END"]
    assert [fill.fraction for fill in trade.fills] == [0.25, 0.25, 0.5]
    assert trade.gross_r == 2.0
    assert trade.base_net_r < trade.gross_r
    assert trade.stress_net_r < trade.base_net_r


@pytest.mark.asyncio
async def test_binance_downloader_normalizes_closed_rows_without_live_network():
    start = BASE
    end = BASE + timedelta(minutes=45)

    def row(index: int, price: str):
        open_time = int((BASE + timedelta(minutes=15 * index)).timestamp() * 1000)
        close_time = open_time + 15 * 60 * 1000 - 1
        return [
            open_time,
            price,
            str(D(price) + 1),
            str(D(price) - 1),
            price,
            "10",
            close_time,
        ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/klines"
        return httpx.Response(
            200,
            json=[row(0, "100"), row(1, "101"), row(2, "102")],
        )

    result = await fetch_binance_futures_klines(
        symbol="BTCUSDT",
        start=start,
        end=end,
        request_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    assert len(result) == 3
    assert result[0].open == D("100")
    assert result[-1].close == D("102")


def test_report_can_never_authorize_runtime_from_backtest_results():
    empty = BacktestWindowResult(
        symbol="BTCUSDT",
        timeframe="15m",
        start=BASE,
        end=BASE + timedelta(days=1),
        candidate_count=0,
        rejected_plan_count=0,
        rejection_reasons=(),
        trades=(),
    )

    report = build_validation_report(
        validation=(empty,),
        oos=(empty,),
        provenance={"source": "test"},
        protocol={"mode": "test"},
    )

    assert report["runtime_approval"] == "DENIED_BACKTEST_ONLY"
    assert report["research_classification"] == "INSUFFICIENT_OOS_SAMPLE"
