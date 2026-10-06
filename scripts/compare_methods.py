from pathlib import Path
import json
import hashlib
import pandas as pd
import numpy as np
import argparse
ap=argparse.ArgumentParser()
ap.add_argument('--source-dir',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args()
run_metadata=json.loads((args.source_dir/'run_metadata.json').read_text(encoding='utf-8-sig'))
out=args.output;out.mkdir(parents=True,exist_ok=True);work=out/'support';work.mkdir(exist_ok=True)
source=args.source_dir/'daily_predictions.csv'
d=pd.read_csv(source)
d=d.loc[d.window_type.eq('effective') & d.baseline_mode.eq('fixed_pre_event')].copy()
keys=['event_id','window_start','window_end','region','industry','age']
dailykeys=keys+['date']
if d.duplicated(dailykeys+['model_id','missing_policy']).any():raise ValueError('duplicate source')
if run_metadata.get('daily_rows') != len(pd.read_csv(source)):
 raise ValueError('run metadata row count differs')
r=pd.read_json(args.source_dir/'event_shortfall.json',convert_dates=False)
r=r.loc[r.window_type.eq('effective') & r.baseline_mode.eq('fixed_pre_event')]
def totals(g):
 q=g.loc[g.amount.notna() & g.prediction.notna()]
 expected=q.prediction.sum() if len(q) else np.nan
 net=(q.prediction-q.amount).sum() if len(q) else np.nan
 gross=(q.prediction-q.amount).clip(lower=0).sum() if len(q) else np.nan
 return dict(paired_days=len(q),expected=expected,net=net,gross=gross,rate=net/expected if expected>0 else np.nan)
lookup=r.set_index(keys+['model_id','missing_policy'])
if not lookup.index.is_unique:raise ValueError('duplicate summary keys')
# Independently reconstruct every effective summary from the daily handoff.
for key,g in d.groupby(keys+['model_id','missing_policy']):
 z=totals(g)
 if key not in lookup.index:raise ValueError('summary key')
 t=lookup.loc[key]
 for left,right in [('paired_days','paired_days'),('expected','expected_total_paired'),('net','net_shortfall_paired'),('gross','gross_shortfall_paired')]:
  if not np.isclose(z[left],t[right],equal_nan=True,rtol=1e-9,atol=1e-5):raise ValueError('summary mismatch '+left)
comparisons=[('mean_vs_median',('weekday_mean','exclude_missing'),('weekday_median','exclude_missing')),
 ('exclude_vs_zero_mean',('weekday_mean','exclude_missing'),('weekday_mean','zero_fill_sensitivity')),
 ('exclude_vs_zero_median',('weekday_median','exclude_missing'),('weekday_median','zero_fill_sensitivity'))]
details=[]
for name,left,right in comparisons:
 a=d.loc[d.model_id.eq(left[0]) & d.missing_policy.eq(left[1])]
 b=d.loc[d.model_id.eq(right[0]) & d.missing_policy.eq(right[1])]
 m=a.merge(b,on=dailykeys,suffixes=('_a','_b'),validate='one_to_one')
 if len(m)!=len(a) or len(a)!=len(b):raise ValueError('comparison grid differs')
 for key,g in m.groupby(keys):
  pa=g.amount_a.notna() & g.prediction_a.notna();pb=g.amount_b.notna() & g.prediction_b.notna();common=pa & pb
  if (pa & ~pb).any():raise ValueError('unexpected lost support')
  if not np.allclose(g.loc[common,'amount_a'],g.loc[common,'amount_b']):raise ValueError('common actual differs')
  def side(s,mask):return totals(g.loc[mask,[f'amount_{s}',f'prediction_{s}']].rename(columns={f'amount_{s}':'amount',f'prediction_{s}':'prediction'}))
  ac,bc,af,bf=side('a',common),side('b',common),side('a',pa),side('b',pb)
  added=side('b',pb & ~pa)
  row=dict(zip(keys,key),comparison=name,window_days=len(g),common_days=int(common.sum()),left_days=int(pa.sum()),right_days=int(pb.sum()),added_days=int((pb & ~pa).sum()),holiday_days=int(g.is_holiday_a.sum()),left_common_net=ac['net'],right_common_net=bc['net'],left_common_gross=ac['gross'],right_common_gross=bc['gross'],left_common_rate=ac['rate'],right_common_rate=bc['rate'],common_rate_difference_pp=(bc['rate']-ac['rate'])*100,common_net_difference=bc['net']-ac['net'],left_available_net=af['net'],right_available_net=bf['net'],added_net=added['net'],left_expected=ac['expected'],right_expected=bc['expected'])
  row['sign_reversed']=bool(ac['net']*bc['net']<0) if common.any() else None
  row['comparison_status']='no_common_days' if not common.any() else ('complete_nonholiday_common' if common.sum()==len(g)-g.is_holiday_a.sum() else 'partial_common')
  if common.any() and not np.isclose(bf['net']-af['net'],row['common_net_difference']+(added['net'] if row['added_days'] else 0),rtol=1e-9,atol=1e-5):raise ValueError('support decomposition')
  if name=='mean_vs_median' and (row['added_days'] or row['left_days']!=row['right_days']):raise ValueError('method support differs')
  details.append(row)
detail=pd.DataFrame(details)
summary=[]
for (event,comparison),g in detail.groupby(['event_id','comparison']):
 valid=g.loc[g.common_rate_difference_pp.notna()]
 summary.append(dict(event_id=event,comparison=comparison,total_groups=len(g),evaluable_groups=len(valid),partial_groups=int(g.comparison_status.eq('partial_common').sum()),no_common_groups=int(g.common_days.eq(0).sum()),sign_reversed_groups=int(valid.sign_reversed.eq(True).sum()),median_abs_rate_difference_pp=valid.common_rate_difference_pp.abs().median(),max_abs_rate_difference_pp=valid.common_rate_difference_pp.abs().max(),groups_with_added_days=int(g.added_days.gt(0).sum())))
s=pd.DataFrame(summary)
detail.to_csv(out/'method_comparison_detail.csv',index=False,encoding='utf-8-sig',na_rep='')
s.to_csv(work/'summary.csv',index=False,encoding='utf-8-sig',na_rep='')
metadata={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'calendar':run_metadata.get('calendar_provenance','unknown_review_required'),'summary_rows_verified':len(r),'detail_rows':len(detail),'comparisons':len(comparisons),'role':'paired common-date sensitivity; not full-window priority input'}
(work/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
print(s.to_string(index=False));print('Verified summary rows',len(r),'detail rows',len(detail))
