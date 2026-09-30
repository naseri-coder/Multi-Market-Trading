"""Rolling financial-performance aggregation for closed trades."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.modules.analytics.entities import (
    TradeExitReason,
    TradePerformanceRecord,
    WinRatePeriod,
    WinRateReport,
)
from app.modules.analytics.errors import InvalidWinRatePeriodError
from app.modules.analytics.repository import WinRateRepository

WinRateClock = Callable[[], datetime]
DISPLAY_QUANTUM = Decimal("0.01")
PNL_STORAGE_QUANTUM = Decimal("0.00000001")
WIN_RATE_WINDOWS = {
    WinRatePeriod.DAILY: timedelta(hours=24),
    WinRatePeriod.WEEKLY: timedelta(days=7),
    WinRatePeriod.MONTHLY: timedelta(days=30),
    WinRatePeriod.YEARLY: timedelta(days=365),
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class WinRateService:
    """Aggregate each canonical trade once using final realized P/L."""

    def __init__(
        self, repository: WinRateRepository, *, clock: WinRateClock = utc_now
    ) -> None:
        self.repository = repository
        self.clock = clock

    async def get_report(self, period: str | WinRatePeriod) -> WinRateReport:
        normalized = self._period(period)
        ended_at = self._now()
        window = WIN_RATE_WINDOWS[normalized]
        started_at = ended_at - window
        data = await self.repository.fetch_outcome_counts(
            started_at=started_at, ended_at=ended_at
        )
        if not data.financial_records_loaded:
            return self._legacy_report(
                normalized=normalized,
                window=window,
                started_at=started_at,
                ended_at=ended_at,
                target_hit=data.target_hit,
                stop_hit=data.stop_hit,
                runner_reversal=data.runner_reversal,
            )
        return self._financial_report(
            normalized=normalized,
            window=window,
            started_at=started_at,
            ended_at=ended_at,
            records=data.trades,
            target_hit=data.target_hit,
            stop_hit=data.stop_hit,
            runner_reversal=data.runner_reversal,
        )

    async def get_daily_report(self) -> WinRateReport:
        return await self.get_report(WinRatePeriod.DAILY)

    async def get_weekly_report(self) -> WinRateReport:
        return await self.get_report(WinRatePeriod.WEEKLY)

    async def get_monthly_report(self) -> WinRateReport:
        return await self.get_report(WinRatePeriod.MONTHLY)

    async def get_yearly_report(self) -> WinRateReport:
        return await self.get_report(WinRatePeriod.YEARLY)

    def _financial_report(
        self, *, normalized, window, started_at, ended_at, records,
        target_hit, stop_hit, runner_reversal
    ) -> WinRateReport:
        ids = [item.signal_id for item in records]
        if len(ids) != len(set(ids)):
            raise RuntimeError("Trading-performance repository returned duplicate trades")
        closed = tuple(item for item in records if item.status == "CLOSED")
        open_count = sum(item.status == "OPEN" for item in records)
        known = tuple(x for x in closed if x.realized_pnl_pct is not None)
        wins = tuple(x for x in known if self._outcome(x) == "WIN")
        losses = tuple(x for x in known if self._outcome(x) == "LOSS")
        breakevens = tuple(x for x in known if self._outcome(x) == "BREAKEVEN")
        denominator = len(wins) + len(losses)
        win_rate = (
            self._percent(len(wins), denominator) if denominator else None
        )
        gross_profit = sum((x.realized_pnl_pct for x in wins), Decimal("0"))
        gross_loss = sum((x.realized_pnl_pct for x in losses), Decimal("0"))
        net_pnl = sum((x.realized_pnl_pct for x in known), Decimal("0"))
        average_win = gross_profit / len(wins) if wins else None
        average_loss = gross_loss / len(losses) if losses else None
        if gross_loss:
            profit_factor = gross_profit / abs(gross_loss)
        elif gross_profit:
            profit_factor = Decimal("Infinity")
        else:
            profit_factor = None
        # Breakevens are excluded from the expectancy denominator, matching win rate.
        expectancy = (
            (
                Decimal(len(wins)) / denominator * average_win
                + Decimal(len(losses)) / denominator * average_loss
            )
            if denominator and average_win is not None and average_loss is not None
            else average_win if denominator and average_win is not None
            else average_loss if denominator and average_loss is not None
            else None
        )
        longest_win, longest_loss, current_win, current_loss = self._streaks(closed)
        exit_counts = self._exit_counts(closed)
        return WinRateReport(
            period=normalized.value, window=window,
            started_at=started_at, ended_at=ended_at,
            target_hit=target_hit, stop_hit=stop_hit,
            evaluated_signals=denominator, win_rate=win_rate,
            runner_reversal=runner_reversal,
            winning_trades=len(wins), losing_trades=len(losses),
            breakeven_trades=len(breakevens), open_trades=open_count,
            unknown_trades=len(closed) - len(known), closed_trades=len(closed),
            gross_profit=gross_profit, gross_loss=gross_loss, net_pnl=net_pnl,
            average_win=average_win, average_loss=average_loss,
            profit_factor=profit_factor, expectancy=expectancy,
            best_trade=max((x.realized_pnl_pct for x in known), default=None),
            worst_trade=min((x.realized_pnl_pct for x in known), default=None),
            longest_win_streak=longest_win, longest_loss_streak=longest_loss,
            current_win_streak=current_win, current_loss_streak=current_loss,
            **exit_counts,
        )

    def _legacy_report(
        self, *, normalized, window, started_at, ended_at,
        target_hit, stop_hit, runner_reversal
    ) -> WinRateReport:
        if min(target_hit, stop_hit, runner_reversal) < 0:
            raise RuntimeError("Win-rate repository returned negative counts")
        evaluated = target_hit + stop_hit
        return WinRateReport(
            period=normalized.value, window=window,
            started_at=started_at, ended_at=ended_at,
            target_hit=target_hit, stop_hit=stop_hit,
            evaluated_signals=evaluated,
            win_rate=self._percent(target_hit, evaluated) if evaluated else Decimal("0.00"),
            runner_reversal=runner_reversal,
        )

    @staticmethod
    def _outcome(record: TradePerformanceRecord) -> str:
        value = record.realized_pnl_pct
        if value is None:
            return "UNKNOWN"
        normalized = value.quantize(PNL_STORAGE_QUANTUM)
        if normalized > 0:
            return "WIN"
        if normalized < 0:
            return "LOSS"
        return "BREAKEVEN"

    @classmethod
    def _streaks(cls, closed: Iterable[TradePerformanceRecord]) -> tuple[int, int, int, int]:
        longest_win = longest_loss = current_win = current_loss = 0
        ordered = sorted(
            closed,
            key=lambda x: (
                x.closed_at or datetime.min.replace(tzinfo=UTC),
                x.signal_id,
            ),
        )
        for item in ordered:
            outcome = cls._outcome(item)
            if outcome == "WIN":
                current_win += 1
                current_loss = 0
                longest_win = max(longest_win, current_win)
            elif outcome == "LOSS":
                current_loss += 1
                current_win = 0
                longest_loss = max(longest_loss, current_loss)
            else:
                current_win = current_loss = 0
        return longest_win, longest_loss, current_win, current_loss

    @classmethod
    def _exit_counts(cls, closed: Iterable[TradePerformanceRecord]) -> dict[str, int]:
        result = {
            "target_exits": 0, "stop_profit_exits": 0, "stop_loss_exits": 0,
            "trailing_profit_exits": 0, "trailing_loss_exits": 0,
            "trailing_breakeven_exits": 0, "breakeven_exits": 0,
            "other_exits": 0,
        }
        for item in closed:
            outcome = cls._outcome(item)
            if item.exit_reason is TradeExitReason.TARGET:
                result["target_exits"] += 1
            elif item.exit_reason is TradeExitReason.TRAILING_STOP:
                key = {
                    "WIN": "trailing_profit_exits",
                    "LOSS": "trailing_loss_exits",
                    "BREAKEVEN": "trailing_breakeven_exits",
                    "UNKNOWN": "other_exits",
                }[outcome]
                result[key] += 1
            elif item.exit_reason is TradeExitReason.BREAKEVEN:
                result["breakeven_exits"] += 1
            elif item.exit_reason is TradeExitReason.STOP:
                key = {
                    "WIN": "stop_profit_exits",
                    "LOSS": "stop_loss_exits",
                    "BREAKEVEN": "breakeven_exits",
                    "UNKNOWN": "other_exits",
                }[outcome]
                result[key] += 1
            else:
                result["other_exits"] += 1
        return result

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("WinRateService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _period(period: str | WinRatePeriod) -> WinRatePeriod:
        try:
            return WinRatePeriod(period)
        except (TypeError, ValueError):
            raise InvalidWinRatePeriodError("Unsupported win-rate period") from None

    @staticmethod
    def _percent(part: int, total: int) -> Decimal:
        return (Decimal(part) * 100 / Decimal(total)).quantize(
            DISPLAY_QUANTUM, rounding=ROUND_HALF_UP
        )
