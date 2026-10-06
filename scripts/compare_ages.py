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
d=pd.read_csv(args.source_dir/'daily_predictions.csv')
if run_metadata.get('daily_rows') != len(d):raise ValueError('run metadata row count differs')
d=d.loc[d.window_type.eq('effective') & d.baseline_mode.eq('fixed_pre_event') & d.missing_policy.eq('exclude_missing') & d.model_id.eq('weekday_mean')].copy()
keys=['event_id','region','industry']
if d.duplicated(keys+['age','date']).any():raise ValueError('duplicate age dates')
details=[]; summaries=[]
for key,g in d.groupby(keys,sort=True):
 ages=g.age.unique(); n=len(ages)
 if not g.groupby('date').age.nunique().eq(n).all():raise ValueError('incomplete age grid')
 g['paired']=g.amount.notna() & g.prediction.notna()
 datecounts=g.groupby('date').paired.sum()
 common_dates=datecounts.index[datecounts.eq(n)]
 common=g.loc[g.date.isin(common_dates)]
 if len(common)!=len(common_dates)*n:raise ValueError('common support shape')
 industry_expected=common.prediction.sum() if len(common) else np.nan
 industry_actual=common.amount.sum() if len(common) else np.nan
 vals=[]
 for age,a in g.groupby('age',sort=True):
  p=a.loc[a.paired];c=a.loc[a.date.isin(common_dates)]
  ep=p.prediction.sum() if len(p) else np.nan;ap=p.amount.sum() if len(p) else np.nan
  ec=c.prediction.sum() if len(c) else np.nan;ac=c.amount.sum() if len(c) else np.nan
  net=(p.prediction-p.amount).sum() if len(p) else np.nan
  gross=(p.prediction-p.amount).clip(lower=0).sum() if len(p) else np.nan
  cn=(c.prediction-c.amount).sum() if len(c) else np.nan
  eligible=int((~a.is_holiday).sum());missing=int(a.actual_status.eq('missing_row_unknown').sum());insufficient=int(a.prediction_status.eq('insufficient_training').sum())
  row=dict(zip(keys,key),age=age,window_start=a.window_start.iloc[0],window_end=a.window_end.iloc[0],window_days=len(a),eligible_days=eligible,holiday_days=int(a.is_holiday.sum()),observed_days=int(a.amount.notna().sum()),missing_actual_days=missing,insufficient_training_days=insufficient,paired_days=len(p),eligible_coverage=len(p)/eligible if eligible else np.nan,complete_nonholiday=bool(eligible and len(p)==eligible),expected_paired=ep,actual_paired=ap,net_shortfall_paired=net,gross_shortfall_paired=gross,net_rate_paired=net/ep if ep>0 else np.nan,common_age_days=len(c),expected_common=ec,actual_common=ac,net_shortfall_common=cn,net_rate_common=cn/ec if ec>0 else np.nan,expected_share_common=ec/industry_expected if industry_expected>0 else np.nan,actual_share_common=ac/industry_actual if industry_actual>0 else np.nan,comparison_status='no_common_age_dates' if not len(c) else ('all_nonholiday_dates' if len(c)==eligible else 'partial_common_age_dates'))
  vals.append(row)
 t=pd.DataFrame(vals)
 valid=t.expected_common.gt(0)
 t['expected_scale_rank']=t.expected_common.where(valid).rank(method='min')
 t['lowest_expected_age']=False
 if n>1 and valid.sum()>1:t.loc[valid & t.expected_common.eq(t.loc[valid,'expected_common'].min()),'lowest_expected_age']=True
 # This is a within-industry descriptive minimum, not an approved small-sales cutoff.
 if len(common):
  if not np.isclose(t.expected_common.sum(),industry_expected) or not np.isclose(t.actual_common.sum(),industry_actual):raise ValueError('age aggregate reconciliation')
  if industry_expected>0 and not np.isclose(t.expected_share_common.sum(),1):raise ValueError('expected share')
 summaries.append(dict(zip(keys,key),age_groups=n,window_days=int(t.window_days.iloc[0]),eligible_days=int(t.eligible_days.iloc[0]),complete_age_groups=int(t.complete_nonholiday.sum()),incomplete_age_groups=int((~t.complete_nonholiday).sum()),no_paired_age_groups=int(t.paired_days.eq(0).sum()),common_age_days=len(common_dates),common_age_coverage=len(common_dates)/t.eligible_days.iloc[0],comparison_status=t.comparison_status.iloc[0],zero_expected_age_groups=int(t.expected_common.eq(0).sum()),lowest_expected_ages=', '.join(t.loc[t.lowest_expected_age,'age'])))
 details.extend(t.to_dict('records'))
detail=pd.DataFrame(details);summary=pd.DataFrame(summaries)
if len(detail)!=d.groupby(keys+['age']).ngroups or len(summary)!=d.groupby(keys).ngroups:raise ValueError('group counts differ')
detail.to_csv(out/'age_comparison_detail.csv',index=False,encoding='utf-8-sig',na_rep='')
summary.to_csv(work/'industry_summary.csv',index=False,encoding='utf-8-sig',na_rep='')
compact=detail[['event_id','industry','age','eligible_days','paired_days','missing_actual_days','insufficient_training_days','common_age_days','expected_common','actual_common','net_shortfall_common','net_rate_common','expected_share_common','lowest_expected_age','comparison_status']]
compact.to_csv(work/'age_view.csv',index=False,encoding='utf-8-sig',na_rep='')
stats=[]
for e,g in summary.groupby('event_id'):
 a=detail.loc[detail.event_id.eq(e)]
 stats.append(dict(event=e,incomplete_age_groups=int((~a.complete_nonholiday).sum()),no_paired_age_groups=int(a.paired_days.eq(0).sum()),industries_no_common=int(g.common_age_days.eq(0).sum()),industries_some_common=int(g.common_age_days.gt(0).sum()),industries_full_common=int(g.comparison_status.eq('all_nonholiday_dates').sum())))
(work/'stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
metadata={'source_sha256':hashlib.sha256((args.source_dir/'daily_predictions.csv').read_bytes()).hexdigest(),'calendar':run_metadata.get('calendar_provenance','unknown_review_required'),'detail_rows':len(detail),'industry_rows':len(summary),'scope':'customer ages on same within-industry dates; descriptive minimum only'}
(work/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(stats,ensure_ascii=False));print('Verified',len(detail),'age rows,',len(summary),'industry rows, common support and aggregate shares')
