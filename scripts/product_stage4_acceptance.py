"""Stage 4 acceptance: installed-wheel, single-host ephemeral, zero real HTTP/bot.

Run with a clean installed mmt-dev preview on a disposable GitHub runner.
This is an audit test, not a Telegram product entrypoint or market adapter.
All mocks are process-local, never written into the installed package.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from naseri_markets import dev_operator
from naseri_markets.bot_admin_app import build_admin_application
from naseri_markets.brooks_kraken_feed import KrakenFeedRefused, poll_once
from naseri_markets.brooks_paper_service import BrooksPaperService
from naseri_markets.brooks_replay import verify_legacy_source
from naseri_markets.custom_admin_panel import _token
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
from naseri_markets.iran_futures_eligibility import (
    available_futures_venues, iran_futures_approved,
)
from naseri_markets.public_futures_contracts import discover_public_contracts
from naseri_markets.trusted_custom import LocalCustomRefused

ADMIN_ID = 123
TOKEN = "123456:STAGE4_NEVER_CONNECT_FAKE_TOKEN"


def check(condition: bool, name: str, records: list[str]) -> None:
    if not condition:
        raise AssertionError("ACCEPTANCE_FAILED_" + name)
    records.append(name)


def fake_update(callback: str, *, actor: int = ADMIN_ID):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data=callback, answer=AsyncMock(), message=message)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=actor),
        effective_chat=SimpleNamespace(id=actor, type="private"),
        effective_message=message,
        callback_query=query)
    return update, message, query


async def admin_acceptance(state: Path, checks: list[str]) -> None:
    from telegram.ext import CommandHandler

    app = build_admin_application(
        token=TOKEN, state_dir=state, admin_ids={ADMIN_ID},
        owner_ids={ADMIN_ID})
    commands = set().union(*(
        h.commands for group in app.handlers.values() for h in group
        if isinstance(h, CommandHandler)))
    check({"engines", "custom"} <= commands,
          "admin_panel_mounted_offline", checks)
    panel = IntegratedEnginePanel(
        state_dir=state, admin_ids={ADMIN_ID}, owner_ids={ADMIN_ID})
    token = _token(BROOKS_ENGINE_ID)
    with EngineControlStore(state) as host:
        previous = host.preferences(BROOKS_ENGINE_ID)
        version = previous["revision"]
        check(previous["timeframe"] == "15m",
              "initial_timeframe_15m", checks)
        check(previous["futures_exchange"] == "kraken"
              and previous["futures_symbol"] == "PF_XBTUSD",
              "legacy_venue_metadata_preserved", checks)
        check(not available_futures_venues(),
              "zero_resident_approved_venues", checks)
        exchange_menu = panel.exchange_keyboard(host, BROOKS_ENGINE_ID, 0)
        pair_menu = panel.pair_keyboard(host, BROOKS_ENGINE_ID)
        check(not any(
            b.callback_data.startswith("ex:set:")
            for row in exchange_menu.inline_keyboard for b in row),
            "restricted_exchange_hidden_in_ui", checks)
        check(not any(
            b.callback_data.startswith("ep:set:")
            for row in pair_menu.inline_keyboard for b in row),
            "unapproved_pair_hidden_in_ui", checks)
        check("غیرمجاز برای انتخاب" in
              panel.settings_text(host, BROOKS_ENGINE_ID),
              "ui_displays_residency_restriction", checks)

    # Unauthorized callback must not change saved state or produce a signal.
    bad, bad_msg, bad_query = fake_update(
        f"et:set:{token}:1:{version}", actor=999)
    await panel.callback(bad, SimpleNamespace(user_data={}))
    with EngineControlStore(state) as host:
        check(host.preferences(BROOKS_ENGINE_ID)["revision"] == version,
              "outsider_denied", checks)
    check(bad_msg.reply_text.await_count == 0
          and bad_query.answer.await_count == 1,
          "outsider_has_no_panel_disclosure", checks)

    # Authorized 5m selection must be durable after new SQLite connection.
    good, good_msg, _ = fake_update(f"et:set:{token}:1:{version}")
    await panel.callback(good, SimpleNamespace(user_data={}))
    with EngineControlStore(state) as host:
        after = host.preferences(BROOKS_ENGINE_ID)
        check(after["timeframe"] == "5m"
              and after["revision"] == version + 1,
              "telegram_timeframe_saved", checks)
    check(good_msg.reply_text.await_count == 1,
          "telegram_timeframe_acknowledged", checks)

    # Replay stale click, then forged exchange and pair choices.
    await panel.callback(good, SimpleNamespace(user_data={}))
    for candidate in (
        f"ex:set:{token}:0:{version+1}",
        f"ep:set:{token}:1:{version+1}",
    ):
        forged, _, _ = fake_update(candidate)
        await panel.callback(forged, SimpleNamespace(user_data={}))
    with EngineControlStore(state) as host:
        prefs = host.preferences(BROOKS_ENGINE_ID)
        check(prefs["timeframe"] == "5m"
              and prefs["revision"] == version + 1,
              "stale_click_and_forged_selections_denied", checks)
        check(prefs["futures_exchange"] == "kraken"
              and prefs["futures_symbol"] == "PF_XBTUSD",
              "venue_and_pair_not_unauthorized", checks)
        try:
            host.change_preference(
                BROOKS_ENGINE_ID, field="futures_exchange",
                value="kucoin", expected_revision=prefs["revision"],
                actor_id=ADMIN_ID)
        except LocalCustomRefused as err:
            check("ELIGIBILITY_DENIED" in str(err),
                  "direct_sqlite_api_eligibility_denied", checks)
        else:
            raise AssertionError("ACCEPTANCE_FAILED_direct_venue_write_allowed")
        check(host.preferences(BROOKS_ENGINE_ID)["revision"] ==
              version + 1, "rejected_write_does_not_increment_cas", checks)


def public_metadata_acceptance(checks: list[str]) -> None:
    def transport(venue: str) -> bytes:
        assert venue == "kucoin"
        return json.dumps({
            "code": "200000",
            "data": [
                {"symbol": "XBTUSDTM", "type": "FFWCSX",
                 "status": "Open", "quoteCurrency": "USDT",
                 "expireDate": None, "tickSize": "0.1"},
            ],
        }).encode("utf-8")
    data = discover_public_contracts("kucoin", transport=transport)
    check(data["contracts"][0]["symbol"] == "XBTUSDTM",
          "official_native_contract_metadata_parsed", checks)
    check(not data["iran_resident_futures_approved"]
          and not data["account_trading_authorized"]
          and not data["paper_signal_generation_authorized"],
          "metadata_never_grants_trading_or_signal_permissions", checks)


def real_policy_worker_acceptance(
        state: Path, source: Path, checks: list[str]) -> None:
    calls = []
    def forbidden_reader(**kwargs):
        calls.append(kwargs)
        raise AssertionError("NO_NETWORK_FOR_RESTRICTED_VENUE")
    worker = BrooksPaperService(
        state_dir=state, legacy_source=source, reader=forbidden_reader)
    with EngineControlStore(state) as host:
        engine = host.get(BROOKS_ENGINE_ID)
        host.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=engine.revision, actor_id=ADMIN_ID)
        prefs = host.preferences(BROOKS_ENGINE_ID)
        host.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=ADMIN_ID)
        publication = host.publication(BROOKS_ENGINE_ID)
        host.request_publication(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=publication["revision"], actor_id=ADMIN_ID)
    worker.start()
    try:
        first = worker.step()
        check(first["phase"] == "IDLE" and not first["attempted"]
              and first["reason"] ==
              "BROOKS_IRAN_FUTURES_ELIGIBILITY_UNVERIFIED",
              "iran_venue_idle_even_when_panel_requested_on", checks)
        check(not calls, "ineligible_worker_does_not_call_reader", checks)
        with EngineControlStore(state) as host:
            check(host.publication(BROOKS_ENGINE_ID)[
                "effective_publication"] is False,
                "publication_request_never_enables_real_delivery", checks)
    finally:
        worker.shutdown()
    with EngineControlStore(state) as host:
        check(host.brooks_worker_status()["phase"] == "STOPPED",
              "first_worker_graceful_stop", checks)
        check(host.brooks_replay_status()["scans"] == 0,
              "zero_real_signals_or_scans", checks)

    # Direct Kraken adapter, not just worker/UI, must fail before HTTP.
    transport_calls = []
    def network_forbidden(*args, **kwargs):
        transport_calls.append(1)
        raise AssertionError("HTTP_MUST_NEVER_BE_CALLED")
    with patch("urllib.request.urlopen", side_effect=network_forbidden):
        try:
            poll_once(
                state_dir=state, legacy_source=source, symbol="PF_XBTUSD",
                metadata_transport=network_forbidden,
                transport=network_forbidden)
        except KrakenFeedRefused as err:
            check(str(err) == "KRAKEN_FEED_PAPER_NOT_ARMED",
                  "direct_poll_fail_closed", checks)
        else:
            raise AssertionError("ACCEPTANCE_FAILED_direct_poll_allowed")
    check(not transport_calls, "direct_poll_zero_network_requests", checks)


def outage_recovery_acceptance(
        state: Path, source: Path, checks: list[str]) -> None:
    # Synthetic only. The local patches CANNOT change product policy or be
    # saved; this validates the existing retry/backoff mechanism, not actual
    # eligibility of Kraken for residents of Iran.
    clock = [float(int(time.time()))]
    called = []
    def flaky_reader(**kwargs):
        called.append(kwargs["symbol"])
        if len(called) == 1:
            raise KrakenFeedRefused("KRAKEN_FEED_HTTP_503")
        return {
            "symbol": "PF_XBTUSD", "selected_exchange": "kraken",
            "market_feed": "KRAKEN_FUTURES_TRADE_PUBLIC_HTTPS",
            "outcome": "NO_SIGNAL", "decision": "NO_SIGNAL",
            "telegram_sent": False, "live_publication_enabled": False,
            "timeframe": "5m",
            "last_closed_candle": datetime.fromtimestamp(
                clock[0] - 60, tz=UTC).isoformat(),
        }
    with patch("naseri_markets.brooks_paper_service.iran_futures_approved",
               side_effect=lambda venue: venue == "kraken"), patch(
                   "naseri_markets.brooks_paper_service.resident_paper_feed_ready",
                   side_effect=lambda venue, symbol:
                   venue == "kraken" and symbol == "PF_XBTUSD"):
        worker = BrooksPaperService(
            state_dir=state, legacy_source=source,
            reader=flaky_reader, clock=lambda: clock[0])
        worker.start()
        try:
            first = worker.step()
            check(first["phase"] == "DEGRADED"
                  and first["reason"] == "KRAKEN_FEED_HTTP_503",
                  "synthetic_network_outage_enters_degraded", checks)
            second = worker.step()
            check(second["phase"] == "WAITING" and len(called) == 1,
                  "bounded_retry_backoff", checks)
            clock[0] += 11
            recovered = worker.step()
            check(recovered["phase"] == "WAITING"
                  and recovered["outcome"] == "NO_SIGNAL"
                  and len(called) == 2,
                  "synthetic_restored_network_recovers", checks)
            with EngineControlStore(state) as host:
                health = host.brooks_worker_status(now=int(clock[0]))
                check(health["completed_cycles"] == 1
                      and health["refused_cycles"] == 1,
                      "outage_and_recovery_visible_in_health", checks)
                check(host.brooks_replay_status()["scans"] == 0,
                      "synthetic_reader_never_writes_signals", checks)
        finally:
            worker.shutdown()
    check(not iran_futures_approved("kraken"),
          "synthetic_permission_patch_not_persistent", checks)
    restarted = BrooksPaperService(
        state_dir=state, legacy_source=source, reader=lambda **_: (
            (_ for _ in ()).throw(AssertionError("NETWORK_SHOULD_STAY_OFF"))))
    restarted.start()
    try:
        after_restart = restarted.step()
        check(after_restart["phase"] == "IDLE"
              and not after_restart["attempted"],
              "restart_restores_actual_residency_fence", checks)
        with EngineControlStore(state) as host:
            prefs = host.preferences(BROOKS_ENGINE_ID)
            health = host.brooks_worker_status()
            check(prefs["timeframe"] == "5m",
                  "settings_persist_after_worker_restart", checks)
            check(health["phase"] == "IDLE" and health["connected"],
                  "restart_lease_and_heartbeat_visible", checks)
    finally:
        restarted.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    state, source = args.state_dir.absolute(), args.legacy_source.absolute()
    records: list[str] = []
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise AssertionError("ACCEPTANCE_NONPRODUCTION_REQUIRED")
    if (not state.is_dir() or state.is_symlink()
            or stat.S_IMODE(state.stat().st_mode) != 0o700):
        raise AssertionError("ACCEPTANCE_PRIVATE_STATE_REQUIRED")
    verify_legacy_source(source)
    check(dev_operator._status(state)["worker_phase"] == "NOT_INSTALLED",
          "fresh_installed_worker_not_autostarted", records)
    asyncio.run(admin_acceptance(state, records))
    public_metadata_acceptance(records)
    real_policy_worker_acceptance(state, source, records)
    outage_recovery_acceptance(state, source, records)
    with EngineControlStore(state) as host:
        check(not host.publication(BROOKS_ENGINE_ID)["effective_publication"],
              "final_effective_publication_false", records)
        check(host.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED",
              "final_telegram_route_disabled", records)
    result = {
        "verdict": "PASS_NONPRODUCTION_OFFLINE_STAGE4_ACCEPTANCE",
        "scenario_count": len(records),
        "passed": records,
        "test_scope": "EPHEMERAL_CI_INSTALLED_WHEEL_NO_LIVE_NETWORK",
        "real_telegram_messages": 0,
        "real_market_http_requests": 0,
        "broker_orders": 0,
        "iran_resident_eligible_venues": 0,
        "frozen_brooks_source_verified": True,
        "production_data_or_servers_modified": False,
        "limitations": [
            "Simulated HTTP outage and restoration, no real venue connection",
            "No live Telegram or real Telegram bot token",
            "Venue/pair switching correctly denied while approved venues empty",
            "No genuine provider signal generation or delivery validation",
        ],
    }
    if args.report.exists() or args.report.is_symlink():
        raise AssertionError("ACCEPTANCE_REPORT_MUST_BE_NEW")
    args.report.write_text(json.dumps(
        result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
