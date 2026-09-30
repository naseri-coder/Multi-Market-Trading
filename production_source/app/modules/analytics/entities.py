"""Framework-independent trading-performance report read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class WinRatePeriod(StrEnum):
    """Allow-listed rolling report windows."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class TradeExitReason(StrEnum):
    """How a closed trade exited; separate from its financial result."""

    TARGET = "TARGET"
    STOP = "STOP"
    TRAILING_STOP = "TRAILING_STOP"
    BREAKEVEN = "BREAKEVEN"
    RUNNER_REVERSAL = "RUNNER_REVERSAL"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class TradePerformanceRecord:
    """One canonical signal/trade used once in financial aggregation."""

    signal_id: int
    status: str
    closed_at: datetime | None
    realized_pnl_pct: Decimal | None
    exit_reason: TradeExitReason


@dataclass(frozen=True, slots=True)
class WinRateOutcomeCounts:
    """Repository result retaining legacy event counts plus financial records."""

    target_hit: int
    stop_hit: int
    runner_reversal: int = 0
    trades: tuple[TradePerformanceRecord, ...] = ()
    open_trades: int = 0
    financial_records_loaded: bool = False


@dataclass(frozen=True, slots=True)
class WinRateReport:
    """One immutable rolling trading-performance report."""

    period: str
    window: timedelta
    started_at: datetime
    ended_at: datetime
    target_hit: int
    stop_hit: int
    evaluated_signals: int
    win_rate: Decimal | None
    runner_reversal: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    open_trades: int = 0
    unknown_trades: int = 0
    closed_trades: int = 0
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    profit_factor: Decimal | None = None
    expectancy: Decimal | None = None
    best_trade: Decimal | None = None
    worst_trade: Decimal | None = None
    longest_win_streak: int = 0
    longest_loss_streak: int = 0
    current_win_streak: int = 0
    current_loss_streak: int = 0
    target_exits: int = 0
    stop_profit_exits: int = 0
    stop_loss_exits: int = 0
    trailing_profit_exits: int = 0
    trailing_loss_exits: int = 0
    trailing_breakeven_exits: int = 0
    breakeven_exits: int = 0
    other_exits: int = 0
