from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.market_data.entities import Candle
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.telegram_updates import render_live_caption
from app.modules.operations.trade_management import TradeManagementPlan

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def bar(i: int, high: str, low: str, close: str | None = None) -> Candle:
    opened = BASE + timedelta(minutes=i)
    high_value, low_value = Decimal(high), Decimal(low)
    close_value = Decimal(close) if close is not None else (high_value + low_value) / Decimal("2")
    return Candle(
        opened,
        opened + timedelta(minutes=1),
        close_value,
        high_value,
        low_value,
        close_value,
        Decimal("1"),
    )


def service() -> LiveSignalLifecycleService:
    return LiveSignalLifecycleService(
        database=object(),
        provider=object(),
        bot=object(),
        vip_channel_id=1,
        cutover_at=BASE,
        candle_limit=50,
    )


def management_plan(mode: str = "AFTER_PARTIAL") -> TradeManagementPlan:
    return TradeManagementPlan(
        context_class="REVERSAL_OR_TRANSITION",
        initial_stop_loss=Decimal("90"),
        initial_risk=Decimal("10"),
        target_exit_fractions=((1, Decimal("0.5")),),
        runner_fraction=Decimal("0.5"),
        breakeven_mode=mode,
        source_rule_ids=("BOOKS-V5-TRADE-MANAGEMENT",),
    )


def structural_bull_candles():
    values = [
        ("101", "100"),
        ("103", "101"),
        ("105", "102"),
        ("104", "100"),
        ("103", "99"),
        ("104", "100"),
        ("106", "102"),
        ("108", "104"),
        ("107", "103"),
        ("106", "102"),
        ("107", "103"),
        ("109", "105"),
        ("111", "107"),
        ("110", "106"),
        ("109", "105"),
    ]
    return tuple(bar(index, high, low) for index, (high, low) in enumerate(values))


def test_only_an_allocated_partial_can_trigger_post_target_breakeven():
    pending = SimpleNamespace(target_number=1, target_price=Decimal("110"), status="PENDING")
    hit = SimpleNamespace(target_number=1, target_price=Decimal("110"), status="HIT")
    assert not service()._breakeven_ready((pending,), management_plan())
    assert service()._breakeven_ready((hit,), management_plan())
    assert not service()._breakeven_ready((hit,), management_plan("STRUCTURE_ONLY"))


def test_structural_long_trail_uses_confirmed_higher_low_after_new_high():
    candles = structural_bull_candles()
    signal = SimpleNamespace(symbol="BTCUSDT", direction="LONG", stop_loss=Decimal("90"))
    result = service()._structural_trailing_stop(
        signal=signal,
        candles=candles,
        candle=candles[-1],
        entry_activated_at=candles[0].close_time,
    )
    assert result == Decimal("101.90")


def test_caption_surfaces_trailing_stop_note():
    signal = SimpleNamespace(
        direction="LONG",
        symbol="BTCUSDT",
        entry_price=Decimal("100"),
        stop_loss=Decimal("101.90"),
        leverage=Decimal("1"),
        profit_loss=None,
    )
    metadata = SimpleNamespace(timeframe="15m", setup_type="H2_CONFIRMED")
    target = SimpleNamespace(target_number=1, target_price=Decimal("110"), status="PENDING")
    text = render_live_caption(
        signal=signal,
        metadata=metadata,
        targets=(target,),
        lifecycle_state="ACTIVE",
        entry_activated=True,
        stop_management_note="🔒 Stop trailed at 101.90 ✅",
    )
    assert "Stop Loss: 101.90" in text
    assert "Stop trailed at 101.90" in text


@pytest.mark.asyncio
async def test_tighten_active_stop_moves_to_breakeven_and_never_backwards():
    lifecycle = service()
    signal = SimpleNamespace(
        id=7,
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
    )
    target = SimpleNamespace(target_number=1, target_price=Decimal("110"), status="HIT")
    updated = SimpleNamespace(stop_loss=Decimal("100"))
    signal_service = SimpleNamespace(update_stop_loss=AsyncMock(return_value=updated))
    candle = bar(30, "106", "101", "105.5")

    changed = await lifecycle._tighten_active_stop(
        service=signal_service,
        signal=signal,
        targets=(target,),
        plan=management_plan(),
        candles=(candle,),
        candle=candle,
        entry_activated_at=BASE,
    )
    assert changed is True
    assert signal.stop_loss == Decimal("100")
    signal_service.update_stop_loss.assert_awaited_once_with(
        7, stop_loss=Decimal("100"), reason="BREAKEVEN_AFTER_SCALE_OUT"
    )

    # Once at breakeven the same trigger cannot move the stop backwards.
    signal_service.update_stop_loss.reset_mock()
    changed = await lifecycle._tighten_active_stop(
        service=signal_service,
        signal=signal,
        targets=(target,),
        plan=management_plan(),
        candles=(candle,),
        candle=candle,
        entry_activated_at=BASE,
    )
    assert changed is False
    signal_service.update_stop_loss.assert_not_awaited()
