"""Causal candidate replay helper for the frozen MARC baseline."""

from __future__ import annotations

from app.modules.market_data.entities import MarketSnapshot

from app.modules.marc_core.engine import MARCSignalEngine
from app.modules.marc_core.entities import MARCEntryPlan


def replay_entry_plans(
    snapshot: MarketSnapshot,
    *,
    engine: MARCSignalEngine | None = None,
) -> tuple[MARCEntryPlan, ...]:
    """Replay next-bar-open MARC plans without using future candles in analysis.

    This helper extracts entry plans only. It deliberately does not decide trade
    outcomes, funding, fees, slippage, or portfolio sizing; those belong to the
    separate backtest stage.
    """
    selected = engine or MARCSignalEngine()
    plans: list[MARCEntryPlan] = []
    minimum = selected.policy.minimum_indicator_bars

    if len(snapshot.candles) <= minimum:
        return ()

    for confirmation_index in range(minimum - 1, len(snapshot.candles) - 1):
        closed = snapshot.candles[: confirmation_index + 1]
        partial = MarketSnapshot(
            exchange=snapshot.exchange,
            market_type=snapshot.market_type,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            candles=closed,
            captured_at=closed[-1].close_time,
            source=snapshot.source,
        )
        decision = selected.evaluate(partial)
        if not decision.trade_ready or not decision.fresh:
            continue
        next_candle = snapshot.candles[confirmation_index + 1]
        plans.append(
            selected.build_entry_plan(
                partial,
                decision,
                entry_price=next_candle.open,
            )
        )

    return tuple(plans)
