"""Durable, entry-gate-approved evidence and independent runner accounting.

No detector, threshold, publication, or order execution lives here.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, String, select, func
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUNNER_EVENT = "RUNNER_CLOSED_ALWAYS_IN_REVERSAL"


class ApprovedMarketEvidence(Base):
    __tablename__ = "brooks_approved_market_evidence"
    __table_args__ = (
        Index("ix_brooks_approval_market_time", "exchange", "market_type", "symbol",
              "timeframe", "approved_at"),
    )

    # Same immutable identifier as SignalAutomationMetadata.source_signal_id.
    source_signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    always_in: Mapped[str] = mapped_column(String(16), nullable=False)
    candle_closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    gates: Mapped[dict] = mapped_column(JSONB, nullable=False)


async def record_approved_candidate(
    session, *, candidate, context, council, risk, quality, gate
) -> bool:
    """Called only after the existing final gate, inside its own committed transaction."""
    gates = {
        "ai_council": bool(council.approved),
        "risk": bool(risk.approved),
        "signal_intelligence": bool(quality.approved),
        "final_gate": bool(gate.approved),
    }
    if not all(gates.values()):
        return False
    if not candidate.source_signal_id:
        raise ValueError("approval evidence requires source_signal_id")
    snapshot = candidate.snapshot
    values = dict(
        source_signal_id=candidate.source_signal_id,
        exchange=candidate.exchange, market_type=candidate.market_type,
        symbol=candidate.symbol, timeframe=candidate.timeframe,
        direction=candidate.direction, always_in=context.always_in,
        candle_closed_at=snapshot.candles[-1].close_time,
        snapshot=json.loads(json.dumps({
            "snapshot_id": snapshot.snapshot_id, "snapshot_hash": snapshot.snapshot_hash,
            "candles": [asdict(c) for c in snapshot.candles],
            "engine_version": candidate.engine_version,
            "configuration_version": candidate.configuration_version,
        }, default=str)),
        context=json.loads(json.dumps(asdict(context), default=str)),
        gates={**gates, "quality_metadata": json.loads(json.dumps(quality.metadata, default=str))},
    )
    await session.execute(insert(ApprovedMarketEvidence).values(**values)
                          .on_conflict_do_nothing(index_elements=["source_signal_id"]))
    return True


def closed_runner_fraction(event) -> Decimal:
    if event is None:
        return Decimal("0")
    return Decimal(str((event.event_metadata if hasattr(event, "event_metadata") else event.metadata)["exit_fraction"]))


def open_position_fraction(plan, targets, runner_event=None) -> Decimal:
    return max(Decimal("0"), plan.remaining_fraction(targets) - closed_runner_fraction(runner_event))


def open_runner_fraction(plan, targets, runner_event=None) -> Decimal:
    """Read the unallocated runner directly from the immutable V6 plan."""
    if runner_event is not None:
        return Decimal("0")
    return min(plan.runner_fraction, open_position_fraction(plan, targets))


def apply_runner_realization(result, terminal_return, runner_event=None) -> Decimal:
    """Replace only the runner's hypothetical terminal return with its realized return."""
    if runner_event is None:
        return result
    m = runner_event.event_metadata if hasattr(runner_event, "event_metadata") else runner_event.metadata
    return result + closed_runner_fraction(runner_event) * (
        Decimal(str(m["return_pct"])) - terminal_return
    )


async def find_reversal_evidence(session, *, signal, metadata, entry_at, candle):
    """Same market/timeframe; both confirmation and candle must be causal.

    Require durable same-direction evidence known by entry. Pre-install signals
    without this baseline fail closed rather than inventing an entry context.
    """
    if entry_at is None or metadata.generation_mode != "LIVE":
        return None
    baseline = await session.get(ApprovedMarketEvidence, metadata.source_signal_id)
    if baseline is None:
        return None
    market = (metadata.exchange, metadata.market_type, signal.symbol, metadata.timeframe)
    baseline_market = (baseline.exchange, baseline.market_type, baseline.symbol, baseline.timeframe)
    if (
        baseline_market != market or baseline.direction != signal.direction
        or baseline.always_in != signal.direction
        or baseline.approved_at > entry_at or baseline.candle_closed_at > entry_at
    ):
        return None
    opposite = "SHORT" if signal.direction == "LONG" else "LONG"
    E = ApprovedMarketEvidence
    return await session.scalar(
        select(E).where(
            E.exchange == metadata.exchange, E.market_type == metadata.market_type,
            E.symbol == signal.symbol, E.timeframe == metadata.timeframe,
            E.direction == opposite, E.always_in == opposite,
            E.approved_at > entry_at, E.candle_closed_at > entry_at,
            # Conservative: evidence must exist before this execution candle opens.
            E.approved_at <= candle.open_time, E.candle_closed_at <= candle.open_time,
        ).order_by(E.approved_at, E.source_signal_id).limit(1)
    )


async def latest_runner_event(session, signal_id):
    from app.modules.signals.models import SignalEvent

    return await session.scalar(select(SignalEvent).where(
        SignalEvent.signal_id == signal_id, SignalEvent.event_type == RUNNER_EVENT
    ).limit(1))
