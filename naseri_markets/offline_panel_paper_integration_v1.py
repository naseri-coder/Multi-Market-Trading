"""Stage 16: operator-invoked OFFLINE panel -> core -> PAPER -> signal handoff.

No live feed, Telegram delivery, broker calls or third-party core loading.
The three ledgers are NOT one atomic transaction; operator-controlled retries
must reuse exact immutable event identities and separately reconcile failures.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from .contracts import Market
from .core_api_v1 import (ClosedCandle, CoreEventType, CoreInput, CoreManifest,
                          DataOrigin, DecisionKind, OfflineCoreHarness, content_digest)
from .market_data_engine_v1 import (FeedDefinition, MarketPacket,
                                    OfflineMarketDataEngine, PriceBasis,
                                    VolumeSemantics)
from .strategy_orchestrator_v1 import (EvaluationStatus,
                                       OfflineStrategyOrchestrator,
                                       TrustedCoreEvaluator)
from .trading_control_center_v1 import OfflineTradingControlCenter


class IntegrationRefused(ValueError):
    """Operator-safe fail-closed reason."""


class OfflinePanelPaperIntegration:
    """Trusted host-only integration; never call from untrusted plugin code."""

    def __init__(self, panel: OfflineTradingControlCenter, *, actor_id: int,
                 core: object, operator_ack: bool = False):
        manifest = getattr(core, "manifest", None)
        if (operator_ack is not True
                or not isinstance(panel, OfflineTradingControlCenter)
                or type(actor_id) is not int or actor_id <= 0
                or not isinstance(manifest, CoreManifest)):
            raise IntegrationRefused("TRUSTED_OPERATOR_AND_CORE_REQUIRED")
        self.panel = panel
        self.actor_id = actor_id
        self.core = core
        self.manifest = manifest

    def _state(self, instance_id, binding_id, now, revision):
        state = self.panel.inspect(self.actor_id, instance_id)
        if state.revision != revision:
            raise IntegrationRefused("STALE_PANEL_REVISION")
        if state.core_id != self.manifest.core_id:
            raise IntegrationRefused("CORE_IDENTITY_MISMATCH")
        listing = self.panel._listing(self.actor_id, state.core_id)
        if listing.manifest != self.manifest:
            raise IntegrationRefused("REVIEWED_MANIFEST_DRIFT")
        selected = [b for b in self.panel.preview_bindings(
            self.actor_id, instance_id, now=now) if b.binding_id == binding_id]
        if len(selected) != 1:
            raise IntegrationRefused("UNAPPROVED_BINDING")
        if (state.telegram_publication_enabled or state.broker_orders_enabled
                or state.live_trading_enabled):
            raise IntegrationRefused("LIVE_PERMISSION_NOT_ALLOWED")
        return state, selected[0]

    @staticmethod
    def _budget(state, policy):
        return (policy["core_id"] == state.core_id
                and policy["account_id"] == state.account_id
                and policy["portfolio_id"] == state.portfolio_id
                and Decimal(policy["max_reserved_risk_fraction"]) == Decimal(
                    state.max_reserved_risk_fraction)
                and Decimal(policy["max_notional_fraction"]) == Decimal(
                    state.max_notional_fraction)
                and Decimal(policy["max_order_risk_fraction"]) == Decimal(
                    state.max_order_risk_fraction)
                and policy["max_active_orders"] == state.max_active_orders)

    def authorize_paper(self, instance_id, *, paper, expected_panel_revision: int,
                        now, operator_ack: bool = False):
        """Pin panel configuration into an already-configured Stage-8 risk DB."""
        if operator_ack is not True:
            raise IntegrationRefused("EXPLICIT_PAPER_ACK_REQUIRED")
        state = self.panel.inspect(self.actor_id, instance_id)
        if (state.revision != expected_panel_revision
                or not state.paper_orders_requested):
            raise IntegrationRefused("PANEL_PAPER_REVISION_OR_MODE_CHANGED")
        bindings = self.panel.preview_bindings(self.actor_id, instance_id, now=now)
        if not bindings or any(b.instrument.market is not Market.CRYPTO for b in bindings):
            raise IntegrationRefused("CRYPTO_PAPER_MODEL_ONLY")
        from .paper_core_risk_bridge_v1 import CoreCapitalAllocation
        record = paper._db.execute(
            "SELECT policy_json FROM paper_core_allocations WHERE instance_id=?",
            (instance_id,)).fetchone()
        if record is None:
            policy = CoreCapitalAllocation(
                instance_id, self.manifest.core_id, self.manifest.core_version,
                state.account_id, state.portfolio_id,
                Decimal(state.max_reserved_risk_fraction),
                Decimal(state.max_notional_fraction),
                Decimal(state.max_order_risk_fraction), state.max_active_orders)
            paper.register_allocation(policy, operator_ack=True)
        elif not self._budget(state, json.loads(record["policy_json"])):
            raise IntegrationRefused("PAPER_BUDGET_DRIFT")
        for binding in bindings:
            previous = paper._db.execute(
                "SELECT manifest_digest,binding_digest FROM paper_core_bindings "
                "WHERE binding_id=?", (binding.binding_id,)).fetchone()
            if previous is None:
                paper.register_binding(self.manifest, binding, operator_ack=True)
            elif (previous["manifest_digest"] != content_digest(self.manifest)
                  or previous["binding_digest"] != content_digest(binding)):
                raise IntegrationRefused("PAPER_BINDING_DRIFT")
        status = paper.status(instance_id)
        if not status["enabled"]:
            paper.set_enabled(instance_id, enabled=True,
                              expected_revision=status["revision"],
                              operator_ack=True)
            status = paper.status(instance_id)
        if self.panel.inspect(self.actor_id, instance_id).revision != expected_panel_revision:
            raise IntegrationRefused("PANEL_CHANGED_RECONCILIATION_REQUIRED")
        return {"allocation_revision": status["revision"],
                "bindings": len(bindings), "broker_order_sent": False}

    def replay_candles(self, instance_id, binding_id, *,
                       candles: tuple[ClosedCandle, ...], source_ref: str,
                       expected_panel_revision: int, operator_ack: bool = False,
                       paper=None, signals=None, quantity: Decimal | None = None,
                       target_fractions: tuple[Decimal, ...] = (Decimal(1),),
                       dry_run_channel_id: int | None = None):
        if (operator_ack is not True or type(candles) is not tuple
                or not 1 <= len(candles) <= 128
                or any(type(c) is not ClosedCandle for c in candles)
                or any(x.close_at != y.open_at for x, y in zip(candles, candles[1:]))
                or type(source_ref) is not str or not source_ref):
            raise IntegrationRefused("CONTIGUOUS_OPERATOR_REPLAY_REQUIRED")
        state, binding = self._state(instance_id, binding_id, candles[-1].close_at,
                                     expected_panel_revision)
        if binding.instrument.market is not Market.CRYPTO:
            raise IntegrationRefused("CRYPTO_CANDLE_REPLAY_ONLY")
        if not (state.analysis_requested or state.telegram_signals_requested
                or state.paper_orders_requested):
            raise IntegrationRefused("ALL_MODES_DISABLED")
        if state.telegram_signals_requested and (
                signals is None or type(dry_run_channel_id) is not int
                or dry_run_channel_id >= 0):
            raise IntegrationRefused("NO_SEND_SIGNAL_LEDGER_REQUIRED")
        revision = None
        if state.paper_orders_requested:
            if (paper is None or type(quantity) is not Decimal
                    or not quantity.is_finite() or quantity <= 0
                    or type(target_fractions) is not tuple
                    or not 1 <= len(target_fractions) <= 5
                    or any(type(x) is not Decimal or not x.is_finite() or x <= 0
                           for x in target_fractions)
                    or sum(target_fractions, Decimal(0)) != 1):
                raise IntegrationRefused("EXPLICIT_PAPER_QUANTITY_REQUIRED")
            status = paper.status(instance_id)
            budget = paper._db.execute(
                "SELECT policy_json FROM paper_core_allocations WHERE instance_id=?",
                (instance_id,)).fetchone()
            route = paper._db.execute(
                "SELECT manifest_digest,binding_digest FROM paper_core_bindings "
                "WHERE binding_id=?", (binding_id,)).fetchone()
            if (not status["enabled"] or status["account_id"] != state.account_id
                    or budget is None
                    or not self._budget(state, json.loads(budget["policy_json"]))
                    or route is None
                    or route["manifest_digest"] != content_digest(self.manifest)
                    or route["binding_digest"] != content_digest(binding)):
                raise IntegrationRefused("PAPER_ALLOCATION_OR_BINDING_DRIFT")
            revision = status["revision"]
        feed_id = "p16_" + content_digest((instance_id, binding_id))[:40]
        definition = FeedDefinition(
            feed_id, binding.instrument, binding.timeframe,
            CoreEventType.CLOSED_CANDLE, DataOrigin.SYNTHETIC,
            source_ref, PriceBasis.TRADE, VolumeSemantics.TRADED)
        data = OfflineMarketDataEngine(enabled=True)
        data.register_feed(definition)
        engine = OfflineStrategyOrchestrator(data, enabled=True)
        engine.attach(feed_id, self.manifest, binding, TrustedCoreEvaluator(
            OfflineCoreHarness(self.core, enabled=True), self.manifest))
        engine.set_enabled(binding_id, enabled=True,
                           expected_revision=engine.state(binding_id).revision,
                           operator_ack=True)
        outcome = None
        for n, candle in enumerate(candles, 1):
            receipt = engine.ingest(MarketPacket(
                feed_id, n, candle.close_at + timedelta(seconds=1),
                source_ref, candle=candle))
            if receipt.outcomes:
                outcome = receipt.outcomes[0]
        if outcome is None or outcome.status is not EvaluationStatus.EVALUATED:
            if outcome is not None and outcome.status is EvaluationStatus.QUARANTINED:
                raise IntegrationRefused("CORE_QUARANTINED")
            return {"status": "NO_EVALUATION", "decision_count": 0,
                    "paper_order_ids": [], "signal_keys": [],
                    "broker_order_sent": False, "telegram_sent": False}
        result = outcome.result
        event = CoreInput(self.manifest.core_id, self.manifest.core_version,
                          binding, CoreEventType.CLOSED_CANDLE,
                          candles[-1].close_at, DataOrigin.SYNTHETIC,
                          source_ref, candles)
        if result is None or result.input_digest != event.input_digest:
            raise IntegrationRefused("RESULT_EVIDENCE_MISMATCH")
        entries = [d for d in result.decisions if d.kind is DecisionKind.ENTRY_INTENT]
        orders, keys = [], []
        for decision in entries:
            if self.panel.inspect(self.actor_id, instance_id).revision != expected_panel_revision:
                raise IntegrationRefused("PANEL_CHANGED_RECONCILIATION_REQUIRED")
            if state.paper_orders_requested:
                from .paper_order_lifecycle_v1 import TargetStep
                if len(decision.targets) != len(target_fractions):
                    raise IntegrationRefused("TARGET_ALLOCATION_MISMATCH")
                order = paper.reserve_entry(
                    self.manifest, event, result,
                    decision_id=decision.decision_id, quantity=quantity,
                    price_basis=PriceBasis.TRADE,
                    volume_semantics=VolumeSemantics.TRADED,
                    expected_allocation_revision=revision, operator_ack=True)
                paper.register_plan(
                    self.manifest, event, result, decision_id=decision.decision_id,
                    order_id=order.order_id,
                    targets=tuple(TargetStep(p, f) for p, f in zip(
                        decision.targets, target_fractions)),
                    operator_ack=True)
                orders.append(order.order_id)
            if state.telegram_signals_requested:
                signal = signals.register(
                    self.manifest, event, result, decision,
                    channel_id=dry_run_channel_id, price_basis=PriceBasis.TRADE,
                    volume_semantics=VolumeSemantics.TRADED,
                    expires_at=event.observed_at + timedelta(minutes=30),
                    operator_ack=True)
                keys.append(signal.key)
        if self.panel.inspect(self.actor_id, instance_id).revision != expected_panel_revision:
            raise IntegrationRefused("PANEL_CHANGED_RECONCILIATION_REQUIRED")
        return {"status": "OFFLINE_JOURNALS_UPDATED",
                "decision_count": len(entries),
                "paper_order_ids": orders, "signal_keys": keys,
                "broker_order_sent": False, "telegram_sent": False,
                "live_trading_enabled": False}


__all__ = ["IntegrationRefused", "OfflinePanelPaperIntegration"]
