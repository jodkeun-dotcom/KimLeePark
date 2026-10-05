"""Review path: compute recovery directly from PR29 age and paired-industry outputs."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import prepare_sales_baseline as baseline
import prepare_sales_handoff as sales
import compute_recovery as recovery

def compute(predictions, industry, events, threshold=0.95, run=3, run_metadata=None):
    if not np.isfinite(threshold) or threshold<=0 or isinstance(run,bool) or not isinstance(run,int) or run<1:
        raise ValueError('invalid recovery threshold/run')
    # Validate age panel, selected mode, date spans and event metadata first.
    _,diagnostic=sales.build(predictions,events,run_metadata)
    provenance=diagnostic.calendar_provenance.iloc[0]
    industry=industry.copy()
    detail=predictions.loc[predictions.window_type.eq('effective') & predictions.baseline_mode.eq('fixed_pre_event') & predictions.missing_policy.eq('exclude_missing') & predictions.model_id.eq('weekday_mean')].copy()
    required=['event_id','date','region','industry','age','window_start','window_end','window_type','baseline_mode','missing_policy','model_id','amount_paired','prediction_paired','paired_groups','total_groups','group_coverage','complete_group_coverage','analysis_role','phase']
    if missing:=set(required)-set(industry):raise ValueError(f'industry missing columns: {sorted(missing)}')
    if not industry.age.eq('ALL').all():raise ValueError('industry age must be ALL')
    expected=baseline.industry_daily(detail)
    keys=['event_id','date','region','industry','age','window_start','window_end','window_type','baseline_mode','missing_policy','model_id']
    for df in [expected,industry]:
        for c in ['date','window_start','window_end']:df[c]=pd.to_datetime(df[c],errors='raise').dt.strftime('%Y-%m-%d')
        if df[keys].isna().any().any() or df.duplicated(keys).any():raise ValueError('industry missing/duplicate keys')
    check=expected.merge(industry,on=keys,how='outer',validate='one_to_one',indicator=True,suffixes=('_expected','_input'))
    if not check._merge.eq('both').all():raise ValueError('industry and age windows/keys differ')
    for c in ['analysis_role','phase']:
        if not check[c+'_expected'].eq(check[c+'_input']).all():raise ValueError(f'industry metadata differs: {c}')
    for c in ['amount_paired','prediction_paired','paired_groups','total_groups','group_coverage']:
        left=pd.to_numeric(check[c+'_expected'],errors='raise');right=pd.to_numeric(check[c+'_input'],errors='raise')
        if not np.allclose(left,right,equal_nan=True,rtol=1e-10,atol=1e-7):raise ValueError(f'industry differs from paired age sum: {c}')
    flags=baseline.bool_column(industry.complete_group_coverage,'complete_group_coverage')
    if not flags.eq(industry.paired_groups.eq(industry.total_groups)).all():raise ValueError('incorrect group coverage flag')
    # Use the validated supplied table as input, rather than training a separate ALL model.
    all_rows=industry.rename(columns={'amount_paired':'amount','prediction_paired':'prediction'}).copy()
    all_rows['complete_group_coverage']=flags
    detail['complete_group_coverage']=detail.amount.notna() & detail.prediction.notna()
    curves=pd.concat([detail,all_rows],ignore_index=True)
    curves['date']=pd.to_datetime(curves.date)
    curves['ratio_paired_exploratory']=curves.amount/curves.prediction.where(curves.prediction.gt(0))
    curves['ratio']=curves.ratio_paired_exploratory.where(curves.complete_group_coverage)
    curves['baseline_source']='PR29_fixed_mean_exclude_missing'
    ends=events.set_index('event_id').end_date.apply(pd.Timestamp)
    curves['window']=np.where(curves.date.le(curves.event_id.map(ends)),'event','observation')
    curves['day_offset']=(curves.date-curves.event_id.map(ends)).dt.days
    curves['is_effective']=True
    metrics=[]
    for key,g in curves.groupby(sales.KEY,dropna=False):
        g=g.sort_values('date');ev=key[0]
        during=g.loc[g.window.eq('event')];paired=during.loc[during.amount.notna() & during.prediction.notna() & during.complete_group_coverage]
        denom=paired.prediction.sum();event_ratio=paired.amount.sum()/denom if denom>0 and len(paired)==len(during) else np.nan
        obs=g.loc[g.window.eq('observation')]
        if pd.isna(event_ratio) or len(paired)!=len(during):status,day,date='insufficient_data',None,pd.NaT
        elif event_ratio>=threshold:status,day,date='no_decline',None,pd.NaT
        else:status,day,date=recovery.recovery_day(obs,threshold=threshold,run=run)
        role=g.analysis_role.iloc[0]
        note=f'source=PR29;fixed_pre_event;weekday_mean;exclude_missing;effective;calendar={provenance};provisional_recovery_rule;analysis_role={role};complete_group_policy_review_pending'
        if key[3]=='ALL':note+=f';all_input_age_groups_required;partial_group_dates={int((~g.complete_group_coverage).sum())};partial_ratio_exploratory_only'
        row=dict(zip(sales.KEY,key))
        for c in ['window_start','window_end']:row[c]=pd.Timestamp(row[c]).strftime('%Y-%m-%d')
        row.update(window_type='effective',analysis_role=role,event_end=ends[ev].strftime('%Y-%m-%d'),event_ratio=event_ratio,event_days=len(during),event_days_paired=len(paired),observation_days=len(obs),observation_days_paired=int(obs.ratio.notna().sum()),recovery_status=status,recovery_days=day,recovery_date=date,recovery_threshold=threshold,consecutive_days=run,recovery_uncertainty_note=note)
        metrics.append(row)
    metrics=pd.DataFrame(metrics)
    metrics['recovery_days']=metrics.recovery_days.astype('Int64')
    return curves,metrics

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily-predictions',type=Path,required=True)
    ap.add_argument('--daily-industry',type=Path,required=True)
    ap.add_argument('--events',type=Path,required=True)
    ap.add_argument('--run-metadata',type=Path)
    ap.add_argument('--threshold',type=float,default=0.95)
    ap.add_argument('--consecutive-days',type=int,default=3)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    metadata=json.loads(args.run_metadata.read_text(encoding='utf-8-sig')) if args.run_metadata else None
    curves,metrics=compute(pd.read_csv(args.daily_predictions),pd.read_csv(args.daily_industry),pd.read_csv(args.events),args.threshold,args.consecutive_days,metadata)
    args.output.mkdir(parents=True,exist_ok=True)
    curves.to_csv(args.output/'recovery_curves_common_baseline.csv',index=False,encoding='utf-8-sig')
    metrics.to_csv(args.output/'recovery_metrics_common_baseline.csv',index=False,encoding='utf-8-sig')
    recovery.handoff(metrics).to_csv(args.output/'recovery_handoff_common_baseline.csv',index=False,encoding='utf-8-sig')
    print(f'{len(metrics)} common-baseline review rows; no rankings calculated')

if __name__=='__main__':main()
