from __future__ import annotations
import json, hashlib, math
from datetime import datetime
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
CAND=ROOT/'tests/fixtures/phase_4_2_41_86_bootstrap_candidates_sep11.json'
CLOSED=ROOT/'tests/fixtures/phase_4_2_41_86_bootstrap_closed_cases_sep11.json'
OLD=ROOT/'artifacts/phase_4_2_41_86_walk_forward.json'
CONTRACT=ROOT/'artifacts/phase_4_2_41_88a_statistics_contract_v1.json'
OUT=ROOT/'artifacts/phase_4_2_41_88a_walkforward_compare.json'
cv=json.loads(CONTRACT.read_text()); version=cv['statistics_contract_version']
candidates=json.loads(CAND.read_text())['candidates']; cases=json.loads(CLOSED.read_text())['cases']; olddoc=json.loads(OLD.read_text())
oldrows=olddoc['current_repository_event_semantics']

def dt(s):return datetime.fromisoformat(s)
def family(s):
 v=str(s or 'UNKNOWN').upper()
 for suf in ('_LONG','_SHORT'):
  if v.endswith(suf):v=v[:-len(suf)]
 for p in ('BREAKOUT_PULLBACK','FAILED_BREAKOUT','FAILED_FAILURE','BREAKOUT','PARABOLIC_WEDGE','MICRO_WEDGE','WEDGE','DOUBLE_TOP','DOUBLE_BOTTOM','MAJOR_TREND_REVERSAL','FINAL_FLAG','CLIMACTIC_REVERSAL','TRADING_RANGE_FADE','H1','H2','H3','H4','L1','L2','L3','L4'):
  if v.startswith(p):return p
 return v

def seed_for(scope, ids):
 material='|'.join([version,scope,*ids]).encode(); return int.from_bytes(hashlib.sha256(material).digest()[:8],'big')
def boott95(values,scope,ids,B=100000):
 x=np.asarray(values,float); n=len(x); theta=float(x.mean())
 if n<2:return None
 se=float(x.std(ddof=1)/math.sqrt(n))
 if not math.isfinite(se) or se<=1e-15:return None
 rng=np.random.default_rng(seed_for(scope,ids)); ts=[]
 for s in range(0,B,2000):
  b=min(2000,B-s); y=x[rng.integers(0,n,size=(b,n))]; m=y.mean(1); sy=y.std(1,ddof=1)/math.sqrt(n); ok=sy>1e-15
  ts.extend(((m[ok]-theta)/sy[ok]).tolist())
 ts=np.asarray(ts)
 if len(ts)<int(.95*B):return None
 q025,q975=np.quantile(ts,[.025,.975]); lo=theta-float(q975)*se;hi=theta-float(q025)*se
 return {'mean_r':theta,'median_r':float(np.median(x)),'std_r':float(x.std(ddof=1)),'ci95':[lo,hi],'lcb95':lo,'positive_fraction':float((x>0).mean()),'zero_fraction':float((x==0).mean()),'n':n}

def select_pool(c, prior):
 setup=c['setup_type'];tf=c['timeframe'];direction=c['direction'];fam=family(setup)
 levels=[
  ('SETUP_TIMEFRAME',[x for x in prior if x['setup_type']==setup and x['timeframe']==tf]),
  ('SETUP_ALL_TIMEFRAMES',[x for x in prior if x['setup_type']==setup]),
  ('FAMILY_TIMEFRAME',[x for x in prior if family(x['setup_type'])==fam and x['timeframe']==tf]),
  ('FAMILY_ALL_TIMEFRAMES',[x for x in prior if family(x['setup_type'])==fam]),
  ('DIRECTION_TIMEFRAME',[x for x in prior if x['direction']==direction and x['timeframe']==tf]),
  ('DIRECTION_ALL_TIMEFRAMES',[x for x in prior if x['direction']==direction]),
 ]
 for scope,pool in levels:
  if len(pool)>=20:return scope,pool
 return levels[-1][0],levels[-1][1]
rows=[]
for i,c in enumerate(candidates,1):
 ts=dt(c['candidate_timestamp'])
 prior=sorted([x for x in cases if dt(x['terminal_timestamp'])<ts],key=lambda x:(x['terminal_timestamp'],x['candidate_identity']))
 scope,pool=select_pool(c,prior)
 if len(pool)<20:
  row={'candidate_no':i,'identity':c['identity_sha256'],'timestamp':c['candidate_timestamp'],'scope':scope,'compatible_case_count':len(pool),'status':'INSUFFICIENT_HISTORY','favorable':False}
 else:
  vals=[float(x['realized_r']) for x in pool];ids=[x['candidate_identity'] for x in pool]; stats=boott95(vals,scope,ids)
  if stats is None:
   row={'candidate_no':i,'identity':c['identity_sha256'],'timestamp':c['candidate_timestamp'],'scope':scope,'compatible_case_count':len(pool),'status':'INSUFFICIENT_HISTORY_ESTIMATOR_INVALID','favorable':False}
  else:
   fav=stats['lcb95']>0
   row={'candidate_no':i,'identity':c['identity_sha256'],'timestamp':c['candidate_timestamp'],'scope':scope,'compatible_case_count':len(pool),'status':'FAVORABLE' if fav else 'UNFAVORABLE','favorable':fav,**stats}
 rows.append(row)
# old comparison keyed candidate no
old_by={x['candidate_no']:x for x in oldrows}
compare=[]
for r in rows:
 o=old_by[r['candidate_no']]
 compare.append({'candidate_no':r['candidate_no'],'new_status':r['status'],'new_favorable':r['favorable'],'new_scope':r['scope'],'new_n':r['compatible_case_count'],'old_calibrated':o['calibrated'],'old_favorable':o['trader_equation_favorable'],'old_scope':o['scope'],'old_probability':o['probability'],'old_ev_r':o['expected_value_r']})
summary={
 'new_favorable':sum(x['favorable'] for x in rows),
 'new_unfavorable':sum(x['status']=='UNFAVORABLE' for x in rows),
 'new_insufficient':sum(x['status'].startswith('INSUFFICIENT') for x in rows),
 'legacy_calibrated':sum(x['calibrated'] for x in oldrows),
 'legacy_favorable':sum(x['trader_equation_favorable'] for x in oldrows),
 'decision_disagreements':sum((x['new_favorable'] != x['old_favorable']) for x in compare),
 'calibration_availability_disagreements':sum(((not x['new_status'].startswith('INSUFFICIENT')) != x['old_calibrated']) for x in compare),
}
out={'phase':'4.2.41.88A','statistics_contract_version':version,'rows':rows,'comparison':compare,'summary':summary}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print('SUMMARY',json.dumps(summary,sort_keys=True))
for x in rows:
 if not x['status'].startswith('INSUFFICIENT'):
  print(x['candidate_no'],x['timestamp'],x['scope'],'n',x['compatible_case_count'],'mean',round(x['mean_r'],6),'LCB',round(x['lcb95'],6),x['status'])
print('OUT',OUT,'SHA256',hashlib.sha256(OUT.read_bytes()).hexdigest())
