"""Installed-wheel Stage-17 supervisor acceptance using only synthetic candles."""
from __future__ import annotations

import argparse
import json
import os
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
from .offline_runtime_supervisor_v1 import (OfflineRuntimeSupervisor,
                                             Stage16ReplayExecutor)
from .offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from .runtime_supervisor_health_v1 import inspect_queue
from .trading_control_center_v1 import CoreListing, OfflineTradingControlCenter


class SmokeRefused(ValueError):
    """Explicitly gated demonstration only."""


def run_offline_smoke(folder: Path) -> dict:
    if os.environ.get('MMT_NONPRODUCTION') != '1' or os.environ.get('MMT_PRODUCTION') == '1':
        raise SmokeRefused('NONPRODUCTION_REQUIRED')
    folder = Path(folder)
    if (not folder.is_absolute() or folder.exists() or folder.is_symlink()
            or not folder.parent.is_dir() or folder.parent.is_symlink()
            or (stat.S_IMODE(folder.parent.stat().st_mode) & 0o002)):
        raise SmokeRefused('NEW_PRIVATE_STATE_DIRECTORY_REQUIRED')
    folder.mkdir(mode=0o700)
    initial=datetime(2026,10,12,10,tzinfo=UTC)
    delta=timedelta(minutes=15)
    bars=(ClosedCandle(initial,initial+delta,D(100),D(102),D(98),D(100),D(10)),
          ClosedCandle(initial+delta,initial+2*delta,D(100),D(108),D(99),D(106),D(10)))
    catalog=ResearchInstrumentCatalog(max_age_seconds=3600)
    origin=MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
    instrument=InstrumentMetadata('synthetic_provider',Market.CRYPTO,'ABCUSD','UTC','USD',
                                  D('0.01'),origin,ListingStatus.OPEN,initial,
                                  'SYNTHETIC_FIXTURE')
    catalog.replace(ProviderSnapshot('synthetic_provider',origin,initial,
                                     (instrument,), 'a'*64))
    core=OfflineContractFixture()
    with OfflineTradingControlCenter(folder/'control.sqlite',admin_ids={123},
          enabled=True,catalog=catalog,listings=(CoreListing(core.manifest.core_id,
          'Public Demonstration Core',core.manifest.core_version,
          manifest=core.manifest),)) as panel:
        state=panel.create_instance(123,core_id=core.manifest.core_id,
                                    instance_id='demo_instance',account_id='demo_account',
                                    portfolio_id='demo_portfolio')
        state=panel.add_binding(123,state.instance_id,provider='synthetic_provider',
                                symbol='ABCUSD',timeframe='15m',now=initial,
                                expected_revision=state.revision)
        state=panel.set_request(123,state.instance_id,field='analysis',
                                requested=True,expected_revision=state.revision)
        state=panel.set_request(123,state.instance_id,field='signals',
                                requested=True,expected_revision=state.revision)
        (binding,)=panel.preview_bindings(123,state.instance_id,now=initial)
        executor=OfflinePanelPaperIntegration(panel,actor_id=123,core=core,operator_ack=True)
        with OfflineSignalLifecycle(folder/'signals.sqlite',enabled=True) as signals:
            path=folder/'supervisor.sqlite'
            with OfflineRuntimeSupervisor(path,panel=panel,actor_id=123,
                                          enabled=True) as supervisor:
                job_id=supervisor.schedule(state.instance_id,binding.binding_id,
                    expected_panel_revision=state.revision,candles=bars,
                    source_ref='synthetic_smoke',due_at=bars[-1].close_at,operator_ack=True)
                results=supervisor.run_due(Stage16ReplayExecutor(
                    executor,signals=signals,dry_run_channel_id=-10017),
                    now=bars[-1].close_at,operator_ack=True)
                if len(results)!=1 or results[0]['status']!='DONE':
                    raise SmokeRefused('EXPECTED_ONE_COMPLETED_REPLAY')
            with OfflineRuntimeSupervisor(path,panel=panel,actor_id=123,
                                          enabled=True) as second:
                assert second.schedule(state.instance_id,binding.binding_id,
                    expected_panel_revision=state.revision,candles=bars,
                    source_ref='synthetic_smoke',due_at=bars[-1].close_at,
                    operator_ack=True)==job_id
                if (second.run_due(lambda _: {},now=bars[-1].close_at,
                                   operator_ack=True) or
                        second.health()['counts']['DONE']!=1):
                    raise SmokeRefused('DUPLICATE_AFTER_RESTART')
            if signals._db.execute('SELECT COUNT(*) FROM offline_signal_states').fetchone()[0]!=1:
                raise SmokeRefused('EXPECTED_ONE_NO_SEND_SIGNAL')
        health=inspect_queue(path)
    return {'status':'STAGE17_INSTALLED_SYNTHETIC_SUPERVISOR_PASS',
            'completed_jobs':health['counts']['DONE'],
            'signal_journal_entries':1,'restart_idempotent':True,
            'telegram_sent':False,'broker_order_sent':False,
            'live_trading_enabled':False,'public_release_authorized':False}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--ack-synthetic-offline',action='store_true')
    args=parser.parse_args(argv)
    try:
        if not args.ack_synthetic_offline:
            raise SmokeRefused('OPERATOR_ACK_REQUIRED')
        result=run_offline_smoke(args.state_dir)
    except (ValueError,OSError,RuntimeError) as exc:
        print('STAGE17_SMOKE_REFUSED:'+type(exc).__name__,file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
