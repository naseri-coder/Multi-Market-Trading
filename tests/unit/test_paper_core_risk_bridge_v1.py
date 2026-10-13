"""Stage 8: exact cross-core PAPER risk reservation; no external effects."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle, CoreBinding, CoreEventType, CoreInput, DataOrigin, DecisionKind,
)
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.market_data_engine_v1 import PriceBasis, VolumeSemantics
from naseri_markets.paper_core_risk_bridge_v1 import (
    CoreCapitalAllocation, CoreRiskRefused, PaperCoreRiskBridge,
)
from naseri_markets.risk_portfolio_contract_v1 import PortfolioRiskPolicy, AccountRiskPolicy

CORE = OfflineContractFixture()
BASE = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)


def inst(symbol="ALPHAUSD", market=Market.CRYPTO):
    return Instrument(market, "offline_example_provider", symbol, "UTC", "USD")


def allocation(instance="instance_a", *, risk="0.03", notional="0.50", per_order="0.02",
               limit=10, account="account_one"):
    return CoreCapitalAllocation(instance, CORE.manifest.core_id, CORE.manifest.core_version,
                                 account, "portfolio_one", D(risk), D(notional),
                                 D(per_order), limit)


def binding(instance="instance_a", name="binding_a", symbol="ALPHAUSD"):
    return CoreBinding(instance, name, inst(symbol), "15m")


def event_result(b, *, period=0, close="106", low="99", previous_high="102"):
    t = BASE + timedelta(minutes=30 * period)
    one = ClosedCandle(t, t+timedelta(minutes=15), D("100"), D(previous_high),
                       D("98"), D("100"), D("10"))
    two = ClosedCandle(t+timedelta(minutes=15), t+timedelta(minutes=30), D("100"),
                       D("108"), D(low), D(close), D("10"))
    event = CoreInput(CORE.manifest.core_id, CORE.manifest.core_version, b,
                      CoreEventType.CLOSED_CANDLE, two.close_at, DataOrigin.SYNTHETIC,
                      "approved_offline_fixture", (one, two))
    result = CORE.evaluate(event)
    assert result.decisions[0].kind is DecisionKind.ENTRY_INTENT
    return event, result


def pp(**kwargs):
    args = dict(portfolio_id="portfolio_one", currency="USD", max_reserved_risk=D("100"),
                max_notional=D("10000"), max_daily_loss=D("100"),
                max_group_risk=D("75"), max_engine_risk=D("70"), max_active_orders=40)
    return PortfolioRiskPolicy(**(args | kwargs))


def ap(account="account_one", **kwargs):
    args = dict(account_id=account, portfolio_id="portfolio_one", currency="USD", equity=D("1000"),
                max_order_risk_fraction=D("0.05"), max_total_risk_fraction=D("0.15"),
                max_daily_loss_fraction=D("0.18"), max_notional_fraction=D("2"),
                max_margin_fraction=D("0.9"), max_leverage=D("3"),
                contract_multiplier=D("1"), quantity_step=D("0.01"),
                roundtrip_fee_fraction=D("0.002"), worst_slippage_fraction=D("0.003"),
                max_active_orders=40, external_exposure_cleared=True)
    return AccountRiskPolicy(**(args | kwargs))


def setup(path, *, policies=None, account_kwargs=None):
    x = PaperCoreRiskBridge(path)
    x.configure_portfolio(pp(**(policies or {})))
    x.configure_account(ap(**(account_kwargs or {})))
    for symbol in ("ALPHAUSD", "BETAUSD"):
        x.register_instrument(portfolio_id="portfolio_one", instrument=inst(symbol),
                              group_id="ONE_CORRELATED_GROUP")
    x.register_allocation(allocation(), operator_ack=True)
    x.register_binding(CORE.manifest, binding(), operator_ack=True)
    x.set_enabled("instance_a", enabled=True, expected_revision=1, operator_ack=True)
    return x


def reserve(x, b=None, *, period=0, quantity="1", close="106", low="99", rev=2,
            basis=PriceBasis.TRADE, volume=VolumeSemantics.TRADED):
    b = b or binding()
    event, result = event_result(b, period=period, close=close, low=low)
    return x.reserve_entry(CORE.manifest, event, result,
                           decision_id=result.decisions[0].decision_id, quantity=D(quantity),
                           price_basis=basis, volume_semantics=volume,
                           expected_allocation_revision=rev, operator_ack=True)


def test_stage8_creates_only_simulated_unfilled_order_and_reserves_portfolio(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        receipt = reserve(x)
        assert receipt.status == "PAPER_CREATED"
        assert receipt.broker_order_sent is False and receipt.telegram_sent is False
        assert x.order_state(receipt.order_id)["status"] == "CREATED"
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 1
        assert D(receipt.modeled_risk) == D("7.530")
        assert x.status("instance_a")["modeled_reserved_risk"] == receipt.modeled_risk


def test_cross_restart_same_decision_exactly_once_and_conflict(tmp_path):
    path=tmp_path/"risk.sqlite"
    with setup(path) as x:
        first = reserve(x)
        assert reserve(x) == first
    with PaperCoreRiskBridge(path) as x:
        assert reserve(x) == first
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 1
        with pytest.raises(CoreRiskRefused, match="DECISION_REPLAY_CONFLICT"):
            reserve(x, quantity="1.01")
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 1


def test_instance_per_order_risk_cap(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        with pytest.raises(CoreRiskRefused, match="INSTANCE_ORDER_RISK_CAP"):
            reserve(x, quantity="3")
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 0


def test_instance_notional_cap_before_writing(tmp_path):
    with PaperCoreRiskBridge(tmp_path/"risk.sqlite") as x:
        x.configure_portfolio(pp())
        x.configure_account(ap())
        x.register_instrument(portfolio_id="portfolio_one", instrument=inst(), group_id="G")
        x.register_allocation(allocation(notional="0.05"), operator_ack=True)
        x.register_binding(CORE.manifest, binding(), operator_ack=True)
        x.set_enabled("instance_a", enabled=True, expected_revision=1, operator_ack=True)
        with pytest.raises(CoreRiskRefused, match="INSTANCE_NOTIONAL_CAP"):
            reserve(x, quantity="1")
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 0


def test_same_instance_aggregates_across_distinct_bindings(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        other=binding(name="binding_b", symbol="BETAUSD")
        x.register_binding(CORE.manifest, other, operator_ack=True)
        reserve(x, quantity="1.5")
        reserve(x, other, quantity="1.5")
        assert x.status("instance_a")["active_orders"] == 2
        with pytest.raises(CoreRiskRefused, match="INSTANCE_TOTAL_RISK_CAP"):
            reserve(x, period=1, quantity="1.5")
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 2


def test_instance_active_order_limit(tmp_path):
    path=tmp_path/"limit.sqlite"
    with PaperCoreRiskBridge(path) as x:
        x.configure_portfolio(pp())
        x.configure_account(ap())
        x.register_instrument(portfolio_id="portfolio_one", instrument=inst(),group_id="G")
        x.register_allocation(allocation(limit=1),operator_ack=True)
        x.register_binding(CORE.manifest,binding(),operator_ack=True)
        x.set_enabled("instance_a",enabled=True,expected_revision=1,operator_ack=True)
        reserve(x)
        with pytest.raises(CoreRiskRefused, match="INSTANCE_ORDER_LIMIT"):
            reserve(x,period=1)


def test_account_risk_across_independent_instances_is_shared(tmp_path):
    with setup(tmp_path/"risk.sqlite",account_kwargs={"max_total_risk_fraction":D("0.01")}) as x:
        x.register_allocation(allocation("instance_b"),operator_ack=True)
        another=binding("instance_b","binding_b","BETAUSD")
        x.register_binding(CORE.manifest,another,operator_ack=True)
        x.set_enabled("instance_b",enabled=True,expected_revision=1,operator_ack=True)
        reserve(x)
        with pytest.raises(Exception, match="ACCOUNT_RESERVED_RISK_CAP"):
            reserve(x,another)
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 1


def test_halt_denies_new_orders_without_changing_existing(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        reserve(x)
        x._engine.halt(portfolio_id="portfolio_one",scope="engine",subject_id=CORE.manifest.core_id,
                       action_id="operator_halt")
        with pytest.raises(Exception,match="NEW_RISK_HALTED"):
            reserve(x,period=1)
        assert x.status("instance_a")["active_orders"] == 1


def test_disable_cas_blocks_new_but_keeps_existing_and_replay(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        first=reserve(x)
        with pytest.raises(CoreRiskRefused,match="STALE_ALLOCATION"):
            x.set_enabled("instance_a",enabled=False,expected_revision=1,operator_ack=True)
        x.set_enabled("instance_a",enabled=False,expected_revision=2,operator_ack=True)
        assert reserve(x) == first
        with pytest.raises(CoreRiskRefused,match="ALLOCATION_DISABLED"):
            reserve(x,period=1,rev=3)
        assert x.status("instance_a")["active_orders"] == 1


def test_missing_exposure_attestation_fail_closed(tmp_path):
    with setup(tmp_path/"risk.sqlite",account_kwargs={"external_exposure_cleared":False}) as x:
        with pytest.raises(CoreRiskRefused,match="EXTERNAL_EXPOSURE_UNVERIFIED"):
            reserve(x)


def test_tampered_binding_manifest_or_core_output_rejected(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        other=binding(name="unregistered")
        event,result=event_result(other)
        with pytest.raises(CoreRiskRefused, match="UNREGISTERED_OR_DRIFTED"):
            x.reserve_entry(CORE.manifest,event,result,
                decision_id=result.decisions[0].decision_id,quantity=D("1"),
                price_basis=PriceBasis.TRADE,volume_semantics=VolumeSemantics.TRADED,
                expected_allocation_revision=2,operator_ack=True)
        event,result=event_result(binding())
        bad=replace(result,input_digest="0"*64)
        with pytest.raises(ValueError,match="RESULT_IDENTITY_OR_PROVENANCE"):
            x.reserve_entry(CORE.manifest,event,bad,
                decision_id=result.decisions[0].decision_id,quantity=D("1"),
                price_basis=PriceBasis.TRADE,volume_semantics=VolumeSemantics.TRADED,
                expected_allocation_revision=2,operator_ack=True)
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 0


def test_reject_unverified_market_price_basis_and_wrong_volume(tmp_path):
    with setup(tmp_path/"risk.sqlite") as x:
        with pytest.raises(CoreRiskRefused,match="CRYPTO_EXECUTION_BASIS_UNVERIFIED"):
            reserve(x,basis=PriceBasis.MARK)
        with pytest.raises(CoreRiskRefused,match="CRYPTO_EXECUTION_BASIS_UNVERIFIED"):
            reserve(x,volume=VolumeSemantics.TICK_COUNT)
        assert x.status("instance_a")["active_orders"] == 0


def test_malformed_allocation_and_missing_ack():
    with pytest.raises(CoreRiskRefused,match="PER_ORDER_EXCEEDS"):
        allocation(risk="0.005",per_order="0.01")
    with pytest.raises(CoreRiskRefused,match="INVALID_MAX_NOTIONAL"):
        allocation(notional="1.5")


def test_stage3_crash_rolls_back_stage8_receipt_and_risk(tmp_path,monkeypatch):
    with setup(tmp_path/"risk.sqlite") as x:
        def crash(*args,**kwargs):
            raise RuntimeError("SIMULATED_STAGE3_CRASH")
        previous=x._engine._orders.create
        monkeypatch.setattr(x._engine._orders,"create",crash)
        with pytest.raises(RuntimeError,match="SIMULATED_STAGE3_CRASH"):
            reserve(x)
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 0
        assert x.status("instance_a")["active_orders"] == 0
        assert x._db.execute("SELECT count(*) FROM paper_core_decisions").fetchone()[0] == 0
        monkeypatch.setattr(x._engine._orders,"create",previous)
        reserve(x)
        assert x.risk_snapshot("portfolio_one")["active_orders"] == 1


def test_no_implicit_activation_credentials_channel_or_live_execution(tmp_path):
    with PaperCoreRiskBridge(tmp_path/"fresh.sqlite") as x:
        assert x._db.execute("SELECT count(*) FROM paper_core_decisions").fetchone()[0] == 0
        with pytest.raises(CoreRiskRefused,match="EXPLICIT_POLICY_APPROVAL"):
            x.register_allocation(allocation())
    from inspect import getsource
    import naseri_markets.paper_core_risk_bridge_v1 as module
    source=getsource(module)
    assert "order_send(" not in source and "send_message(" not in source
    assert "socket.connect(" not in source