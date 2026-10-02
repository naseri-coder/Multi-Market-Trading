from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.scale_in.entities import EntryFill, ExitFill, ReconciliationStatus
from app.modules.scale_in.models import (
    BrooksPositionEntryLot,
    BrooksPositionRiskSnapshot,
    BrooksPositionScaleEvent,
)
from app.modules.scale_in.reconciliation import ExchangeExecutionTruth, reconcile
from app.modules.scale_in.repository import PositionRepository
from app.modules.scale_in.policy import ScaleInPolicyContext
from app.modules.scale_in.shadow import ShadowScaleInEvaluator
from app.modules.performance_intelligence.collector import PerformanceCollector

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="isolated PostgreSQL required"
)
NOW = datetime(2026, 9, 14, 20, 0, tzinfo=UTC)


def session_factory():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def entry(key: str, position_id: int, price: str, qty: str, *, seq: int = 0,
          client_order_id: str | None = None) -> EntryFill:
    return EntryFill(
        execution_key=key,
        position_id=position_id,
        direction="LONG",
        filled_qty=D(qty),
        fill_price=D(price),
        fill_time=NOW,
        requested_qty=D(qty),
        entry_reason="POSTGRES_INTEGRATION_TEST",
        scale_sequence_number=seq,
        structural_stop_at_entry=D("90.000000000000000001"),
        risk_budget_at_entry=D("10.000000000000000000"),
        fee=D("0.000000000000000123"),
        slippage=D("0.000000000000000321"),
        risk_buffer_per_unit=D("0.000000000000000111"),
        client_order_id=client_order_id,
        fill_id=key,
        fill_source="FAKE_EXCHANGE",
    )


def exit_fill(key: str, position_id: int, price: str, qty: str) -> ExitFill:
    return ExitFill(
        execution_key=key,
        position_id=position_id,
        filled_qty=D(qty),
        fill_price=D(price),
        fill_time=NOW,
        exit_reason="TEST_EXIT",
        fee=D("0.000000000000000222"),
        fill_id=key,
    )


async def make_position(session, *, source: str = "pg-scalein-test"):
    repo = PositionRepository(session)
    return await repo.create_position(
        signal_id=9000001,
        initial_source_signal_id=source,
        mode="SHADOW",
        symbol="BTCUSDT",
        direction="LONG",
        initial_trade_risk_budget=D("10.000000000000000000"),
        executable_stop=D("90.000000000000000001"),
        metadata={"integration": True},
    )

from sqlalchemy import text


