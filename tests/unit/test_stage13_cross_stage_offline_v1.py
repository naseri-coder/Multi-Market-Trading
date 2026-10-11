"""Actual Stage 12 -> 5 -> 7 -> 10 and manually-authorized 8/9 acceptance.

All market events are SYNTHETIC; no Telegram transport, API key, feed client
or live order route is used. Stages intentionally have no automatic handoff.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import sqlite3

import pytest

from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import ClosedCandle, CoreEventType, DataOrigin, OfflineCoreHarness
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin, ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, MarketPacket, OfflineMarketDataEngine, PriceBasis, VolumeSemantics,
)
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from naseri_markets.strategy_orchestrator_v1 import (
    OfflineStrategyOrchestrator, TrustedCoreEvaluator,
)
from naseri_markets.trading_control_center_v1 import CoreListing, OfflineTradingControlCenter
from naseri_markets.reliability_acceptance_v1 import LedgerPaths, evaluate_offline_reliability

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
CORE = DualSetupExampleCore()
PROVIDER="example_offline_venue"
SYMBOL="ABCUSD"


def prepared_control(tmp_path):
    catalog = ResearchInstrumentCatalog(max_age_seconds=1800)
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    record = InstrumentMetadata(PROVIDER, Market.CRYPTO, SYMBOL, "UTC", "USD",
                                D("0.01"), origin, ListingStatus.OPEN, T0, "RESEARCH_PERPETUAL")
    catalog.replace(ProviderSnapshot(PROVIDER, origin, T0, (record,), "a" * 64))
    control = OfflineTradingControlCenter(
        tmp_path / "control.sqlite", admin_ids={7123}, catalog=catalog,
        listings=(CoreListing(CORE.manifest.core_id, "Public Test Dual Core",
                              CORE.manifest.core_version, manifest=CORE.manifest),), enabled=True,
    )
    status = control.create_instance(7123, core_id=CORE.manifest.core_id,
                                     instance_id="instance_demo", account_id="account_demo",
                                     portfolio_id="portfolio_demo")
    control.add_binding(7123, status.instance_id, provider=PROVIDER, symbol=SYMBOL,
                        timeframe="15m", now=T0, expected_revision=status.revision)
    revision = control.inspect(7123, "instance_demo").revision
    control.set_allocation(7123, "instance_demo", max_reserved=D("0.10"),
                           max_notional=D("0.50"),max_order=D("0.05"),max_orders=10,
                           expected_revision=revision)
    for field in ("analysis", "signals", "paper"):
        revision = control.inspect(7123, "instance_demo").revision
        control.set_request(7123,"instance_demo",field=field,requested=True,
                            expected_revision=revision)
    binding, = control.preview_bindings(7123, "instance_demo", now=T0)
    return control, binding


def produced_decision(binding):
    definition = FeedDefinition("feed_replay_test", binding.instrument,
                 binding.timeframe, CoreEventType.CLOSED_CANDLE, DataOrigin.SYNTHETIC,
                 "stage13_synthetic_fixture", PriceBasis.TRADE, VolumeSemantics.TRADED)
    data = OfflineMarketDataEngine(enabled=True)
    data.register_feed(definition)
    manager = OfflineStrategyOrchestrator(data, enabled=True)
    manager.attach(definition.feed_id, CORE.manifest, binding,
                   TrustedCoreEvaluator(OfflineCoreHarness(CORE,enabled=True),CORE.manifest))
    status = manager.state(binding.binding_id)
    manager.set_enabled(binding.binding_id, enabled=True,expected_revision=status.revision,
                        operator_ack=True)
    def candle(t, o,h,l,c):
        return ClosedCandle(t,t+timedelta(minutes=15),D(o),D(h),D(l),D(c),D(10))
    one = candle(T0,"100","102","98","100")
    two = candle(T0+timedelta(minutes=15),"100","108","99","106")
    for i,bar in enumerate((one,two),1):
        receipt=manager.ingest(MarketPacket(definition.feed_id,i,
                           bar.close_at+timedelta(seconds=1),definition.source_ref,candle=bar))
    outcome, = receipt.outcomes
    assert outcome.result is not None
    assert receipt.telegram_sent is False and receipt.broker_order_sent is False
    assert len(outcome.actionable_decisions)==1
    from naseri_markets.core_api_v1 import CoreInput
    event=CoreInput(CORE.manifest.core_id,CORE.manifest.core_version,binding,
          CoreEventType.CLOSED_CANDLE,two.close_at,DataOrigin.SYNTHETIC,
          definition.source_ref,(one,two))
    assert event.input_digest == outcome.result.input_digest
    return event, outcome.result, two


def test_cross_stage_preview_analysis_signal_and_restart_without_delivery(tmp_path):
    control,binding=prepared_control(tmp_path)
    try:
        event,result,_=produced_decision(binding)
        assert result.decisions[0].entry == D(106)
        with OfflineSignalLifecycle(tmp_path/"signals.sqlite",enabled=True) as signals:
            entry=result.decisions[0]
            got=signals.register(CORE.manifest,event,result,entry,channel_id=-10013,
                     price_basis=PriceBasis.TRADE,volume_semantics=VolumeSemantics.TRADED,
                     expires_at=event.observed_at+timedelta(minutes=30),operator_ack=True)
            assert got.message_id is None
            assert signals.register(CORE.manifest,event,result,entry,channel_id=-10013,
                     price_basis=PriceBasis.TRADE,volume_semantics=VolumeSemantics.TRADED,
                     expires_at=event.observed_at+timedelta(minutes=30),operator_ack=True).key==got.key
            assert len(signals.commands(got.key))==1
        with OfflineSignalLifecycle(tmp_path/"signals.sqlite",enabled=True) as again:
            assert len(again.commands(got.key))==1
            assert again.snapshot(got.key).message_id is None
        assert not control.inspect(7123,"instance_demo").telegram_publication_enabled
        assert not control.inspect(7123,"instance_demo").broker_orders_enabled
    finally:
        control.close()


def test_offline_manual_handoff_paper_and_signal_are_separate(tmp_path):
    # Stage 9 is present in the actual repository; minimal local Stage 12
    # fixture tree intentionally does not contain Stage 3 execution internals.
    pytest.importorskip("naseri_markets.execution_position_core_v1")
    from naseri_markets.paper_core_risk_bridge_v1 import CoreCapitalAllocation
    from naseri_markets.paper_order_lifecycle_v1 import (
        OfflinePaperPositionLifecycle, TargetStep,
    )
    from naseri_markets.risk_portfolio_contract_v1 import PortfolioRiskPolicy, AccountRiskPolicy

    control,binding=prepared_control(tmp_path)
    event,result,bar=produced_decision(binding)
    signal_path=tmp_path/"signals.sqlite"
    try:
        with OfflineSignalLifecycle(signal_path, enabled=True) as observer:
            observer.register(CORE.manifest,event,result,result.decisions[0],
                channel_id=-10013,price_basis=PriceBasis.TRADE,
                volume_semantics=VolumeSemantics.TRADED,
                expires_at=event.observed_at+timedelta(minutes=30),operator_ack=True)
        paper_path=tmp_path/"paper.sqlite"
        with OfflinePaperPositionLifecycle(paper_path) as paper:
            paper.configure_portfolio(PortfolioRiskPolicy("portfolio_demo","USD",D(100),D(5000),D(100),D(90),D(90),25))
            paper.configure_account(AccountRiskPolicy(
                "account_demo","portfolio_demo","USD",D(1000),D("0.05"),D("0.20"),D("0.20"),
                D(2),D("0.90"),D(3),D(1),D("0.01"),D("0.002"),D("0.003"),25,True))
            paper.register_instrument(portfolio_id="portfolio_demo",instrument=binding.instrument,group_id="CRYPTO")
            paper.register_allocation(CoreCapitalAllocation(
                "instance_demo",CORE.manifest.core_id,CORE.manifest.core_version,
                "account_demo","portfolio_demo",D("0.10"),D("0.50"),D("0.05"),10),operator_ack=True)
            paper.register_binding(CORE.manifest,binding,operator_ack=True)
            paper.set_enabled("instance_demo",enabled=True,expected_revision=1,operator_ack=True)
            decision=result.decisions[0]
            receipt=paper.reserve_entry(CORE.manifest,event,result,
                decision_id=decision.decision_id,quantity=D(1),
                price_basis=PriceBasis.TRADE,volume_semantics=VolumeSemantics.TRADED,
                expected_allocation_revision=2,operator_ack=True)
            paper.register_plan(CORE.manifest,event,result,decision_id=decision.decision_id,
                order_id=receipt.order_id,targets=(TargetStep(decision.targets[0],D(1)),),operator_ack=True)
            oid=receipt.order_id
            paper.apply_paper_event(oid,action_id="paper_submit",event="SUBMIT",expected_revision=0,operator_ack=True)
            paper.apply_paper_event(oid,action_id="paper_ack",event="ACK",expected_revision=1,
                remote_order_id="synthetic_ack_only",operator_ack=True)
            entry_bar=ClosedCandle(bar.close_at,bar.close_at+timedelta(minutes=15),
                        D(106),D(108),D(104),D(107),D(10))
            paper.apply_paper_event(oid,action_id="paper_fill",event="FILL",expected_revision=2,
                quantity=D(1),price=D(106),entry_bar=entry_bar,operator_ack=True)
            exit_bar=ClosedCandle(entry_bar.close_at,entry_bar.close_at+timedelta(minutes=15),
                       D(107),D(114),D(104),D(113),D(10))
            out=paper.step_closed_bar(oid,exit_bar,operator_ack=True)
            assert out["status"]=="CLOSED"
            assert not paper.performance(oid)["broker_verified"]
        control.close()
        gate=evaluate_offline_reliability(LedgerPaths(
            tmp_path/"control.sqlite",paper_path,signal_path))
        assert gate.integrity_verdict == "PASS",gate.blockers
        assert gate.release_verdict == "BLOCKED_NONPRODUCTION_UNATTESTED"
        assert gate.counts["paper_orders"] == gate.counts["signal_states"] == 1
        assert not gate.telegram_sent and not gate.broker_order_sent
        assert gate == evaluate_offline_reliability(LedgerPaths(tmp_path/"control.sqlite",paper_path,signal_path))
    finally:
        try:control.close()
        except sqlite3.ProgrammingError:pass
