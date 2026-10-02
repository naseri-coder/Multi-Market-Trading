"""Real PostgreSQL integration of durable approvals and V6 runner accounting."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select, update, text

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.operations.approval_evidence import (
    ApprovedMarketEvidence as E, RUNNER_EVENT, record_approved_candidate,
    open_runner_fraction, open_position_fraction,
)
from app.modules.operations.lifecycle import LiveSignalLifecycleService, LifecycleItem
from app.modules.operations.models import SignalLifecycleState
from app.modules.operations.trade_management import build_trade_management_plan
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signals.models import Signal, SignalTarget, SignalEvent

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="isolated PostgreSQL required")
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def chart(direction, end, timeframe="15m", noise=False):
    step = timedelta(minutes=15 if timeframe == "15m" else 60)
    result = []
    price = D("100")
    for i in range(80):
        delta = (D("0.02") if i % 2 else D("-0.02")) if noise else (
            D("0.6") if direction == "LONG" else D("-0.6"))
        close = price + delta
        at = end - step * (80-i)
        result.append(Candle(at, at+step, price, max(price,close)+D("0.05"),
                             min(price,close)-D("0.05"), close, D("10")))
        price = close
    return MarketSnapshot("binance","futures","BTCUSDT",timeframe,tuple(result),end)


async def approval(session, key, direction, at, *, accepted=True, timeframe="15m"):
    snapshot = chart(direction, at-timedelta(minutes=1), timeframe, noise=not accepted)
    context = assess_books_context(snapshot, policy=BrooksBooksPolicy())
    if accepted:
        assert context.always_in == direction
    candidate = NS(source_signal_id=key, snapshot=snapshot, exchange="binance",
                   market_type="futures",symbol="BTCUSDT",timeframe=timeframe,
                   direction=direction,engine_version="test-existing-core",configuration_version="test")
    stored = await record_approved_candidate(
        session,candidate=candidate,context=context,
        council=NS(approved=accepted),risk=NS(approved=accepted),
        quality=NS(approved=accepted,metadata={"always_in":context.always_in}),
        gate=NS(approved=accepted),
    )
    if stored:
        # Explicit historical fixture time, never production backdating.
        await session.execute(update(E).where(E.source_signal_id==key).values(approved_at=at))
    return stored


@pytest.mark.parametrize("case", [
    "positive", "noise", "lagging", "no_runner", "pending_target",
    "pending_then_stop", "wrong_timeframe", "stop_priority",
])
async def test_shared_evidence_runner_lifecycle(case, valid_token):
    settings=Settings(telegram_bot_token=valid_token,
        database_url=os.environ["TEST_DATABASE_URL"],_env_file=None)
    db=DatabaseManager.from_settings(settings)
    origin="origin-"+uuid4().hex; opposite="opposite-"+uuid4().hex
    signal_id=None
    try:
        async with db.session() as session, session.begin():
            signal=Signal(symbol="BTCUSDT",direction="LONG",entry_price=D("100"),
                stop_loss=D("98") if case=="no_runner" else D("101.5"),
                leverage=D("1"),status="OPEN",publication_scope="VIP",created_at=BASE)
            session.add(signal); await session.flush(); signal_id=signal.id
            pending=case in {"pending_target","pending_then_stop"}
            prices=(D("104"),D("106")) if pending else (D("102"),D("104"))
            targets=[]
            for i,price in enumerate(prices,1):
                hit=case!="no_runner" and (not pending or i==1)
                target=SignalTarget(signal_id=signal_id,target_number=i,target_price=price,
                    status="HIT" if hit else "PENDING",
                    hit_at=BASE+timedelta(minutes=10) if hit else None,
                    profit_loss=(price-D("100")) if hit else None)
                session.add(target); targets.append(target)
            plan=build_trade_management_plan(direction="LONG",entry_price=D("100"),
                initial_stop_loss=D("98"),targets=targets,
                market_regime="TRADING_RANGE" if case=="no_runner" else "BULL_TREND")
            meta=SignalAutomationMetadata(signal_id=signal_id,producer="BROOKS",
                generation_mode="LIVE",exchange="binance",market_type="futures",timeframe="15m",
                source_signal_id=origin,idempotency_key=uuid4().hex,
                market_snapshot_id="test",market_snapshot_hash="test",engine_version="test",
                rule_set_version="test",configuration_version="test",
                analysis_metadata={"trade_management_v6":plan.to_metadata()},
                counts_toward_performance=True,created_at=BASE)
            session.add(meta)
            session.add(SignalLifecycleState(signal_id=signal_id,state="ACTIVE",
                entry_activated_at=BASE+timedelta(minutes=5),
                last_processed_candle_close=BASE+timedelta(minutes=20)))
            assert await approval(session,origin,"LONG",BASE+timedelta(minutes=1))
            accepted=case!="noise"
            at=BASE+timedelta(minutes=25 if case=="lagging" else 19)
            assert await approval(session,opposite,"SHORT",at,accepted=accepted,
                timeframe="1h" if case=="wrong_timeframe" else "15m") == accepted
            if case=="no_runner":
                assert plan.remaining_fraction(targets)==D("1")
                assert open_runner_fraction(plan,targets)==0

        lifecycle=LiveSignalLifecycleService(database=db,provider=object(),bot=object(),
            vip_channel_id=1,cutover_at=BASE-timedelta(days=1),candle_limit=100)
        lifecycle._refresh_message=AsyncMock(return_value=True)
        # No stop algorithm is replaced: short fixture history gives no causal swing.
        item=LifecycleItem(signal,meta,None,tuple(targets))
        price=D("101") if case=="no_runner" else (D("105") if pending else D("103"))
        low=D("101") if case=="stop_priority" else price-D("0.2")
        candle=Candle(BASE+timedelta(minutes=20),BASE+timedelta(minutes=21),
                      price,price+D("0.2"),low,price,D("1"))
        await lifecycle._process_item(item,(candle,))
        async with db.session() as session:
            events=list((await session.scalars(select(SignalEvent).where(SignalEvent.signal_id==signal_id))).all())
            exits=[e for e in events if e.event_type==RUNNER_EVENT]
            current=await session.get(Signal,signal_id)
            if case in {"noise","lagging","no_runner","wrong_timeframe"}:
                assert not exits and current.status=="OPEN"
            elif case=="stop_priority":
                assert not exits and current.status=="CLOSED"
                assert any(e.event_type=="STOP_HIT" for e in events)
            else:
                assert len(exits)==1
                assert not any(e.event_type=="STOP_HIT" for e in events)
                expected=D("0.25") if pending else D("0.5")
                assert D(exits[0].event_metadata["exit_fraction"])==expected
                assert D(exits[0].event_metadata["exit_price"])==price
                assert current.status==("OPEN" if pending else "CLOSED")
                if not pending:
                    assert current.profit_loss==D("3.5")
                report=await session.execute(text(
                    "SELECT exit_fraction FROM brooks_runner_reversal_outcomes WHERE signal_id=:id"
                ),{"id":signal_id})
                assert report.scalar_one()==expected
                from app.modules.analytics.repository import SQLAlchemyWinRateRepository
                counts=await SQLAlchemyWinRateRepository(session).fetch_outcome_counts(
                    started_at=BASE,ended_at=BASE+timedelta(minutes=22))
                assert counts.runner_reversal == 1
                assert counts.target_hit == 0 and counts.stop_hit == 0
                remaining=open_position_fraction(plan,targets,exits[0])
                assert remaining==(D("0.25") if pending else D("0"))
        if case=="lagging":
            later=Candle(BASE+timedelta(minutes=26),BASE+timedelta(minutes=27),
                D("103"),D("103.2"),D("102.8"),D("103"),D("1"))
            await lifecycle._process_item(item,(candle,later))
            async with db.session() as session:
                exit_event=await session.scalar(select(SignalEvent).where(
                    SignalEvent.signal_id==signal_id,SignalEvent.event_type==RUNNER_EVENT))
                assert exit_event is not None and exit_event.created_at==later.close_time
        if pending:
            stop=case=="pending_then_stop"
            price=D("101.5") if stop else D("106")
            later=Candle(BASE+timedelta(minutes=21),BASE+timedelta(minutes=22),
                price,price+D("0.1"),price-D("0.1"),price,D("1"))
            await lifecycle._process_item(item,(candle,later))
            async with db.session() as session:
                current=await session.get(Signal,signal_id)
                assert current.status=="CLOSED"
                assert current.profit_loss==(D("3.625") if stop else D("4.75"))
        # Replaying a cycle must not create a second runner exit.
        await lifecycle._process_item(item,(candle,))
        async with db.session() as session:
            exits=list((await session.scalars(select(SignalEvent).where(
                SignalEvent.signal_id==signal_id,SignalEvent.event_type==RUNNER_EVENT))).all())
            assert len(exits)<=1
        print("CASE",case,"PASS; accounting, causality, persisted event and replay checked")
    finally:
        async with db.session() as session, session.begin():
            if signal_id is not None:
                await session.execute(delete(Signal).where(Signal.id==signal_id))
            await session.execute(delete(E).where(E.source_signal_id.in_([origin,opposite])))
        await db.dispose()
