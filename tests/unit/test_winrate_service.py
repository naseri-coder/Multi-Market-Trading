"""Financial-outcome trading-performance aggregation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.analytics.entities import (
    TradeExitReason,
    TradePerformanceRecord,
    WinRateOutcomeCounts,
    WinRatePeriod,
)
from app.modules.analytics.errors import InvalidWinRatePeriodError
from app.modules.analytics.repository import SQLAlchemyWinRateRepository
from app.modules.analytics.service import WinRateService
from app.modules.operations.lifecycle import _return_pct
from app.modules.operations.trade_management import (
    TradeManagementPlan,
    weighted_close_return,
)

NOW = datetime(2026, 9, 22, 16, tzinfo=UTC)


def trade(
    signal_id: int,
    pnl: str | None,
    *,
    reason: TradeExitReason = TradeExitReason.STOP,
    status: str = "CLOSED",
    minute: int = 0,
) -> TradePerformanceRecord:
    return TradePerformanceRecord(
        signal_id=signal_id,
        status=status,
        closed_at=NOW - timedelta(minutes=minute) if status == "CLOSED" else None,
        realized_pnl_pct=Decimal(pnl) if pnl is not None else None,
        exit_reason=reason,
    )


async def report_for(*records: TradePerformanceRecord):
    repository = AsyncMock()
    repository.fetch_outcome_counts.return_value = WinRateOutcomeCounts(
        target_hit=sum(x.exit_reason is TradeExitReason.TARGET for x in records),
        stop_hit=sum(x.exit_reason is TradeExitReason.STOP for x in records),
        trades=records,
        open_trades=sum(x.status == "OPEN" for x in records),
        financial_records_loaded=True,
    )
    return await WinRateService(repository, clock=lambda: NOW).get_daily_report()


@pytest.mark.parametrize(
    ("direction", "entry", "exit_price", "expected"),
    (
        ("LONG", "100", "105", "5"),
        ("LONG", "100", "95", "-5"),
        ("SHORT", "100", "95", "5"),
        ("SHORT", "100", "105", "-5"),
        ("LONG", "100", "104", "4"),
        ("SHORT", "100", "96", "4"),
        ("LONG", "100", "97", "-3"),
        ("SHORT", "100", "103", "-3"),
        ("LONG", "100", "100", "0"),
    ),
)
def test_existing_lifecycle_return_semantics(
    direction: str, entry: str, exit_price: str, expected: str
) -> None:
    assert _return_pct(
        direction=direction,
        entry=Decimal(entry),
        price=Decimal(exit_price),
        leverage=Decimal("1"),
    ) == Decimal(expected)


def test_existing_lifecycle_return_is_leverage_aware() -> None:
    assert _return_pct(
        direction="LONG",
        entry=Decimal("100"),
        price=Decimal("102"),
        leverage=Decimal("5"),
    ) == Decimal("10")


@pytest.mark.parametrize(
    ("terminal_return", "expected"),
    (("2", "3"), ("-2", "1")),
)
def test_partial_target_uses_existing_weighted_accounting(
    terminal_return: str, expected: str
) -> None:
    plan = TradeManagementPlan(
        context_class="TEST",
        initial_stop_loss=Decimal("95"),
        initial_risk=Decimal("5"),
        target_exit_fractions=((1, Decimal("0.5")),),
        runner_fraction=Decimal("0.5"),
        breakeven_mode="AFTER_PARTIAL",
        source_rule_ids=("TEST",),
    )
    target = SimpleNamespace(target_number=1, target_price=Decimal("104"), status="HIT")
    assert weighted_close_return(
        plan=plan,
        targets=(target,),
        target_returns={1: Decimal("4")},
        terminal_return=Decimal(terminal_return),
    ) == Decimal(expected)


async def test_financial_outcome_not_exit_event_drives_classification() -> None:
    report = await report_for(
        trade(1, "4", reason=TradeExitReason.TRAILING_STOP, minute=5),
        trade(2, "-3", reason=TradeExitReason.TRAILING_STOP, minute=4),
        trade(3, "2", reason=TradeExitReason.STOP, minute=3),
        trade(4, "-1", reason=TradeExitReason.TARGET, minute=2),
        trade(5, "0", reason=TradeExitReason.BREAKEVEN, minute=1),
    )

    assert report.winning_trades == 2
    assert report.losing_trades == 2
    assert report.breakeven_trades == 1
    assert report.win_rate == Decimal("50.00")
    assert report.trailing_profit_exits == 1
    assert report.trailing_loss_exits == 1
    assert report.stop_profit_exits == 1
    assert report.target_exits == 1


async def test_stop_moved_into_profit_is_a_win() -> None:
    report = await report_for(trade(1, "4", reason=TradeExitReason.STOP))
    assert report.winning_trades == 1
    assert report.losing_trades == 0


async def test_open_and_unknown_are_excluded_from_financial_denominators() -> None:
    report = await report_for(
        trade(1, None),
        trade(2, None, status="OPEN"),
        trade(3, "0"),
    )
    assert report.closed_trades == 2
    assert report.unknown_trades == 1
    assert report.open_trades == 1
    assert report.breakeven_trades == 1
    assert report.evaluated_signals == 0
    assert report.win_rate is None
    assert report.profit_factor is None
    assert report.expectancy is None


async def test_aggregate_metrics_and_streaks() -> None:
    report = await report_for(
        trade(1, "5", minute=9),
        trade(2, "3", minute=8),
        trade(3, "0", minute=7),
        trade(4, "-2", minute=6),
        trade(5, "-3", minute=5),
        trade(6, "2", minute=4),
        trade(7, "1", minute=3),
        trade(8, "4", minute=2),
        trade(9, "6", minute=1),
    )
    assert report.gross_profit == Decimal("21")
    assert report.gross_loss == Decimal("-5")
    assert report.net_pnl == Decimal("16")
    assert report.average_win == Decimal("3.5")
    assert report.average_loss == Decimal("-2.5")
    assert report.profit_factor == Decimal("4.2")
    assert report.expectancy == Decimal("2")
    assert report.best_trade == Decimal("6")
    assert report.worst_trade == Decimal("-3")
    assert report.longest_win_streak == 4
    assert report.longest_loss_streak == 2


async def test_wins_only_profit_factor_is_infinite() -> None:
    report = await report_for(trade(1, "2"), trade(2, "3"))
    assert report.profit_factor == Decimal("Infinity")
    assert report.expectancy == Decimal("2.5")


async def test_duplicate_trade_ids_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="duplicate"):
        await report_for(trade(1, "2"), trade(1, "3"))


@pytest.mark.parametrize(
    ("period", "window"),
    (
        (WinRatePeriod.DAILY, timedelta(hours=24)),
        (WinRatePeriod.WEEKLY, timedelta(days=7)),
        (WinRatePeriod.MONTHLY, timedelta(days=30)),
        (WinRatePeriod.YEARLY, timedelta(days=365)),
    ),
)
async def test_each_period_uses_shared_aggregation(period, window) -> None:
    repository = AsyncMock()
    repository.fetch_outcome_counts.return_value = WinRateOutcomeCounts(
        0, 0, trades=(trade(1, "1"),), financial_records_loaded=True
    )
    report = await WinRateService(repository, clock=lambda: NOW).get_report(period)
    assert report.window == window
    assert report.started_at == NOW - window


async def test_legacy_count_contract_remains_backward_compatible() -> None:
    repository = AsyncMock()
    repository.fetch_outcome_counts.return_value = WinRateOutcomeCounts(2, 1)
    report = await WinRateService(repository, clock=lambda: NOW).get_daily_report()
    assert report.win_rate == Decimal("66.67")


async def test_invalid_period_is_rejected_before_repository_access() -> None:
    repository = AsyncMock()
    with pytest.raises(InvalidWinRatePeriodError):
        await WinRateService(repository, clock=lambda: NOW).get_report("quarterly")
    repository.fetch_outcome_counts.assert_not_awaited()


def test_exit_reason_distinguishes_trailing_breakeven_and_stop() -> None:
    classify = SQLAlchemyWinRateRepository._exit_reason
    assert classify(
        terminal_event="STOP_HIT", stop_reason="STRUCTURAL_TRAIL", pnl=Decimal("4")
    ) is TradeExitReason.TRAILING_STOP
    assert classify(
        terminal_event="STOP_HIT",
        stop_reason="BREAKEVEN_STRUCTURE_CONFIRMED",
        pnl=Decimal("0"),
    ) is TradeExitReason.BREAKEVEN
    assert classify(
        terminal_event="STOP_HIT", stop_reason=None, pnl=Decimal("-1")
    ) is TradeExitReason.STOP
