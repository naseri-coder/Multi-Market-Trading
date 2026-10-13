"""Stage 16: stage-12 binding and toggle choices drive real offline routing."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import ClosedCandle
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin,
    ProviderSnapshot, ResearchInstrumentCatalog,
)
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from naseri_markets.offline_panel_paper_integration_v1 import (
    IntegrationRefused, OfflinePanelPaperIntegration,
)
from naseri_markets.trading_control_center_v1 import (
    CoreListing, OfflineTradingControlCenter,
)

T0 = datetime(2026, 10, 12, 10, tzinfo=UTC)
CORE = OfflineContractFixture()


def prepared(tmp_path, *, signal=False, timeframe="15m", symbol="ABCUSD"):
    catalog = ResearchInstrumentCatalog(max_age_seconds=7200)
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    record = InstrumentMetadata(
        "synthetic_provider", Market.CRYPTO, symbol, "UTC", "USD",
        D("0.01"), origin, ListingStatus.OPEN, T0, "SYNTHETIC_RESEARCH")
    catalog.replace(ProviderSnapshot(
        "synthetic_provider", origin, T0, (record,), "a" * 64))
    panel = OfflineTradingControlCenter(
        tmp_path / "control.sqlite", admin_ids={123},
        catalog=catalog, listings=(CoreListing(
            CORE.manifest.core_id, "Public Test Core",
            CORE.manifest.core_version, manifest=CORE.manifest),),
        enabled=True)
    state = panel.create_instance(
        123, core_id=CORE.manifest.core_id, instance_id="demo_instance",
        account_id="demo_account", portfolio_id="demo_portfolio")
    state = panel.add_binding(
        123, "demo_instance", provider="synthetic_provider",
        symbol=symbol, timeframe=timeframe, now=T0,
        expected_revision=state.revision)
    state = panel.set_request(
        123, "demo_instance", field="analysis", requested=True,
        expected_revision=state.revision)
    if signal:
        state = panel.set_request(
            123, "demo_instance", field="signals", requested=True,
            expected_revision=state.revision)
    binding, = panel.preview_bindings(123, "demo_instance", now=T0)
    host = OfflinePanelPaperIntegration(
        panel, actor_id=123, core=CORE, operator_ack=True)
    return panel, host, binding


def candles(timeframe="15m"):
    duration = timedelta(minutes={"5m": 5, "15m": 15, "1h": 60}[timeframe])
    a = ClosedCandle(T0, T0 + duration, D(100), D(102), D(98), D(100), D(10))
    b = ClosedCandle(a.close_at, a.close_at + duration,
                     D(100), D(108), D(99), D(106), D(10))
    return a, b


def replay(panel, host, binding, **kwargs):
    return host.replay_candles(
        "demo_instance", binding.binding_id,
        candles=candles(binding.timeframe),
        source_ref="operator_synthetic",
        expected_panel_revision=panel.inspect(123, "demo_instance").revision,
        operator_ack=True, **kwargs)


@pytest.mark.parametrize("timeframe", ["5m", "15m", "1h"])
def test_analysis_only_binding_controls_timeframe_and_symbol(tmp_path, timeframe):
    panel, host, binding = prepared(
        tmp_path, timeframe=timeframe, symbol="XYZUSD")
    try:
        assert binding.instrument.symbol == "XYZUSD"
        result = replay(panel, host, binding)
        assert result["decision_count"] == 1
        assert result["paper_order_ids"] == result["signal_keys"] == []
        assert not result["telegram_sent"] and not result["broker_order_sent"]
    finally:
        panel.close()


def test_offline_signal_journal_idempotent_across_restart(tmp_path):
    panel, host, binding = prepared(tmp_path, signal=True)
    path = tmp_path / "signal.sqlite"
    try:
        with OfflineSignalLifecycle(path, enabled=True) as ledger:
            first = replay(
                panel, host, binding, signals=ledger,
                dry_run_channel_id=-10016)
            assert first["decision_count"] == 1
            assert first == replay(
                panel, host, binding, signals=ledger,
                dry_run_channel_id=-10016)
            assert len(ledger.commands(first["signal_keys"][0])) == 1
        with OfflineSignalLifecycle(path, enabled=True) as again:
            assert first == replay(
                panel, host, binding, signals=again,
                dry_run_channel_id=-10016)
            assert again.snapshot(first["signal_keys"][0]).message_id is None
    finally:
        panel.close()


def test_missing_signal_store_refused_before_strategy(tmp_path):
    panel, host, binding = prepared(tmp_path, signal=True)
    try:
        with pytest.raises(IntegrationRefused, match="NO_SEND_SIGNAL_LEDGER_REQUIRED"):
            replay(panel, host, binding)
    finally:
        panel.close()


def test_stale_revision_blocks_execution(tmp_path):
    panel, host, binding = prepared(tmp_path)
    try:
        old = panel.inspect(123, "demo_instance").revision
        panel.set_request(
            123, "demo_instance", field="analysis", requested=False,
            expected_revision=old)
        with pytest.raises(IntegrationRefused, match="STALE_PANEL_REVISION"):
            host.replay_candles(
                "demo_instance", binding.binding_id,
                candles=candles(), source_ref="operator_synthetic",
                expected_panel_revision=old, operator_ack=True)
    finally:
        panel.close()


def test_missing_binding_denied(tmp_path):
    panel, host, binding = prepared(tmp_path)
    try:
        with pytest.raises(IntegrationRefused, match="UNAPPROVED_BINDING"):
            host.replay_candles(
                "demo_instance", "not_a_binding", candles=candles(),
                source_ref="operator_synthetic",
                expected_panel_revision=panel.inspect(123, "demo_instance").revision,
                operator_ack=True)
    finally:
        panel.close()
