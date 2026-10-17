"""Bounded clean-wheel pinned V5 -> PAPER risk acceptance (no network).

This test intentionally uses real frozen Brooks V5 on synthetic CLOSED bars.
It does not assert a profitable signal, submit orders, or launch providers.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import naseri_markets
from naseri_markets.brooks_replay import verify_legacy_source
from naseri_markets.brooks_stage10_paper_bridge import panel_stage10_overview
from naseri_markets.contracts import Instrument, Market
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.execution_position_core_v1 import PaperExecutionOrchestratorV1
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy


def accept(parent: Path, source: Path) -> dict:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or os.geteuid() == 0):
        raise ValueError("EXPLICIT_NONROOT_NONPRODUCTION_REQUIRED")
    wheel = Path(naseri_markets.__file__).resolve()
    if Path(sys.prefix).resolve() not in wheel.parents:
        raise ValueError("INSTALLED_PACKAGE_NOT_VERIFIED")
    parent = parent.absolute()
    state = parent / "p07-cleanwheel"
    if (not parent.is_dir() or parent.is_symlink() or parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(parent.stat().st_mode) & 0o022
            or state.exists() or state.is_symlink()):
        raise ValueError("NEW_OWNER_PRIVATE_TEST_STATE_REQUIRED")
    verify_legacy_source(source)
    state.mkdir(mode=0o700)
    with EngineControlStore(state) as store:
        current = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=current.revision, actor_id=123,
        )
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123,
        )
    with PaperExecutionOrchestratorV1(state / "brooks_stage10_paper.sqlite") as core:
        core.configure_portfolio(PortfolioRiskPolicy(
            "p07-portfolio", "USDT", D(150), D(20000), D(100),
            D(150), D(150), 5,
        ))
        core.configure_account(AccountRiskPolicy(
            "p07-account", "p07-portfolio", "USDT", D(1000),
            D("0.05"), D("0.20"), D("0.10"), D(2), D("0.90"),
            D(3), D(1), D("0.01"), D("0.002"), D("0.003"), 5, True,
        ))
        core.register_instrument(
            portfolio_id="p07-portfolio",
            instrument=Instrument(
                Market.CRYPTO, "offline_paper_fixture", "BTCUSDT", "UTC", "USDT",
            ),
            group_id="CRYPTO_PAPER",
        )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(72):
        opened = start + timedelta(minutes=15 * i)
        candles.append({
            "open_time": opened.isoformat(),
            "close_time": (opened + timedelta(minutes=15)).isoformat(),
            "open": "100", "high": "101", "low": "99", "close": "100", "volume": "10",
        })
    replay = state / "closed-bars.json"
    replay.write_text(json.dumps({
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "offline_paper_fixture", "symbol": "BTCUSDT",
        "timezone": "UTC", "quote_currency": "USDT",
        "exchange": "offline_fixture", "market_type": "futures",
        "timeframe": "15m", "candles": candles,
    }), encoding="utf-8")
    def invoke():
        proc = subprocess.run(
            [sys.executable, "-I", "-m", "naseri_markets.brooks_stage10_cli",
             "--replay-and-link", "--state-dir", str(state),
             "--legacy-source", str(source), "--replay-file", str(replay),
             "--account-id", "p07-account", "--quantity", "1.00",
             "--ack-real-brooks-offline", "--ack-nonproduction-stage10-paper"],
            cwd=parent, env={
                "MMT_NONPRODUCTION": "1",
                "HOME": str(parent), "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True, text=True, timeout=60, check=False,
        )
        if proc.returncode or proc.stderr or not proc.stdout:
            raise ValueError("INSTALLED_GENUINE_BROOKS_REPLAY_REFUSED")
        return json.loads(proc.stdout)
    first = invoke()
    second = invoke()
    if (first["mode"] != "PINNED_BROOKS_OFFLINE_TO_STAGE10_PAPER"
            or first["scan_id"] != second["scan_id"]
            or second["scan_outcome"] != "DUPLICATE_SCAN"
            or first["engine_decision"] not in ("LONG", "SHORT", "NO_SIGNAL")
            or any(result[key] for result in (first, second)
                   for key in ("broker_order_sent", "telegram_sent",
                               "real_market_feed_used", "stage20_core_integrated",
                               "live_orders_authorized", "public_release_authorized"))):
        raise ValueError("INSTALLED_BROOKS_REPLAY_IDENTITY_OR_RELEASE_DRIFT")
    overview = panel_stage10_overview(state)
    if first["engine_decision"] == "NO_SIGNAL":
        if first["paper"] is not None or second["paper"] is not None:
            raise ValueError("NO_SIGNAL_CREATED_PAPER_ORDER")
        if overview["linked_orders"] != 0 or overview["active_paper_reservations"] != 0:
            raise ValueError("NO_SIGNAL_RESERVED_RISK")
    else:
        one, two = first["paper"], second["paper"]
        if (one is None or two is None or not first["paper_order_created"]
                or second["paper_order_created"] or one["order_status"] != "CREATED"
                or two["status"] != "EXISTING_PAPER_ORDER"
                or two["risk_reservation_created"] or one["order_id"] != two["order_id"]
                or overview["linked_orders"] != 1
                or overview["active_paper_reservations"] != 1):
            raise ValueError("BROOKS_PAPER_RESERVATION_OR_DUPLICATE_INVALID")
        with PaperExecutionOrchestratorV1(
            state / "brooks_stage10_paper.sqlite",
        ) as core:
            position = core.order_state(one["order_id"])
            if position["status"] != "CREATED" or position["filled_quantity"] != "0":
                raise ValueError("PAPER_ORDER_AUTO_FILLED")
    # Stage08: a fresh independent process must be able to read and
    # reconcile BOTH persisted ledgers without resuming or mutating either.
    inspected = subprocess.run(
        [sys.executable, "-I", "-m", "naseri_markets.brooks_stage10_cli",
         "--reconcile", "--state-dir", str(state)],
        cwd=parent, env={
            "HOME": str(parent), "PYTHONDONTWRITEBYTECODE": "1",
        }, capture_output=True, text=True, timeout=20, check=False,
    )
    if inspected.returncode or not inspected.stdout or inspected.stderr:
        raise ValueError("P08_INSTALLED_READ_ONLY_RECONCILIATION_REFUSED")
    recovery = json.loads(inspected.stdout)
    expected = ("CLEAN_NO_SIGNALS" if first["engine_decision"] == "NO_SIGNAL"
                else "MATCHED_PAPER_ORDER")
    if (recovery["status"] != expected
            or recovery["can_automatically_resume"]
            or recovery["live_orders_authorized"]
            or recovery["telegram_publication_authorized"]):
        raise ValueError("P08_RECOVERY_STATUS_OR_PERMISSION_DRIFT")
    return {
        "verdict": "PINNED_BROOKS_INSTALLED_OFFLINE_PAPER_PASS",
        "decision": first["engine_decision"],
        "two_process_replay": True,
        "linked_orders": overview["linked_orders"],
        "duplicate_reservation_created": False,
        "broker_orders_sent": False,
        "telegram_sent": False,
        "market_feed_used": False,
        "stage20_integrated": False,
        "production_authorized": False,
        "recovery_status": recovery["status"],
        "automatic_recovery_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-parent", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = accept(args.state_parent, args.legacy_source)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired):
        print("P07_CLEAN_WHEEL_ACCEPTANCE_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
