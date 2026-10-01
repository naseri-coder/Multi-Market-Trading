"""Read-only-to-real-state Scale-In SHADOW observer.

The observer may persist only SHADOW position/evaluation records. It never creates
Signals, publishes messages, sends exchange orders, or mutates legacy TM state.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.modules.operations.models import SignalLifecycleState
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signals.models import Signal, SignalEvent

from .entities import EntryFill
from .repository import PositionRepository
from .shadow_runtime import (
    INITIAL_RISK_ALLOCATION, NORMALIZED_RISK_BUDGET,
    ShadowPositionState, _unit_qty, evaluate_shadow_candidate,
)

SHADOW_OBSERVER_VERSION = "brooks-scale-in-shadow-observer-v1"


def _initial_stop(metadata: SignalAutomationMetadata, created_event: SignalEvent | None) -> Decimal | None:
    tm = dict(metadata.analysis_metadata or {}).get("trade_management_v6")
    if isinstance(tm, dict) and tm.get("initial_stop_loss") is not None:
        return Decimal(str(tm["initial_stop_loss"]))
    if created_event is not None:
        raw = dict(created_event.metadata or {}).get("stop_loss")
        if raw is not None:
            return Decimal(str(raw))
    return None


class ShadowScaleInObserver:
    def __init__(self, database: Any) -> None:
        self.database = database

    async def observe(self, *, candidate: Any, signal_quality: Any) -> dict[str, object]:
        now = getattr(candidate.snapshot, "captured_at", None) or datetime.now(UTC)
        async with self.database.session() as session, session.begin():
            target_hit = select(SignalEvent.id).where(
                SignalEvent.signal_id == Signal.id,
                SignalEvent.event_type == "TARGET_HIT",
                SignalEvent.created_at <= now,
            ).exists()
            stmt = (
                select(Signal, SignalAutomationMetadata, SignalLifecycleState)
                .join(SignalAutomationMetadata, SignalAutomationMetadata.signal_id == Signal.id)
                .join(SignalLifecycleState, SignalLifecycleState.signal_id == Signal.id)
                .where(
                    Signal.status == "OPEN", Signal.symbol == candidate.symbol,
                    Signal.direction == candidate.direction,
                    SignalAutomationMetadata.producer == "BROOKS",
                    SignalAutomationMetadata.timeframe == candidate.timeframe,
                    SignalLifecycleState.state == "ACTIVE",
                    SignalLifecycleState.entry_activated_at.is_not(None),
                    SignalLifecycleState.entry_activated_at < now,
                    ~target_hit,
                )
                .order_by(SignalLifecycleState.entry_activated_at.desc(), Signal.id.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).first()
            if row is None:
                return {"action": "NO_ACTION", "reason": "NO_ELIGIBLE_ACTIVE_POSITION"}
            signal, metadata, lifecycle = row
            created_event = await session.scalar(
                select(SignalEvent).where(
                    SignalEvent.signal_id == signal.id,
                    SignalEvent.event_type == "CREATED",
                ).order_by(SignalEvent.id).limit(1)
            )
            initial_stop = _initial_stop(metadata, created_event)
            if initial_stop is None:
                return {"action": "NO_ACTION", "reason": "INITIAL_STOP_UNAVAILABLE"}

            repo = PositionRepository(session)
            position = await repo.create_position(
                signal_id=signal.id, initial_source_signal_id=metadata.source_signal_id,
                mode="SHADOW", symbol=signal.symbol, direction=signal.direction,
                initial_trade_risk_budget=NORMALIZED_RISK_BUDGET,
                executable_stop=initial_stop,
                metadata={"timeframe": metadata.timeframe, "setup_type": metadata.setup_type,
                          "observer_version": SHADOW_OBSERVER_VERSION},
            )
            lots = await repo.list_entry_lots(position.id)
            if not lots:
                qty = _unit_qty(Decimal(signal.entry_price), initial_stop, INITIAL_RISK_ALLOCATION)
                if qty <= 0:
                    return {"action": "NO_ACTION", "reason": "SHADOW_SEED_QTY_ZERO"}
                await repo.apply_entry_fill(EntryFill(
                    execution_key=f"shadow-seed:{position.id}", position_id=position.id,
                    direction=signal.direction, filled_qty=qty, requested_qty=qty,
                    fill_price=Decimal(signal.entry_price), fill_time=lifecycle.entry_activated_at,
                    entry_reason="SHADOW_INITIAL_REAL_ENTRY_ACTIVATED", scale_sequence_number=0,
                    structural_stop_at_entry=initial_stop, risk_budget_at_entry=NORMALIZED_RISK_BUDGET,
                    fill_source="SHADOW", setup_type=metadata.setup_type,
                    rule_id="ENG-SCALE-SHADOW-REAL-ACTIVE-SEED",
                    metadata={"observer_version": SHADOW_OBSERVER_VERSION,
                              "tm_plan": dict(metadata.analysis_metadata or {}).get("trade_management_v6")},
                ), snapshot_key=f"shadow-seed-risk:{position.id}")
                lots = await repo.list_entry_lots(position.id)
            ledger = repo._ledger(position, lots)
            current_stop = Decimal(signal.stop_loss)
            if current_stop != ledger.executable_stop:
                await repo.update_executable_stop(
                    position.id, current_stop, snapshot_key=f"shadow-stop:{position.id}:{candidate.source_signal_id}"
                )
                position = await repo.get_position(position.id, for_update=True)
                assert position is not None
                lots = await repo.list_entry_lots(position.id, for_update=True)
                ledger = repo._ledger(position, lots)

            from .models import BrooksPositionScaleEvent
            approved_count = int(await session.scalar(
                select(func.count()).select_from(BrooksPositionScaleEvent).where(
                    BrooksPositionScaleEvent.position_id == position.id,
                    BrooksPositionScaleEvent.state == "SCALE_IN_APPROVED",
                )
            ) or 0)
            state = ShadowPositionState(
                ledger=ledger, source_signal_id=metadata.source_signal_id,
                scale_adds=approved_count, last_setup_type=metadata.setup_type or "UNKNOWN",
            )
            quality_meta = dict(getattr(signal_quality, "metadata", {}) or {})
            always_in = str(quality_meta.get("always_in") or "")
            regime = str(quality_meta.get("market_regime") or "")
            if not always_in or not regime:
                return {"action": "NO_ACTION", "reason": "CANDIDATE_CONTEXT_UNAVAILABLE"}
            result = evaluate_shadow_candidate(
                state=state, candidate=candidate, market_regime=regime,
                always_in=always_in, full_pipeline_approved=True, premise_valid=True,
            )
            if result.evaluation is None:
                return {"action": result.action, **dict(result.metadata)}
            evaluation = result.evaluation
            risk = evaluation.risk
            event_state = "SCALE_IN_APPROVED" if evaluation.approved else "SCALE_IN_REJECTED"
            event_key = f"shadow-decision:{candidate.source_signal_id}"
            inserted = await repo.record_scale_event(
                position_id=position.id, event_key=event_key,
                intent_id=str(candidate.source_signal_id), state=event_state,
                category=evaluation.policy.category.value,
                desired_qty=Decimal(str(result.metadata.get("desired_qty", "0"))),
                approved_qty=(risk.approved_qty if risk is not None else None),
                expected_price=Decimal(candidate.entry_price),
                structural_stop=Decimal(candidate.stop_loss), reason=evaluation.reason,
                metadata={
                    "observer_version": SHADOW_OBSERVER_VERSION,
                    "candidate_setup_type": candidate.setup_type,
                    "candidate_market_snapshot_id": candidate.market_snapshot_id,
                    "hypothetical_avg_entry": str(evaluation.hypothetical_avg_entry),
                    "hypothetical_open_qty": str(evaluation.hypothetical_open_qty),
                    "hypothetical_stop": str(evaluation.hypothetical_stop),
                    "post_scale_aggregate_risk": (
                        str(risk.post_scale_aggregate_risk) if risk is not None else None
                    ),
                },
            )
            return {
                "action": result.action if inserted else "DUPLICATE_SHADOW_DECISION",
                "position_id": position.id, "source_signal_id": metadata.source_signal_id,
                "category": evaluation.policy.category.value,
                "approved": evaluation.approved, "reason": evaluation.reason,
                "event_inserted": inserted,
            }
