"""Tests for MARC R2 descriptive diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.market_data.entities import Candle
from research_layer.marc_backtest.entities import BacktestTrade, BacktestWindowResult
from research_layer.marc_diagnostic.analysis import (
    MARCTradeDiagnostic,
    build_diagnostic_report,
    diagnose_trades,
    resample_30m_to_1h,
)

D = Decimal
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _series(count: int, *, minutes: int, start_price: str = "100") -> tuple[Candle, ...]:
    base = D(start_price)
    candles = []
    for index in range(count):
        price = base + D(index) * D("0.10")
        start = BASE + timedelta(minutes=minutes * index)
        candles.append(
            Candle(
                open_time=start,
                close_time=start + timedelta(minutes=minutes) - timedelta(milliseconds=1),
                open=price,
                high=price + D("1"),
                low=price - D("1"),
                close=price + D("0.20"),
                volume=D("1"),
            )
        )
    return tuple(candles)


def _trade(entry_time: datetime) -> BacktestTrade:
    return BacktestTrade(
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        source_signal_id="marc-r1-test",
        entry_time=entry_time,
        entry_price=112.0,
        stop_loss=110.0,
        exit_time=entry_time + timedelta(hours=1),
        duration_bars=4,
        fills=(),
        gross_r=0.5,
        base_net_r=0.3,
        stress_net_r=0.2,
        tp1_hit=True,
        tp2_hit=False,
        terminal_reason="WINDOW_END",
    )


def test_resample_30m_to_1h_uses_complete_utc_aligned_pairs():
    source = _series(4, minutes=30)

    result = resample_30m_to_1h(source)

    assert len(result) == 2
    assert result[0].open_time.minute == 0
    assert result[0].open == source[0].open
    assert result[0].close == source[1].close
    assert result[0].high == max(source[0].high, source[1].high)
    assert result[0].volume == D("2")


def test_diagnose_trades_reconstructs_causal_confirmation_features():
    candles = _series(140, minutes=15)
    trade = _trade(candles[120].open_time)
    result = BacktestWindowResult(
        symbol="BTCUSDT",
        timeframe="15m",
        start=candles[0].open_time,
        end=candles[-1].close_time,
        candidate_count=1,
        rejected_plan_count=0,
        rejection_reasons=(),
        trades=(trade,),
    )

    diagnostics = diagnose_trades(result=result, candles=candles)

    assert len(diagnostics) == 1
    item = diagnostics[0]
    assert item.source_signal_id == trade.source_signal_id
    assert item.full_ma_alignment is True
    assert item.ma99_slope_directionally_aligned is True
    assert item.ma99_slope_5_atr_per_bar is not None
    assert item.initial_risk_atr is not None
    assert item.cost_drag_r == 0.2
    assert item.htf_directional_alignment == "UNAVAILABLE"


def _diagnostic(*, gross: float, base: float, aligned: bool) -> MARCTradeDiagnostic:
    return MARCTradeDiagnostic(
        source_signal_id=f"sig-{gross}-{aligned}",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        entry_time=BASE,
        gross_r=gross,
        base_net_r=base,
        stress_net_r=base - 0.1,
        tp1_hit=gross > 0,
        tp2_hit=False,
        terminal_reason="TEST",
        cross_age_bars=2,
        confirmation_extension_atr=0.4,
        entry_extension_atr=0.5,
        initial_risk_atr=1.0,
        initial_risk_pct=0.01,
        ma99_slope_5_atr_per_bar=0.02,
        ma99_slope_directionally_aligned=aligned,
        full_ma_alignment=aligned,
        ma7_25_directional_gap_atr=0.2,
        ma25_99_directional_gap_atr=0.3,
        htf_state="BULL" if aligned else "BEAR",
        htf_directional_alignment="ALIGNED" if aligned else "OPPOSED",
        first_ma99_touch_bars=None,
        first_retest_rejection_bars=None,
        first_ma99_loss_bars=None,
        first_opposite_band_failure_bars=None,
        ma99_touch_within_4=False,
        ma99_touch_within_8=False,
        retest_rejection_within_4=False,
        retest_rejection_within_8=False,
        ma99_loss_within_3=False,
        ma99_loss_within_5=False,
        opposite_band_failure_within_3=False,
        opposite_band_failure_within_5=False,
        cost_drag_r=gross - base,
    )


def test_report_is_descriptive_only_and_exposes_alignment_uplift():
    records = (
        _diagnostic(gross=1.0, base=0.8, aligned=True),
        _diagnostic(gross=-1.0, base=-1.2, aligned=False),
    )

    report = build_diagnostic_report(
        validation=records,
        diagnostic_oos=records,
    )

    contrast = report["diagnostic_oos"]["contrasts"]["full_ma_alignment"]
    assert contrast["gross_expectancy_uplift_r"] == 2.0
    assert report["future_r2_approval"] == "DENIED_DIAGNOSTIC_ONLY"
    assert report["purpose"] == "DESCRIPTIVE_ROOT_CAUSE_ANALYSIS_ONLY"
