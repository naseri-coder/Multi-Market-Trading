"""Offline Stage-9 DEMO operator smoke acceptance and privacy/failure tests."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from naseri_markets.mt5_demo_operator_smoke_cli import run_once
from naseri_markets.mt5_demo_operator_smoke_v1 import (
    MT5DemoSmokeRefused,
    observe_demo_smoke,
    preflight_window,
    sdk_contract_preflight,
)
from naseri_markets.mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5ReadRefused,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
END = START + timedelta(hours=12)
NOW = END + timedelta(days=1)
T1 = int((START + timedelta(hours=3)).timestamp() * 1000)


def order(ticket: int = 101) -> NS:
    return NS(
        ticket=ticket, position_id=501, symbol="PRIVATE_EURUSD",
        type=0, state=4, time_setup_msc=T1 - 1000, time_done_msc=T1,
        volume_initial=0.75, volume_current=0.0, price_open=100.0,
    )


def deal(ticket: int = 201) -> NS:
    return NS(
        ticket=ticket, order=101, position_id=501,
        symbol="PRIVATE_EURUSD", type=0, entry=0,
        time_msc=T1, volume=0.75, price=100.0,
        profit=0.0, commission=-0.1, swap=0.0, fee=-0.02,
    )


def active(ticket=901, *, volume=0.75) -> NS:
    return NS(
        ticket=ticket, symbol="PRIVATE_EURUSD", type=0,
        volume=volume, price_open=100.0, sl=90.0, tp=120.0,
    )


class MockBroker:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0

    def __init__(self):
        self.account = NS(
            trade_mode=0, login=87654321, server="Private-Fake-Demo-Server",
            margin_mode=2, currency="USD", equity=10000.0, margin_free=9000.0,
        )
        self.terminal = NS(connected=True)
        self.orders = [order()]
        self.deals = [deal()]
        self.active = [active()]
        self.pending = []
        self.calls: list[str] = []
        self.account_reads = 0
        self.switch_login_after = 0
        self.switch_mode_after = 0
        self.move_volume_after = 0
        self.initialize_result = True
        self.history_none = False
        self.history_count_offset = 0

    def initialize(self):
        self.calls.append("initialize")
        return self.initialize_result

    def shutdown(self):
        self.calls.append("shutdown")

    def terminal_info(self):
        self.calls.append("terminal_info")
        return self.terminal

    def account_info(self):
        self.calls.append("account_info")
        self.account_reads += 1
        data = vars(self.account).copy()
        if self.switch_login_after and self.account_reads >= self.switch_login_after:
            data["login"] = 99999999
        if self.switch_mode_after and self.account_reads >= self.switch_mode_after:
            data["margin_mode"] = 0
        return NS(**data)

    def positions_get(self):
        self.calls.append("positions_get")
        if self.move_volume_after and self.account_reads >= self.move_volume_after:
            return [active(volume=0.8)]
        return self.active

    def orders_get(self):
        self.calls.append("orders_get")
        return self.pending

    def _slice(self, data, from_date, to_date, attr):
        a, b = int(from_date.timestamp()*1000), int(to_date.timestamp()*1000)
        return tuple(x for x in data if a <= getattr(x, attr) <= b)

    def history_orders_get(self, from_date, to_date):
        self.calls.append("history_orders_get")
        if self.history_none:
            return None
        return self._slice(self.orders, from_date, to_date, "time_done_msc")

    def history_deals_get(self, from_date, to_date):
        self.calls.append("history_deals_get")
        return self._slice(self.deals, from_date, to_date, "time_msc")

    def history_orders_total(self, from_date, to_date):
        self.calls.append("history_orders_total")
        return len(self._slice(self.orders, from_date, to_date, "time_done_msc")) + self.history_count_offset

    def history_deals_total(self, from_date, to_date):
        self.calls.append("history_deals_total")
        return len(self._slice(self.deals, from_date, to_date, "time_msc"))


@pytest.fixture
def provider():
    return MockBroker()


def expected():
    return DemoAccountExpectation(
        account_id="local-private-demo", login=87654321,
        server="Private-Fake-Demo-Server",
    )


def args(**changes):
    data = dict(
        sdk_preflight_only=False,
        connect_existing_demo_terminal=True,
        ack_initialize_may_start_terminal=True,
        account_id="local-private-demo",
        expected_login=87654321,
        expected_server="Private-Fake-Demo-Server",
        start_utc=START.isoformat(),
        end_utc=END.isoformat(),
    )
    data.update(changes)
    return argparse.Namespace(**data)


def test_sdk_preflight_calls_nothing_even_when_broker_has_no_account(provider):
    provider.account = None
    report = sdk_contract_preflight(provider)
    assert report["read_methods_verified"] == 8
    assert report["session_functions_present"]
    assert not report["terminal_connected"]
    assert not report["live_demo_compatibility_verified"]
    assert provider.calls == []


def test_sdk_only_cli_never_initializes_or_logs_into_account(provider):
    result = run_once(args(sdk_preflight_only=True), provider)
    assert result["mode"] == "MT5_READONLY_SDK_CONTRACT_CHECK"
    assert provider.calls == []


@pytest.mark.parametrize("missing", [
    "history_orders_total", "history_deals_get", "orders_get", "initialize", "shutdown",
])
def test_broken_sdk_capability_prevents_terminal_connection(provider, missing):
    setattr(provider, missing, None)
    with pytest.raises(MT5DemoSmokeRefused, match="SDK_READ_CONTRACT"):
        run_once(args(), provider)
    assert provider.calls == []


def test_sdk_constant_validation_blocks_unknown_margin_mode(provider):
    provider.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 2
    with pytest.raises(MT5DemoSmokeRefused, match="SDK_READ_CONTRACT"):
        run_once(args(), provider)
    assert provider.calls == []


@pytest.mark.parametrize("field", [
    "connect_existing_demo_terminal", "ack_initialize_may_start_terminal",
])
def test_explicit_two_part_operator_consent_required(provider, field):
    with pytest.raises(MT5DemoSmokeRefused, match="OPT_IN_AND_INITIALIZE_ACK"):
        run_once(args(**{field: False}), provider)
    assert provider.calls == []


@pytest.mark.parametrize("first,last", [
    (START, START),
    (END, START),
    (START - timedelta(days=2), END),
    (START.replace(tzinfo=None), END),
    (START, END.replace(tzinfo=None)),
    (START, NOW + timedelta(days=1)),
])
def test_time_scope_failure_never_initializes(provider, first, last):
    with pytest.raises(MT5DemoSmokeRefused):
        preflight_window(first, last, now=NOW)
    with pytest.raises(MT5DemoSmokeRefused):
        run_once(args(start_utc=first.isoformat(), end_utc=last.isoformat()),
                 provider, now=NOW)
    assert provider.calls == []


def test_successful_bounded_demo_smoke_redacts_every_sensitive_field(provider):
    result = run_once(args(), provider, now=NOW)
    assert result["status"] == "PASS_DEMO_READONLY_API_OBSERVATION"
    assert result["account_trade_mode"] == "DEMO"
    assert result["account_margin_mode"] == "HEDGING"
    assert result["observed_positions"] == 1
    assert result["observed_pending_orders"] == 0
    assert result["historical_order_count"] == 1
    assert result["historical_deal_count"] == 1
    assert result["checked_slices"] == 1
    assert len(result["history_content_sha256"]) == 64
    assert result["active_exposure_stable_during_scan"]
    assert not result["all_time_history_proven"]
    assert not result["broker_authenticated"]
    assert not result["atomic_account_snapshot"]
    assert not result["production_ready"]
    assert not result["may_release_paper_risk"]
    assert not result["may_unlock_stage4"]
    assert not result["may_execute_orders"]
    assert not result["may_publish_signals"]
    serialized = json.dumps(result, sort_keys=True)
    for secret in ("87654321", "Private-Fake-Demo-Server", "PRIVATE_EURUSD",
                   "901", "10000", "9000", "0.75", "100.0"):
        assert secret not in serialized
    assert provider.calls[0] == "initialize"
    assert provider.calls[-1] == "shutdown"
    assert not set(provider.calls).intersection(
        {"login", "order_send", "order_check", "symbol_select"}
    )


def test_direct_observation_no_initialize_or_shutdown(provider):
    report = observe_demo_smoke(provider, expected(), START, END, now=NOW)
    assert report["status"] == "PASS_DEMO_READONLY_API_OBSERVATION"
    assert "initialize" not in provider.calls
    assert "shutdown" not in provider.calls


def test_demo_real_account_refused_before_history_read(provider):
    provider.account.trade_mode = 2
    with pytest.raises(MT5ReadRefused, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        run_once(args(), provider, now=NOW)
    assert "history_orders_get" not in provider.calls
    assert provider.calls[-1] == "shutdown"


def test_labeled_demo_server_does_not_override_real_trade_mode(provider):
    provider.account.server = "Private-Fake-Demo-Server"
    provider.account.trade_mode = 1
    with pytest.raises(MT5ReadRefused, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        run_once(args(), provider, now=NOW)


def test_wrong_pinned_account_login_refused_before_history(provider):
    with pytest.raises(MT5ReadRefused, match="LOGIN_MISMATCH"):
        run_once(args(expected_login=12345), provider, now=NOW)
    assert "history_orders_get" not in provider.calls


def test_wrong_pinned_demo_server_refused(provider):
    with pytest.raises(MT5ReadRefused, match="SERVER_MISMATCH"):
        run_once(args(expected_server="Attacker"), provider, now=NOW)
    assert "history_orders_get" not in provider.calls


def test_mode_switch_during_snapshot_fails(provider):
    provider.switch_mode_after = 7
    with pytest.raises((MT5DemoSmokeRefused, MT5ReadRefused)):
        run_once(args(), provider, now=NOW)
    assert provider.calls[-1] == "shutdown"


def test_login_switch_during_history_fails_and_shuts_down(provider):
    provider.switch_login_after = 8
    with pytest.raises(MT5ReadRefused, match="LOGIN_MISMATCH"):
        run_once(args(), provider, now=NOW)
    assert provider.calls[-1] == "shutdown"


def test_unsupported_exchange_account_denied(provider):
    provider.account.margin_mode = 1
    with pytest.raises(ValueError, match="UNSUPPORTED_ACCOUNT_MARGIN_MODE"):
        run_once(args(), provider, now=NOW)


def test_history_none_refused_not_reported_as_empty(provider):
    provider.history_none = True
    with pytest.raises(MT5ReadRefused, match="INCOMPLETE_RESPONSE"):
        run_once(args(), provider, now=NOW)
    assert provider.calls[-1] == "shutdown"


def test_history_count_mismatch_fails_closed(provider):
    provider.history_count_offset = 1
    with pytest.raises(MT5ReadRefused, match="TOTAL_MISMATCH"):
        run_once(args(), provider, now=NOW)
    assert provider.calls[-1] == "shutdown"


def test_empty_history_is_inconclusive_not_fake_pass(provider):
    provider.orders = []
    provider.deals = []
    result = run_once(args(), provider, now=NOW)
    assert result["status"] == "INCONCLUSIVE_NO_MATCHED_HISTORY_ACTIVITY"
    assert result["historical_deal_count"] == 0
    assert not result["production_ready"]


def test_empty_deals_with_historical_pending_order_still_inconclusive(provider):
    provider.deals = []
    result = run_once(args(), provider, now=NOW)
    assert result["status"] == "INCONCLUSIVE_NO_MATCHED_HISTORY_ACTIVITY"


def test_non_atomic_open_positions_change_is_not_a_pass(provider):
    provider.move_volume_after = 8
    result = run_once(args(), provider, now=NOW)
    assert result["status"] == "INCONCLUSIVE_ACTIVE_EXPOSURE_CHANGED"
    assert not result["active_exposure_stable_during_scan"]
    assert not result["atomic_account_snapshot"]


def test_no_active_positions_but_historical_deals_is_observed(provider):
    provider.active = []
    result = run_once(args(), provider, now=NOW)
    assert result["status"] == "PASS_DEMO_READONLY_API_OBSERVATION"
    assert result["observed_positions"] == 0


def test_provider_initialize_false_still_uses_shutdown(provider):
    provider.initialize_result = False
    with pytest.raises(MT5DemoSmokeRefused, match="INITIALIZE_FAILED"):
        run_once(args(), provider, now=NOW)
    assert provider.calls == ["initialize", "shutdown"]


def test_provider_exception_from_history_does_not_bypass_shutdown(provider):
    def broken(*_args):
        raise RuntimeError("SECRET_ACCOUNT_87654321")
    provider.history_orders_get = broken
    with pytest.raises(MT5ReadRefused, match="MT5_HISTORY_QUERY_FAILURE"):
        run_once(args(), provider, now=NOW)
    assert provider.calls[-1] == "shutdown"


def test_duplicate_provider_history_ticket_is_never_accepted(provider):
    provider.orders.append(order())
    with pytest.raises(MT5ReadRefused, match="DUPLICATE_TICKET_IN_SLICE"):
        run_once(args(), provider, now=NOW)


def test_pending_order_count_is_diagnostic_not_trade_authority(provider):
    provider.pending = [NS(
        ticket=903, symbol="PRIVATE_EURUSD", type=2,
        volume_initial=1.0, volume_current=0.5, price_open=99.0,
        sl=90.0, tp=111.0,
    )]
    result = run_once(args(), provider, now=NOW)
    assert result["observed_pending_orders"] == 1
    assert not result["may_execute_orders"]


def test_preflight_window_normalizes_non_utc_offsets(provider):
    tz = END.astimezone().tzinfo
    # A deterministic UTC-clock input remains timezone aware.
    first, last = preflight_window(START.astimezone(tz), END.astimezone(tz), now=NOW)
    assert first == START and last == END


def test_absolute_position_identity_not_inferred_from_private_symbols(provider):
    result = run_once(args(), provider, now=NOW)
    assert result["sensitive_broker_records_in_output"] is False
    assert not any("position_id" in key or "ticket" in key for key in result)
