"""Stage 3: atomic shared-ledger PAPER execution/position safety acceptance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal as D
from threading import Barrier

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.execution_contract_v1 import OrderKind, OrderSpec
from naseri_markets.execution_position_core_v1 import (
    OrchestrationRefused,
    PaperExecutionOrchestratorV1,
)
from naseri_markets.position_lifecycle_simulator import LifecycleRefused
from naseri_markets.risk_portfolio_contract_v1 import (
    AccountRiskPolicy,
    PortfolioRiskPolicy,
)
from naseri_markets.risk_portfolio_manager_v1 import RiskRefused


def instrument(symbol: str = "BTC-PAPER") -> Instrument:
    return Instrument(
        market=Market.CRYPTO, provider="offline-fixture", symbol=symbol,
        timezone="UTC", quote_currency="USD",
    )


def order(
    order_id: str = "order-1", *, account: str = "account-1",
    engine: str = "brooks", symbol: str = "BTC-PAPER", quantity: str = "1",
) -> OrderSpec:
    return OrderSpec(
        order_id=order_id, signal_id="signal-1", account_id=account,
        engine_id=engine, instrument=instrument(symbol), direction=Direction.LONG,
        kind=OrderKind.LIMIT, quantity=D(quantity), reference_entry=D("100"),
        stop=D("90"), target=D("120"),
    )


def portfolio(**kwargs) -> PortfolioRiskPolicy:
    params = dict(
        portfolio_id="portfolio-1", currency="USD",
        max_reserved_risk=D("100"), max_notional=D("10000"),
        max_daily_loss=D("100"), max_group_risk=D("70"),
        max_engine_risk=D("70"), max_active_orders=20,
    )
    return PortfolioRiskPolicy(**(params | kwargs))


def account(account_id: str = "account-1", **kwargs) -> AccountRiskPolicy:
    params = dict(
        account_id=account_id, portfolio_id="portfolio-1",
        currency="USD", equity=D("1000"),
        max_order_risk_fraction=D("0.05"),
        max_total_risk_fraction=D("0.2"),
        max_daily_loss_fraction=D("0.2"),
        max_notional_fraction=D("2"), max_margin_fraction=D("0.9"),
        max_leverage=D("3"), contract_multiplier=D("1"),
        quantity_step=D("0.01"), roundtrip_fee_fraction=D("0.002"),
        worst_slippage_fraction=D("0.003"), max_active_orders=20,
        external_exposure_cleared=True,
    )
    return AccountRiskPolicy(**(params | kwargs))


def configure(core: PaperExecutionOrchestratorV1, *, two_accounts=False) -> None:
    core.configure_portfolio(portfolio())
    core.configure_account(account())
    if two_accounts:
        core.configure_account(account("account-2"))
    core.register_instrument(
        portfolio_id="portfolio-1", instrument=instrument(), group_id="CRYPTO_BETA"
    )
    core.register_instrument(
        portfolio_id="portfolio-1", instrument=instrument("ETH-PAPER"),
        group_id="CRYPTO_BETA",
    )
    core.register_instrument(
        portfolio_id="portfolio-1", instrument=instrument("SOL-PAPER"),
        group_id="ALT_BETA",
    )


@pytest.fixture
def core(tmp_path):
    with PaperExecutionOrchestratorV1(
        tmp_path / "stage3.sqlite", clock=lambda: date(2026, 10, 11)
    ) as service:
        configure(service, two_accounts=True)
        yield service


def submit(core, order_id="order-1", *, action="submit"):
    return core.apply(order_id, action_id=action, event="SUBMIT")


def ack(core, order_id="order-1", *, action="ack"):
    return core.apply(
        order_id, action_id=action, event="ACK", remote_order_id="offline-ack"
    )


def fill(core, order_id="order-1", *, quantity="1", price="100", action="fill"):
    return core.apply(
        order_id, action_id=action, event="FILL", quantity=quantity, price=price
    )


def state(core, order_id="order-1"):
    return core.order_state(order_id)


def risk(core):
    return core.risk_snapshot("portfolio-1")


def test_create_requires_budget_and_atomically_records_both(core):
    receipt = core.create(order(), action_id="create")
    assert receipt["mode"] == "PAPER_ONLY"
    assert receipt["order"]["status"] == "CREATED"
    assert receipt["risk_reservation"]["status"] == "ACTIVE"
    assert risk(core)["active_orders"] == 1
    assert risk(core)["reserved_risk"] == "10.500"
    assert [x["event"] for x in core.order_events("order-1")] == ["CREATE"]
    assert [x["event"] for x in core.risk_audit() if x["event"] == "RESERVE"] == [
        "RESERVE"
    ]


def test_create_idempotency_global_conflicts_and_duplicate_order(core):
    original = core.create(order(), action_id="create")
    assert core.create(order(), action_id="create") == original
    with pytest.raises(OrchestrationRefused, match="GLOBAL_ACTION_ID_CONFLICT"):
        core.create(order("different"), action_id="create")
    with pytest.raises(RiskRefused, match="ORDER_ID_ALREADY_RESERVED"):
        core.create(order(), action_id="other-create")
    assert risk(core)["active_orders"] == 1
    assert len(core.order_events("order-1")) == 1


def test_create_without_risk_permission_never_creates_order(tmp_path):
    with PaperExecutionOrchestratorV1(tmp_path / "stage3.sqlite") as service:
        service.configure_portfolio(portfolio())
        service.configure_account(account(external_exposure_cleared=False))
        service.register_instrument(
            portfolio_id="portfolio-1", instrument=instrument(), group_id="CRYPTO_BETA"
        )
        with pytest.raises(RiskRefused, match="EXTERNAL_EXPOSURE_UNVERIFIED"):
            service.create(order(), action_id="not-authorized")
        assert service.order_state("order-1") is None
        assert risk(service)["active_orders"] == 0


def test_stage_one_create_failure_rolls_back_preceding_risk_reservation(
    core, monkeypatch,
):
    def crash(*_args, **_kwargs):
        raise RuntimeError("SIMULATED_CRASH_BEFORE_COMMIT")

    original = core._orders.create
    monkeypatch.setattr(core._orders, "create", crash)
    with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
        core.create(order(), action_id="failed-create")
    assert risk(core)["active_orders"] == 0
    assert state(core) is None
    monkeypatch.setattr(core._orders, "create", original)
    assert core.create(order(), action_id="failed-create")["order"]["status"] == "CREATED"


def test_submit_and_ack_are_distinct_from_fill(core):
    core.create(order(), action_id="create")
    assert submit(core)["order"]["status"] == "SENT_UNCONFIRMED"
    assert risk(core)["active_orders"] == 1
    assert ack(core)["order"]["status"] == "ACKNOWLEDGED"
    assert state(core)["filled_quantity"] == "0"
    assert fill(core)["order"]["status"] == "FILLED"
    assert state(core)["open_position_quantity"] == "1"
    assert risk(core)["active_orders"] == 1


def test_submission_unknown_blocks_blind_retry_and_unverified_ack(core):
    core.create(order(), action_id="create")
    submit(core)
    core.apply("order-1", action_id="timeout", event="MARK_UNKNOWN")
    assert state(core)["status"] == "SUBMISSION_UNKNOWN"
    with pytest.raises(LifecycleRefused, match="SUBMIT_RETRY_FORBIDDEN"):
        submit(core, action="blind-retry")
    with pytest.raises(LifecycleRefused, match="RECONCILIATION_EVIDENCE_REQUIRED"):
        core.apply(
            "order-1", action_id="bad-reconcile", event="RECONCILE_ACK",
            remote_order_id="remote-1",
        )
    assert state(core)["status"] == "SUBMISSION_UNKNOWN"
    assert risk(core)["active_orders"] == 1
    recovered = core.apply(
        "order-1", action_id="safe-reconcile", event="RECONCILE_ACK",
        remote_order_id="remote-1", evidence="verified-offline-order-lookup",
    )
    assert recovered["order"]["status"] == "ACKNOWLEDGED"
    assert risk(core)["active_orders"] == 1


def test_rejection_releases_only_after_terminal_confirmation(core):
    core.create(order(), action_id="create")
    submit(core)
    result = core.apply("order-1", action_id="rejected", event="REJECT")
    assert result["risk_released"]
    assert risk(core)["active_orders"] == 0
    assert state(core)["status"] == "REJECTED"
    assert result == core.apply("order-1", action_id="rejected", event="REJECT")
    with pytest.raises(OrchestrationRefused, match="ACTIVE_RISK_RESERVATION_REQUIRED"):
        core.apply("order-1", action_id="bad-new-action", event="SUBMIT")


def test_unknown_order_rejected_only_by_reconciliation(core):
    core.create(order(), action_id="create")
    submit(core)
    core.apply("order-1", action_id="timeout", event="MARK_UNKNOWN")
    result = core.apply(
        "order-1", action_id="remote-refused", event="RECONCILE_REJECT",
        evidence="verified-offline-order-history",
    )
    assert result["risk_released"]
    assert result["order"]["status"] == "REJECTED"
    assert risk(core)["reserved_risk"] == "0"


def test_partial_fill_cancellation_keeps_budget_until_closed(core):
    core.create(order(quantity="3"), action_id="create")
    submit(core)
    ack(core)
    fill(core, quantity="1.2", price="99", action="partial")
    assert state(core)["status"] == "PARTIALLY_FILLED"
    assert state(core)["current_stop"] == "90"
    assert risk(core)["active_orders"] == 1
    with pytest.raises(LifecycleRefused, match="CANCEL_REMAINDER_BEFORE_CLOSE"):
        core.apply(
            "order-1", action_id="unsafe-close", event="CLOSE_FILL",
            quantity="0.2", price="101",
        )
    core.apply("order-1", action_id="cancel-rest", event="CANCEL")
    assert risk(core)["active_orders"] == 1
    partial = core.apply(
        "order-1", action_id="partial-close", event="CLOSE_FILL",
        quantity="0.2", price="102",
    )
    assert not partial["risk_released"]
    assert state(core)["open_position_quantity"] == "1.0"
    final = core.apply(
        "order-1", action_id="remaining-close", event="CLOSE_FILL",
        quantity="1.0", price="103",
    )
    assert final["risk_released"]
    assert final["order"]["status"] == "CLOSED"
    assert final["order"]["open_position_quantity"] == "0.0"
    assert risk(core)["active_orders"] == 0


def test_stop_tightening_and_failed_widening_keeps_risk(core):
    core.create(order(), action_id="create")
    submit(core)
    ack(core)
    fill(core)
    changed = core.apply(
        "order-1", action_id="breakeven", event="AMEND_STOP", stop="100"
    )
    assert changed["order"]["current_stop"] == "100"
    with pytest.raises(LifecycleRefused, match="STOP_WIDENING_FORBIDDEN"):
        core.apply("order-1", action_id="weaken", event="AMEND_STOP", stop="99")
    assert state(core)["revision"] == changed["order"]["revision"]
    assert risk(core)["active_orders"] == 1


def test_closing_loss_posts_cumulative_daily_budget_and_releases(core):
    core.create(order(), action_id="create")
    submit(core)
    ack(core)
    fill(core)
    result = core.apply(
        "order-1", action_id="close-loss", event="CLOSE_FILL",
        quantity="1", price="40",
    )
    assert result["risk_released"]
    assert D(result["modeled_realized_loss"]) > D("60")
    assert risk(core)["active_orders"] == 0
    assert D(risk(core)["daily_realized_loss_magnitude"]) > D("60")
    with pytest.raises(RiskRefused, match="PORTFOLIO_DAILY_WORST_CASE_CAP"):
        core.create(order("next-order", quantity="4"), action_id="new-after-loss")
    assert state(core, "next-order") is None
    assert risk(core)["active_orders"] == 0


def test_profitable_close_does_not_erase_existing_daily_losses(core):
    core.record_loss("account-1", action_id="manual-loss", amount=D("5"))
    core.create(order(), action_id="create")
    submit(core)
    ack(core)
    fill(core)
    result = core.apply(
        "order-1", action_id="profit-close", event="CLOSE_FILL",
        quantity="1", price="110",
    )
    assert result["modeled_realized_loss"] == "0"
    assert risk(core)["daily_realized_loss_magnitude"] == "5"
    assert result["risk_released"]


def test_close_loss_and_risk_release_failure_roll_back_order_and_loss(
    core, monkeypatch,
):
    core.create(order(), action_id="create")
    submit(core)
    ack(core)
    fill(core)
    before = risk(core)
    original = core._risk.release

    def fail(*_args, **_kwargs):
        raise RuntimeError("SIMULATED_RELEASE_STORAGE_FAILURE")

    monkeypatch.setattr(core._risk, "release", fail)
    with pytest.raises(RuntimeError, match="SIMULATED_RELEASE_STORAGE_FAILURE"):
        core.apply(
            "order-1", action_id="close", event="CLOSE_FILL",
            quantity="1", price="40",
        )
    assert state(core)["status"] == "FILLED"
    assert state(core)["closed_quantity"] == "0"
    assert risk(core) == before
    monkeypatch.setattr(core._risk, "release", original)
    assert core.apply(
        "order-1", action_id="close", event="CLOSE_FILL",
        quantity="1", price="40",
    )["risk_released"]


def test_emergency_close_is_synthetic_and_clears_filled_partial(core):
    core.create(order(quantity="3"), action_id="create")
    submit(core)
    ack(core)
    fill(core, quantity="0.5", action="fill-half")
    core.halt(
        portfolio_id="portfolio-1", scope="portfolio",
        subject_id="portfolio-1", action_id="halt-all",
    )
    assert risk(core)["active_orders"] == 1
    with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
        core.create(order("no-new"), action_id="no-new")
    closed = core.apply(
        "order-1", action_id="emergency", event="EMERGENCY_CLOSE", price="80"
    )
    assert closed["risk_released"]
    assert closed["order"]["status"] == "CLOSED"
    assert closed["order"]["open_position_quantity"] == "0.0"
    assert D(closed["modeled_realized_loss"]) > 0
    assert risk(core)["active_orders"] == 0
    assert risk(core)["halted"]


def test_halt_engine_still_allows_existing_position_exit(core):
    core.create(order(), action_id="create")
    submit(core)
    ack(core)
    fill(core)
    core.halt(
        portfolio_id="portfolio-1", scope="engine",
        subject_id="brooks", action_id="halt-engine",
    )
    result = core.apply(
        "order-1", action_id="exit-after-halt", event="CLOSE_FILL",
        quantity="1", price="102",
    )
    assert result["risk_released"]
    with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
        core.create(order("new"), action_id="blocked-new")


def test_cancel_before_sent_releases_unfilled_intent(core):
    core.create(order(), action_id="create")
    result = core.apply("order-1", action_id="cancel-created", event="CANCEL")
    assert result["risk_released"]
    assert result["order"]["status"] == "CANCELED"


def test_out_of_band_state_mutation_mismatch_blocks_stage3(core):
    core.create(order(), action_id="create")
    # Fault injection: simulate an untrusted mutation bypassing Stage-3 ledger.
    core._db.execute(
        "UPDATE paper_risk_reservations SET contract_json=? WHERE order_id=?",
        ('{"forged":true}', "order-1"),
    )
    with pytest.raises(OrchestrationRefused, match="RESERVED_ORDER_SPEC_MISMATCH"):
        submit(core)
    assert state(core)["status"] == "CREATED"


def test_duplicate_action_payload_drift_refused_even_after_close(core):
    core.create(order(), action_id="create")
    submit(core)
    original = ack(core)
    assert ack(core) == original
    with pytest.raises(OrchestrationRefused, match="GLOBAL_ACTION_ID_CONFLICT"):
        core.apply(
            "order-1", action_id="ack", event="ACK", remote_order_id="different"
        )


def test_full_recovery_from_unknown_after_new_instance(tmp_path):
    path = tmp_path / "recover.sqlite"
    with PaperExecutionOrchestratorV1(path) as service:
        configure(service)
        service.create(order(), action_id="create")
        submit(service)
        service.apply("order-1", action_id="lost-network", event="MARK_UNKNOWN")
    with PaperExecutionOrchestratorV1(path) as service:
        assert state(service)["status"] == "SUBMISSION_UNKNOWN"
        assert risk(service)["active_orders"] == 1
        with pytest.raises(LifecycleRefused, match="SUBMIT_RETRY_FORBIDDEN"):
            submit(service, action="retry")
        service.apply(
            "order-1", action_id="reconciled", event="RECONCILE_ACK",
            remote_order_id="provider-1", evidence="offline-provider-ledger",
        )
        fill(service)
        assert risk(service)["active_orders"] == 1
        service.apply(
            "order-1", action_id="close", event="CLOSE_FILL",
            quantity="1", price="101",
        )
    with PaperExecutionOrchestratorV1(path) as service:
        assert state(service)["status"] == "CLOSED"
        assert risk(service)["active_orders"] == 0
        assert len(service.order_events("order-1")) == 6


def test_multiple_accounts_and_engines_still_share_portfolio_budget(core):
    core.create(order("b1", quantity="3"), action_id="b1-create")
    core.create(
        order("c1", account="account-2", engine="custom",
              symbol="ETH-PAPER", quantity="3"),
        action_id="c1-create",
    )
    assert risk(core)["reserved_risk"] == "63.000"
    with pytest.raises(RiskRefused, match="CORRELATION_GROUP_CAP"):
        core.create(
            order("b2", engine="brooks", symbol="ETH-PAPER"),
            action_id="correlated-limit",
        )
    assert risk(core)["active_orders"] == 2


def test_simultaneous_create_one_shared_slot(tmp_path):
    path = tmp_path / "concurrent.sqlite"
    with PaperExecutionOrchestratorV1(path) as service:
        service.configure_portfolio(portfolio(
            max_reserved_risk=D("15"), max_group_risk=D("15"),
            max_engine_risk=D("15"),
        ))
        service.configure_account(account())
        service.configure_account(account("account-2"))
        service.register_instrument(
            portfolio_id="portfolio-1", instrument=instrument(), group_id="BETA"
        )
    gate = Barrier(2)

    def race(n):
        with PaperExecutionOrchestratorV1(path) as service:
            gate.wait(timeout=5)
            try:
                service.create(
                    order(f"order-{n}", account=f"account-{n}"),
                    action_id=f"create-{n}",
                )
                return "APPROVED"
            except RiskRefused:
                return "DENIED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcome = list(pool.map(race, (1, 2)))
    assert sorted(outcome) == ["APPROVED", "DENIED"]
    with PaperExecutionOrchestratorV1(path) as service:
        assert risk(service)["active_orders"] == 1
        created = [service.order_state(f"order-{i}") is not None for i in (1, 2)]
        assert sorted(created) == [False, True]


def test_failed_mutation_never_changes_risk_or_lifecycle_event_counts(core):
    core.create(order(), action_id="create")
    before_state = state(core)
    before_budget = risk(core)
    event_count = len(core.order_events("order-1"))
    with pytest.raises(LifecycleRefused, match="FILL_REQUIRES_ACKNOWLEDGEMENT"):
        fill(core)
    assert state(core) == before_state
    assert risk(core) == before_budget
    assert len(core.order_events("order-1")) == event_count


def test_nonregular_path_refused(tmp_path):
    directory = tmp_path / "dbdir"
    directory.mkdir()
    with pytest.raises(OrchestrationRefused, match="NONREGULAR"):
        PaperExecutionOrchestratorV1(directory)
    link = tmp_path / "link"
    link.symlink_to(directory)
    with pytest.raises(OrchestrationRefused, match="NONREGULAR"):
        PaperExecutionOrchestratorV1(link)


def test_short_position_direction_and_realized_loss_are_correct(core):
    spec = OrderSpec(
        order_id="short-1", signal_id="s-short", account_id="account-1",
        engine_id="brooks", instrument=instrument(), direction=Direction.SHORT,
        kind=OrderKind.MARKET, quantity=D("1"),
        reference_entry=D("100"), stop=D("110"), target=D("80"),
    )
    core.create(spec, action_id="create-short")
    submit(core, "short-1", action="submit-short")
    ack(core, "short-1", action="ack-short")
    fill(core, "short-1", action="fill-short", price="100")
    result = core.apply(
        "short-1", action_id="close-short", event="CLOSE_FILL",
        quantity="1", price="120",
    )
    assert result["risk_released"]
    assert D(result["modeled_realized_loss"]) > D("20")
    assert D(risk(core)["daily_realized_loss_magnitude"]) > D("20")


def test_direct_shared_manager_writes_require_orchestrator_transaction(core):
    with pytest.raises(RiskRefused, match="SHARED_TRANSACTION_REQUIRED"):
        core._risk.reserve(order(), action_id="direct-risk-unsafe")
    with pytest.raises(LifecycleRefused, match="SHARED_TRANSACTION_REQUIRED"):
        core._orders.create(order(), action_id="direct-order-unsafe")
    assert risk(core)["active_orders"] == 0
    assert state(core) is None


def test_loss_post_failure_rolls_back_close_fill_and_budget(core, monkeypatch):
    core.create(order(), action_id="create")
    submit(core)
    ack(core)
    fill(core)
    original = core._risk.record_loss
    before_budget = risk(core)
    before_events = len(core.order_events("order-1"))

    def simulate_failure(*_args, **_kwargs):
        raise RuntimeError("PAPER_LOSS_POSTING_FAILED")

    monkeypatch.setattr(core._risk, "record_loss", simulate_failure)
    with pytest.raises(RuntimeError, match="PAPER_LOSS_POSTING_FAILED"):
        core.apply(
            "order-1", action_id="close-post", event="CLOSE_FILL",
            quantity="1", price="50",
        )
    assert state(core)["status"] == "FILLED"
    assert risk(core) == before_budget
    assert len(core.order_events("order-1")) == before_events
    monkeypatch.setattr(core._risk, "record_loss", original)
    assert core.apply(
        "order-1", action_id="close-post", event="CLOSE_FILL",
        quantity="1", price="50",
    )["risk_released"]
