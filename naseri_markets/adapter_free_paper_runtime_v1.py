"""Single operator-controlled OFFLINE integration boundary, before real adapters.

Reuses the existing Stage-12 control panel, Stage-16 offline pipeline,
Stage-8 PAPER risk/lifecycle and Stage-10 inert signal outbox.
No production engine imports, broker, Telegram transport or live data.
The ONLY executable accepted today is the internal deterministic test fixture.
Three ledgers remain distinct: cross-ledger atomicity is NOT claimed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .core_api_v1 import ClosedCandle, DataOrigin
from .offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
from .offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from .paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
from .trading_control_center_v1 import OfflineTradingControlCenter


class PipelineRefused(ValueError):
    """Fail-closed operator-facing refusal without secret core detail."""


@dataclass(frozen=True, slots=True)
class PipelineReadiness:
    instance_id: str
    core_id: str
    panel_revision: int
    binding_count: int
    adapter_state: str
    analysis_requested: bool
    paper_requested: bool
    signal_preview_requested: bool
    mode: str = "OFFLINE_PAPER_ONLY"
    feed_authenticated: bool = False
    live_runtime_connected: bool = False
    telegram_publication_enabled: bool = False
    broker_orders_enabled: bool = False


class AdapterFreePaperRuntime:
    """One operator API over existing reviewed components; default DENY.

    It does not create a strategy adapter. Production engine references remain
    unmounted until a separately reviewed, independently authorized adapter is
    implemented. Only the internal test fixture can exercise the pipeline now.
    """

    def __init__(
        self,
        control: OfflineTradingControlCenter,
        paper: OfflinePaperPositionLifecycle,
        signals: OfflineSignalLifecycle,
        *,
        actor_id: int,
        operator_ack: bool = False,
    ) -> None:
        if (operator_ack is not True
                or not isinstance(control, OfflineTradingControlCenter)
                or not control.enabled
                or not isinstance(paper, OfflinePaperPositionLifecycle)
                or not isinstance(signals, OfflineSignalLifecycle)
                or not signals.enabled
                or type(actor_id) is not int or actor_id <= 0):
            raise PipelineRefused("OFFLINE_OPERATOR_AND_LEDGERS_REQUIRED")
        control._auth(actor_id)
        self._control = control
        self._paper = paper
        self._signals = signals
        self._actor_id = actor_id
        self._fixtures: dict[str, tuple[int, OfflinePanelPaperIntegration]] = {}

    @staticmethod
    def _offline() -> None:
        if (os.environ.get("MMT_NONPRODUCTION") != "1"
                or "MMT_PRODUCTION" in os.environ):
            raise PipelineRefused("NONPRODUCTION_ENV_REQUIRED")

    def status(self, instance_id: str) -> PipelineReadiness:
        state = self._control.inspect(self._actor_id, instance_id)
        attached = self._fixtures.get(instance_id)
        mounted = attached is not None and attached[0] == state.revision
        return PipelineReadiness(
            instance_id=state.instance_id,
            core_id=state.core_id,
            panel_revision=state.revision,
            binding_count=state.binding_count,
            adapter_state=("SYNTHETIC_FIXTURE_ONLY" if mounted
                           else "ADAPTER_NOT_INSTALLED"),
            analysis_requested=state.analysis_requested,
            paper_requested=state.paper_orders_requested,
            signal_preview_requested=state.telegram_signals_requested,
        )

    def attach_test_fixture(
        self, instance_id: str, *,
        core: object,
        expected_panel_revision: int,
        operator_ack: bool = False,
    ) -> PipelineReadiness:
        """Never accepts Al Brooks/NYFR or arbitrary user code."""
        self._offline()
        from ._contract_acceptance_fixture_v1 import OfflineContractFixture

        state = self._control.inspect(self._actor_id, instance_id)
        if (operator_ack is not True
                or type(core) is not OfflineContractFixture
                or type(expected_panel_revision) is not int
                or state.revision != expected_panel_revision
                or state.core_id != core.manifest.core_id
                or state.telegram_publication_enabled
                or state.broker_orders_enabled or state.live_trading_enabled):
            raise PipelineRefused("TEST_FIXTURE_NOT_APPROVED")
        listing = self._control._listing(self._actor_id, state.core_id)
        if listing.manifest != core.manifest:
            raise PipelineRefused("TEST_MANIFEST_NOT_REVIEWED")
        bridge = OfflinePanelPaperIntegration(
            self._control, actor_id=self._actor_id, core=core,
            operator_ack=True)
        self._fixtures[instance_id] = (state.revision, bridge)
        return self.status(instance_id)

    def _bridge(
        self, instance_id: str, expected_panel_revision: int
    ) -> OfflinePanelPaperIntegration:
        self._offline()
        state = self._control.inspect(self._actor_id, instance_id)
        attached = self._fixtures.get(instance_id)
        if (type(expected_panel_revision) is not int
                or state.revision != expected_panel_revision):
            raise PipelineRefused("STALE_PANEL_REVISION")
        if attached is None or attached[0] != state.revision:
            raise PipelineRefused("ADAPTER_NOT_INSTALLED")
        return attached[1]

    def authorize_paper(
        self, instance_id: str, *,
        expected_panel_revision: int, now: datetime,
        operator_ack: bool = False,
    ) -> dict:
        if operator_ack is not True:
            raise PipelineRefused("EXPLICIT_OPERATOR_ACK_REQUIRED")
        bridge = self._bridge(instance_id, expected_panel_revision)
        return bridge.authorize_paper(
            instance_id, paper=self._paper,
            expected_panel_revision=expected_panel_revision,
            now=now, operator_ack=True)

    def replay(
        self, instance_id: str, binding_id: str, *,
        candles: tuple[ClosedCandle, ...],
        source_ref: str,
        expected_panel_revision: int,
        origin: DataOrigin = DataOrigin.SYNTHETIC,
        quantity: Decimal | None = None,
        target_fractions: tuple[Decimal, ...] = (Decimal(1),),
        dry_run_channel_id: int | None = None,
        operator_ack: bool = False,
    ) -> dict:
        if operator_ack is not True:
            raise PipelineRefused("EXPLICIT_OPERATOR_ACK_REQUIRED")
        bridge = self._bridge(instance_id, expected_panel_revision)
        state = self._control.inspect(self._actor_id, instance_id)
        if not (state.analysis_requested or state.paper_orders_requested
                or state.telegram_signals_requested):
            raise PipelineRefused("ALL_MODES_DISABLED")
        receipt = bridge.replay_candles(
            instance_id, binding_id, candles=candles, source_ref=source_ref,
            expected_panel_revision=expected_panel_revision,
            operator_ack=True, paper=self._paper if state.paper_orders_requested else None,
            signals=self._signals if state.telegram_signals_requested else None,
            quantity=quantity, target_fractions=target_fractions,
            dry_run_channel_id=dry_run_channel_id, data_origin=origin)
        if (receipt.get("telegram_sent") is not False
                or receipt.get("broker_order_sent") is not False):
            raise PipelineRefused("UNEXPECTED_EXTERNAL_SIDE_EFFECT")
        return receipt

    def admin_preview(self, instance_id: str, *, signal_key: str) -> dict:
        """Only renders local Stage-10 observations; no Telegram network I/O."""
        self._offline()
        state = self._control.inspect(self._actor_id, instance_id)
        if not state.telegram_signals_requested:
            raise PipelineRefused("SIGNAL_PREVIEW_DISABLED")
        snapshot = self._signals.snapshot(signal_key)
        if snapshot.instance_id != state.instance_id or snapshot.core_id != state.core_id:
            raise PipelineRefused("CROSS_INSTANCE_SIGNAL_DENIED")
        commands = self._signals.commands(signal_key)
        return {
            "instance_id": state.instance_id,
            "core_id": state.core_id,
            "signal_key": signal_key,
            "status": snapshot.state.value,
            "dry_run_commands": len(commands),
            "telegram_sent": False,
            "broker_order_sent": False,
            "live_runtime_connected": False,
        }


__all__ = ["AdapterFreePaperRuntime", "PipelineReadiness", "PipelineRefused"]
