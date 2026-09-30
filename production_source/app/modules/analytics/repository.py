"""Trading-performance repository using persisted realized P/L."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.entities import (
    TradeExitReason,
    TradePerformanceRecord,
    WinRateOutcomeCounts,
)
from app.modules.analytics.errors import WinRateRepositoryError
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signals.models import Signal, SignalEvent, SignalEventType

_TERMINAL_EVENTS = (
    SignalEventType.TARGET_HIT.value,
    SignalEventType.STOP_HIT.value,
    SignalEventType.RUNNER_CLOSED_ALWAYS_IN_REVERSAL.value,
)


def _closed_at_in_window(closed_at, *, started_at: datetime, ended_at: datetime):
    """Return the canonical half-open closed-trade interval [start, end)."""
    return and_(closed_at >= started_at, closed_at < ended_at)


class WinRateRepository(Protocol):
    async def fetch_outcome_counts(
        self, *, started_at: datetime, ended_at: datetime
    ) -> WinRateOutcomeCounts:
        """Return canonical closed trades and current open-trade count."""
        ...


class SQLAlchemyWinRateRepository:
    """Read financial outcomes from the lifecycle's authoritative Signal P/L."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch_outcome_counts(
        self, *, started_at: datetime, ended_at: datetime
    ) -> WinRateOutcomeCounts:
        eligible = (
            SignalAutomationMetadata.signal_id.is_(None)
            | SignalAutomationMetadata.counts_toward_performance.is_(True)
        )
        latest_terminal = (
            select(SignalEvent.event_type)
            .where(
                SignalEvent.signal_id == Signal.id,
                SignalEvent.event_type.in_(_TERMINAL_EVENTS),
            )
            .order_by(SignalEvent.created_at.desc(), SignalEvent.id.desc())
            .limit(1)
            .correlate(Signal)
            .scalar_subquery()
        )
        latest_stop_reason = (
            select(SignalEvent.event_metadata["reason"].astext)
            .where(
                SignalEvent.signal_id == Signal.id,
                SignalEvent.event_type == SignalEventType.STOP_LOSS_UPDATED.value,
            )
            .order_by(SignalEvent.created_at.desc(), SignalEvent.id.desc())
            .limit(1)
            .correlate(Signal)
            .scalar_subquery()
        )
        statement = (
            select(Signal, latest_terminal, latest_stop_reason)
            .outerjoin(
                SignalAutomationMetadata,
                SignalAutomationMetadata.signal_id == Signal.id,
            )
            .where(
                eligible,
                or_(
                    and_(
                        Signal.status == "CLOSED",
                        _closed_at_in_window(
                            Signal.closed_at,
                            started_at=started_at,
                            ended_at=ended_at,
                        ),
                    ),
                    and_(Signal.status == "OPEN", Signal.created_at <= ended_at),
                ),
            )
            .order_by(func.coalesce(Signal.closed_at, Signal.created_at), Signal.id)
        )
        try:
            rows = tuple((await self.session.execute(statement)).all())
        except SQLAlchemyError as exc:
            raise WinRateRepositoryError(
                "Unable to load trading-performance records"
            ) from exc

        trades: list[TradePerformanceRecord] = []
        for signal, terminal_event, stop_reason in rows:
            if signal.status == "OPEN":
                trades.append(TradePerformanceRecord(
                    signal_id=signal.id,
                    status=signal.status,
                    closed_at=None,
                    realized_pnl_pct=None,
                    exit_reason=TradeExitReason.OTHER,
                ))
                continue
            trades.append(TradePerformanceRecord(
                signal_id=signal.id,
                status=signal.status,
                closed_at=signal.closed_at,
                realized_pnl_pct=(
                    Decimal(signal.profit_loss)
                    if signal.profit_loss is not None
                    else None
                ),
                exit_reason=self._exit_reason(
                    terminal_event=terminal_event,
                    stop_reason=stop_reason,
                    pnl=signal.profit_loss,
                ),
            ))

        closed = tuple(item for item in trades if item.status == "CLOSED")
        return WinRateOutcomeCounts(
            target_hit=sum(x.exit_reason is TradeExitReason.TARGET for x in closed),
            stop_hit=sum(
                x.exit_reason in {
                    TradeExitReason.STOP,
                    TradeExitReason.TRAILING_STOP,
                    TradeExitReason.BREAKEVEN,
                }
                for x in closed
            ),
            runner_reversal=sum(
                x.exit_reason is TradeExitReason.RUNNER_REVERSAL for x in closed
            ),
            trades=tuple(trades),
            open_trades=sum(x.status == "OPEN" for x in trades),
            financial_records_loaded=True,
        )

    @staticmethod
    def _exit_reason(
        *, terminal_event: str | None, stop_reason: str | None, pnl
    ) -> TradeExitReason:
        if terminal_event == SignalEventType.TARGET_HIT.value:
            return TradeExitReason.TARGET
        if terminal_event == SignalEventType.RUNNER_CLOSED_ALWAYS_IN_REVERSAL.value:
            return TradeExitReason.RUNNER_REVERSAL
        if terminal_event != SignalEventType.STOP_HIT.value:
            return TradeExitReason.OTHER
        normalized = str(stop_reason or "").upper()
        if normalized == "STRUCTURAL_TRAIL":
            return TradeExitReason.TRAILING_STOP
        if normalized.startswith("BREAKEVEN"):
            return TradeExitReason.BREAKEVEN
        if pnl is not None and Decimal(pnl) == 0:
            return TradeExitReason.BREAKEVEN
        return TradeExitReason.STOP
