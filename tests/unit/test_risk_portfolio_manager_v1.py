"""Risk & Portfolio Manager V1: offline deterministic safety acceptance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from threading import Barrier

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.execution_contract_v1 import OrderKind, OrderSpec
from naseri_markets.position_lifecycle_simulator import PositionLifecycleSimulator
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from naseri_markets.risk_portfolio_manager_v1 import PaperRiskPortfolioManager, RiskRefused


def inst(symbol="BTC-PAPER", provider="offline-fixture"):
    return Instrument(
        market=Market.CRYPTO, provider=provider, symbol=symbol,
        timezone="UTC", quote_currency="USD",
    )


def order(order_id="order-1", *, account="account-1", engine="brooks",
          symbol="BTC-PAPER", quantity="1"):
    return OrderSpec(
        order_id=order_id, signal_id="signal-1", account_id=account,
        engine_id=engine, instrument=inst(symbol), direction=Direction.LONG,
        kind=OrderKind.LIMIT, quantity=D(quantity), reference_entry=D("100"),
        stop=D("90"), target=D("120"),
    )


def pp(**kwargs):
    values = dict(
        portfolio_id="portfolio-1", currency="USD",
        max_reserved_risk=D("100"), max_notional=D("10000"),
        max_daily_loss=D("100"), max_group_risk=D("50"),
        max_engine_risk=D("70"), max_active_orders=20,
    )
    return PortfolioRiskPolicy(**(values | kwargs))


def ap(account="account-1", **kwargs):
    values = dict(
        account_id=account, portfolio_id="portfolio-1", currency="USD",
        equity=D("1000"), max_order_risk_fraction=D("0.03"),
        max_total_risk_fraction=D("0.2"),
        max_daily_loss_fraction=D("0.2"),
        max_notional_fraction=D("2"),
        max_margin_fraction=D("0.9"), max_leverage=D("3"),
        contract_multiplier=D("1"), quantity_step=D("0.01"),
        roundtrip_fee_fraction=D("0.002"),
        worst_slippage_fraction=D("0.003"), max_active_orders=20,
        external_exposure_cleared=True,
    )
    return AccountRiskPolicy(**(values | kwargs))


@pytest.fixture
def managed(tmp_path):
    with PaperRiskPortfolioManager(tmp_path / "paper-risk.sqlite",
                                   clock=lambda: date(2026, 10, 11)) as risk:
        risk.configure_portfolio(pp())
        risk.configure_account(ap())
        risk.configure_account(ap("account-2"))
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst("ETH-PAPER"), group_id="CRYPTO_BETA")
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst("SOL-PAPER"), group_id="ALT_BETA")
        yield risk


def reserve(manager, order_id="order-1", *, account="account-1",
            engine="brooks", symbol="BTC-PAPER", quantity="1", action=None):
    return manager.reserve(
        order(order_id, account=account, engine=engine, symbol=symbol,
              quantity=quantity),
        action_id=action or ("reserve-" + order_id),
    )


def test_atomic_reservation_receipt_and_audit(managed):
    r = reserve(managed)
    assert r["mode"] == "PAPER_RISK_RESERVATION_ONLY"
    assert r["risk"] == "10.500"
    assert r["notional"] == "100"
    assert D(r["modeled_margin"]) == D("100") / D("3")
    status = managed.snapshot("portfolio-1")
    assert status["active_orders"] == 1
    assert status["reserved_risk"] == "10.500"
    assert [e["event"] for e in managed.audit()] == [
        "CONFIGURE_PORTFOLIO", "CONFIGURE_ACCOUNT", "CONFIGURE_ACCOUNT",
        "REGISTER_INSTRUMENT", "REGISTER_INSTRUMENT", "REGISTER_INSTRUMENT",
        "RESERVE",
    ]


def test_idempotent_request_replays_exact_original_receipt(managed):
    first = reserve(managed, action="same-action")
    assert first == reserve(managed, action="same-action")
    assert managed.snapshot("portfolio-1")["active_orders"] == 1
    with pytest.raises(RiskRefused, match="ACTION_ID_PAYLOAD_CONFLICT"):
        reserve(managed, "other", action="same-action")
    with pytest.raises(RiskRefused, match="ORDER_ID_ALREADY_RESERVED"):
        reserve(managed, "order-1", action="different-action")
    assert len([e for e in managed.audit() if e["event"] == "RESERVE"]) == 1


def test_account_and_portfolio_cross_engine_budget_share(managed):
    reserve(managed, "b1", engine="brooks", symbol="BTC-PAPER", quantity="2")
    reserve(managed, "c1", engine="custom", symbol="ETH-PAPER", quantity="2",
            account="account-2")
    assert managed.snapshot("portfolio-1")["reserved_risk"] == "42.000"
    with pytest.raises(RiskRefused, match="CORRELATION_GROUP_CAP"):
        reserve(managed, "b2", engine="brooks", symbol="ETH-PAPER")
    # Different correlated groups may consume the residual portfolio budget.
    reserve(managed, "s1", engine="custom", symbol="SOL-PAPER",
            account="account-2")
    assert managed.snapshot("portfolio-1")["reserved_risk"] == "52.500"


def test_portfolio_cap_across_accounts_and_groups(managed):
    # Two large orders are allowed under account caps but aggregate exceeds 100.
    reserve(managed, "b1", quantity="2")
    reserve(managed, "s1", account="account-2", symbol="SOL-PAPER", quantity="2")
    with pytest.raises(RiskRefused, match="CORRELATION_GROUP_CAP"):
        reserve(managed, "e1", symbol="ETH-PAPER", quantity="2.8")
    assert managed.snapshot("portfolio-1")["active_orders"] == 2


def test_engine_concentration_cap_across_accounts(managed):
    for i in range(3):
        reserve(managed, f"a{i}", engine="same-engine", symbol="BTC-PAPER",
                quantity="1.5", account="account-1" if i == 0 else "account-2")
    # The group cap triggers earlier than engine cap here (47.25 + 10.5 > 50).
    with pytest.raises(RiskRefused, match="CORRELATION_GROUP_CAP"):
        reserve(managed, "no-4", engine="same-engine", symbol="BTC-PAPER")
    with pytest.raises(RiskRefused, match="ENGINE_CONCENTRATION_CAP"):
        reserve(managed, "no-alt", engine="same-engine",
                symbol="SOL-PAPER", quantity="2.8")


def test_unregistered_instrument_and_currency_never_sneak_in(managed):
    with pytest.raises(RiskRefused, match="INSTRUMENT_UNMAPPED"):
        reserve(managed, "unknown", symbol="DOGE-PAPER")
    with pytest.raises(RiskRefused, match="INSTRUMENT_GROUP_IMMUTABLE"):
        managed.register_instrument(portfolio_id="portfolio-1",
                                    instrument=inst(), group_id="FAKE_GROUP")
    with pytest.raises(RiskRefused, match="CURRENCY_MISMATCH"):
        managed.register_instrument(
            portfolio_id="portfolio-1",
            instrument=replace(inst(), quote_currency="EUR"),
            group_id="CRYPTO_BETA",
        )


def test_contract_quantity_step_account_per_order_and_margin_caps(managed):
    with pytest.raises(RiskRefused, match="QUANTITY_STEP_VIOLATION"):
        reserve(managed, "fraction", quantity="0.001")
    with pytest.raises(RiskRefused, match="PER_ORDER_RISK_CAP"):
        reserve(managed, "over-order", quantity="3")
    with pytest.raises(RiskRefused, match="ACCOUNT_NOTIONAL_CAP"):
        managed.reserve(replace(order("notional"), quantity=D("21"),
                                stop=D("99.9"), target=D("120")),
                        action_id="large-notional")
    # Already failed reservations never consume portfolio funds.
    assert managed.snapshot("portfolio-1")["active_orders"] == 0


def test_account_total_and_count_caps(tmp_path):
    with PaperRiskPortfolioManager(tmp_path / "risk.sqlite") as risk:
        risk.configure_portfolio(pp())
        risk.configure_account(ap(max_total_risk_fraction=D("0.015")))
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        reserve(risk)
        with pytest.raises(RiskRefused, match="ACCOUNT_RESERVED_RISK_CAP"):
            reserve(risk, "next")
    with PaperRiskPortfolioManager(tmp_path / "count.sqlite") as risk:
        risk.configure_portfolio(pp())
        risk.configure_account(ap(max_active_orders=1))
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        reserve(risk)
        with pytest.raises(RiskRefused, match="ACCOUNT_ACTIVE_ORDER_CAP"):
            reserve(risk, "next")


def test_halts_one_way_and_keep_existing_risk_reserved(managed):
    reserve(managed)
    decision = managed.halt(portfolio_id="portfolio-1", scope="engine",
                            subject_id="brooks", action_id="halt-brooks")
    assert decision["halt_new_risk"]
    with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
        reserve(managed, "blocked")
    reserve(managed, "custom", engine="custom", symbol="SOL-PAPER")
    assert managed.snapshot("portfolio-1")["active_orders"] == 2
    managed.halt(portfolio_id="portfolio-1", scope="account",
                 subject_id="account-2", action_id="halt-account")
    with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
        reserve(managed, "other-acct", account="account-2", engine="custom")
    managed.halt(portfolio_id="portfolio-1", scope="portfolio",
                 subject_id="portfolio-1", action_id="halt-all")
    with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
        reserve(managed, "any", engine="custom", symbol="SOL-PAPER")
    assert managed.snapshot("portfolio-1")["active_orders"] == 2


def test_halt_wrong_account_cannot_cross_portfolio(managed):
    managed.configure_portfolio(pp(portfolio_id="portfolio-2"))
    managed.configure_account(ap("account-other-portfolio", portfolio_id="portfolio-2"))
    with pytest.raises(RiskRefused, match="HALT_ACCOUNT_PORTFOLIO_MISMATCH"):
        managed.halt(portfolio_id="portfolio-1", scope="account",
                     subject_id="account-other-portfolio", action_id="wrong")
    with pytest.raises(RiskRefused, match="PORTFOLIO_HALT_ID_MISMATCH"):
        managed.halt(portfolio_id="portfolio-1", scope="portfolio",
                     subject_id="other-portfolio", action_id="wrong2")


def test_daily_loss_monotone_idempotent_and_worst_case(managed):
    receipt = managed.record_loss("account-1", action_id="loss-1", amount=D("191"))
    assert receipt["daily_loss"] == "191"
    assert managed.record_loss("account-1", action_id="loss-1", amount=D("191")) == receipt
    with pytest.raises(RiskRefused, match="DAILY_LOSS_CIRCUIT_BREAKER"):
        reserve(managed)
    with pytest.raises(RiskRefused, match="DAILY_LOSS_CIRCUIT_BREAKER"):
        reserve(managed, "account-other", account="account-2")
    assert managed.snapshot("portfolio-1")["daily_realized_loss_magnitude"] == "191"
    with pytest.raises(RiskRefused, match="ACTION_ID_PAYLOAD_CONFLICT"):
        managed.record_loss("account-1", action_id="loss-1", amount=D("1"))


def test_account_daily_worst_case_reservations_consume_budget(tmp_path):
    with PaperRiskPortfolioManager(tmp_path / "risk.sqlite") as risk:
        risk.configure_portfolio(pp(max_group_risk=D("100"), max_daily_loss=D("500")))
        risk.configure_account(ap(max_daily_loss_fraction=D("0.03")))
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        reserve(risk, "first", quantity="2")
        with pytest.raises(RiskRefused, match="ACCOUNT_DAILY_WORST_CASE_CAP"):
            reserve(risk, "next", quantity="1")


def test_rollover_and_clock_rollback_no_bypass(tmp_path):
    day = [date(2026, 10, 11)]
    with PaperRiskPortfolioManager(tmp_path / "risk.sqlite",
                                   clock=lambda: day[0]) as risk:
        risk.configure_portfolio(pp())
        risk.configure_account(ap())
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        risk.record_loss("account-1", action_id="loss", amount=D("100"))
        with pytest.raises(RiskRefused, match="DAILY_LOSS_CIRCUIT_BREAKER"):
            reserve(risk)
        day[0] = date(2026, 10, 12)
        reserve(risk)
        assert risk.snapshot("portfolio-1")["daily_realized_loss_magnitude"] == "0"
        day[0] = date(2026, 10, 11)
        with pytest.raises(RiskRefused, match="CLOCK_ROLLBACK_REFUSED"):
            reserve(risk, "replayed-past")


def test_external_exposure_unknown_blocks_even_offline(tmp_path):
    with PaperRiskPortfolioManager(tmp_path / "risk.sqlite") as risk:
        risk.configure_portfolio(pp())
        risk.configure_account(ap(external_exposure_cleared=False))
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        with pytest.raises(RiskRefused, match="EXTERNAL_EXPOSURE_UNVERIFIED"):
            reserve(risk)


def test_release_requires_exact_terminal_stage_one_snapshot(managed, tmp_path):
    reserve(managed)
    with PositionLifecycleSimulator(tmp_path / "positions.sqlite") as sim:
        pending = sim.create(order(), action_id="create")
        with pytest.raises(RiskRefused, match="RESERVATION_STILL_AT_RISK"):
            managed.release("order-1", action_id="unsafe", evidence="simulated-state",
                            lifecycle_snapshot=pending)
        sim.apply("order-1", action_id="send", event="SUBMIT")
        unknown = sim.apply("order-1", action_id="unknown", event="MARK_UNKNOWN")
        with pytest.raises(RiskRefused, match="RESERVATION_STILL_AT_RISK"):
            managed.release("order-1", action_id="unknown-release", evidence="simulated-state",
                            lifecycle_snapshot=unknown)
        with pytest.raises(RiskRefused, match="TERMINAL_IDENTITY_MISMATCH"):
            managed.release("order-1", action_id="forged", evidence="simulated-state",
                            lifecycle_snapshot={**pending, "spec": {"order_id": "other"}})
        sim.apply("order-1", action_id="reconciled", event="RECONCILE_REJECT",
                  evidence="offline-order-history-fixture")
        terminal = sim.state("order-1")
        receipt = managed.release("order-1", action_id="safe-release",
                                  evidence="offline-terminal-fixture",
                                  lifecycle_snapshot=terminal)
        assert receipt["status"] == "RELEASED"
        assert managed.release("order-1", action_id="safe-release",
                               evidence="offline-terminal-fixture",
                               lifecycle_snapshot=terminal) == receipt
        assert managed.snapshot("portfolio-1")["active_orders"] == 0
        with pytest.raises(RiskRefused, match="NO_ACTIVE_RESERVATION"):
            managed.release("order-1", action_id="another",
                            evidence="offline-terminal-fixture", lifecycle_snapshot=terminal)


def test_partial_fill_and_open_position_never_release_early(managed, tmp_path):
    reserve(managed)
    with PositionLifecycleSimulator(tmp_path / "sim.sqlite") as sim:
        sim.create(order(), action_id="created")
        sim.apply("order-1", action_id="send", event="SUBMIT")
        sim.apply("order-1", action_id="ack", event="ACK", remote_order_id="mock-1")
        sim.apply("order-1", action_id="fill", event="FILL", quantity="1", price="100")
        with pytest.raises(RiskRefused, match="RESERVATION_STILL_AT_RISK"):
            managed.release("order-1", action_id="premature",
                            evidence="offline-fixture",
                            lifecycle_snapshot=sim.state("order-1"))
        sim.apply("order-1", action_id="close", event="CLOSE_FILL",
                  quantity="1", price="102")
        assert managed.release("order-1", action_id="releasable",
                               evidence="offline-fixture",
                               lifecycle_snapshot=sim.state("order-1"))["status"] == "RELEASED"


def test_crash_restart_does_not_lose_risk_or_one_way_halt(tmp_path):
    path = tmp_path / "risk.sqlite"
    with PaperRiskPortfolioManager(path) as risk:
        risk.configure_portfolio(pp())
        risk.configure_account(ap())
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
        previous = reserve(risk)
        risk.halt(portfolio_id="portfolio-1", scope="engine",
                  subject_id="brooks", action_id="halt")
    with PaperRiskPortfolioManager(path) as risk:
        assert risk.snapshot("portfolio-1")["reserved_risk"] == "10.500"
        assert reserve(risk) == previous
        with pytest.raises(RiskRefused, match="NEW_RISK_HALTED"):
            reserve(risk, "after-restart")


def test_concurrent_connections_serialize_and_only_one_fits(tmp_path):
    db = tmp_path / "risk.sqlite"
    with PaperRiskPortfolioManager(db) as risk:
        risk.configure_portfolio(
            pp(max_reserved_risk=D("17"), max_group_risk=D("17"),
               max_engine_risk=D("17"))
        )
        risk.configure_account(ap())
        risk.configure_account(ap("account-2"))
        risk.register_instrument(portfolio_id="portfolio-1",
                                 instrument=inst(), group_id="CRYPTO_BETA")
    barrier = Barrier(2)

    def try_reserve(i):
        with PaperRiskPortfolioManager(db) as risk:
            barrier.wait(timeout=5)
            try:
                reserve(risk, f"order-{i}", account=f"account-{i}")
                return "APPROVED"
            except RiskRefused:
                return "DENIED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(try_reserve, (1, 2)))
    assert sorted(results) == ["APPROVED", "DENIED"]
    with PaperRiskPortfolioManager(db) as risk:
        assert risk.snapshot("portfolio-1")["active_orders"] == 1


def test_configuration_cannot_relax_budget_or_rebind_instrument(managed):
    managed.configure_portfolio(pp())
    managed.configure_account(ap())
    with pytest.raises(RiskRefused, match="PORTFOLIO_POLICY_IMMUTABLE"):
        managed.configure_portfolio(pp(max_reserved_risk=D("1000")))
    with pytest.raises(RiskRefused, match="ACCOUNT_POLICY_IMMUTABLE"):
        managed.configure_account(ap(max_order_risk_fraction=D("0.7")))
    with pytest.raises(RiskRefused, match="INSTRUMENT_GROUP_IMMUTABLE"):
        managed.register_instrument(portfolio_id="portfolio-1",
                                    instrument=inst(), group_id="DIFFERENT")


@pytest.mark.parametrize("bad_policy", [
    {"equity": D("NaN")}, {"max_daily_loss_fraction": D("1.1")},
    {"external_exposure_cleared": "yes"}, {"max_active_orders": True},
    {"quantity_step": D("0")}, {"max_margin_fraction": D("-1")},
])
def test_invalid_account_policy_fails_closed(bad_policy):
    with pytest.raises(ValueError):
        ap(**bad_policy)


def test_error_paths_never_consume_risk_or_audit_mutation(managed):
    before = managed.snapshot("portfolio-1")
    events = len(managed.audit())
    with pytest.raises(RiskRefused):
        reserve(managed, quantity="100")
    with pytest.raises(RiskRefused):
        managed.record_loss("account-1", action_id="bad-loss", amount=D("NaN"))
    assert managed.snapshot("portfolio-1") == before
    assert len(managed.audit()) == events


def test_nonregular_storage_refused(tmp_path):
    folder = tmp_path / "directory"
    folder.mkdir()
    with pytest.raises(RiskRefused, match="NONREGULAR"):
        PaperRiskPortfolioManager(folder)
    link = tmp_path / "sym"
    link.symlink_to(folder)
    with pytest.raises(RiskRefused, match="NONREGULAR"):
        PaperRiskPortfolioManager(link)
