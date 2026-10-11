"""Acceptance tests for the disconnected Execution Architecture V1 PAPER simulator."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Direction, EvidenceMode, Instrument, Market
from naseri_markets.execution_contract_v1 import (
    OrderKind,
    OrderSpec,
    RiskEnvelope,
    size_linear_paper_order,
)
from naseri_markets.position_lifecycle_simulator import (
    LifecycleRefused,
    PositionLifecycleSimulator,
)


def instrument() -> Instrument:
    return Instrument(
        market=Market.CRYPTO, provider="offline-fixture",
        symbol="BTC-PAPER", timezone="UTC", quote_currency="USD",
    )


def spec(*, order_id: str = "paper-1", direction: Direction = Direction.LONG) -> OrderSpec:
    return OrderSpec(
        order_id=order_id, signal_id="signal-1", account_id="demo-1",
        engine_id="brooks", instrument=instrument(), direction=direction,
        kind=OrderKind.LIMIT, quantity=D("3"), reference_entry=D("100"),
        stop=D("90") if direction is Direction.LONG else D("110"),
        target=D("120") if direction is Direction.LONG else D("80"),
    )


def risk(**kw) -> RiskEnvelope:
    values = {
        "equity": D("1000"), "risk_fraction": D("0.01"),
        "max_daily_loss_fraction": D("0.05"), "daily_realized_loss": D("0"),
        "reserved_risk": D("0"), "existing_notional": D("0"),
        "max_notional_fraction": D("2"), "max_leverage": D("3"),
        "contract_multiplier": D("1"), "quantity_step": D("0.01"),
        "roundtrip_fee_fraction": D("0.002"),
        "worst_slippage_fraction": D("0.003"),
    }
    return RiskEnvelope(**(values | kw))


def apply(sim: PositionLifecycleSimulator, action: str, event: str, **kwargs):
    return sim.apply("paper-1", action_id=action, event=event, **kwargs)


def sent_and_ack(sim):
    sim.create(spec(), action_id="create")
    apply(sim, "send", "SUBMIT")
    return apply(sim, "ack", "ACK", remote_order_id="fake-broker-order-1")


def test_risk_sizes_by_stop_fees_slippage_and_rounds_down():
    approval = size_linear_paper_order(
        reference_entry=D("100"), stop=D("90"), envelope=risk()
    )
    assert approval.quantity == D("0.95")
    assert approval.reserved_risk == D("9.975")
    assert approval.notional == D("95")


@pytest.mark.parametrize("modifier,diagnostic", [
    ({"daily_realized_loss": D("50")}, "DAILY_LOSS_CIRCUIT_BREAKER"),
    ({"reserved_risk": D("10")}, "ACCOUNT_RISK_OR_EXPOSURE_EXHAUSTED"),
    ({"existing_notional": D("2000")}, "ACCOUNT_RISK_OR_EXPOSURE_EXHAUSTED"),
    ({"quantity_step": D("10")}, "QUANTITY_BELOW_MINIMUM_STEP"),
])
def test_risk_fail_closed(modifier, diagnostic):
    with pytest.raises(ValueError, match=diagnostic):
        size_linear_paper_order(
            reference_entry=D("100"), stop=D("90"), envelope=risk(**modifier)
        )


def test_risk_refuses_invalid_inputs_and_zero_stop_distance():
    with pytest.raises(ValueError):
        risk(equity=D("NaN"))
    with pytest.raises(ValueError):
        risk(risk_fraction=D("1.1"))
    with pytest.raises(ValueError):
        risk(max_notional_fraction=D("10"))
    with pytest.raises(ValueError):
        size_linear_paper_order(
            reference_entry=D("100"), stop=D("100"), envelope=risk()
        )


def test_contract_requires_strict_geometry_and_paper_only():
    with pytest.raises(ValueError, match="PAPER_ONLY"):
        replace(spec(), mode=EvidenceMode.FORWARD)
    with pytest.raises(ValueError, match="LONG_STOP_TARGET_GEOMETRY"):
        replace(spec(), stop=D("101"))
    with pytest.raises(ValueError):
        replace(spec(), quantity=D("Infinity"))
    with pytest.raises(ValueError):
        replace(spec(), engine_id="../../bad")
    assert spec(direction=Direction.SHORT).direction is Direction.SHORT


def test_send_is_not_ack_and_unknown_requires_reconciliation(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        state = sim.create(spec(), action_id="create")
        assert state["status"] == "CREATED"
        state = apply(sim, "send", "SUBMIT")
        assert state["status"] == "SENT_UNCONFIRMED"
        assert state["filled_quantity"] == "0"
        state = apply(sim, "lost-reply", "MARK_UNKNOWN")
        assert state["status"] == "SUBMISSION_UNKNOWN"
        with pytest.raises(LifecycleRefused, match="SUBMIT_RETRY_FORBIDDEN"):
            apply(sim, "unsafe-retry", "SUBMIT")
        with pytest.raises(LifecycleRefused, match="RECONCILIATION_EVIDENCE_REQUIRED"):
            apply(sim, "unproven", "RECONCILE_ACK", remote_order_id="remote-1")
        assert apply(sim, "recovered", "RECONCILE_ACK",
                     remote_order_id="remote-1", evidence="provider-order-query")[
            "status"
        ] == "ACKNOWLEDGED"


def test_unknown_rejection_with_evidence_and_late_fill_refused(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sim.create(spec(), action_id="create")
        apply(sim, "send", "SUBMIT")
        apply(sim, "timeout", "MARK_UNKNOWN")
        assert apply(sim, "rejected", "RECONCILE_REJECT",
                     evidence="provider-order-history")["status"] == "REJECTED"
        with pytest.raises(LifecycleRefused, match="FILL_REQUIRES"):
            apply(sim, "late-fill", "FILL", quantity="1", price="100")


def test_fill_requires_ack_and_never_exceeds_order(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sim.create(spec(), action_id="create")
        with pytest.raises(LifecycleRefused, match="FILL_REQUIRES"):
            apply(sim, "premature", "FILL", quantity="1", price="100")
        apply(sim, "send", "SUBMIT")
        with pytest.raises(LifecycleRefused, match="FILL_REQUIRES"):
            apply(sim, "too-early", "FILL", quantity="1", price="100")
        apply(sim, "ack", "ACK", remote_order_id="remote-1")
        assert apply(sim, "partial-1", "FILL", quantity="1.25", price="100")[
            "status"
        ] == "PARTIALLY_FILLED"
        assert apply(sim, "partial-2", "FILL", quantity="1.75", price="102")[
            "status"
        ] == "FILLED"
        state = sim.state("paper-1")
        assert state["average_fill_price"] == str(
            (D("1.25") * 100 + D("1.75") * 102) / D("3")
        )
        assert state["open_position_quantity"] == "3.00"
        with pytest.raises(LifecycleRefused, match="FILL_REQUIRES"):
            apply(sim, "overfill", "FILL", quantity="1", price="101")


def test_partial_fill_protected_cancel_and_close(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sent_and_ack(sim)
        state = apply(sim, "partial", "FILL", quantity="1.2", price="99")
        assert state["current_stop"] == "90"
        assert state["open_position_quantity"] == "1.2"
        with pytest.raises(LifecycleRefused, match="CANCEL_REMAINDER"):
            apply(sim, "unsafe-close", "CLOSE_FILL", quantity="1", price="101")
        assert apply(sim, "cancel-rest", "CANCEL")["status"] == "CANCELED"
        state = apply(sim, "first-close", "CLOSE_FILL", quantity="0.4", price="101")
        assert state["open_position_quantity"] == "0.8"
        assert state["status"] == "CANCELED"
        assert apply(sim, "last-close", "CLOSE_FILL",
                     quantity="0.8", price="103")["status"] == "CLOSED"
        assert sim.state("paper-1")["open_position_quantity"] == "0.0"


def test_stop_tightens_not_widens_and_needs_open_position(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sent_and_ack(sim)
        with pytest.raises(LifecycleRefused, match="NO_OPEN_POSITION"):
            apply(sim, "no-position", "AMEND_STOP", stop="95")
        apply(sim, "fill", "FILL", quantity="3", price="100")
        assert apply(sim, "breakeven", "AMEND_STOP", stop="100")["current_stop"] == "100"
        with pytest.raises(LifecycleRefused, match="STOP_WIDENING_FORBIDDEN"):
            apply(sim, "weaken", "AMEND_STOP", stop="99")
        assert sim.state("paper-1")["current_stop"] == "100"


def test_short_position_protection_and_stop_amend(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sim.create(spec(direction=Direction.SHORT), action_id="create")
        apply(sim, "send", "SUBMIT")
        apply(sim, "ack", "ACK", remote_order_id="demo-1")
        with pytest.raises(LifecycleRefused, match="UNPROTECTED_SHORT_FILL"):
            apply(sim, "bad-fill", "FILL", quantity="1", price="111")
        apply(sim, "good-fill", "FILL", quantity="1", price="100")
        assert apply(sim, "tight-stop", "AMEND_STOP", stop="100")[
            "current_stop"
        ] == "100"
        with pytest.raises(LifecycleRefused, match="STOP_WIDENING_FORBIDDEN"):
            apply(sim, "widen-stop", "AMEND_STOP", stop="101")


def test_emergency_close_simulated_partial_and_full(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sent_and_ack(sim)
        apply(sim, "partial", "FILL", quantity="0.75", price="100")
        state = apply(sim, "emergency", "EMERGENCY_CLOSE", price="96")
        assert state["status"] == "CLOSED"
        assert state["closed_quantity"] == state["filled_quantity"] == "0.75"
        assert state["open_position_quantity"] == "0.00"
        with pytest.raises(LifecycleRefused):
            apply(sim, "repeat-new-action", "EMERGENCY_CLOSE", price="96")


def test_idempotent_create_retry_and_no_same_key_payload_drift(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        created = sim.create(spec(), action_id="create")
        assert created == sim.create(spec(), action_id="create")
        with pytest.raises(LifecycleRefused, match="IDEMPOTENCY_KEY_PAYLOAD_CONFLICT"):
            sim.create(replace(spec(), stop=D("91")), action_id="create")
        with pytest.raises(LifecycleRefused, match="ORDER_ID_ALREADY_EXISTS"):
            sim.create(spec(), action_id="different-create")
        sent = apply(sim, "send", "SUBMIT")
        assert sent == apply(sim, "send", "SUBMIT")
        with pytest.raises(LifecycleRefused, match="IDEMPOTENCY_KEY_PAYLOAD_CONFLICT"):
            apply(sim, "send", "MARK_UNKNOWN")
        assert [x["event"] for x in sim.events("paper-1")] == ["CREATE", "SUBMIT"]


def test_recovered_journal_no_duplicate_order_after_restart(tmp_path):
    path = tmp_path / "durable.sqlite"
    with PositionLifecycleSimulator(path) as sim:
        sim.create(spec(), action_id="create")
        apply(sim, "send", "SUBMIT")
        snapshot = apply(sim, "timeout", "MARK_UNKNOWN")
    with PositionLifecycleSimulator(path) as sim:
        assert sim.state("paper-1") == snapshot
        with pytest.raises(LifecycleRefused, match="SUBMIT_RETRY_FORBIDDEN"):
            apply(sim, "new-send", "SUBMIT")
        apply(sim, "proven", "RECONCILE_ACK",
              remote_order_id="exchange-1", evidence="verified-order-detail")
        apply(sim, "fill", "FILL", quantity="3", price="101")
        assert sim.state("paper-1")["open_position_quantity"] == "3"
        assert len(sim.events("paper-1")) == 6


def test_failed_transition_rolls_back_without_event_or_revision(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sent_and_ack(sim)
        original = sim.state("paper-1")
        count = len(sim.events("paper-1"))
        with pytest.raises(LifecycleRefused, match="OVERFILL"):
            apply(sim, "overflow", "FILL", quantity="4", price="100")
        with pytest.raises(LifecycleRefused, match="UNPROTECTED_LONG_FILL"):
            apply(sim, "unsafe", "FILL", quantity="1", price="80")
        assert sim.state("paper-1") == original
        assert len(sim.events("paper-1")) == count


def test_two_accounts_in_same_journal_are_separate(tmp_path):
    with PositionLifecycleSimulator(tmp_path / "paper.sqlite") as sim:
        sim.create(spec(), action_id="create")
        sim.create(replace(spec(order_id="other-order"), account_id="demo-2"),
                   action_id="create")
        apply(sim, "send", "SUBMIT")
        assert sim.state("other-order")["status"] == "CREATED"


def test_nonregular_simulator_file_rejected(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    with pytest.raises(LifecycleRefused, match="NONREGULAR"):
        PositionLifecycleSimulator(folder)
    link = tmp_path / "link"
    link.symlink_to(folder)
    with pytest.raises(LifecycleRefused, match="NONREGULAR"):
        PositionLifecycleSimulator(link)
