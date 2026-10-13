"""Stage-16 disposable installed-wheel proof: panel -> core -> PAPER -> NO-SEND.

The demonstration uses only synthetic prices/equity and a reviewed built-in
example. It neither proves an edge nor authorizes an actual market order.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from .contracts import Market
from .core_api_v1 import ClosedCandle
from ._contract_acceptance_fixture_v1 import OfflineContractFixture
from .instrument_registry_v1 import (InstrumentMetadata, ListingStatus,
                                       MetadataOrigin, ProviderSnapshot,
                                       ResearchInstrumentCatalog)
from .offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
from .offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from .paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
from .reliability_acceptance_v1 import LedgerPaths, evaluate_offline_reliability
from .risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from .trading_control_center_v1 import CoreListing, OfflineTradingControlCenter


class SyntheticDemoRefused(ValueError):
    """Stable safe refusal; no secret, traceback or path disclosure."""


def run_synthetic_demo(destination: Path, *, symbol: str = "ABCUSD",
                       timeframe: str = "15m") -> dict:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or os.environ.get("MMT_PRODUCTION") == "1":
        raise SyntheticDemoRefused("NONPRODUCTION_ENV_REQUIRED")
    if (type(symbol) is not str or re.fullmatch(r"[A-Z0-9]{3,20}", symbol) is None
            or timeframe not in ("5m", "15m", "1h")):
        raise SyntheticDemoRefused("SYNTHETIC_SYMBOL_OR_TIMEFRAME_INVALID")
    path = Path(destination)
    parent = path.parent
    if (not path.is_absolute() or path.exists() or path.is_symlink()
            or not parent.is_dir() or parent.is_symlink()
            or stat.S_IMODE(parent.stat().st_mode) & 0o002):
        raise SyntheticDemoRefused("FRESH_PRIVATE_STATE_REQUIRED")
    path.mkdir(mode=0o700)
    start = datetime(2026, 10, 12, 10, tzinfo=UTC)
    duration = timedelta(minutes={"5m": 5, "15m": 15, "1h": 60}[timeframe])
    first = ClosedCandle(start, start + duration, D(100), D(102), D(98), D(100), D(10))
    second = ClosedCandle(first.close_at, first.close_at + duration,
                          D(100), D(108), D(99), D(106), D(10))
    entry = ClosedCandle(second.close_at, second.close_at + duration,
                         D(106), D(108), D(104), D(107), D(10))
    exit_bar = ClosedCandle(entry.close_at, entry.close_at + duration,
                            D(107), D(114), D(104), D(113), D(10))
    catalog = ResearchInstrumentCatalog(max_age_seconds=86400)
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    metadata = InstrumentMetadata(
        "synthetic_provider", Market.CRYPTO, symbol, "UTC", "USD",
        D("0.01"), origin, ListingStatus.OPEN, start, "SYNTHETIC_FIXTURE")
    catalog.replace(ProviderSnapshot(
        "synthetic_provider", origin, start, (metadata,), "a" * 64))
    core = OfflineContractFixture()
    with OfflineTradingControlCenter(
        path / "control.sqlite", admin_ids={123}, catalog=catalog,
        listings=(CoreListing(core.manifest.core_id, "Public Demonstration Core",
                              core.manifest.core_version, manifest=core.manifest),),
        enabled=True,
    ) as control:
        instance = control.create_instance(
            123, core_id=core.manifest.core_id, instance_id="demo_instance",
            account_id="demo_account", portfolio_id="demo_portfolio")
        instance = control.add_binding(
            123, instance.instance_id, provider="synthetic_provider", symbol=symbol,
            timeframe=timeframe, now=start, expected_revision=instance.revision)
        instance = control.set_allocation(
            123, instance.instance_id, max_reserved=D("0.10"),
            max_notional=D("0.50"), max_order=D("0.05"),
            max_orders=10, expected_revision=instance.revision)
        for mode in ("analysis", "signals", "paper"):
            instance = control.set_request(
                123, instance.instance_id, field=mode,
                requested=True, expected_revision=instance.revision)
        (binding,) = control.preview_bindings(123, instance.instance_id, now=start)
        bridge = OfflinePanelPaperIntegration(
            control, actor_id=123, core=core, operator_ack=True)
        with OfflinePaperPositionLifecycle(path / "paper.sqlite") as paper:
            paper.configure_portfolio(PortfolioRiskPolicy(
                "demo_portfolio", "USD", D(100), D(5000), D(100),
                D(90), D(90), 25))
            paper.configure_account(AccountRiskPolicy(
                "demo_account", "demo_portfolio", "USD", D(1000), D("0.05"),
                D("0.20"), D("0.20"), D(2), D("0.90"), D(3), D(1),
                D("0.01"), D("0.002"), D("0.003"), 25, True))
            paper.register_instrument(
                portfolio_id="demo_portfolio", instrument=binding.instrument,
                group_id="CRYPTO")
            bridge.authorize_paper(
                instance.instance_id, paper=paper,
                expected_panel_revision=instance.revision, now=start,
                operator_ack=True)
            with OfflineSignalLifecycle(path / "signals.sqlite", enabled=True) as signals:
                receipt = bridge.replay_candles(
                    instance.instance_id, binding.binding_id,
                    candles=(first, second), source_ref="stage16_synthetic",
                    expected_panel_revision=instance.revision, operator_ack=True,
                    paper=paper, signals=signals, quantity=D(1),
                    dry_run_channel_id=-10016)
                if (len(receipt["paper_order_ids"]) != 1
                        or len(receipt["signal_keys"]) != 1):
                    raise SyntheticDemoRefused("EXPECTED_ONE_SYNTHETIC_SETUP")
                order_id = receipt["paper_order_ids"][0]
                signal_key = receipt["signal_keys"][0]
                paper.apply_paper_event(
                    order_id, action_id="demo_submit", event="SUBMIT",
                    expected_revision=0, operator_ack=True)
                paper.apply_paper_event(
                    order_id, action_id="demo_ack", event="ACK",
                    expected_revision=1, remote_order_id="synthetic_not_broker",
                    operator_ack=True)
                paper.apply_paper_event(
                    order_id, action_id="demo_fill", event="FILL",
                    quantity=D(1), price=D(106), entry_bar=entry,
                    expected_revision=2, operator_ack=True)
                paper.step_closed_bar(order_id, exit_bar, operator_ack=True)
                before = paper.performance(order_id)
                if signals.snapshot(signal_key).message_id is not None:
                    raise SyntheticDemoRefused("UNEXPECTED_TELEGRAM_MESSAGE")
    with OfflinePaperPositionLifecycle(path / "paper.sqlite") as paper:
        after = paper.performance(order_id)
    with OfflineSignalLifecycle(path / "signals.sqlite", enabled=True) as signals:
        dry_commands = len(signals.commands(signal_key))
    gate = evaluate_offline_reliability(LedgerPaths(
        path / "control.sqlite", path / "paper.sqlite",
        path / "signals.sqlite"))
    if (after != before or after["status"] != "CLOSED"
            or dry_commands != 1 or gate.integrity_verdict != "PASS"):
        raise SyntheticDemoRefused("RESTART_OR_LEDGER_AUDIT_FAILED")
    return {
        "mode": "SYNTHETIC_INSTALLED_PAPER_ONLY", "symbol": symbol,
        "timeframe": timeframe, "decision_count": receipt["decision_count"],
        "paper_closed_trades": 1, "dry_run_commands": dry_commands,
        "modeled_net_pnl": before["net"],
        "modeled_net_realized_r": before["net_realized_r"],
        "restart_verified": True, "integrity_verdict": gate.integrity_verdict,
        "release_verdict": gate.release_verdict,
        "telegram_sent": False, "broker_order_sent": False,
        "live_trading_enabled": False, "profitability_proven": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--symbol", default="ABCUSD")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--ack-synthetic-offline", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.ack_synthetic_offline:
            raise SyntheticDemoRefused("EXPLICIT_OPERATOR_ACK_REQUIRED")
        result = run_synthetic_demo(
            args.state_dir, symbol=args.symbol, timeframe=args.timeframe)
    except (ValueError, RuntimeError, OSError) as exc:
        print("STAGE16_SYNTHETIC_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
