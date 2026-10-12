"""Stage 20: explicitly invoked multi-binding offline PAPER pilot.

Uses a trusted public *example*, synthetic bars and existing Stage 12-19
journals. Never sends Telegram, broker orders or real market requests.
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
from .example_dual_setup_core_v1 import DualSetupExampleCore
from .instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin, ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from .job_effect_intent_v1 import JobEffectIntentExecutor, OfflineJobEffectLedger
from .job_effect_reconciliation_v1 import (
    EffectEvidencePaths, evaluate_effect_evidence,
)
from .offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
from .offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
from .offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from .paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
from .reliability_acceptance_v1 import LedgerPaths, evaluate_offline_reliability
from .risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from .trading_control_center_v1 import CoreListing, OfflineTradingControlCenter


class PilotRefused(ValueError):
    """Safe, non-sensitive refusal."""


T0 = datetime(2026, 10, 12, 10, tzinfo=UTC)
PERIODS = {"5m": 5, "15m": 15, "1h": 60}


def _bars(period: str) -> tuple[ClosedCandle, ...]:
    dt = timedelta(minutes=PERIODS[period])
    one = ClosedCandle(T0, T0 + dt, D(100), D(102), D(98), D(100), D(10))
    two = ClosedCandle(one.close_at, one.close_at + dt,
                       D(100), D(108), D(99), D(106), D(10))
    entry = ClosedCandle(two.close_at, two.close_at + dt,
                         D(106), D(108), D(104), D(107), D(10))
    exit_bar = ClosedCandle(entry.close_at, entry.close_at + dt,
                            D(107), D(114), D(104), D(113), D(10))
    return one, two, entry, exit_bar


def run_paper_pilot(folder: Path, *, first_symbol: str = "ABCUSD",
                    second_symbol: str = "XYZUSD", first_timeframe: str = "5m",
                    second_timeframe: str = "15m",
                    dry_run_signals: bool = True) -> dict:
    """New private state only; rejected runs never auto-retry ambiguous effects."""
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise PilotRefused("NONPRODUCTION_REQUIRED")
    symbols = (first_symbol, second_symbol)
    periods = (first_timeframe, second_timeframe)
    if (type(dry_run_signals) is not bool
            or any(type(s) is not str or re.fullmatch(r"[A-Z0-9]{3,20}", s) is None
                   for s in symbols)
            or first_symbol == second_symbol or any(p not in PERIODS for p in periods)):
        raise PilotRefused("TWO_DISTINCT_SYNTHETIC_BINDINGS_REQUIRED")
    folder = Path(folder)
    parent = folder.parent
    if (not folder.is_absolute() or folder.exists() or folder.is_symlink()
            or not parent.is_dir() or parent.is_symlink()
            or parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(parent.stat().st_mode) & 0o022):
        raise PilotRefused("NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED")
    folder.mkdir(mode=0o700)
    if stat.S_IMODE(folder.stat().st_mode) != 0o700:
        raise PilotRefused("PRIVATE_DIRECTORY_REQUIRED")
    control_path = folder / "control.sqlite"
    paper_path = folder / "paper.sqlite"
    signal_path = folder / "signals.sqlite"
    runtime_path = folder / "runtime.sqlite"
    effects_path = folder / "effects.sqlite"
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    catalog = ResearchInstrumentCatalog(max_age_seconds=86400)
    instruments = tuple(InstrumentMetadata(
        "synthetic_provider", Market.CRYPTO, symbol, "UTC", "USD",
        D("0.01"), origin, ListingStatus.OPEN, T0, "SYNTHETIC_FIXTURE")
        for symbol in symbols)
    catalog.replace(ProviderSnapshot("synthetic_provider", origin, T0,
                                     instruments, "a" * 64))
    core = DualSetupExampleCore()
    with OfflineTradingControlCenter(
        control_path, admin_ids={123}, catalog=catalog, enabled=True,
        listings=(CoreListing(core.manifest.core_id, "Reviewed public example",
                              core.manifest.core_version, manifest=core.manifest),)
    ) as panel:
        state = panel.create_instance(
            123, core_id=core.manifest.core_id, instance_id="pilot_instance",
            account_id="pilot_account", portfolio_id="pilot_portfolio")
        for symbol, period in zip(symbols, periods):
            state = panel.add_binding(
                123, state.instance_id, provider="synthetic_provider",
                symbol=symbol, timeframe=period, now=T0,
                expected_revision=state.revision)
        state = panel.set_allocation(
            123, state.instance_id, max_reserved=D("0.10"),
            max_notional=D("0.50"), max_order=D("0.05"),
            max_orders=10, expected_revision=state.revision)
        modes = ("analysis", "paper", "signals") if dry_run_signals else ("analysis", "paper")
        for mode in modes:
            state = panel.set_request(123, state.instance_id, field=mode,
                                      requested=True, expected_revision=state.revision)
        bindings = panel.preview_bindings(123, state.instance_id, now=T0)
        if len(bindings) != 2 or {b.instrument.symbol for b in bindings} != set(symbols):
            raise PilotRefused("PANEL_BINDING_MISMATCH")
        bridge = OfflinePanelPaperIntegration(
            panel, actor_id=123, core=core, operator_ack=True)
        with OfflineRuntimeSupervisor(runtime_path, panel=panel,
                actor_id=123, enabled=True) as runtime, \
             OfflinePaperPositionLifecycle(paper_path) as paper, \
             OfflineSignalLifecycle(signal_path, enabled=True) as signals, \
             OfflineJobEffectLedger(effects_path, enabled=True) as effects:
            paper.configure_portfolio(PortfolioRiskPolicy(
                "pilot_portfolio", "USD", D(100), D(5000), D(100),
                D(90), D(90), 25))
            paper.configure_account(AccountRiskPolicy(
                "pilot_account", "pilot_portfolio", "USD", D(1000),
                D("0.05"), D("0.20"), D("0.20"), D(2), D("0.90"), D(3),
                D(1), D("0.01"), D("0.002"), D("0.003"), 25, True))
            for binding in bindings:
                paper.register_instrument(
                    portfolio_id="pilot_portfolio",
                    instrument=binding.instrument, group_id="CRYPTO")
            bridge.authorize_paper(state.instance_id, paper=paper,
                                   expected_panel_revision=state.revision,
                                   now=T0, operator_ack=True)
            jobs = {}
            for binding in bindings:
                candles = _bars(binding.timeframe)
                job_id = runtime.schedule(
                    state.instance_id, binding.binding_id,
                    expected_panel_revision=state.revision,
                    candles=candles[:2],
                    source_ref="stage20_synthetic_" + binding.instrument.symbol,
                    due_at=candles[1].close_at, operator_ack=True)
                jobs[binding.binding_id] = (job_id, candles)
            executor = JobEffectIntentExecutor(
                supervisor=runtime, ledger=effects, integration=bridge,
                paper=paper, signals=signals if dry_run_signals else None,
                quantity=D(1),
                dry_run_channel_id=-10020 if dry_run_signals else None)
            done = runtime.run_due(
                executor, now=max(x[1][1].close_at for x in jobs.values()),
                limit=2, operator_ack=True)
            if (len(done) != 2 or any(x["status"] != "DONE" for x in done)
                    or runtime.run_due(executor, now=T0 + timedelta(days=1),
                                       limit=2, operator_ack=True)):
                raise PilotRefused("TWO_COMPLETED_UNIQUE_JOBS_REQUIRED")
            performance = {}
            signal_count = 0
            for binding in bindings:
                job_id, candles = jobs[binding.binding_id]
                intents = effects.intents(job_id=job_id)
                expected = {"PAPER_RESERVE", "PAPER_PLAN"}
                if dry_run_signals:
                    expected.add("DRY_SIGNAL")
                if (len(intents) != len(expected)
                        or {x["kind"] for x in intents} != expected
                        or any(x["state"] != "RECORDED" for x in intents)):
                    raise PilotRefused("EXACT_EFFECTS_MISSING")
                order_id = next(x["target_id"] for x in intents
                                if x["kind"] == "PAPER_RESERVE")
                if dry_run_signals:
                    key = next(x["target_id"] for x in intents
                               if x["kind"] == "DRY_SIGNAL")
                    if (signals.snapshot(key).message_id is not None
                            or len(signals.commands(key)) != 1):
                        raise PilotRefused("NO_SEND_SIGNAL_INVALID")
                    signal_count += 1
                action = "st20_" + binding.binding_id[-16:]
                paper.apply_paper_event(
                    order_id, action_id=action + "_submit", event="SUBMIT",
                    expected_revision=0, operator_ack=True)
                paper.apply_paper_event(
                    order_id, action_id=action + "_ack", event="ACK",
                    expected_revision=1,
                    remote_order_id="synthetic_" + binding.binding_id[-16:],
                    operator_ack=True)
                paper.apply_paper_event(
                    order_id, action_id=action + "_fill", event="FILL",
                    expected_revision=2, quantity=D(1), price=D(106),
                    entry_bar=candles[2], operator_ack=True)
                close = paper.step_closed_bar(order_id, candles[3],
                                              operator_ack=True)
                stats = paper.performance(order_id)
                if close["status"] != "CLOSED" or stats["status"] != "CLOSED":
                    raise PilotRefused("PAPER_POSITION_NOT_CLOSED")
                performance[binding.binding_id] = stats
            health = runtime.health()
            if (health["counts"]["DONE"] != 2
                    or health["manual_reconciliation_required"]):
                raise PilotRefused("RUNTIME_NOT_HEALTHY")
    with OfflinePaperPositionLifecycle(paper_path) as paper:
        if any(paper.performance(stats["order_id"]) != stats
               for stats in performance.values()):
            raise PilotRefused("PERSISTENT_PERFORMANCE_DRIFT")
        paper.reconcile_offline(operator_ack=True)
    # The pilot owns these newly created files. Stop all writers before auditing.
    for path in (control_path, paper_path, signal_path, runtime_path, effects_path):
        path.chmod(0o600)
    gate = evaluate_offline_reliability(LedgerPaths(
        control_path, paper_path, signal_path))
    proof = evaluate_effect_evidence(EffectEvidencePaths(
        effects_path, runtime_path, paper_path, signal_path))
    expected_effects = 6 if dry_run_signals else 4
    if (gate.integrity_verdict != "PASS"
            or gate.release_verdict != "BLOCKED_NONPRODUCTION_UNATTESTED"
            or proof.blocking_effects or proof.exact_local_effects != expected_effects):
        raise PilotRefused("READ_ONLY_AUDIT_FAILED")
    positions = [
        {"binding_id": b.binding_id, "symbol": b.instrument.symbol,
         "timeframe": b.timeframe,
         "order_id": performance[b.binding_id]["order_id"],
         "status": performance[b.binding_id]["status"],
         "modeled_net_pnl": performance[b.binding_id]["net"],
         "modeled_net_realized_r": performance[b.binding_id]["net_realized_r"]}
        for b in bindings
    ]
    return {
        "mode": "STAGE20_SYNTHETIC_PAPER_ONLY", "core": core.manifest.core_id,
        "bindings": positions, "completed_jobs": 2, "closed_paper_trades": 2,
        "dry_run_commands": signal_count, "exact_effects": proof.exact_local_effects,
        "modeled_net_total": str(sum((D(p["modeled_net_pnl"]) for p in positions), D(0))),
        "restart_verified": True, "integrity_verdict": gate.integrity_verdict,
        "effects_verdict": proof.verdict, "release_verdict": gate.release_verdict,
        "telegram_sent": False, "broker_order_sent": False,
        "real_feed_used": False, "live_trading_enabled": False,
        "profitability_proven": False, "public_release_authorized": False,
        "brooks_core_api_integrated": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--first-symbol", default="ABCUSD")
    parser.add_argument("--second-symbol", default="XYZUSD")
    parser.add_argument("--first-timeframe", default="5m")
    parser.add_argument("--second-timeframe", default="15m")
    parser.add_argument("--no-dry-run-signals", action="store_true")
    parser.add_argument("--ack-synthetic-offline", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.ack_synthetic_offline:
            raise PilotRefused("OPERATOR_ACK_REQUIRED")
        result = run_paper_pilot(
            args.state_dir, first_symbol=args.first_symbol,
            second_symbol=args.second_symbol,
            first_timeframe=args.first_timeframe,
            second_timeframe=args.second_timeframe,
            dry_run_signals=not args.no_dry_run_signals)
    except (ValueError, RuntimeError, OSError):
        print("STAGE20_PILOT_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
