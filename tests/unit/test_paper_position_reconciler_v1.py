"""Offline Stage-4 broker reconciliation, crash/restart, and drift-fencing tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.execution_contract_v1 import OrderKind, OrderSpec
from naseri_markets.execution_position_core_v1 import (
    OrchestrationRefused,
    PaperExecutionOrchestratorV1,
)
from naseri_markets.offline_broker_fixture_v1 import (
    BrokerOrder,
    BrokerSnapshot,
    BrokerState,
    IndependentPaperBrokerV1,
    order_digest,
)
from naseri_markets.paper_position_reconciler_v1 import PaperPositionReconcilerV1
from naseri_markets.risk_portfolio_contract_v1 import (
    AccountRiskPolicy,
    PortfolioRiskPolicy,
)
from naseri_markets.risk_portfolio_manager_v1 import RiskRefused

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def instrument(symbol="BTC-PAPER"):
    return Instrument(
        market=Market.CRYPTO, provider="fixture", symbol=symbol,
        timezone="UTC", quote_currency="USD",
    )


def order(order_id="order-1", *, account_id="acct-a", quantity="1"):
    return OrderSpec(
        order_id=order_id, signal_id="signal-1", account_id=account_id,
        engine_id="brooks", instrument=instrument(),
        direction=Direction.LONG, kind=OrderKind.LIMIT,
        quantity=D(quantity), reference_entry=D("100"),
        stop=D("90"), target=D("120"),
    )


def configure(core):
    core.configure_portfolio(PortfolioRiskPolicy(
        portfolio_id="folio", currency="USD",
        max_reserved_risk=D("200"), max_notional=D("10000"),
        max_daily_loss=D("300"), max_group_risk=D("200"),
        max_engine_risk=D("200"), max_active_orders=10,
    ))
    for account_id in ("acct-a", "acct-b"):
        core.configure_account(AccountRiskPolicy(
            account_id=account_id, portfolio_id="folio", currency="USD",
            equity=D("1000"), max_order_risk_fraction=D("0.05"),
            max_total_risk_fraction=D("0.2"),
            max_daily_loss_fraction=D("0.3"),
            max_notional_fraction=D("2"), max_margin_fraction=D("0.9"),
            max_leverage=D("3"), contract_multiplier=D("1"),
            quantity_step=D("0.01"), roundtrip_fee_fraction=D("0.002"),
            worst_slippage_fraction=D("0.003"), max_active_orders=10,
            external_exposure_cleared=True,
        ))
    core.register_instrument(
        portfolio_id="folio", instrument=instrument(), group_id="BETA"
    )


def obs(
    spec, status=BrokerState.ACKNOWLEDGED, *,
    filled="0", avg=None, closed="0", close_avg=None, remote="mock-100",
):
    return BrokerOrder(
        order_id=spec.order_id, account_id=spec.account_id,
        spec_digest=order_digest(spec), state=status,
        remote_order_id=remote, requested_quantity=spec.quantity,
        filled_quantity=D(filled), average_fill_price=D(avg) if avg else None,
        closed_quantity=D(closed),
        average_close_price=D(close_avg) if close_avg else None,
    )


@pytest.fixture
def harness(tmp_path):
    with (
        PaperExecutionOrchestratorV1(tmp_path / "core.sqlite") as core,
        IndependentPaperBrokerV1(tmp_path / "broker.sqlite") as broker,
    ):
        configure(core)
        reconciler = PaperPositionReconcilerV1(core, clock=lambda: NOW)
        reconciler.install("acct-a")
        yield core, broker, reconciler


def snapshot(broker, account_id="acct-a", *, complete=True, timestamp=NOW):
    return broker.snapshot(account_id, captured_at=timestamp, complete=complete)


def start(core, spec=None):
    spec = spec or order()
    core.create(spec, action_id="create-" + spec.order_id)
    core.apply(spec.order_id, action_id="send-" + spec.order_id, event="SUBMIT")
    return spec


def unknown(core, spec=None):
    spec = start(core, spec)
    core.apply(spec.order_id, action_id="lost-" + spec.order_id, event="MARK_UNKNOWN")
    return spec


def blocked(core, reason=None):
    with pytest.raises(OrchestrationRefused, match=reason or "ACCOUNT_RECONCILIATION_REQUIRED"):
        core.create(order("new-risk"), action_id="new-risk")


def test_install_blocks_new_risk_before_first_full_snapshot(harness):
    core, broker, reconciler = harness
    blocked(core)
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["status"] == "RECONCILED"
    assert result["revision"] == 0
    assert reconciler.fence("acct-a")["ready_for_new_paper_risk"]
    assert core.create(order(), action_id="create")["order"]["status"] == "CREATED"


def test_independent_broker_storage_is_distinct_and_durable(harness, tmp_path):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core)
    broker.publish(spec, obs(spec))
    assert broker.snapshot("acct-a", captured_at=NOW).revision == 1
    assert core.order_state(spec.order_id)["status"] == "SUBMISSION_UNKNOWN"
    with IndependentPaperBrokerV1(tmp_path / "broker.sqlite") as reopened:
        assert reopened.snapshot("acct-a", captured_at=NOW).orders[0].order_id == spec.order_id
    assert core.order_state(spec.order_id)["status"] == "SUBMISSION_UNKNOWN"


def test_unknown_submission_ack_recovery_without_retransmission(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core)
    broker.publish(spec, obs(spec))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["status"] == "RECONCILED"
    assert [a["event"] for a in result["repaired"]] == ["RECONCILE_ACK"]
    assert core.order_state("order-1")["status"] == "ACKNOWLEDGED"
    assert len([e for e in core.order_events("order-1") if e["event"] == "SUBMIT"]) == 1
    assert core.risk_snapshot("folio")["active_orders"] == 1


def test_sent_unconfirmed_receipt_recovered_by_direct_ack(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = start(core)
    broker.publish(spec, obs(spec))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert [r["event"] for r in result["repaired"]] == ["ACK"]


@pytest.mark.parametrize("event", ["SUBMITTED", "UNKNOWN"])
def test_broker_rejection_releases_only_with_external_evidence(harness, event):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = start(core) if event == "SUBMITTED" else unknown(core)
    broker.publish(spec, obs(spec, BrokerState.REJECTED, remote=None))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["repaired"][0]["event"] == (
        "REJECT" if event == "SUBMITTED" else "RECONCILE_REJECT"
    )
    assert core.order_state(spec.order_id)["status"] == "REJECTED"
    assert core.risk_snapshot("folio")["active_orders"] == 0


def test_missed_partial_fills_then_full_fill_recover_exact_average(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core, order(quantity="3"))
    broker.publish(spec, obs(
        spec, BrokerState.PARTIALLY_FILLED, filled="1", avg="99"
    ))
    first = reconciler.reconcile("acct-a", snapshot(broker))
    assert [a["event"] for a in first["repaired"]] == ["RECONCILE_ACK", "FILL"]
    assert core.order_state(spec.order_id)["filled_quantity"] == "1"
    broker.publish(spec, obs(
        spec, BrokerState.FILLED, filled="3", avg="100"
    ))
    second = reconciler.reconcile("acct-a", snapshot(broker))
    assert [a["event"] for a in second["repaired"]] == ["FILL"]
    state = core.order_state(spec.order_id)
    assert state["status"] == "FILLED"
    assert D(state["average_fill_price"]) == D("100")
    assert core.risk_snapshot("folio")["active_orders"] == 1


def test_cancel_after_partial_fill_retains_open_position_risk(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core, order(quantity="3"))
    broker.publish(spec, obs(
        spec, BrokerState.CANCELED, filled="1", avg="99"
    ))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert [a["event"] for a in result["repaired"]] == [
        "RECONCILE_ACK", "FILL", "CANCEL",
    ]
    assert core.order_state(spec.order_id)["open_position_quantity"] == "1"
    assert core.risk_snapshot("folio")["active_orders"] == 1


def test_external_full_close_repaired_and_modeled_loss_persisted(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core, order(quantity="2"))
    broker.publish(spec, obs(
        spec, BrokerState.CLOSED, filled="2", avg="100",
        closed="2", close_avg="80",
    ))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert [a["event"] for a in result["repaired"]] == [
        "RECONCILE_ACK", "FILL", "CLOSE_FILL",
    ]
    assert core.order_state(spec.order_id)["status"] == "CLOSED"
    assert core.risk_snapshot("folio")["active_orders"] == 0
    assert D(core.risk_snapshot("folio")["daily_realized_loss_magnitude"]) > D("40")


def test_external_close_of_partially_filled_order_cancels_first(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core, order(quantity="3"))
    broker.publish(spec, obs(
        spec, BrokerState.CLOSED, filled="1", avg="100",
        closed="1", close_avg="102",
    ))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert [a["event"] for a in result["repaired"]] == [
        "RECONCILE_ACK", "FILL", "CANCEL", "CLOSE_FILL",
    ]
    assert core.order_state(spec.order_id)["status"] == "CLOSED"
    assert core.risk_snapshot("folio")["active_orders"] == 0


def test_repeated_same_revision_is_safe_and_does_not_duplicate_losses(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core)
    broker.publish(spec, obs(
        spec, BrokerState.CLOSED, filled="1", avg="100",
        closed="1", close_avg="80",
    ))
    first = reconciler.reconcile("acct-a", snapshot(broker))
    budget = core.risk_snapshot("folio")
    events = len(core.order_events(spec.order_id))
    second = reconciler.reconcile("acct-a", snapshot(broker))
    assert first["status"] == second["status"] == "RECONCILED"
    assert second["repaired"] == []
    assert core.risk_snapshot("folio") == budget
    assert len(core.order_events(spec.order_id)) == events


def test_restart_requires_new_instance_reconciliation_before_new_risk(tmp_path):
    path = tmp_path / "core.sqlite"
    provider = tmp_path / "broker.sqlite"
    with (
        PaperExecutionOrchestratorV1(path) as core,
        IndependentPaperBrokerV1(provider) as broker,
    ):
        configure(core)
        reconciler = PaperPositionReconcilerV1(core, clock=lambda: NOW)
        reconciler.install("acct-a")
        reconciler.reconcile("acct-a", snapshot(broker))
        spec = unknown(core)
        broker.publish(spec, obs(spec))
    with (
        PaperExecutionOrchestratorV1(path) as core,
        IndependentPaperBrokerV1(provider) as broker,
    ):
        reconciler = PaperPositionReconcilerV1(core, clock=lambda: NOW)
        assert not reconciler.fence("acct-a")["ready_for_new_paper_risk"]
        blocked(core)
        result = reconciler.reconcile("acct-a", snapshot(broker))
        assert result["status"] == "RECONCILED"
        assert core.order_state("order-1")["status"] == "ACKNOWLEDGED"
        assert core.create(order("new-risk"), action_id="new-risk")["order"]["status"] == "CREATED"


def test_disconnect_halting_new_risk_never_releases_unknown_position(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    unknown(core)
    broker.connected = False
    result = reconciler.scan("acct-a", broker)
    assert result["status"] == "QUARANTINED"
    assert result["new_risk_halted"]
    assert core.order_state("order-1")["status"] == "SUBMISSION_UNKNOWN"
    assert core.risk_snapshot("folio")["active_orders"] == 1
    blocked(core)


def test_missing_remote_order_in_full_snapshot_blocks_without_fake_rejection(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    unknown(core)
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["reason"] == "SUBMITTED_ORDER_MISSING_FROM_SNAPSHOT"
    assert core.order_state("order-1")["status"] == "SUBMISSION_UNKNOWN"
    assert core.risk_snapshot("folio")["reserved_risk"] != "0"


@pytest.mark.parametrize("timestamp,complete,expected", [
    (NOW - timedelta(minutes=6), True, "STALE_OR_FUTURE_BROKER_SNAPSHOT"),
    (NOW + timedelta(minutes=1), True, "STALE_OR_FUTURE_BROKER_SNAPSHOT"),
    (NOW, False, "INCOMPLETE_BROKER_SNAPSHOT"),
])
def test_invalid_capture_or_incomplete_scope_quarantined(
    harness, timestamp, complete, expected,
):
    core, broker, reconciler = harness
    result = reconciler.reconcile(
        "acct-a", snapshot(broker, timestamp=timestamp, complete=complete),
    )
    assert result["status"] == "QUARANTINED"
    assert result["reason"] == expected
    blocked(core)


def test_remote_order_identity_mismatch_quarantines_after_original_ack(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core)
    broker.publish(spec, obs(spec, remote="first-remote"))
    reconciler.reconcile("acct-a", snapshot(broker))
    broker.publish(spec, obs(spec, remote="other-remote"))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["reason"] == "REMOTE_ORDER_ID_CONFLICT"
    assert core.order_state(spec.order_id)["remote_order_id"] == "first-remote"
    assert core.risk_snapshot("folio")["active_orders"] == 1


def test_cumulative_fill_regression_halts_account(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core, order(quantity="3"))
    broker.publish(spec, obs(
        spec, BrokerState.PARTIALLY_FILLED, filled="2", avg="100",
    ))
    reconciler.reconcile("acct-a", snapshot(broker))
    broker.publish(spec, obs(
        spec, BrokerState.PARTIALLY_FILLED, filled="1", avg="100",
    ))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["reason"] == "BROKER_CUMULATIVE_QUANTITY_REGRESSION"
    assert core.order_state(spec.order_id)["filled_quantity"] == "2"
    assert core.risk_snapshot("folio")["active_orders"] == 1


def test_same_revision_tampered_evidence_detected_without_double_apply(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    forged = BrokerSnapshot(
        account_id="acct-a", revision=0, captured_at=NOW, complete=True,
        orders=(obs(order("ghost")),),
    )
    result = reconciler.reconcile("acct-a", forged)
    assert result["reason"] == "BROKER_SAME_REVISION_DIGEST_CONFLICT"


def test_older_account_revision_is_rejected(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core)
    broker.publish(spec, obs(spec))
    reconciler.reconcile("acct-a", snapshot(broker))
    old = BrokerSnapshot(
        account_id="acct-a", revision=0, captured_at=NOW, complete=True,
        orders=(),
    )
    assert reconciler.reconcile("acct-a", old)["reason"] == "BROKER_REVISION_ROLLBACK"


def test_cross_account_snapshot_cannot_clear_account_fence(harness):
    core, broker, reconciler = harness
    result = reconciler.reconcile("acct-a", snapshot(broker, account_id="acct-b"))
    assert result["reason"] == "CROSS_ACCOUNT_SNAPSHOT"
    blocked(core)


def test_forged_external_order_cannot_create_unreserved_position(harness):
    core, broker, reconciler = harness
    forged = BrokerSnapshot(
        account_id="acct-a", revision=1, captured_at=NOW, complete=True,
        orders=(obs(order("unknown-broker-order")),),
    )
    result = reconciler.reconcile("acct-a", forged)
    assert result["reason"] == "UNTRACKED_BROKER_ORDER"
    assert core.order_state("unknown-broker-order") is None
    assert core.risk_snapshot("folio")["active_orders"] == 0


def test_unexpected_external_order_before_submit_quarantines(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = order()
    core.create(spec, action_id="create")
    broker.publish(spec, obs(spec))
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["reason"] == "UNEXPECTED_BROKER_ORDER_BEFORE_SUBMIT"
    assert core.order_state(spec.order_id)["status"] == "CREATED"
    assert core.risk_snapshot("folio")["active_orders"] == 1


def test_broker_spec_digest_mismatch_is_fail_closed(harness):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    spec = unknown(core)
    forged = BrokerSnapshot(
        account_id="acct-a", revision=1, captured_at=NOW, complete=True,
        orders=(replace(obs(spec), spec_digest="f" * 64),),
    )
    assert reconciler.reconcile("acct-a", forged)["reason"] == "BROKER_ORDER_SPEC_CONFLICT"


def test_failed_replay_rolls_back_all_prior_repairs_then_quarantines(harness, monkeypatch):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    first = unknown(core, order("a-order"))
    second = unknown(core, order("b-order"))
    broker.publish(first, obs(first, remote="remote-a"))
    broker.publish(second, obs(second, remote="remote-b"))
    original = core.apply

    def fail_second(order_id, **kwargs):
        if order_id == "b-order":
            raise ValueError("INJECTED_REPLAY_FAILURE")
        return original(order_id, **kwargs)

    monkeypatch.setattr(core, "apply", fail_second)
    result = reconciler.reconcile("acct-a", snapshot(broker))
    assert result["reason"] == "INJECTED_REPLAY_FAILURE"
    assert core.order_state("a-order")["status"] == "SUBMISSION_UNKNOWN"
    assert core.order_state("b-order")["status"] == "SUBMISSION_UNKNOWN"
    assert core.risk_snapshot("folio")["active_orders"] == 2


def test_quarantine_hard_halt_survives_restart_even_after_good_snapshot(
    harness, tmp_path,
):
    core, broker, reconciler = harness
    reconciler.reconcile("acct-a", snapshot(broker))
    unknown(core)
    broker.connected = False
    reconciler.scan("acct-a", broker)
    broker.connected = True
    spec = order()
    broker.publish(spec, obs(spec))
    repaired = reconciler.reconcile("acct-a", snapshot(broker))
    assert repaired["status"] == "RECONCILED"
    assert repaired["account_hard_halted"]
    with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
        core.create(order("after-quarantine"), action_id="new-risk")
    assert reconciler.audit("acct-a")[-2]["status"] == "QUARANTINED"


def test_authority_fixture_invariants_and_nonregular_storage(tmp_path):
    spec = order()
    with pytest.raises(ValueError, match="IMPOSSIBLE_BROKER_QUANTITIES"):
        obs(spec, BrokerState.FILLED, filled="2", avg="100")
    with pytest.raises(ValueError, match="INVALID_PARTIAL_STATE"):
        obs(spec, BrokerState.PARTIALLY_FILLED, filled="0")
    with pytest.raises(ValueError, match="INVALID_CLOSED_STATE"):
        obs(spec, BrokerState.CLOSED, filled="1", avg="100",
            closed="0")
    folder = tmp_path / "directory"
    folder.mkdir()
    with pytest.raises(ValueError, match="NONREGULAR_BROKER_FIXTURE_PATH"):
        IndependentPaperBrokerV1(folder)
    with pytest.raises(ValueError, match="DUPLICATE_BROKER_IDENTITY"):
        BrokerSnapshot(
            account_id="acct-a", revision=1, captured_at=NOW, complete=True,
            orders=(obs(spec), obs(spec)),
        )


def test_healthy_other_account_not_blocked_by_first_account_fence(harness):
    core, broker, reconciler = harness
    blocked(core)
    created = core.create(order("acct-b-order", account_id="acct-b"),
                          action_id="other-account")
    assert created["order"]["status"] == "CREATED"
    assert reconciler.fence("acct-a")["state"] == "BLOCKED"
