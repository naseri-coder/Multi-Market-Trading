"""Synthetic unit tests for the FM research contract."""

from __future__ import annotations

from decimal import Decimal

from research_layer.fm_backtest.data import Candle, resample_30m
from research_layer.fm_backtest.engine import FMPolicy, scan_fm

D = Decimal


def _c(index: int, o: str, h: str, l: str, c: str) -> Candle:
    return Candle(
        open_time_ms=index * 15 * 60 * 1000,
        open=D(o),
        high=D(h),
        low=D(l),
        close=D(c),
        volume=D("1"),
    )


def test_resample_30m_requires_complete_aligned_pairs():
    candles = (
        _c(0, "100", "101", "99", "100.5"),
        _c(1, "100.5", "102", "100", "101.5"),
        _c(2, "101.5", "103", "101", "102"),
        _c(3, "102", "104", "101.5", "103"),
    )

    out = resample_30m(candles)

    assert len(out) == 2
    assert out[0].open == D("100")
    assert out[0].close == D("101.5")
    assert out[0].high == D("102")
    assert out[0].low == D("99")


def test_bearish_fm_spike_pullback_break_gap_limit_reaches_tp1():
    prefix = tuple(
        _c(i, "120", "121", "119", "120")
        for i in range(15)
    )
    setup = (
        _c(15, "110", "111", "108", "109"),
        _c(16, "109", "109.5", "106", "107"),
        _c(17, "106.5", "107", "104", "105"),
        _c(18, "104.5", "105", "102", "103"),
        _c(19, "102.5", "103", "100", "101"),
        _c(20, "101", "103", "100.8", "102.5"),
        _c(21, "102", "102", "98.5", "99"),
        _c(22, "99", "99.2", "96.5", "97"),
        _c(23, "96.8", "97.5", "94", "95"),
        _c(24, "95", "98", "94.5", "97"),
        _c(25, "97", "97.2", "91", "92"),
        _c(26, "92", "93", "90", "91"),
    )

    result = scan_fm(prefix + setup, policy=FMPolicy())

    assert result.setups == 1
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction == "SHORT"
    assert trade.entry == D("97.5")
    assert trade.stop == D("103")
    assert trade.outcome == "TP1"
    assert trade.gross_r > 0


def test_missing_post_break_fvg_does_not_form_setup():
    prefix = tuple(
        _c(i, "120", "121", "119", "120")
        for i in range(15)
    )
    bars = (
        _c(15, "110", "111", "108", "109"),
        _c(16, "109", "109.5", "106", "107"),
        _c(17, "106.5", "107", "104", "105"),
        _c(18, "104.5", "105", "102", "103"),
        _c(19, "102.5", "103", "100", "101"),
        _c(20, "101", "103", "100.8", "102.5"),
        _c(21, "102", "102", "98.5", "99"),
        _c(22, "99", "100", "97", "98"),
        _c(23, "98", "99", "96.8", "97"),
        _c(24, "97", "98", "96", "96.5"),
    )

    result = scan_fm(prefix + bars, policy=FMPolicy())

    assert result.setups == 0
    assert result.trades == ()
