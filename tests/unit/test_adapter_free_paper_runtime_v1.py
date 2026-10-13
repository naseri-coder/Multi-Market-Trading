"""Adapter-free Stage-12/16/8/10 integration; no trading core is changed."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.adapter_free_paper_runtime_v1 import (
    AdapterFreePaperRuntime,
    PipelineRefused,
)
from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import ClosedCandle, DataOrigin
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata,
    ListingStatus,
    MetadataOrigin,
    ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from naseri_markets.paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
from naseri_markets.risk_portfolio_contract_v1 import (
    AccountRiskPolicy,
    PortfolioRiskPolicy,
)
from naseri_markets.trading_control_center_v1 import (
    CoreListing,
    OfflineTradingControlCenter,
)

T0 = datetime(2026, 10, 12, 10, tzinfo=UTC)


def _setup(tmp_path, *, with_fixture=True, signals_on=True, paper_on=True):
    core = OfflineContractFixture()
    catalog = ResearchInstrumentCatalog(max_age_seconds=7200)
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    market = InstrumentMetadata(
        "synthetic_provider", Market.CRYPTO, "ABCUSD", "UTC", "USD",
        D("0.01"), origin, ListingStatus.OPEN, T0, "SYNTHETIC_RESEARCH")
    catalog.replace(ProviderSnapshot(
        "synthetic_provider", origin, T0, (market,), "a" * 64))
    control = OfflineTradingControlCenter(
        tmp_path / "control.sqlite", admin_ids={123}, catalog=catalog,
        listings=(CoreListing(
            core.manifest.core_id, "Internal Fixture",
            core.manifest.core_version, manifest=core.manifest),),
        enabled=True)
    state = control.create_instance(
        123, core_id=core.manifest.core_id, instance_id="fixture_instance",
        account_id="fixture_account", portfolio_id="fixture_portfolio")
    state = control.add_binding(
        123, state.instance_id, provider="synthetic_provider",
        symbol="ABCUSD", timeframe="15m", now=T0,
        expected_revision=state.revision)
    state = control.set_allocation(
        123, state.instance_id, max_reserved=D("0.10"),
        max_notional=D("0.50"), max_order=D("0.05"),
        max_orders=10, expected_revision=state.revision)
    modes = ["analysis"]
    if signals_on:
        modes.append("signals")
    if paper_on:
        modes.append("paper")
    for mode in modes:
        state = control.set_request(
            123, state.instance_id, field=mode, requested=True,
            expected_revision=state.revision)
    binding, = control.preview_bindings(123, state.instance_id, now=T0)
    paper = OfflinePaperPositionLifecycle(tmp_path / "paper.sqlite")
    paper.configure_portfolio(PortfolioRiskPolicy(
        "fixture_portfolio", "USD", D(100), D(5000), D(100),
        D(90), D(90), 25))
    paper.configure_account(AccountRiskPolicy(
        "fixture_account", "fixture_portfolio", "USD", D(1000),
        D("0.05"), D("0.20"), D("0.20"), D(2), D("0.90"),
        D(3), D(1), D("0.01"), D("0.002"), D("0.003"),
        25, True))
    paper.register_instrument(
        portfolio_id="fixture_portfolio",
        instrument=binding.instrument, group_id="CRYPTO")
    signals = OfflineSignalLifecycle(tmp_path / "signals.sqlite", enabled=True)
    coordinator = AdapterFreePaperRuntime(
        control, paper, signals, actor_id=123, operator_ack=True)
    if with_fixture:
        coordinator.attach_test_fixture(
            "fixture_instance", core=core,
            expected_panel_revision=state.revision, operator_ack=True)
    return control, paper, signals, coordinator, state, binding


def _candles():
    first = ClosedCandle(
        T0, T0 + timedelta(minutes=15), D(100), D(102),
        D(98), D(100), D(10))
    second = ClosedCandle(
        first.close_at, first.close_at + timedelta(minutes=15),
        D(100), D(108), D(99), D(106), D(10))
    return (first, second)


def test_missing_adapter_fails_closed_before_any_paper_write(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    control, paper, signals, runtime, state, binding = _setup(
        tmp_path, with_fixture=False)
    try:
        info = runtime.status("fixture_instance")
        assert info.adapter_state == "ADAPTER_NOT_INSTALLED"
        assert not info.live_runtime_connected
        assert not info.telegram_publication_enabled
        assert not info.broker_orders_enabled
        with pytest.raises(PipelineRefused, match="ADAPTER_NOT_INSTALLED"):
            runtime.replay(
                "fixture_instance", binding.binding_id,
                candles=_candles(), source_ref="synthetic-only",
                expected_panel_revision=state.revision, operator_ack=True)
        assert paper._db.execute(
            "SELECT count(*) FROM paper_core_orders").fetchone()[0] == 0
        assert signals._db.execute(
            "SELECT count(*) FROM offline_signal_states").fetchone()[0] == 0
    finally:
        signals.close()
        paper.close()
        control.close()


def test_integrated_paper_and_no_send_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    control, paper, signals, runtime, state, binding = _setup(tmp_path)
    try:
        assert runtime.status("fixture_instance").adapter_state == "SYNTHETIC_FIXTURE_ONLY"
        prepared = runtime.authorize_paper(
            "fixture_instance", expected_panel_revision=state.revision,
            now=T0, operator_ack=True)
        assert prepared["broker_order_sent"] is False
        kwargs = dict(
            candles=_candles(), source_ref="offline-synthetic",
            expected_panel_revision=state.revision, quantity=D(1),
            dry_run_channel_id=-100123, operator_ack=True)
        receipt = runtime.replay("fixture_instance", binding.binding_id, **kwargs)
        assert receipt["decision_count"] == 1
        assert len(receipt["paper_order_ids"]) == 1
        assert len(receipt["signal_keys"]) == 1
        assert receipt["telegram_sent"] is receipt["broker_order_sent"] is False
        assert runtime.replay("fixture_instance", binding.binding_id, **kwargs) == receipt
        preview = runtime.admin_preview(
            "fixture_instance", signal_key=receipt["signal_keys"][0])
        assert preview["dry_run_commands"] == 1
        assert preview["status"] == "WAITING_ENTRY"
        assert preview["telegram_sent"] is False
        assert preview["live_runtime_connected"] is False
    finally:
        signals.close()
        paper.close()
        control.close()


def test_panel_revision_revokes_fixture_and_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    control, paper, signals, runtime, state, binding = _setup(tmp_path)
    try:
        control.set_request(
            123, "fixture_instance", field="analysis", requested=False,
            expected_revision=state.revision)
        assert runtime.status("fixture_instance").adapter_state == "ADAPTER_NOT_INSTALLED"
        with pytest.raises(PipelineRefused, match="STALE_PANEL_REVISION"):
            runtime.replay(
                "fixture_instance", binding.binding_id,
                candles=_candles(), source_ref="offline-synthetic",
                expected_panel_revision=state.revision, operator_ack=True)
        with pytest.raises(PipelineRefused, match="ADAPTER_NOT_INSTALLED"):
            runtime.replay(
                "fixture_instance", binding.binding_id,
                candles=_candles(), source_ref="offline-synthetic",
                expected_panel_revision=state.revision+1, operator_ack=True)
    finally:
        signals.close()
        paper.close()
        control.close()


def test_production_environment_refused_even_with_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    control, paper, signals, runtime, state, binding = _setup(tmp_path)
    try:
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(PipelineRefused, match="NONPRODUCTION_ENV_REQUIRED"):
            runtime.replay(
                "fixture_instance", binding.binding_id,
                candles=_candles(), source_ref="offline-synthetic",
                expected_panel_revision=state.revision, operator_ack=True)
        with pytest.raises(PipelineRefused, match="NONPRODUCTION_ENV_REQUIRED"):
            runtime.admin_preview("fixture_instance", signal_key="0"*64)
    finally:
        signals.close()
        paper.close()
        control.close()


def test_no_unreviewed_core_can_mount(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    control, paper, signals, runtime, state, binding = _setup(
        tmp_path, with_fixture=False)
    try:
        with pytest.raises(PipelineRefused, match="TEST_FIXTURE_NOT_APPROVED"):
            runtime.attach_test_fixture(
                "fixture_instance", core=object(),
                expected_panel_revision=state.revision, operator_ack=True)
        with pytest.raises(PipelineRefused, match="TEST_FIXTURE_NOT_APPROVED"):
            runtime.attach_test_fixture(
                "fixture_instance", core=OfflineContractFixture(),
                expected_panel_revision=state.revision+1, operator_ack=True)
        assert runtime.status("fixture_instance").adapter_state == "ADAPTER_NOT_INSTALLED"
    finally:
        signals.close()
        paper.close()
        control.close()
