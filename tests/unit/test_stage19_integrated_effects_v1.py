"""Installed-code Stage 17 -> 16 -> 8/9/10, with Stage 19 PRE-call intent proof.

Runs against the complete repository in CI. No live feed, Telegram or broker.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

# The compact local research copy lacks the Stage-3 risk dependencies.
pytest.importorskip("naseri_markets.execution_position_core_v1")

from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import ClosedCandle
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin,
    ProviderSnapshot, ResearchInstrumentCatalog,
)
from naseri_markets.trading_control_center_v1 import CoreListing, OfflineTradingControlCenter
from naseri_markets.offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
from naseri_markets.offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from naseri_markets.paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from naseri_markets.job_effect_intent_v1 import OfflineJobEffectLedger, JobEffectIntentExecutor
from naseri_markets.job_effect_reconciliation_v1 import (
    EffectEvidencePaths, evaluate_effect_evidence,
)

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def test_actual_stage16_through_stage19_with_durable_exact_receipts(tmp_path):
    core = OfflineContractFixture()
    provider = "synthetic_provider"
    catalog = ResearchInstrumentCatalog(max_age_seconds=86400)
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    instrument = InstrumentMetadata(provider, Market.CRYPTO, "ABCUSD", "UTC", "USD",
                                    D("0.01"), origin, ListingStatus.OPEN,
                                    T0, "SYNTHETIC_FIXTURE")
    catalog.replace(ProviderSnapshot(provider, origin, T0, (instrument,), "a" * 64))
    panel_path = tmp_path / "control.sqlite"
    with OfflineTradingControlCenter(
        panel_path, admin_ids={123}, enabled=True, catalog=catalog,
        listings=(CoreListing(core.manifest.core_id, "Demonstration Core",
                              core.manifest.core_version, manifest=core.manifest),)
    ) as panel:
        instance = panel.create_instance(123, core_id=core.manifest.core_id,
            instance_id="demo_instance", account_id="demo_account",
            portfolio_id="demo_portfolio")
        instance = panel.add_binding(123, instance.instance_id, provider=provider,
            symbol="ABCUSD", timeframe="15m", now=T0,
            expected_revision=instance.revision)
        instance = panel.set_allocation(123, instance.instance_id,
            max_reserved=D("0.10"), max_notional=D("0.50"),
            max_order=D("0.05"), max_orders=10,
            expected_revision=instance.revision)
        for toggle in ("analysis", "signals", "paper"):
            instance = panel.set_request(123, instance.instance_id, field=toggle,
                requested=True, expected_revision=instance.revision)
        binding, = panel.preview_bindings(123, instance.instance_id, now=T0)
        first = ClosedCandle(T0, T0+timedelta(minutes=15),
                             D(100), D(102), D(98), D(100), D(10))
        second = ClosedCandle(first.close_at, first.close_at+timedelta(minutes=15),
                              D(100), D(108), D(99), D(106), D(10))
        runtime_path = tmp_path / "runtime.sqlite"
        paper_path = tmp_path / "paper.sqlite"
        signals_path = tmp_path / "signals.sqlite"
        effect_path = tmp_path / "effect.sqlite"
        integration = OfflinePanelPaperIntegration(
            panel, actor_id=123, core=core, operator_ack=True)
        with OfflineRuntimeSupervisor(runtime_path, panel=panel,
                actor_id=123, enabled=True) as supervisor, \
             OfflinePaperPositionLifecycle(paper_path) as paper, \
             OfflineSignalLifecycle(signals_path, enabled=True) as signals, \
             OfflineJobEffectLedger(effect_path, enabled=True) as effects:
            paper.configure_portfolio(PortfolioRiskPolicy(
                "demo_portfolio", "USD", D(100), D(5000), D(100), D(90), D(90), 25))
            paper.configure_account(AccountRiskPolicy(
                "demo_account", "demo_portfolio", "USD", D(1000), D("0.05"),
                D("0.20"), D("0.20"), D(2), D("0.90"), D(3), D(1),
                D("0.01"), D("0.002"), D("0.003"), 25, True))
            paper.register_instrument(portfolio_id="demo_portfolio",
                                      instrument=binding.instrument, group_id="CRYPTO")
            integration.authorize_paper(instance.instance_id, paper=paper,
                expected_panel_revision=instance.revision, now=T0, operator_ack=True)
            job_id = supervisor.schedule(instance.instance_id, binding.binding_id,
                expected_panel_revision=instance.revision, candles=(first, second),
                source_ref="stage19_synthetic", due_at=second.close_at,
                operator_ack=True)
            executor = JobEffectIntentExecutor(
                supervisor=supervisor, ledger=effects, integration=integration,
                paper=paper, signals=signals, quantity=D(1),
                dry_run_channel_id=-10019)
            result = supervisor.run_due(executor, now=second.close_at, operator_ack=True)
            assert len(result) == 1 and result[0]["status"] == "DONE"
            assert len(effects.intents(job_id=job_id)) == 3
            assert {r["kind"] for r in effects.intents()} == {
                "PAPER_RESERVE", "PAPER_PLAN", "DRY_SIGNAL"}
            assert all(r["state"] == "RECORDED" for r in effects.intents())
            assert supervisor.run_due(executor, now=second.close_at,
                                      operator_ack=True) == ()
        # The Stage-8/10 SQLite engines may use the OS creation umask. For
        # high-assurance forensic inspection, the operator supplies private
        # 0600 evidence files after stopping all writers.
        for evidence_file in (effect_path, runtime_path, paper_path, signals_path):
            evidence_file.chmod(0o600)
        report = evaluate_effect_evidence(EffectEvidencePaths(
            effect_path, runtime_path, paper_path, signals_path))
        assert report.blocking_effects == 0, report.as_dict()
        assert report.exact_local_effects == 3
        assert report.auto_retry_authorized is False
        assert report.telegram_send_authorized is False
        assert report.broker_orders_authorized is False
        assert report.verdict == "OFFLINE_EVIDENCE_ONLY_NOT_RELEASE_AUTHORIZATION"
