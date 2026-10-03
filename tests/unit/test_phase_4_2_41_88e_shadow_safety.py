from __future__ import annotations
import json,hashlib
from pathlib import Path
from research_layer.phase_4_2_41_88e.contract import *
from research_layer.phase_4_2_41_88e.statistics import evaluate
ROOT=Path('/opt/crypto-signal-telegram-bot')
def test_statistics_contract_unchanged_and_module_hash_same_as_88d():
 assert_contract(); assert hashlib.sha256((ROOT/'research_layer/phase_4_2_41_88e/statistics.py').read_bytes()).hexdigest()==hashlib.sha256((ROOT/'research_layer/phase_4_2_41_88d/statistics.py').read_bytes()).hexdigest()
def test_no_production_writers_or_publication_imports():
 src=(ROOT/'research_layer/phase_4_2_41_88e/live_shadow.py').read_text().lower(); forbidden=('from app.db','import app.db','app.modules.signal_intelligence','app.modules.signal_gate','app.modules.operations.telegram','app.modules.signals.repository','app.modules.signals.service'); assert not any(x in src for x in forbidden); assert '.send_message(' not in src and '.publish(' not in src
def test_shadow_uses_manifest_start_cutover_and_minute_aligned_fetch():
 src=(ROOT/'research_layer/phase_4_2_41_88e/live_shadow.py').read_text(); assert 'cutover_at=self.start' in src and 'one_minute_query_start(floor)' in src and 'floor-timedelta(seconds=1)' not in src
def test_version_mismatch_remains_fail_closed():
 c={'candidate_identity':'c','candidate_timestamp':'2026-01-03T00:00:00+00:00','symbol':'BTCUSDT','timeframe':'15m','direction':'LONG','setup_type':'FAILED_BREAKOUT_LONG','engine_version':ENGINE,'rule_set_version':RULES,'configuration_version':'cfg','exchange':'binance','market_type':'futures','management_version':MGMT,'statistics_contract_version':STAT}; hist=[]
 for i in range(20): hist.append({**{k:c[k] for k in COHORT_FIELDS},'candidate_identity':f'h{i}','candidate_timestamp':'2026-01-01T00:00:00+00:00','terminal_timestamp':'2026-01-02T00:00:00+00:00','symbol':'BTCUSDT','timeframe':'15m','direction':'LONG','setup_type':'FAILED_BREAKOUT_LONG','realized_r':'1'})
 hist[0]['statistics_contract_version']='WRONG'; assert evaluate(c,hist)['compatible_n']==19 and evaluate(c,hist)['status']=='INSUFFICIENT_HISTORY'
def test_r1_offline_regression_exact():
 d=json.loads((ROOT/'artifacts/phase_4_2_41_88d_r1_offline_regression.json').read_text()); assert d['sep11_development']['status']=={'INSUFFICIENT_HISTORY':57,'UNFAVORABLE':29}; assert d['phase88b']['status']=={'INSUFFICIENT_HISTORY':51,'UNFAVORABLE':11}; assert d['phase88c']['status']=={'FAVORABLE':1,'INSUFFICIENT_HISTORY':58,'UNFAVORABLE':76}; f=d['phase88c_first_favorable']; assert f['available_compatible_closed_count']==21 and abs(f['sample_mean_r']-.11130284660429764)<1e-15 and abs(f['bootstrap_t_lower95']-.013522355209727596)<1e-15
def test_r1_section_c_parity_100_percent():
 d=json.loads((ROOT/'artifacts/phase_4_2_41_88d_r1_section_c_parity.json').read_text()); assert d['summary']=={'exact14':[14,14],'holdout67':[67,67],'bootstrap86':[86,86]}; assert all(x['pass'] for k in ('exact14','holdout67','bootstrap86') for x in d[k])
def test_original_88d_source_still_matches_manifest():
 m=json.loads((ROOT/'artifacts/phase_4_2_41_88d_forward_shadow_manifest.json').read_text()); assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in m['source_hashes'].items())
def test_operational_seal_classification():
 d=json.loads((ROOT/'artifacts/phase_4_2_41_88d_operational_seal.json').read_text()); assert d['experiment_status']=='OPERATIONALLY_INTERRUPTED_NOT_ECONOMICALLY_USABLE' and d['statistical_contract_failure'] is False and d['economic_analysis_performed'] is False and d['replacement_initialization_eligible'] is False
