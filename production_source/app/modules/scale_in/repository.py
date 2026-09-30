"""Transactional persistence for multi-lot positions and exactly-once fills."""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # register complete FK metadata

from .accounting import LotState, PositionLedger
from .entities import EntryFill, ExitFill, PositionState
from .models import (
    BrooksPosition, BrooksPositionEntryLot, BrooksPositionExitFill,
    BrooksPositionRiskSnapshot, BrooksPositionScaleEvent,
)

POSITION_VERSION = "brooks-multi-lot-position-v1"


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_position(self, *, signal_id: int | None, initial_source_signal_id: str,
                              mode: str, symbol: str, direction: str,
                              initial_trade_risk_budget: Decimal, executable_stop: Decimal,
                              metadata: dict | None = None) -> BrooksPosition:
        existing = await self.session.scalar(select(BrooksPosition).where(
            BrooksPosition.mode == mode,
            BrooksPosition.initial_source_signal_id == initial_source_signal_id,
        ))
        if existing is not None:
            return existing
        row = BrooksPosition(
            signal_id=signal_id, initial_source_signal_id=initial_source_signal_id,
            mode=mode, symbol=symbol, direction=direction, state=PositionState.OPEN.value,
            initial_trade_risk_budget=initial_trade_risk_budget,
            executable_stop=executable_stop, open_qty=Decimal("0"), avg_entry=None,
            realized_net_pnl=Decimal("0"), cumulative_fees=Decimal("0"),
            position_version=POSITION_VERSION, metadata_json=metadata or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_position(self, position_id: int, *, for_update: bool = False) -> BrooksPosition | None:
        stmt = select(BrooksPosition).where(BrooksPosition.id == position_id)
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list_entry_lots(self, position_id: int, *, for_update: bool = False) -> tuple[BrooksPositionEntryLot, ...]:
        stmt = select(BrooksPositionEntryLot).where(
            BrooksPositionEntryLot.position_id == position_id
        ).order_by(BrooksPositionEntryLot.id)
        if for_update:
            stmt = stmt.with_for_update()
        rows = (await self.session.scalars(stmt)).all()
        return tuple(rows)

    @staticmethod
    def _ledger(position: BrooksPosition, lots: tuple[BrooksPositionEntryLot, ...]) -> PositionLedger:
        ledger = PositionLedger(
            position_id=position.id, direction=position.direction,
            initial_trade_risk_budget=Decimal(position.initial_trade_risk_budget),
            executable_stop=Decimal(position.executable_stop),
        )
        ledger.state = PositionState(position.state)
        ledger.open_qty = Decimal(position.open_qty)
        ledger.avg_entry = Decimal(position.avg_entry) if position.avg_entry is not None else None
        ledger.realized_net_pnl = Decimal(position.realized_net_pnl)
        ledger.fees_paid = Decimal(position.cumulative_fees)
        ledger.lots = [LotState(
            execution_key=row.execution_key,
            fill_price=Decimal(row.fill_price), filled_qty=Decimal(row.filled_qty),
            open_qty=Decimal(row.open_qty), risk_buffer_per_unit=Decimal(row.risk_buffer_per_unit),
            scale_sequence_number=row.scale_sequence_number, entry_reason=row.entry_reason,
            setup_type=row.setup_type, rule_id=row.rule_id, metadata=dict(row.metadata_json or {}),
        ) for row in lots]
        ledger.entry_fill_keys = {row.execution_key for row in lots}
        return ledger

    async def apply_entry_fill(self, fill: EntryFill, *, snapshot_key: str) -> bool:
        position = await self.get_position(int(fill.position_id), for_update=True)
        if position is None:
            raise ValueError("position not found")
        lots = await self.list_entry_lots(position.id, for_update=True)
        if any(row.execution_key == fill.execution_key for row in lots):
            return False
        ledger = self._ledger(position, lots)
        changed = ledger.apply_entry_fill(fill)
        if not changed:
            return False
        self.session.add(BrooksPositionEntryLot(
            position_id=position.id, execution_key=fill.execution_key,
            client_order_id=fill.client_order_id, exchange_order_id=fill.exchange_order_id,
            fill_id=fill.fill_id, requested_qty=fill.requested_qty, filled_qty=fill.filled_qty,
            open_qty=fill.filled_qty, fill_price=fill.fill_price, fill_time=fill.fill_time,
            entry_reason=fill.entry_reason, setup_type=fill.setup_type, rule_id=fill.rule_id,
            scale_sequence_number=fill.scale_sequence_number,
            structural_stop_at_entry=fill.structural_stop_at_entry,
            risk_budget_at_entry=fill.risk_budget_at_entry, fee=fill.fee,
            slippage=fill.slippage, risk_buffer_per_unit=fill.risk_buffer_per_unit,
            fill_source=fill.fill_source, metadata_json=dict(fill.metadata),
        ))
        position.open_qty = ledger.open_qty
        position.avg_entry = ledger.avg_entry
        position.realized_net_pnl = ledger.realized_net_pnl
        position.cumulative_fees = ledger.fees_paid
        position.state = ledger.state.value
        await self._add_risk_snapshot(position, ledger, snapshot_key=snapshot_key, reason="ENTRY_FILL")
        await self.session.flush()
        return True

    async def apply_exit_fill(self, fill: ExitFill, *, snapshot_key: str) -> bool:
        position = await self.get_position(int(fill.position_id), for_update=True)
        if position is None:
            raise ValueError("position not found")
        duplicate = await self.session.scalar(select(BrooksPositionExitFill.id).where(
            BrooksPositionExitFill.position_id == position.id,
            BrooksPositionExitFill.execution_key == fill.execution_key,
        ))
        if duplicate is not None:
            return False
        lots = await self.list_entry_lots(position.id, for_update=True)
        ledger = self._ledger(position, lots)
        before_realized = ledger.realized_net_pnl
        changed = ledger.apply_exit_fill(fill)
        if not changed:
            return False
        for domain_lot, row in zip(ledger.lots, lots, strict=True):
            row.open_qty = domain_lot.open_qty
        realized_delta = ledger.realized_net_pnl - before_realized
        self.session.add(BrooksPositionExitFill(
            position_id=position.id, execution_key=fill.execution_key,
            client_order_id=fill.client_order_id, exchange_order_id=fill.exchange_order_id,
            fill_id=fill.fill_id, filled_qty=fill.filled_qty, fill_price=fill.fill_price,
            fill_time=fill.fill_time, exit_reason=fill.exit_reason,
            target_number=fill.target_number, fee=fill.fee,
            realized_net_pnl=realized_delta, metadata_json=dict(fill.metadata),
        ))
        position.open_qty = ledger.open_qty
        position.avg_entry = ledger.avg_entry
        position.realized_net_pnl = ledger.realized_net_pnl
        position.cumulative_fees = ledger.fees_paid
        position.state = ledger.state.value
        await self._add_risk_snapshot(position, ledger, snapshot_key=snapshot_key, reason="EXIT_FILL")
        await self.session.flush()
        return True

    async def record_scale_event(self, *, position_id: int, event_key: str, intent_id: str,
                                 state: str, category: str, desired_qty: Decimal,
                                 approved_qty: Decimal | None, expected_price: Decimal,
                                 structural_stop: Decimal, reason: str,
                                 client_order_id: str | None = None,
                                 exchange_order_id: str | None = None,
                                 metadata: dict | None = None) -> bool:
        existing = await self.session.scalar(select(BrooksPositionScaleEvent.id).where(
            BrooksPositionScaleEvent.position_id == position_id,
            BrooksPositionScaleEvent.event_key == event_key,
        ))
        if existing is not None:
            return False
        self.session.add(BrooksPositionScaleEvent(
            position_id=position_id, event_key=event_key, intent_id=intent_id,
            state=state, category=category, desired_qty=desired_qty,
            approved_qty=approved_qty, expected_price=expected_price,
            structural_stop=structural_stop, client_order_id=client_order_id,
            exchange_order_id=exchange_order_id, reason=reason,
            metadata_json=metadata or {},
        ))
        await self.session.flush()
        return True

    async def _add_risk_snapshot(self, position: BrooksPosition, ledger: PositionLedger, *,
                                 snapshot_key: str, reason: str) -> None:
        self.session.add(BrooksPositionRiskSnapshot(
            position_id=position.id, snapshot_key=snapshot_key, reason=reason,
            executable_stop=ledger.executable_stop, open_qty=ledger.open_qty,
            avg_entry=ledger.avg_entry, current_aggregate_risk=ledger.current_aggregate_risk,
            remaining_risk_budget=ledger.remaining_risk_budget, metadata_json={},
        ))

    async def update_executable_stop(self, position_id: int, new_stop: Decimal, *, snapshot_key: str) -> bool:
        """Tighten a SHADOW/managed position stop while preserving risk-budget invariants."""
        position = await self.get_position(position_id, for_update=True)
        if position is None:
            raise ValueError("position not found")
        if Decimal(position.executable_stop) == new_stop:
            return False
        lots = await self.list_entry_lots(position.id, for_update=True)
        ledger = self._ledger(position, lots)
        ledger.update_executable_stop(new_stop)
        position.executable_stop = ledger.executable_stop
        await self._add_risk_snapshot(
            position, ledger, snapshot_key=snapshot_key, reason="STOP_UPDATE"
        )
        await self.session.flush()
        return True
