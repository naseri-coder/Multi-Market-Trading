from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.market_data.entities import Candle
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.telegram_updates import render_live_caption
from app.modules.operations.trade_management import (
    TradeManagementPlan,
    build_legacy_carryover_plan,
    build_trade_management_plan,
    weighted_close_return,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def target(number: int, price: str, status: str = "PENDING"):
    return SimpleNamespace(
        target_number=number,
        target_price=Decimal(price),
        status=status,
    )


def build(regime: str, *, channel: str = "BROAD"):
    return build_trade_management_plan(
        direction="LONG",
        entry_price=Decimal("100"),
        initial_stop_loss=Decimal("90"),
        targets=(target(1, "110"), target(2, "120")),
        market_regime=regime,
        context_metadata={"channel_quality": channel},
    )


def test_strong_trend_does_not_scale_out_at_one_r():
    plan = build("BULL_TREND")
    assert plan.target_exit_fractions == (
        (1, Decimal("0")),
        (2, Decimal("0.5")),
    )
    assert plan.runner_fraction == Decimal("0.5")


def test_strong_trend_can_scale_half_at_first_target_at_or_beyond_two_r():
    plan = build_trade_management_plan(
        direction="LONG",
        entry_price=Decimal("100"),
        initial_stop_loss=Decimal("90"),
        targets=(target(1, "120"), target(2, "130")),
        market_regime="BULL_TREND",
        context_metadata={"channel_quality": "BROAD"},
    )
    assert plan.fraction_for_target(1) == Decimal("0.5")
    assert plan.fraction_for_target(2) == Decimal("0.25")
    assert plan.runner_fraction == Decimal("0.25")


def test_trading_range_exits_remainder_at_final_structural_target():
    plan = build("TRADING_RANGE")
    assert plan.target_exit_fractions == (
        (1, Decimal("0.5")),
        (2, Decimal("0.5")),
    )
    assert plan.runner_fraction == 0


def test_reversal_or_transition_keeps_a_quarter_runner():
    plan = build("TRANSITION")
    assert plan.target_exit_fractions == (
        (1, Decimal("0.5")),
        (2, Decimal("0.25")),
    )
    assert plan.runner_fraction == Decimal("0.25")


def test_tight_trend_requires_structure_before_breakeven():
    assert build("BULL_TREND", channel="TIGHT").breakeven_mode == "STRUCTURE_ONLY"
    assert build("BULL_TREND", channel="BROAD").breakeven_mode == "AFTER_PARTIAL"


def test_weighted_return_counts_only_actual_scale_outs_and_open_runner():
    plan = build("BULL_TREND")
    targets = (target(1, "110", "HIT"), target(2, "120", "HIT"))
    result = weighted_close_return(
        plan=plan,
        targets=targets,
        target_returns={1: Decimal("10"), 2: Decimal("20")},
        terminal_return=Decimal("5"),
    )
    assert result == Decimal("12.5")


def test_plan_round_trip_preserves_exact_decimals():
    plan = build("TRANSITION")
    assert TradeManagementPlan.from_metadata(plan.to_metadata()) == plan


def test_pre_v6_target_hit_keeps_v5_equal_target_accounting():
    plan = build_legacy_carryover_plan(
        entry_price=Decimal("100"),
        initial_stop_loss=Decimal("90"),
        targets=(target(1, "110", "HIT"), target(2, "120")),
    )
    assert plan.context_class == "V5_LEGACY_CARRYOVER"
    assert plan.target_exit_fractions == (
        (1, Decimal("0.5")),
        (2, Decimal("0.5")),
    )
    assert plan.runner_fraction == 0


def candle(i: int, high: str, low: str, close: str) -> Candle:
    opened = BASE + timedelta(minutes=i)
    return Candle(
        opened,
        opened + timedelta(minutes=1),
        Decimal(close),
        Decimal(high),
        Decimal(low),
        Decimal(close),
        Decimal("1"),
    )


def lifecycle() -> LiveSignalLifecycleService:
    return LiveSignalLifecycleService(
        database=object(),
        provider=object(),
        bot=object(),
        vip_channel_id=1,
        cutover_at=BASE,
        candle_limit=50,
    )


def test_entry_retest_then_new_high_is_structural_breakeven_confirmation():
    candles = (
        candle(0, "101", "99.8", "100.5"),
        candle(1, "104", "101", "103"),
        candle(2, "106", "102", "105"),
        candle(3, "103", "99.9", "101"),
        candle(4, "107", "102", "106.5"),
    )
    signal = SimpleNamespace(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=Decimal("100"),
    )
    assert lifecycle()._entry_tested_then_resumed(
        signal=signal,
        plan=build("BULL_TREND", channel="TIGHT"),
        candles=candles,
        candle=candles[-1],
        entry_activated_at=candles[0].close_time,
    )


def test_entry_retest_without_new_high_is_not_confirmation():
    candles = (
        candle(0, "101", "99.8", "100.5"),
        candle(1, "104", "101", "103"),
        candle(2, "106", "102", "105"),
        candle(3, "103", "99.9", "101"),
        candle(4, "105", "102", "104"),
    )
    signal = SimpleNamespace(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=Decimal("100"),
    )
    assert not lifecycle()._entry_tested_then_resumed(
        signal=signal,
        plan=build("BULL_TREND", channel="TIGHT"),
        candles=candles,
        candle=candles[-1],
        entry_activated_at=candles[0].close_time,
    )


def test_zero_risk_is_rejected_instead_of_silently_inventing_a_threshold():
    with pytest.raises(ValueError, match="initial risk"):
        build_trade_management_plan(
            direction="LONG",
            entry_price=Decimal("100"),
            initial_stop_loss=Decimal("100"),
            targets=(target(1, "110"),),
            market_regime="BULL_TREND",
        )


def test_caption_distinguishes_completed_runner_stop_from_range_target_close():
    signal = SimpleNamespace(
        direction="LONG",
        symbol="BTCUSDT",
        entry_price=Decimal("100"),
        stop_loss=Decimal("105"),
        leverage=Decimal("1"),
        profit_loss=Decimal("12.5"),
    )
    metadata = SimpleNamespace(timeframe="15m", setup_type="H2_CONFIRMED")
    text = render_live_caption(
        signal=signal,
        metadata=metadata,
        targets=(target(1, "110", "HIT"), target(2, "120", "HIT")),
        lifecycle_state="COMPLETE",
        terminal_stop_hit=True,
        trade_management_note="50% runner closed by stop",
    )
    assert "TARGETS HIT • RUNNER STOPPED" in text
    assert "50% runner closed by stop" in text
