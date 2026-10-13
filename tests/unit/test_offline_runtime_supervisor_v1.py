"""Durable Stage-17 operator scheduler, all inputs synthetic; no sockets."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import ClosedCandle
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin, ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from naseri_markets.offline_runtime_supervisor_v1 import (
    OfflineRuntimeSupervisor, Stage16ReplayExecutor, SupervisorRefused,
)
from naseri_markets.trading_control_center_v1 import (
    CoreListing, OfflineTradingControlCenter,
)

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
CORE = OfflineContractFixture()


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def panel_fixture(tmp_path, *, timeframe="15m", signals=False, paper=False):
    catalog = ResearchInstrumentCatalog(max_age_seconds=86400)
    origin = MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    metadata = InstrumentMetadata("synthetic_provider", Market.CRYPTO, "ABCUSD", "UTC",
                                  "USD", D("0.01"), origin, ListingStatus.OPEN,
                                  T0, "SYNTHETIC_FIXTURE")
    catalog.replace(ProviderSnapshot("synthetic_provider", origin, T0,
                                     (metadata,), "a" * 64))
    control = OfflineTradingControlCenter(
        tmp_path / "panel.sqlite", admin_ids={123}, enabled=True, catalog=catalog,
        listings=(CoreListing(CORE.manifest.core_id, "Public Demonstration Core",
                              CORE.manifest.core_version, manifest=CORE.manifest),))
    instance = control.create_instance(123, core_id=CORE.manifest.core_id,
        instance_id="demo_instance", account_id="demo_account",
        portfolio_id="demo_portfolio")
    instance = control.add_binding(123, instance.instance_id,
        provider="synthetic_provider", symbol="ABCUSD", timeframe=timeframe,
        now=T0, expected_revision=instance.revision)
    for mode, enabled in (("analysis", True), ("signals", signals), ("paper", paper)):
        instance = control.set_request(123, instance.instance_id, field=mode,
                                       requested=enabled, expected_revision=instance.revision)
    binding, = control.preview_bindings(123, instance.instance_id, now=T0)
    return control, binding, instance


def bars(minutes=15):
    a = ClosedCandle(T0, T0+timedelta(minutes=minutes),
                     D(100), D(102), D(98), D(100), D(10))
    b = ClosedCandle(a.close_at, a.close_at+timedelta(minutes=minutes),
                     D(100), D(108), D(99), D(106), D(10))
    return (a, b)


def scheduled(scheduler, binding, instance, *, candles=None, source="synthetic_fixture"):
    cs = candles if candles is not None else bars()
    return scheduler.schedule(instance.instance_id, binding.binding_id,
        expected_panel_revision=instance.revision, candles=cs,
        source_ref=source, due_at=cs[-1].close_at, operator_ack=True)


def receipt(job):
    return {"status": "OFFLINE_JOURNALS_UPDATED", "decision_count": 1,
            "paper_order_ids": [], "signal_keys": [],
            "broker_order_sent": False, "telegram_sent": False,
            "live_trading_enabled": False}


def test_lifecycle_and_exact_idempotency_across_restart(tmp_path):
    control, binding, inst = panel_fixture(tmp_path)
    path=tmp_path / "runtime.sqlite"
    with OfflineRuntimeSupervisor(path, panel=control, actor_id=123, enabled=True) as run:
        identity = scheduled(run, binding, inst)
        assert scheduled(run, binding, inst)==identity
        assert run.health()["counts"]["PENDING"] == 1
        assert run.run_due(receipt, now=T0, operator_ack=True)==()
        got=run.run_due(receipt, now=bars()[-1].close_at,operator_ack=True)
        assert len(got)==1 and got[0]["status"]=="DONE"
        assert run.run_due(receipt, now=bars()[-1].close_at,operator_ack=True)==()
    with OfflineRuntimeSupervisor(path, panel=control, actor_id=123,enabled=True) as again:
        assert scheduled(again,binding,inst)==identity
        assert again.health()["counts"]=={"PENDING":0,"CLAIMED":0,"DONE":1,"QUARANTINED":0}
        assert again.jobs()[0]["attempt"]==1
    control.close()


def test_two_instances_do_not_double_claim(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    path=tmp_path/'runtime.sqlite'
    with OfflineRuntimeSupervisor(path,panel=control,actor_id=123,enabled=True) as first, \
         OfflineRuntimeSupervisor(path,panel=control,actor_id=123,enabled=True) as second:
        scheduled(first,binding,inst)
        counter=[]
        def nested(job):
            counter.append(job.job_id)
            assert second.run_due(receipt,now=bars()[-1].close_at,
                                  operator_ack=True)==()
            return receipt(job)
        assert first.run_due(nested,now=bars()[-1].close_at,operator_ack=True)[0]["status"]=="DONE"
        assert len(counter)==1
    control.close()


def test_claim_crash_must_never_be_replayed(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    path=tmp_path/'runtime.sqlite'
    class KillWorker(BaseException):
        pass
    with OfflineRuntimeSupervisor(path,panel=control,actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
        def die(_):
            raise KillWorker()
        with pytest.raises(KillWorker):
            s.run_due(die,now=bars()[-1].close_at,operator_ack=True)
        assert s.health()["counts"]["CLAIMED"]==1
    with OfflineRuntimeSupervisor(path,panel=control,actor_id=123,enabled=True) as s:
        assert s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)==()
        with pytest.raises(SupervisorRefused,match="STOP_ALL_WORKERS"):
            s.quarantine_inflight(operator_ack=True)
        assert s.quarantine_inflight(operator_ack=True,all_workers_stopped=True)==1
        assert s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)==()
        assert s.health()["manual_reconciliation_required"]
        assert s.jobs()[0]["error_code"]=="CRASH_RECONCILIATION_REQUIRED"
    control.close()


def test_callback_failure_quarantines_without_retry(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
        def fails(_):
            raise OSError("sensitive.example")
        out=s.run_due(fails,now=bars()[-1].close_at,operator_ack=True)
        assert out[0]["status"]=="QUARANTINED"
        assert "sensitive" not in str(s.jobs())
        assert s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)==()
    control.close()


def test_live_claim_and_forged_receipt_are_refused(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
        out=s.run_due(lambda _: {"status":"OFFLINE_JOURNALS_UPDATED",
                                  "telegram_sent":True,"broker_order_sent":False},
                      now=bars()[-1].close_at,operator_ack=True)
        assert out[0]["status"]=="QUARANTINED"
    control.close()


def test_panel_revision_changes_block_stale_queue(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
        control.set_request(123,inst.instance_id,field="analysis",requested=False,
                            expected_revision=inst.revision)
        out=s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)
        assert out[0]["status"]=="QUARANTINED"
    control.close()


def test_schedule_refuses_unapproved_binding_and_modes(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        with pytest.raises(SupervisorRefused,match="BINDING_NOT_APPROVED"):
            scheduled(s, type("Other",(),{"binding_id":"bogus"})(), inst)
        with pytest.raises(SupervisorRefused,match="CANNOT_SCHEDULE_OPEN_CANDLE"):
            s.schedule(inst.instance_id,binding.binding_id,
                expected_panel_revision=inst.revision,candles=bars(),source_ref="fixture",
                due_at=T0,operator_ack=True)
    control.close()


def test_exact_timeframe_matters(tmp_path):
    control,binding,inst=panel_fixture(tmp_path,timeframe="5m")
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        job=scheduled(s,binding,inst,candles=bars(5))
        assert job.startswith("job17_")
        assert s.run_due(receipt,now=bars(5)[-1].close_at,operator_ack=True)[0]["status"]=="DONE"
    control.close()


def test_no_authorization_without_env(tmp_path,monkeypatch):
    control,_,_=panel_fixture(tmp_path)
    monkeypatch.delenv('MMT_NONPRODUCTION')
    with pytest.raises(SupervisorRefused,match="NONPRODUCTION_OPERATOR"):
        OfflineRuntimeSupervisor(tmp_path/'blocked.sqlite',panel=control,actor_id=123,enabled=True)
    assert not (tmp_path/'blocked.sqlite').exists()
    control.close()


def test_bad_state_rejected_without_writing(tmp_path):
    control,_,_=panel_fixture(tmp_path)
    wrong=tmp_path/'legacy.sqlite'
    conn=sqlite3.connect(wrong)
    conn.execute('CREATE TABLE other_important_data(v INTEGER)')
    conn.close()
    wrong.chmod(0o600)
    with pytest.raises(SupervisorRefused,match="UNKNOWN_DATABASE"):
        OfflineRuntimeSupervisor(wrong,panel=control,actor_id=123,enabled=True)
    assert sqlite3.connect(wrong).execute('SELECT count(*) FROM other_important_data').fetchone()[0]==0
    control.close()


def test_symlink_refused(tmp_path):
    control,_,_=panel_fixture(tmp_path)
    target=tmp_path/'target.sqlite'
    target.touch(mode=0o600)
    (tmp_path/'symlink.sqlite').symlink_to(target)
    with pytest.raises(SupervisorRefused,match="PRIVATE_DEDICATED"):
        OfflineRuntimeSupervisor(tmp_path/'symlink.sqlite',panel=control,actor_id=123,enabled=True)
    control.close()


def test_inconsistent_input_integrity_quarantined(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    path=tmp_path/'runtime.sqlite'
    with OfflineRuntimeSupervisor(path,panel=control,actor_id=123,enabled=True) as s:
        job=scheduled(s,binding,inst)
        s.db.execute("UPDATE runtime17_jobs SET payload='{}' WHERE job_id=?",(job,))
        assert s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)[0]["status"]=="QUARANTINED"
    control.close()


def test_operator_ack_and_limit_required(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        with pytest.raises(SupervisorRefused,match="EXPLICIT_SCHEDULE"):
            s.schedule(inst.instance_id,binding.binding_id,expected_panel_revision=inst.revision,
                       candles=bars(),source_ref='fixture',due_at=bars()[-1].close_at)
        with pytest.raises(SupervisorRefused,match="EXPLICIT_BOUNDED"):
            s.run_due(receipt,now=bars()[-1].close_at,limit=100,operator_ack=True)
    control.close()


def test_exact_retry_same_id_never_changes_schedule_time(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        job=scheduled(s,binding,inst)
        original=s.jobs()[0]['due_at']
        assert s.schedule(inst.instance_id,binding.binding_id,
                          expected_panel_revision=inst.revision,candles=bars(),
                          source_ref='synthetic_fixture',due_at=bars()[-1].close_at+timedelta(hours=2),
                          operator_ack=True)==job
        assert s.jobs()[0]['due_at']==original
    control.close()


def test_stage16_real_replay_analysis_mode(tmp_path):
    # Source-tree and CI use Stage 16's existing adapter with a known reviewed
    # public example, no PAPER ledger or Telegram channel required.
    from naseri_markets.offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
    control,binding,inst=panel_fixture(tmp_path)
    host=OfflinePanelPaperIntegration(control,actor_id=123,core=CORE,operator_ack=True)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
        result=s.run_due(Stage16ReplayExecutor(host),now=bars()[-1].close_at,
                         operator_ack=True)
        assert result[0]['status']=='DONE', s.jobs()
    control.close()


def test_stage16_actual_signal_journal_and_restart(tmp_path):
    from naseri_markets.offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
    from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
    control,binding,inst=panel_fixture(tmp_path,signals=True)
    host=OfflinePanelPaperIntegration(control,actor_id=123,core=CORE,operator_ack=True)
    runtime_path=tmp_path/'runtime.sqlite'
    with OfflineSignalLifecycle(tmp_path/'signals.sqlite',enabled=True) as signal:
        with OfflineRuntimeSupervisor(runtime_path,panel=control,actor_id=123,enabled=True) as s:
            job=scheduled(s,binding,inst)
            out=s.run_due(Stage16ReplayExecutor(host,signals=signal,dry_run_channel_id=-10017),
                          now=bars()[-1].close_at,operator_ack=True)
            assert out[0]['status']=='DONE',s.jobs()
        assert signal._db.execute('SELECT COUNT(*) FROM offline_signal_states').fetchone()[0]==1
    with OfflineRuntimeSupervisor(runtime_path,panel=control,actor_id=123,enabled=True) as s:
        assert scheduled(s,binding,inst)==job
        assert s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)==()
        assert s.health()['counts']['DONE']==1
    control.close()


def test_stage16_actual_paper_and_signal_on_full_repo(tmp_path):
    pytest.importorskip('naseri_markets.execution_position_core_v1')
    from naseri_markets.offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
    from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
    from naseri_markets.paper_order_lifecycle_v1 import OfflinePaperPositionLifecycle
    from naseri_markets.risk_portfolio_contract_v1 import PortfolioRiskPolicy,AccountRiskPolicy
    from naseri_markets.reliability_acceptance_v1 import LedgerPaths,evaluate_offline_reliability
    control,binding,inst=panel_fixture(tmp_path,signals=True,paper=True)
    inst=control.set_allocation(123,inst.instance_id,max_reserved=D('.10'),
            max_notional=D('.50'),max_order=D('.05'),max_orders=10,
            expected_revision=inst.revision)
    integration=OfflinePanelPaperIntegration(control,actor_id=123,core=CORE,operator_ack=True)
    runtime_path=tmp_path/'runtime.sqlite'
    paper_path=tmp_path/'paper.sqlite'
    signals_path=tmp_path/'signals.sqlite'
    with OfflinePaperPositionLifecycle(paper_path) as paper:
        paper.configure_portfolio(PortfolioRiskPolicy('demo_portfolio','USD',D(100),
                                D(5000),D(100),D(90),D(90),25))
        paper.configure_account(AccountRiskPolicy('demo_account','demo_portfolio','USD',
              D(1000),D('.05'),D('.20'),D('.20'),D(2),D('.90'),D(3),D(1),
              D('.01'),D('.002'),D('.003'),25,True))
        paper.register_instrument(portfolio_id='demo_portfolio',
                                  instrument=binding.instrument,group_id='CRYPTO')
        integration.authorize_paper(inst.instance_id,paper=paper,
                      expected_panel_revision=inst.revision,now=T0,operator_ack=True)
        with OfflineSignalLifecycle(signals_path,enabled=True) as signal, \
             OfflineRuntimeSupervisor(runtime_path,panel=control,actor_id=123,enabled=True) as s:
            scheduled(s,binding,inst)
            out=s.run_due(Stage16ReplayExecutor(integration,paper=paper,signals=signal,
                                                quantity=D(1),dry_run_channel_id=-10017),
                          now=bars()[-1].close_at,operator_ack=True)
            assert out[0]['status']=='DONE',s.jobs()
            assert s.health()['counts']['DONE']==1
            assert paper.status(inst.instance_id)['active_orders']==1
            assert signal._db.execute('SELECT COUNT(*) FROM offline_signal_states').fetchone()[0]==1
    with OfflineRuntimeSupervisor(runtime_path,panel=control,actor_id=123,enabled=True) as s:
        assert s.run_due(receipt,now=bars()[-1].close_at,operator_ack=True)==()
    control.close()
    gate=evaluate_offline_reliability(LedgerPaths(tmp_path/'panel.sqlite',paper_path,signals_path))
    assert gate.integrity_verdict=='PASS',gate.blockers
    assert gate.release_verdict=='BLOCKED_NONPRODUCTION_UNATTESTED'


def test_readonly_health_cli_and_no_state_mutation(tmp_path,monkeypatch,capsys):
    from naseri_markets.runtime_supervisor_health_v1 import inspect_queue,main
    control,binding,inst=panel_fixture(tmp_path)
    path=tmp_path/'runtime.sqlite'
    with OfflineRuntimeSupervisor(path,panel=control,actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
    before=path.read_bytes()
    result=inspect_queue(path)
    assert result['counts']['PENDING']==1
    assert result['product_release_authorized'] is False
    assert path.read_bytes()==before
    assert main(['--runtime-db',str(path)])==2
    assert main(['--runtime-db',str(path),'--ack-nonproduction-readonly'])==0
    assert 'READ_ONLY_OFFLINE_RUNTIME17' in capsys.readouterr().out
    control.close()


def test_unauthorized_admin_must_not_read_other_instances(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with pytest.raises(ValueError):
        OfflineRuntimeSupervisor(tmp_path/'noauth.sqlite',panel=control,
                                 actor_id=777,enabled=True)
    assert not (tmp_path/'noauth.sqlite').exists()
    control.close()


def test_background_polling_or_network_never_started(tmp_path):
    control,binding,inst=panel_fixture(tmp_path)
    with OfflineRuntimeSupervisor(tmp_path/'runtime.sqlite',panel=control,
                                  actor_id=123,enabled=True) as s:
        scheduled(s,binding,inst)
        data=s.health()
        assert data['background_poller'] is False
        assert data['broker_order_sent'] is data['telegram_sent'] is False
        assert data['counts']['PENDING']==1
    control.close()
