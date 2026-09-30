"""Read-only performance data collection layer.

This module observes completed signal data only. It must not call
Decision Layer, Risk Engine, AI Council, or signal creation services.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PerformanceSnapshot:
    signal_id: int
    outcome: str | None
    profit_loss: Decimal | None
    rr: Decimal | None
    holding_time_seconds: int | None
    context: dict[str, Any]
    evidence: dict[str, Any]


class PerformanceCollector:
    """Transforms existing signal records into analytics snapshots only."""

    def collect(self, signal: Any) -> PerformanceSnapshot:
        return PerformanceSnapshot(
            signal_id=signal.id,
            outcome=getattr(signal, "status", None),
            profit_loss=getattr(signal, "profit_loss", None),
            rr=None,
            holding_time_seconds=None,
            context={},
            evidence={},
        )

    def collect_position(self, position: Any, *, entry_lot_count: int | None = None) -> PerformanceSnapshot:
        """Collect one aggregate multi-lot trade without counting lots as signals."""
        if str(getattr(position, "state", "")) != "CLOSED":
            raise ValueError("performance collection requires a CLOSED aggregate position")
        signal_id = getattr(position, "signal_id", None)
        if signal_id is None:
            raise ValueError("aggregate performance requires the linked initial signal_id")
        budget = Decimal(str(getattr(position, "initial_trade_risk_budget", "0")))
        if budget <= 0:
            raise ValueError("aggregate performance requires positive initial risk budget")
        pnl = Decimal(str(getattr(position, "realized_net_pnl", "0")))
        return PerformanceSnapshot(
            signal_id=int(signal_id), outcome="CLOSED", profit_loss=pnl, rr=pnl / budget,
            holding_time_seconds=None,
            context={
                "multi_lot_position": True, "position_id": getattr(position, "id", None),
                "position_version": getattr(position, "position_version", None),
                "initial_source_signal_id": getattr(position, "initial_source_signal_id", None),
                "mode": getattr(position, "mode", None),
            },
            evidence={"entry_lot_count": entry_lot_count},
        )