@pytest.mark.asyncio
async def test_repository_roundtrip_partial_fills_exits_and_numeric_fidelity():
    engine, Session = session_factory()
    try:
        async with Session() as s, s.begin():
            await s.execute(text("TRUNCATE brooks_positions CASCADE"))
            p = await make_position(s)
            repo = PositionRepository(s)
            f1 = entry("ord-a:fill-1", p.id, "100.123456789012345678", "0.125000000000000000", client_order_id="ord-a")
            f2 = entry("ord-a:fill-2", p.id, "99.876543210987654322", "0.125000000000000000", seq=1, client_order_id="ord-a")
            assert await repo.apply_entry_fill(f1, snapshot_key="risk-entry-1") is True
            assert await repo.apply_entry_fill(f2, snapshot_key="risk-entry-2") is True
            assert await repo.apply_entry_fill(f2, snapshot_key="risk-duplicate") is False
            assert p.open_qty == D("0.250000000000000000")
            assert p.avg_entry == D("100.000000000000000000")
            assert await repo.record_scale_event(
                position_id=p.id,event_key="evt-1",intent_id="intent-1",state="SCALE_IN_FILLED",
                category="ADD_ON_PULLBACK",desired_qty=D("0.125"),approved_qty=D("0.125"),
                expected_price=f2.fill_price,structural_stop=f2.structural_stop_at_entry,reason="TEST") is True
            e1 = exit_fill("exit-1", p.id, "101.111111111111111111", "0.100000000000000000")
            e2 = exit_fill("exit-2", p.id, "102.222222222222222222", "0.150000000000000000")
            assert await repo.apply_exit_fill(e1, snapshot_key="risk-exit-1") is True
            assert await repo.apply_exit_fill(e2, snapshot_key="risk-exit-2") is True
            assert p.open_qty == D("0")
            assert p.state == "CLOSED"
        async with Session() as s:
            repo = PositionRepository(s)
            p2 = await repo.get_position(p.id)
            lots = await repo.list_entry_lots(p.id)
            ledger = repo._ledger(p2, lots)
            assert ledger.open_qty == D("0")
            assert ledger.avg_entry is None
            perf = PerformanceCollector().collect_position(p2, entry_lot_count=len(lots))
            assert perf.signal_id == p2.signal_id
            assert perf.rr == D(p2.realized_net_pnl) / D(p2.initial_trade_risk_budget)
            assert perf.context["multi_lot_position"] is True
            assert [x.fill_price for x in lots] == [
                D("100.123456789012345678"), D("99.876543210987654322")]
            assert all(x.fee == D("0.000000000000000123") for x in lots)
            risks = (await s.scalars(select(BrooksPositionRiskSnapshot).where(
                BrooksPositionRiskSnapshot.position_id == p.id))).all()
            events = (await s.scalars(select(BrooksPositionScaleEvent).where(
                BrooksPositionScaleEvent.position_id == p.id))).all()
            assert len(risks) == 4
            assert len(events) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_transaction_rollback_unique_fk_and_cross_session_duplicate():
    engine, Session = session_factory()
    try:
        async with Session() as s:
            try:
                async with s.begin():
                    await make_position(s, source="rollback-test")
                    raise RuntimeError("force rollback")
            except RuntimeError:
                pass
        async with Session() as s:
            assert await s.scalar(text("SELECT count(*) FROM brooks_positions WHERE initial_source_signal_id='rollback-test'")) == 0
            repo = PositionRepository(s)
            p = await repo.get_position((await s.scalar(text("SELECT id FROM brooks_positions WHERE initial_source_signal_id='pg-scalein-test'"))))
            assert p is not None
            lots = await repo.list_entry_lots(p.id)
            original = lots[0]
            dup = BrooksPositionEntryLot(
                position_id=p.id, execution_key=original.execution_key,
                requested_qty=original.requested_qty, filled_qty=original.filled_qty, open_qty=D("0.01"),
                fill_price=original.fill_price, fill_time=NOW, entry_reason="DUP", scale_sequence_number=3,
                structural_stop_at_entry=original.structural_stop_at_entry, risk_budget_at_entry=D("1"),
                fee=D("0"), slippage=D("0"), risk_buffer_per_unit=D("0"), fill_source="TEST", metadata_json={})
            s.add(dup)
            with pytest.raises(IntegrityError):
                await s.flush()
            await s.rollback()
        async with Session() as s:
            bad = BrooksPositionRiskSnapshot(
                position_id=999999999,snapshot_key="bad-fk",reason="TEST",
                executable_stop=D("1"),open_qty=D("0"),avg_entry=None,
                current_aggregate_risk=D("0"),remaining_risk_budget=D("1"),metadata_json={})
            s.add(bad)
            with pytest.raises(IntegrityError):
                await s.flush()
            await s.rollback()
        async with Session() as s, s.begin():
            cp = await make_position(s, source="concurrent-test")
            p_id = cp.id
            repo = PositionRepository(s)
            assert await repo.apply_entry_fill(entry("concurrent-seed", p_id, "100", "0.010000000000000000"), snapshot_key="concurrent-seed-risk")
        duplicate = entry("concurrent-fill", p_id, "100.500000000000000001", "0.010000000000000000", seq=1)
        async def apply_once():
            async with Session() as s, s.begin():
                return await PositionRepository(s).apply_entry_fill(duplicate, snapshot_key="concurrent-risk")
        results = await asyncio.gather(apply_once(), apply_once())
        assert sorted(results) == [False, True]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_partial_fill_recovery_and_reconciliation_exactly_once():
    engine, Session = session_factory()
    try:
        async with Session() as s, s.begin():
            p = await make_position(s, source="recovery-test")
            repo = PositionRepository(s)
            local = entry("recovery-local", p.id, "100", "0.050000000000000000")
            assert await repo.apply_entry_fill(local, snapshot_key="recovery-local-risk")
            for key,state in (("pending","SCALE_IN_ORDER_PENDING"),("partial","SCALE_IN_PARTIALLY_FILLED")):
                assert await repo.record_scale_event(position_id=p.id,event_key=key,intent_id="intent-r",
                    state=state,category="ADD_ON_PULLBACK",desired_qty=D("0.05"),approved_qty=D("0.05"),
                    expected_price=D("99"),structural_stop=D("90"),reason="FAKE_EXCHANGE_TEST")
        async with Session() as s, s.begin():
            repo=PositionRepository(s); p=await repo.get_position(p.id); lots=await repo.list_entry_lots(p.id)
            truth=ExchangeExecutionTruth(open_qty=D("0.100000000000000000"),fill_keys=("recovery-local","recovery-remote"))
            result=reconcile(local_open_qty=p.open_qty,local_fill_keys=tuple(x.execution_key for x in lots),exchange=truth)
            assert result.status is ReconciliationStatus.EXCHANGE_AHEAD
            remote=entry("recovery-remote",p.id,"99","0.050000000000000000",seq=1)
            assert await repo.apply_entry_fill(remote,snapshot_key="recovery-remote-risk") is True
            assert await repo.apply_entry_fill(remote,snapshot_key="recovery-remote-risk-dup") is False
            assert await repo.record_scale_event(position_id=p.id,event_key="filled",intent_id="intent-r",
                state="SCALE_IN_FILLED",category="ADD_ON_PULLBACK",desired_qty=D("0.05"),approved_qty=D("0.05"),
                expected_price=D("99"),structural_stop=D("90"),reason="FAKE_EXCHANGE_TEST")
        async with Session() as s:
            repo=PositionRepository(s); p=await repo.get_position(p.id); lots=await repo.list_entry_lots(p.id)
            result=reconcile(local_open_qty=p.open_qty,local_fill_keys=tuple(x.execution_key for x in lots),
                exchange=ExchangeExecutionTruth(open_qty=p.open_qty,fill_keys=tuple(x.execution_key for x in lots)))
            assert result.status is ReconciliationStatus.IN_SYNC
            states=(await s.scalars(select(BrooksPositionScaleEvent.state).where(
                BrooksPositionScaleEvent.position_id==p.id).order_by(BrooksPositionScaleEvent.id))).all()
            assert states == ["SCALE_IN_ORDER_PENDING","SCALE_IN_PARTIALLY_FILLED","SCALE_IN_FILLED"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_backed_shadow_evaluation_does_not_mutate_durable_position():
    engine, Session = session_factory()
    try:
        async with Session() as s, s.begin():
            p=await make_position(s,source="shadow-immutability-test"); repo=PositionRepository(s)
            assert await repo.apply_entry_fill(entry("shadow-seed",p.id,"100","0.100000000000000000"),snapshot_key="shadow-seed-risk")
        async with Session() as s:
            repo=PositionRepository(s); p=await repo.get_position(p.id); lots=await repo.list_entry_lots(p.id)
            ledger=repo._ledger(p,lots)
            before=(p.open_qty,p.avg_entry,p.executable_stop,p.realized_net_pnl,
                    tuple((x.execution_key,x.open_qty) for x in lots))
            ctx=ScaleInPolicyContext(direction="LONG",position_state=ledger.state,
                always_in="LONG",market_regime="STRONG_TREND",setup_type="BREAKOUT_PULLBACK_LONG",
                full_pipeline_approved=True,premise_valid=True,unrealized_pnl=D("1"))
            result=ShadowScaleInEvaluator().evaluate(position=ledger,context=ctx,
                desired_qty=D("0.010000000000000000"),expected_price=D("101"),
                structural_stop=D("90.000000000000000001"),qty_step=D("0.000000000000000001"))
            assert result.hypothetical_open_qty >= ledger.open_qty
            await s.commit()
        async with Session() as s:
            repo=PositionRepository(s); p2=await repo.get_position(p.id); lots2=await repo.list_entry_lots(p.id)
            after=(p2.open_qty,p2.avg_entry,p2.executable_stop,p2.realized_net_pnl,
                   tuple((x.execution_key,x.open_qty) for x in lots2))
            assert after == before
    finally:
        await engine.dispose()


from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete
from app.modules.operations.models import SignalLifecycleState
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signals.models import Signal, SignalEvent
from app.modules.scale_in.models import BrooksPosition
from app.modules.scale_in.runtime_observer import ShadowScaleInObserver


@pytest.mark.asyncio
async def test_shadow_observer_persists_only_shadow_state_and_is_idempotent():
    engine, Session = session_factory()
    source = "observer-active-" + uuid4().hex
    candidate_source = "observer-candidate-" + uuid4().hex
    signal_id = None

    class DB:
        @asynccontextmanager
        async def session(self):
            async with Session() as session:
                yield session

    try:
        async with Session() as s, s.begin():
            signal = Signal(symbol="BTCUSDT", direction="LONG", entry_price=D("100"),
                stop_loss=D("90"), leverage=D("1"), status="OPEN",
                description="shadow observer integration", publication_scope="VIP")
            s.add(signal); await s.flush(); signal_id = signal.id
            s.add(SignalAutomationMetadata(
                signal_id=signal.id, producer="BROOKS", generation_mode="LIVE",
                exchange="binance", market_type="futures", timeframe="15m",
                setup_type="BREAKOUT_PULLBACK_LONG", source_signal_id=source,
                idempotency_key="observer-" + uuid4().hex,
                market_snapshot_id="snapshot-initial", market_snapshot_hash="hash-initial",
                engine_version="brooks-trilogy-full-core-v5-context-structural",
                rule_set_version="brooks-trilogy-full-source-catalog-v6",
                configuration_version="observer-test", reasoning=[], rule_ids=[], failed_rules=[],
                analysis_metadata={"trade_management_v6":{"initial_stop_loss":"90"}},
                counts_toward_performance=True,
            ))
            s.add(SignalLifecycleState(
                signal_id=signal.id, state="ACTIVE",
                entry_activated_at=NOW.replace(minute=0) - __import__("datetime").timedelta(minutes=15),
                last_processed_candle_close=NOW.replace(minute=15), last_market_price=D("100.5"),
            ))
            s.add(SignalEvent(signal_id=signal.id, event_type="CREATED",
                metadata={"entry_price":"100","stop_loss":"90"}, created_at=NOW.replace(minute=0)))

        async with Session() as s:
            before = (await s.execute(text(
                "SELECT symbol,direction,entry_price,stop_loss,status FROM signals WHERE id=:id"
            ), {"id":signal_id})).one()

        candidate = SimpleNamespace(
            source_signal_id=candidate_source, symbol="BTCUSDT", timeframe="15m",
            direction="LONG", entry_price=D("101"), stop_loss=D("95"),
            setup_type="BREAKOUT_PULLBACK_LONG", market_snapshot_id="shadow-candidate-snap",
            snapshot=SimpleNamespace(captured_at=NOW),
        )
        quality = SimpleNamespace(metadata={"always_in":"LONG","market_regime":"BULL_TREND"})
        observer = ShadowScaleInObserver(DB())
        first = await observer.observe(candidate=candidate, signal_quality=quality)
        second = await observer.observe(candidate=candidate, signal_quality=quality)
        assert first["action"] == "SHADOW_SCALE_APPROVED"
        assert first["approved"] is True
        assert second["action"] == "NO_ACTION"
        assert second["reason"] == "MAX_SCALE_ADDS_REACHED"

        async with Session() as s:
            after = (await s.execute(text(
                "SELECT symbol,direction,entry_price,stop_loss,status FROM signals WHERE id=:id"
            ), {"id":signal_id})).one()
            assert after == before
            position = await s.scalar(select(BrooksPosition).where(
                BrooksPosition.initial_source_signal_id == source,
                BrooksPosition.mode == "SHADOW"))
            assert position is not None
            lots = (await s.scalars(select(BrooksPositionEntryLot).where(
                BrooksPositionEntryLot.position_id == position.id))).all()
            events = (await s.scalars(select(BrooksPositionScaleEvent).where(
                BrooksPositionScaleEvent.position_id == position.id))).all()
            assert len(lots) == 1
            assert lots[0].fill_source == "SHADOW"
            assert len(events) == 1 and events[0].state == "SCALE_IN_APPROVED"
            assert position.open_qty == lots[0].filled_qty
    finally:
        if signal_id is not None:
            async with Session() as s, s.begin():
                position_ids = (await s.scalars(select(BrooksPosition.id).where(
                    BrooksPosition.initial_source_signal_id == source))).all()
                if position_ids:
                    await s.execute(delete(BrooksPosition).where(BrooksPosition.id.in_(position_ids)))
                await s.execute(delete(Signal).where(Signal.id == signal_id))
        await engine.dispose()


@pytest.mark.asyncio
async def test_shadow_observer_older_active_not_hidden_by_newer_waiting_entry():
    engine, Session = session_factory()
    token = uuid4().hex
    active_source = "observer-old-active-" + token
    pending_source = "observer-new-pending-" + token
    signal_ids: list[int] = []

    class DB:
        @asynccontextmanager
        async def session(self):
            async with Session() as session:
                yield session

    async def seed(s, *, source: str, state: str, activated_at, created_at):
        signal = Signal(symbol="ETHUSDT", direction="LONG", entry_price=D("100"),
            stop_loss=D("90"), leverage=D("1"), status="OPEN",
            description=source, publication_scope="VIP")
        s.add(signal); await s.flush(); signal_ids.append(signal.id)
        s.add(SignalAutomationMetadata(
            signal_id=signal.id, producer="BROOKS", generation_mode="LIVE",
            exchange="binance", market_type="futures", timeframe="15m",
            setup_type="BREAKOUT_PULLBACK_LONG", source_signal_id=source,
            idempotency_key="observer-" + uuid4().hex,
            market_snapshot_id="snap-" + source, market_snapshot_hash="hash-" + source,
            engine_version="brooks-trilogy-full-core-v5-context-structural",
            rule_set_version="brooks-trilogy-full-source-catalog-v6",
            configuration_version="observer-test", reasoning=[], rule_ids=[], failed_rules=[],
            analysis_metadata={"trade_management_v6":{"initial_stop_loss":"90"}},
            counts_toward_performance=True,
        ))
        s.add(SignalLifecycleState(
            signal_id=signal.id, state=state, entry_activated_at=activated_at,
            last_processed_candle_close=NOW.replace(minute=15), last_market_price=D("100.5"),
        ))
        s.add(SignalEvent(signal_id=signal.id, event_type="CREATED",
            metadata={"entry_price":"100","stop_loss":"90"}, created_at=created_at))
        return signal.id

    try:
        async with Session() as s, s.begin():
            older_active = await seed(
                s, source=active_source, state="ACTIVE",
                activated_at=NOW.replace(minute=0) - __import__("datetime").timedelta(minutes=30),
                created_at=NOW.replace(minute=0) - __import__("datetime").timedelta(minutes=45),
            )
            newer_pending = await seed(
                s, source=pending_source, state="WAITING_ENTRY", activated_at=None,
                created_at=NOW.replace(minute=0) - __import__("datetime").timedelta(minutes=5),
            )
            assert newer_pending > older_active

        candidate = SimpleNamespace(
            source_signal_id="observer-edge-candidate-" + token, symbol="ETHUSDT", timeframe="15m",
            direction="LONG", entry_price=D("101"), stop_loss=D("95"),
            setup_type="BREAKOUT_PULLBACK_LONG", market_snapshot_id="edge-shadow-snap",
            snapshot=SimpleNamespace(captured_at=NOW),
        )
        quality = SimpleNamespace(metadata={"always_in":"LONG","market_regime":"BULL_TREND"})
        result = await ShadowScaleInObserver(DB()).observe(candidate=candidate, signal_quality=quality)
        assert result["source_signal_id"] == active_source
        async with Session() as s:
            position = await s.scalar(select(BrooksPosition).where(
                BrooksPosition.initial_source_signal_id == active_source,
                BrooksPosition.mode == "SHADOW"))
            assert position is not None and position.signal_id == older_active
            hidden_wrong = await s.scalar(select(BrooksPosition).where(
                BrooksPosition.initial_source_signal_id == pending_source,
                BrooksPosition.mode == "SHADOW"))
            assert hidden_wrong is None
    finally:
        async with Session() as s, s.begin():
            position_ids = (await s.scalars(select(BrooksPosition.id).where(
                BrooksPosition.initial_source_signal_id.in_((active_source, pending_source))))).all()
            if position_ids:
                await s.execute(delete(BrooksPosition).where(BrooksPosition.id.in_(position_ids)))
            if signal_ids:
                await s.execute(delete(Signal).where(Signal.id.in_(signal_ids)))
        await engine.dispose()


@pytest.mark.asyncio
async def test_shadow_observer_waiting_entry_remains_ineligible():
    engine, Session = session_factory()
    token = uuid4().hex
    source = "observer-waiting-" + token
    signal_id = None

    class DB:
        @asynccontextmanager
        async def session(self):
            async with Session() as session:
                yield session

    try:
        async with Session() as s, s.begin():
            signal = Signal(
                symbol="XRPUSDT", direction="LONG", entry_price=D("1.00"),
                stop_loss=D("0.90"), leverage=D("1"), status="OPEN",
                description=source, publication_scope="VIP",
            )
            s.add(signal); await s.flush(); signal_id = signal.id
            s.add(SignalAutomationMetadata(
                signal_id=signal.id, producer="BROOKS", generation_mode="LIVE",
                exchange="binance", market_type="futures", timeframe="15m",
                setup_type="BREAKOUT_PULLBACK_LONG", source_signal_id=source,
                idempotency_key="observer-" + uuid4().hex,
                market_snapshot_id="snap-" + source, market_snapshot_hash="hash-" + source,
                engine_version="brooks-trilogy-full-core-v5-context-structural",
                rule_set_version="brooks-trilogy-full-source-catalog-v6",
                configuration_version="observer-test", reasoning=[], rule_ids=[], failed_rules=[],
                analysis_metadata={"trade_management_v6":{"initial_stop_loss":"0.90"}},
                counts_toward_performance=True,
            ))
            s.add(SignalLifecycleState(
                signal_id=signal.id, state="WAITING_ENTRY", entry_activated_at=None,
                last_processed_candle_close=NOW.replace(minute=15), last_market_price=D("0.98"),
            ))
            s.add(SignalEvent(
                signal_id=signal.id, event_type="CREATED",
                metadata={"entry_price":"1.00","stop_loss":"0.90"}, created_at=NOW.replace(minute=0),
            ))

        candidate = SimpleNamespace(
            source_signal_id="observer-waiting-candidate-" + token, symbol="XRPUSDT", timeframe="15m",
            direction="LONG", entry_price=D("1.01"), stop_loss=D("0.95"),
            setup_type="BREAKOUT_PULLBACK_LONG", market_snapshot_id="waiting-shadow-snap",
            snapshot=SimpleNamespace(captured_at=NOW),
        )
        quality = SimpleNamespace(metadata={"always_in":"LONG","market_regime":"BULL_TREND"})
        result = await ShadowScaleInObserver(DB()).observe(candidate=candidate, signal_quality=quality)
        assert result == {"action":"NO_ACTION", "reason":"NO_ELIGIBLE_ACTIVE_POSITION"}

        async with Session() as s:
            position = await s.scalar(select(BrooksPosition).where(
                BrooksPosition.initial_source_signal_id == source, BrooksPosition.mode == "SHADOW"
            ))
            assert position is None
    finally:
        if signal_id is not None:
            async with Session() as s, s.begin():
                await s.execute(delete(Signal).where(Signal.id == signal_id))
        await engine.dispose()
