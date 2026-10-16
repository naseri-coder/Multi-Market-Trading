"""R30 synthetic isolation tests: no real accounts, brokers or orders."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Direction, EvidenceMode, Instrument, Market
from naseri_markets.execution_contract_v1 import OrderKind, OrderSpec, OrderStatus
from naseri_markets.mmt_r30_offline_risk_order_preflight_v1 import (
    R30ActiveReservation,
    R30RiskRefused,
    evaluate_r30_offline_preorder_risk,
)
from naseri_markets.risk_portfolio_contract_v1 import (
    AccountRiskPolicy,
    PortfolioRiskPolicy,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def example():
    instrument = Instrument(Market.CRYPTO, "sample_venue", "BTCUSDT", "UTC", "USDT")
    proposal = OrderSpec(
        "order_r30_first", "signal_r30_first", "account_r30", "brooks_public",
        instrument, Direction.LONG, OrderKind.MARKET,
        D("1"), D("100"), D("98"), D("104"), EvidenceMode.PAPER,
    )
    account = AccountRiskPolicy(
        account_id="account_r30", portfolio_id="portfolio_r30", currency="USDT",
        equity=D("10000"), max_order_risk_fraction=D(".02"),
        max_total_risk_fraction=D(".05"), max_daily_loss_fraction=D(".06"),
        max_notional_fraction=D("2"), max_margin_fraction=D(".5"),
        max_leverage=D("5"), contract_multiplier=D("1"),
        quantity_step=D(".001"), roundtrip_fee_fraction=D(".001"),
        worst_slippage_fraction=D(".002"), max_active_orders=3,
        external_exposure_cleared=True,
    )
    portfolio = PortfolioRiskPolicy(
        portfolio_id="portfolio_r30", currency="USDT",
        max_reserved_risk=D("700"), max_notional=D("50000"),
        max_daily_loss=D("900"), max_group_risk=D("350"),
        max_engine_risk=D("500"), max_active_orders=5,
    )
    snapshot = {
        "portfolio_id": "portfolio_r30", "mode": "PAPER_ONLY",
        "halted": False, "day": "2026-10-16", "active_orders": 0,
        "reserved_risk": "0", "reserved_notional": "0",
        "modeled_margin": "0", "daily_realized_loss_magnitude": "0",
        "account_losses": {},
    }
    recovery = {
        "account_id": "account_r30", "state": "READY",
        "ready_for_new_paper_risk": True, "last_revision": 1,
    }
    health = {
        "mode": "OFFLINE_OPERATOR_DRIVEN_SUPERVISOR",
        "counts": {k: 0 for k in (
            "PENDING", "CLAIMED", "DONE", "QUARANTINED")},
        "manual_reconciliation_required": False,
        "background_poller": False, "telegram_sent": False,
        "broker_order_sent": False, "live_trading_enabled": False,
    }
    return {
        "proposal": proposal, "account_policy": account,
        "portfolio_policy": portfolio, "group_id": "btc_group",
        "active_reservations": (), "known_order_statuses": {},
        "portfolio_snapshot": snapshot, "account_recovery_fence": recovery,
        "runtime_health": health, "engine_halted": False,
        "account_halted": False, "order_switch_enabled": True,
        "operator_ack": True,
    }


def reservations(args, *, risk="20", notional="1000", margin="200",
                 state=OrderStatus.ACKNOWLEDGED,
                 symbol="ETHUSDT", group="btc_group", engine="brooks_public"):
    instrument = Instrument(
        Market.CRYPTO, "sample_venue", symbol, "UTC", "USDT",
    )
    item = R30ActiveReservation(
        "order_prior", "account_r30", engine, group,
        instrument, Direction.SHORT, state,
        D(risk), D(notional), D(margin),
    )
    args["active_reservations"] = (item,)
    args["known_order_statuses"] = {"order_prior": state}
    snap = args["portfolio_snapshot"]
    snap.update(
        active_orders=1, reserved_risk=risk, reserved_notional=notional,
        modeled_margin=margin,
    )
    return args


def reject(args, reason):
    with pytest.raises(R30RiskRefused, match=reason):
        evaluate_r30_offline_preorder_risk(**args)


def test_r30_zero_position_model_pass_is_explicitly_non_authorizing():
    result = evaluate_r30_offline_preorder_risk(**example())
    assert result["verdict"] == "LOCAL_MODEL_PASS_NO_RESERVATION_OR_SEND_AUTHORITY"
    assert result["modeled_incremental_notional"] == "100"
    assert result["modeled_incremental_risk"] == "2.3"
    assert result["modeled_incremental_margin"] == "20"
    assert result["broker_order_sent"] is False
    assert result["connected_paper_enabled"] is False
    assert result["live_trading_enabled"] is False
    assert result["order_reservation_created"] is False
    assert len(result["local_report_sha256"]) == 64


def test_r30_existing_cross_engine_exposure_counted_without_reservation():
    args = reservations(example())
    result = evaluate_r30_offline_preorder_risk(**args)
    assert result["concurrent_portfolio_orders"] == 1
    assert result["known_order_states_count"] == 1
    assert result["order_reservation_created"] is False


@pytest.mark.parametrize("state", [
    OrderStatus.SENT_UNCONFIRMED, OrderStatus.SUBMISSION_UNKNOWN,
])
def test_r30_unknown_order_states_always_block(state):
    args = reservations(example(), state=state)
    reject(args, "UNKNOWN_OR_UNCONFIRMED")


@pytest.mark.parametrize("status", [
    OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.CLOSED,
])
def test_r30_terminal_orders_with_live_reservation_are_inconsistent(status):
    args = reservations(example(), state=status)
    reject(args, "UNRECONCILED_RESERVATION")


@pytest.mark.parametrize("bad", ["CLAIMED", "QUARANTINED", "DONE", "PENDING"])
def test_r30_any_unsettled_runtime_effects_block(bad):
    args = example()
    args["runtime_health"]["counts"][bad] = 1
    if bad in ("CLAIMED", "QUARANTINED"):
        # The supervisor sets this fence before R30 checks job counters.
        # Both guards deny new risk; the outer reconciliation fence wins.
        args["runtime_health"]["manual_reconciliation_required"] = True
        reject(args, "UNVERIFIED_RUNTIME_OR_SIDE_EFFECTS")
        # A stale/missing reconciliation flag must not bypass the counter guard.
        args["runtime_health"]["manual_reconciliation_required"] = False
    reject(args, "PENDING_DONE_OR_UNKNOWN_RUNTIME_EFFECTS")


def test_r30_manual_reconciliation_blocks_even_with_zero_pending_counts():
    args = example()
    args["runtime_health"]["manual_reconciliation_required"] = True
    reject(args, "UNVERIFIED_RUNTIME_OR_SIDE_EFFECTS")


def test_r30_stop_and_order_switch_cannot_be_overridden():
    for flag in ("engine_halted", "account_halted"):
        args = example()
        args[flag] = True
        reject(args, "ONE_WAY_HALT")
    args = example()
    args["order_switch_enabled"] = False
    reject(args, "ONE_WAY_HALT")
    args = example()
    args["portfolio_snapshot"]["halted"] = True
    reject(args, "SNAPSHOT_HALTED")


def test_r30_drift_and_missing_orders_are_denied():
    args = reservations(example())
    args["portfolio_snapshot"]["reserved_notional"] = "999"
    reject(args, "TOTAL_DRIFT")
    args = reservations(example())
    args["known_order_statuses"] = {}
    reject(args, "UNRECONCILED_RESERVATION")
    args = example()
    args["known_order_statuses"] = {"order_other": OrderStatus.FILLED}
    reject(args, "ACTIVE_ORDER_MISSING")
    args = example()
    args["known_order_statuses"] = {
        args["proposal"].order_id: OrderStatus.CLOSED,
    }
    reject(args, "REUSED_ORDER_ID")


def test_r30_refuse_same_market_position_even_if_other_direction():
    args = reservations(example(), symbol="BTCUSDT")
    reject(args, "SAME_INSTRUMENT_CONCURRENT")


def test_r30_amount_caps_derived_from_existing_policy():
    args = example()
    args["proposal"] = replace(args["proposal"], quantity=D("120"))
    reject(args, "PER_ORDER_RISK_LIMIT")
    args = example()
    args["proposal"] = replace(args["proposal"], quantity=D("201"))
    reject(args, "PER_ORDER_RISK_LIMIT")
    args = example()
    args["proposal"] = replace(args["proposal"], quantity=D("1.0005"))
    reject(args, "QUANTITY_STEP")


def test_r30_aggregate_caps_are_checked():
    args = reservations(example(), risk="499", notional="1000", margin="200",
                        group="independent_group", engine="another_engine")
    reject(args, "ACCOUNT_ACCUMULATED_RISK_LIMIT")
    args = reservations(example(), risk="349", notional="1000", margin="200")
    reject(args, "CORRELATED_GROUP_LIMIT")
    args = reservations(example(), risk="499", notional="1000", margin="200",
                        group="independent_group")
    reject(args, "ACCOUNT_ACCUMULATED_RISK_LIMIT")


def test_r30_daily_loss_circuit_breaker_and_worst_case():
    args = example()
    args["portfolio_snapshot"]["account_losses"] = {"account_r30": "600"}
    args["portfolio_snapshot"]["daily_realized_loss_magnitude"] = "600"
    reject(args, "DAILY_LOSS_CIRCUIT")
    args = example()
    args["portfolio_snapshot"]["account_losses"] = {"account_r30": "599"}
    args["portfolio_snapshot"]["daily_realized_loss_magnitude"] = "599"
    reject(args, "ACCOUNT_DAILY_WORST_CASE")
    args = example()
    args["portfolio_snapshot"]["account_losses"] = {"account_r30": "1"}
    reject(args, "DAILY_LOSS_DRIFT")


def test_r30_restart_fence_and_unknown_exposure_denied():
    args = example()
    args["account_recovery_fence"]["state"] = "BLOCKED"
    reject(args, "RESTART_ACCOUNT_RECOVERY_NOT_READY")
    args = example()
    args["account_policy"] = replace(
        args["account_policy"], external_exposure_cleared=False,
    )
    reject(args, "EXTERNAL_EXPOSURE_UNVERIFIED")


def test_r30_production_switch_and_missing_ack_fail_closed(monkeypatch):
    args = example()
    args["operator_ack"] = False
    reject(args, "NONPRODUCTION")
    args = example()
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    reject(args, "NONPRODUCTION")


def test_r30_no_side_effect_or_network_module_calls():
    # This isolated preflight has no writable service/DB/broker parameter.
    args = example()
    before = args["portfolio_snapshot"].copy()
    result = evaluate_r30_offline_preorder_risk(**args)
    assert args["portfolio_snapshot"] == before
    assert result["production_modified"] is False



def test_r30_smaller_policies_block_notional_margin_group_and_engine():
    args = example()
    args["account_policy"] = replace(
        args["account_policy"], max_notional_fraction=D(".005"),
    )
    reject(args, "ACCOUNT_NOTIONAL_LIMIT")

    args = example()
    args["account_policy"] = replace(
        args["account_policy"], max_margin_fraction=D(".001"),
    )
    reject(args, "ACCOUNT_MODELED_MARGIN_LIMIT")

    args = example()
    args["portfolio_policy"] = replace(
        args["portfolio_policy"], max_group_risk=D("2"),
    )
    reject(args, "CORRELATED_GROUP_LIMIT")

    args = example()
    args["portfolio_policy"] = replace(
        args["portfolio_policy"], max_engine_risk=D("2"),
    )
    reject(args, "ENGINE_CONCENTRATION_LIMIT")

    args = example()
    args["portfolio_policy"] = replace(
        args["portfolio_policy"], max_reserved_risk=D("2"),
    )
    reject(args, "PORTFOLIO_RESERVED_RISK_LIMIT")


def test_r30_order_count_and_cross_account_portfolio_limit():
    args = reservations(example(), risk="2", notional="1000", margin="200",
                        group="independent_group", engine="another_engine")
    args["account_policy"] = replace(
        args["account_policy"], max_active_orders=1,
    )
    reject(args, "ACTIVE_POSITION_LIMIT")

    args = reservations(example(), risk="699", notional="1000", margin="200",
                        group="independent_group", engine="another_engine")
    # Previous exposure belongs to a different account and must STILL count
    # towards portfolio caps. The account may not be the proposed account.
    old = args["active_reservations"][0]
    args["active_reservations"] = (
        replace(old, account_id="different_account"),
    )
    reject(args, "PORTFOLIO_RESERVED_RISK_LIMIT")


def test_r30_unconfirmed_status_blocks_even_when_not_in_active_reservation():
    args = example()
    args["known_order_statuses"] = {
        "external_unknown": OrderStatus.SUBMISSION_UNKNOWN,
    }
    reject(args, "UNKNOWN_OR_UNCONFIRMED")


def test_r30_conservative_snapshot_type_checks():
    args = example()
    args["portfolio_snapshot"]["active_orders"] = True
    reject(args, "ACTIVE_ORDER_COUNT_MISMATCH")
    args = example()
    args["portfolio_snapshot"]["reserved_risk"] = "NaN"
    reject(args, "NEGATIVE_OR_NONFINITE")
    args = example()
    args["portfolio_snapshot"]["account_losses"] = {"account_r30": "1e999999"}
    reject(args, "DAILY_LOSS_DRIFT")
