"""Stage 21B: strict offline captured futures -> causal PAPER life cycle.

No network access, real order, trading eligibility, Telegram send, or external
strategy loading. Uses only the reviewed built-in illustration and all Stage
12/16/17/19/8/9/10 operational fences. Venue economics are NOT calibrated.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path

from .contracts import Direction, Market
from .core_api_v1 import (
    DataOrigin, DecisionKind, OfflineCoreHarness, validate_core_result,
)
from ._contract_acceptance_fixture_v1 import OfflineContractFixture
from .instrument_registry_v1 import (
    CatalogRefused, ListingStatus, MetadataOrigin, ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from .job_effect_intent_v1 import JobEffectIntentExecutor, OfflineJobEffectLedger
from .job_effect_reconciliation_v1 import (
    EffectEvidencePaths, evaluate_effect_evidence,
)
from .kucoin_futures_replay_stage21_v1 import (
    FuturesKlineRequest, offline_replay_to_core_inputs, parse_futures_klines,
)
from .offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
from .offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
from .offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from .paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
from .paper_contract_economics_stage21d_v1 import PaperContractEconomics
from .paper_contract_audit_stage21d_v1 import audit_paper_contract_economics
from .reliability_acceptance_v1 import LedgerPaths, evaluate_offline_reliability
from .risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from .trading_control_center_v1 import CoreListing, OfflineTradingControlCenter


class CapturedPaperRefused(ValueError):
    """Fail-closed nonproduction research refusal; no private data disclosed."""


def _first_setup(capture, binding, core):
    """Select the *first* eligible setup, never select after seeing outcomes."""
    harness = OfflineCoreHarness(core, enabled=True)
    for event in offline_replay_to_core_inputs(
            capture, manifest=core.manifest, binding=binding):
        result = harness.evaluate(event)
        validate_core_result(core.manifest, event, result)
        entries = tuple(decision for decision in result.decisions
                        if decision.kind is DecisionKind.ENTRY_INTENT)
        if len(entries) > 1:
            raise CapturedPaperRefused("MULTIPLE_SAME_BAR_ENTRIES_UNSUPPORTED")
        # Need the next full bar to model entry. Do not use future prices
        # when deciding whether a setup exists.
        if entries:
            index = len(event.candles) - 1
            return (index, entries[0]) if index + 1 < len(capture.candles) else None
    return None


def _fill_decision(bar, decision):
    """A limit-at-intent model; uncertain intrabar stop/TP ordering is unscored."""
    touched = bar.low <= decision.entry <= bar.high
    if not touched:
        return "NOT_TOUCHED"
    stop_hit = (bar.low <= decision.stop if decision.direction is Direction.LONG
                else bar.high >= decision.stop)
    target_hit = (bar.high >= decision.targets[0] if decision.direction is Direction.LONG
                  else bar.low <= decision.targets[0])
    return "INTRABAR_UNRESOLVED" if stop_hit or target_hit else "MODELED_LIMIT_TOUCH"


def run_captured_paper_pilot(
    directory: Path, *, datasets: tuple[tuple[FuturesKlineRequest, bytes], ...],
    provider_snapshot: ProviderSnapshot, observed_at: datetime,
    operator_ack: bool = False, quantity: D = D("0.001"),
    dry_run_signals: bool = True,
    contract_economics: tuple[PaperContractEconomics, ...] | None = None,
) -> dict:
    """Interpret operator-held official-format data; NO remote market fetch.

    Raw bytes and historical metadata are untrusted operator inputs. A passing
    local audit cannot attest KuCoin origin or correct contract economics.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise CapturedPaperRefused("EXPLICIT_NONPRODUCTION_PAPER_ACK_REQUIRED")
    if (type(datasets) is not tuple or len(datasets) != 2
            or any(type(x) is not tuple or len(x) != 2
                   or not isinstance(x[0], FuturesKlineRequest)
                   or type(x[1]) is not bytes for x in datasets)
            or type(quantity) is not D or not quantity.is_finite()
            or not D(0) < quantity <= D(1) or type(dry_run_signals) is not bool):
        raise CapturedPaperRefused("BOUNDED_DATASET_AND_MODEL_QUANTITY_REQUIRED")
    if (not isinstance(provider_snapshot, ProviderSnapshot)
            or provider_snapshot.provider != "kucoin_futures"
            or provider_snapshot.origin is not MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
            or not provider_snapshot.instruments):
        raise CapturedPaperRefused("STAGE6_PUBLIC_METADATA_SNAPSHOT_REQUIRED")
    captures = tuple(parse_futures_klines(
        raw, query, observed_at=observed_at) for query, raw in datasets)
    symbols = tuple(c.request.symbol for c in captures)
    if len(set(symbols)) != 2 or any(len(c.candles) < 4 for c in captures):
        raise CapturedPaperRefused("TWO_DISTINCT_FOUR_BAR_DATASETS_REQUIRED")
    metadata = {item.symbol: item for item in provider_snapshot.instruments}
    if (any(symbol not in metadata or metadata[symbol].listing_status is not ListingStatus.OPEN
            or metadata[symbol].market is not Market.CRYPTO
            or metadata[symbol].quote_currency != "USDT" for symbol in symbols)
            or provider_snapshot.observed_at > min(c.request.start for c in captures)):
        raise CapturedPaperRefused("REVIEWED_HISTORIC_METADATA_REQUIRED")
    if contract_economics is not None:
        if (type(contract_economics) is not tuple
                or len(contract_economics) != len(captures)
                or any(type(e) is not PaperContractEconomics
                       for e in contract_economics)
                or {e.symbol for e in contract_economics} != set(symbols)
                or any(e.metadata_sha256 != provider_snapshot.raw_sha256
                       or e.provider != "kucoin_futures"
                       for e in contract_economics)):
            raise CapturedPaperRefused("EXACT_STAGE21D_CONTRACT_BINDING_REQUIRED")
        for econ in contract_economics:
            if (quantity / econ.quantity_step) != (
                    quantity / econ.quantity_step).to_integral_value():
                raise CapturedPaperRefused("CONTRACT_QUANTITY_NOT_VENUE_ALIGNED")
    directory = Path(directory)
    parent = directory.parent
    if (not directory.is_absolute() or directory.exists() or directory.is_symlink()
            or not parent.is_dir() or parent.is_symlink()
            or parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(parent.stat().st_mode) & 0o077):
        raise CapturedPaperRefused("NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED")
    # Prevent a file/DB being created before all purely input-level checks.
    catalog = ResearchInstrumentCatalog(max_age_seconds=86400)
    catalog.replace(provider_snapshot)
    core = OfflineContractFixture()
    # Reject stale operator metadata across the *entire* intended replay
    # before creating any state, not just the first signal bar.
    try:
        for capture in captures:
            catalog.lookup("kucoin_futures", capture.request.symbol,
                           now=capture.request.end)
    except CatalogRefused as exc:
        raise CapturedPaperRefused("REVIEWED_HISTORIC_METADATA_REQUIRED") from exc
    directory.mkdir(mode=0o700)
    paths = {name: directory / (name + ".sqlite") for name in (
        "control", "paper", "signals", "runtime", "effects")}
    results = {}
    with OfflineTradingControlCenter(
            paths["control"], admin_ids={123}, catalog=catalog, enabled=True,
            listings=(CoreListing(core.manifest.core_id, "Reviewed example",
                                  core.manifest.core_version,
                                  manifest=core.manifest),)) as panel:
        state = panel.create_instance(
            123, core_id=core.manifest.core_id, instance_id="captured_instance",
            account_id="captured_account", portfolio_id="captured_portfolio")
        for capture in captures:
            state = panel.add_binding(
                123, state.instance_id, provider="kucoin_futures",
                symbol=capture.request.symbol,
                timeframe=capture.request.timeframe,
                now=capture.request.start,
                expected_revision=state.revision)
        state = panel.set_allocation(
            123, state.instance_id, max_reserved=D("0.10"),
            max_notional=D("0.50"), max_order=D("0.05"),
            max_orders=10, expected_revision=state.revision)
        for toggle in (("analysis", "paper", "signals") if dry_run_signals
                       else ("analysis", "paper")):
            state = panel.set_request(
                123, state.instance_id, field=toggle, requested=True,
                expected_revision=state.revision)
        bindings = panel.preview_bindings(
            123, state.instance_id,
            now=min(c.request.start for c in captures))
        by_symbol = {b.instrument.symbol: b for b in bindings}
        if set(by_symbol) != set(symbols):
            raise CapturedPaperRefused("PANEL_INSTRUMENT_IDENTITY_DRIFT")
        planned = {}
        for capture in captures:
            binding = by_symbol[capture.request.symbol]
            decision = _first_setup(capture, binding, core)
            planned[binding.binding_id] = (capture, binding, decision)
        bridge = OfflinePanelPaperIntegration(
            panel, actor_id=123, core=core, operator_ack=True)
        with OfflineRuntimeSupervisor(
                paths["runtime"], panel=panel, actor_id=123, enabled=True) as runtime, \
             OfflinePaperPositionLifecycle(paths["paper"]) as paper, \
             OfflineSignalLifecycle(paths["signals"], enabled=True) as signals, \
             OfflineJobEffectLedger(paths["effects"], enabled=True) as effects:
            paper.configure_portfolio(PortfolioRiskPolicy(
                "captured_portfolio", "USDT", D(100), D(5000),
                D(100), D(90), D(90), 25))
            paper.configure_account(AccountRiskPolicy(
                "captured_account", "captured_portfolio", "USDT",
                D(1000), D("0.05"), D("0.20"), D("0.20"),
                D(2), D("0.90"), D(3), D(1), D("0.0001"),
                D("0.002"), D("0.003"), 25, True))
            econ_by_symbol = {e.symbol: e for e in (contract_economics or ())}
            for capture, binding, _decision in planned.values():
                paper.register_instrument(
                    portfolio_id="captured_portfolio",
                    instrument=binding.instrument, group_id="CRYPTO")
                if contract_economics is not None:
                    paper.register_contract_economics(
                        portfolio_id="captured_portfolio",
                        policy=econ_by_symbol[capture.request.symbol],
                        operator_ack=True)
            bridge.authorize_paper(
                state.instance_id, paper=paper,
                expected_panel_revision=state.revision,
                now=min(c.request.start for c in captures),
                operator_ack=True)
            scheduled = {}
            for capture, binding, detected in planned.values():
                if detected is None:
                    results[binding.binding_id] = {
                        "symbol": capture.request.symbol, "timeframe": binding.timeframe,
                        "status": "NO_ELIGIBLE_ENTRY", "raw_sha256": capture.raw_sha256}
                    continue
                index, decision = detected
                # Scan has not used bars following index to select the setup.
                job_id = runtime.schedule(
                    state.instance_id, binding.binding_id,
                    expected_panel_revision=state.revision,
                    candles=capture.candles[:index + 1],
                    source_ref=capture.source_ref,
                    due_at=capture.candles[index].close_at, operator_ack=True)
                scheduled[binding.binding_id] = (job_id, index, decision)
            executor = JobEffectIntentExecutor(
                supervisor=runtime, ledger=effects, integration=bridge,
                paper=paper, signals=signals if dry_run_signals else None,
                quantity=quantity,
                dry_run_channel_id=-10021 if dry_run_signals else None,
                data_origin=DataOrigin.REPLAY)
            if scheduled:
                done = runtime.run_due(
                    executor, now=max(c.request.end for c in captures),
                    limit=len(scheduled), operator_ack=True)
                if (len(done) != len(scheduled)
                        or any(row["status"] != "DONE" for row in done)):
                    raise CapturedPaperRefused("REPLAY_JOB_REQUIRES_MANUAL_RECONCILIATION")
                if runtime.run_due(executor, now=max(c.request.end for c in captures),
                                   limit=2, operator_ack=True):
                    raise CapturedPaperRefused("DUPLICATE_DISPATCH")
            expected_effects = 0
            for capture, binding, detected in planned.values():
                if detected is None:
                    continue
                job_id, index, decision = scheduled[binding.binding_id]
                intents = effects.intents(job_id=job_id)
                required = {"PAPER_RESERVE", "PAPER_PLAN"}
                if dry_run_signals:
                    required.add("DRY_SIGNAL")
                if (len(intents) != len(required)
                        or {x["kind"] for x in intents} != required
                        or any(x["state"] != "RECORDED" for x in intents)):
                    raise CapturedPaperRefused("EFFECT_IDENTITY_OR_JOURNAL_MISMATCH")
                expected_effects += len(required)
                order_id = next(x["target_id"] for x in intents
                                if x["kind"] == "PAPER_RESERVE")
                if dry_run_signals:
                    key = next(x["target_id"] for x in intents if x["kind"] == "DRY_SIGNAL")
                    if signals.snapshot(key).message_id is not None:
                        raise CapturedPaperRefused("TELEGRAM_DELIVERY_FORBIDDEN")
                action = "s21b_" + order_id[-36:]
                paper.apply_paper_event(
                    order_id, action_id=action + "_submit", event="SUBMIT",
                    expected_revision=0, operator_ack=True)
                paper.apply_paper_event(
                    order_id, action_id=action + "_ack", event="ACK",
                    expected_revision=1,
                    remote_order_id="simulated_" + order_id[-30:],
                    operator_ack=True)
                entry_bar = capture.candles[index + 1]
                fill_status = _fill_decision(entry_bar, decision)
                if fill_status != "MODELED_LIMIT_TOUCH":
                    paper.apply_paper_event(
                        order_id, action_id=action + "_cancel", event="CANCEL",
                        expected_revision=2, operator_ack=True)
                else:
                    paper.apply_paper_event(
                        order_id, action_id=action + "_fill", event="FILL",
                        expected_revision=2, quantity=quantity,
                        price=decision.entry, entry_bar=entry_bar,
                        operator_ack=True)
                    for bar in capture.candles[index + 2:]:
                        state_bar = paper.step_closed_bar(
                            order_id, bar, operator_ack=True)
                        if state_bar["status"] == "CLOSED":
                            break
                performance = paper.performance(order_id)
                if contract_economics is not None and (
                        performance["economics_digest"] !=
                        econ_by_symbol[capture.request.symbol].digest):
                    raise CapturedPaperRefused("ORDER_ECONOMICS_SNAPSHOT_MISMATCH")
                results[binding.binding_id] = {
                    "symbol": capture.request.symbol,
                    "timeframe": binding.timeframe,
                    "order_id": order_id,
                    "decision_id": decision.decision_id,
                    "data_origin": "replay",
                    "source_ref": capture.source_ref,
                    "raw_sha256": capture.raw_sha256,
                    "entry_bar_open_at": entry_bar.open_at.isoformat(),
                    "fill_model": fill_status,
                    "status": performance["status"],
                    "modeled_realized_net": performance["net"],
                    "modeled_realized_r": performance["net_realized_r"],
                    "contract_units": str(quantity) if contract_economics else None,
                    "per_instrument_economics_digest": performance["economics_digest"],
                    "unrealized_pnl_included": False,
                    "broker_verified": False,
                }
            if runtime.health()["manual_reconciliation_required"]:
                raise CapturedPaperRefused("MANUAL_RECONCILIATION_REQUIRED")
    with OfflinePaperPositionLifecycle(paths["paper"]) as paper:
        paper.reconcile_offline(operator_ack=True)
        for item in results.values():
            if "order_id" in item:
                stats = paper.performance(item["order_id"])
                if stats["status"] != item["status"] or stats["net"] != item["modeled_realized_net"]:
                    raise CapturedPaperRefused("PAPER_RESTART_EVIDENCE_DRIFT")
    for path in paths.values():
        path.chmod(0o600)
    ledger = evaluate_offline_reliability(LedgerPaths(
        paths["control"], paths["paper"], paths["signals"]))
    # Stage19 correctly refuses to attest an empty intent ledger. Never
    # fabricate an empty-ledger Stage19 PASS or dispatch a dummy effect.
    proof = (evaluate_effect_evidence(EffectEvidencePaths(
        paths["effects"], paths["runtime"], paths["paper"], paths["signals"]))
        if expected_effects else None)
    no_output_expected = expected_effects == 0
    # Stage 13 explicitly blocks the absence of evaluated output evidence.
    # A genuine NO_SETUP is not a proof of cross-stage execution.
    gate_ok = (ledger.integrity_verdict == "PASS" if not no_output_expected
               else ledger.blockers == ("NO_EVALUATED_OUTPUT_EVIDENCE",))
    if (not gate_ok
            or ledger.release_verdict != "BLOCKED_NONPRODUCTION_UNATTESTED"
            or (proof is not None and (proof.blocking_effects
                or proof.exact_local_effects != expected_effects))):
        raise CapturedPaperRefused("CROSS_LEDGER_AUDIT_FAILED")
    economy_audit = (audit_paper_contract_economics(
        paths["paper"], expected=contract_economics,
        expected_orders=len(scheduled)) if contract_economics is not None
        else None)
    rows = [results[b.binding_id] for b in bindings]
    if economy_audit is not None and (
            D(economy_audit.total_net) !=
            sum((D(item.get("modeled_realized_net", "0"))
                 for item in rows), D(0))):
        raise CapturedPaperRefused("PER_CONTRACT_PNL_AUDIT_DRIFT")
    return {
        "mode": ("STAGE21D_UNATTESTED_CONTRACT_AWARE_OFFLINE_PAPER"
                 if contract_economics is not None else
                 "STAGE21B_UNATTESTED_PUBLIC_FORMAT_OFFLINE_PAPER"),
        "provider": "kucoin_futures",
        "core": core.manifest.core_id,
        "datasets": rows,
        "reviewed_metadata_raw_sha256": provider_snapshot.raw_sha256,
        "modeled_realized_net_total": str(sum((
            D(item.get("modeled_realized_net", "0")) for item in rows), D(0))),
        "completed_jobs": len(scheduled),
        "exact_effects": proof.exact_local_effects if proof else 0,
        "effect_evidence_verdict": (proof.verdict if proof else
                                     "NO_EFFECT_INTENTS_NOT_STAGE19_ATTESTED"),
        "integrity_verdict": ledger.integrity_verdict,
        "integrity_blockers": list(ledger.blockers),
        "no_output_cross_stage_unattested": no_output_expected,
        "release_verdict": ledger.release_verdict,
        "restarted_and_reconciled": True,
        "paper_positions_possible_open": any(row.get("status") not in
            ("CLOSED", "CANCELED", "NO_ELIGIBLE_ENTRY") for row in rows),
        "telegram_sent": False, "broker_order_sent": False,
        "provider_origin_independently_attested": False,
        "real_network_used": False, "provider_contract_size_verified": False,
        "modeled_per_contract_economics_applied": contract_economics is not None,
        "local_economic_audit": (economy_audit.state if economy_audit is not None
                                 else "NOT_APPLICABLE_LEGACY_PAPER"),
        "economic_audited_orders": economy_audit.orders if economy_audit else 0,
        "per_contract_metadata_sha256": (provider_snapshot.raw_sha256
                                         if contract_economics else None),
        "real_futures_pnl_proven": False, "profitability_proven": False,
        "live_trading_enabled": False, "public_release_authorized": False,
        "brooks_core_api_integrated": False,
    }


__all__ = ["CapturedPaperRefused", "run_captured_paper_pilot"]
