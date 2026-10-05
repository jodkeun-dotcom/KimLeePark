"""Create effective, fixed-mean sales handoff and coverage diagnostics; no rankings."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

KEY=['event_id','region','industry','age','window_start','window_end']
SALES=['decline_rate','gross_shortfall','net_shortfall','net_shortfall_rate','sales_uncertainty_note']

def build(daily, events):
    required=KEY+['date','amount','prediction','window_type','baseline_mode','missing_policy','model_id','is_holiday']
    if missing:=set(required)-set(daily):raise ValueError(f'missing columns: {sorted(missing)}')
    d=daily.loc[daily.window_type.eq('effective') & daily.baseline_mode.eq('fixed_pre_event') & daily.missing_policy.eq('exclude_missing') & daily.model_id.eq('weekday_mean')].copy()
    if d.empty:raise ValueError('no default effective rows')
    if d[KEY+['date']].isna().any().any() or d[KEY].astype(str).eq('').any().any():raise ValueError('missing keys')
    if d.age.eq('ALL').any():raise ValueError('input must be age detail, not ALL')
    for c in ['date','window_start','window_end']:d[c]=pd.to_datetime(d[c],errors='raise')
    holiday=d.is_holiday.astype(str).str.lower()
    if not holiday.isin(['true','false']).all():raise ValueError('invalid holiday flags')
    d['is_holiday']=holiday.eq('true')
    for c in ['amount','prediction']:
        d[c]=pd.to_numeric(d[c],errors='raise')
        if d[c].dropna().lt(0).any() or not np.isfinite(d[c].dropna()).all():raise ValueError('invalid amounts')
    if d.duplicated(KEY+['date']).any():raise ValueError('duplicate selected rows')
    if events.event_id.duplicated().any():raise ValueError('duplicate event metadata')
    ends=events.set_index('event_id').end_date.apply(pd.Timestamp)
    if not set(d.event_id)<=set(ends.index):raise ValueError('missing event ends')
    if d.loc[d.is_holiday,'prediction'].notna().any():raise ValueError('holiday prediction present')
    base=['event_id','region','industry','window_start','window_end']
    all_rows=[]
    for key,g in d.groupby(base):
        n=g.age.nunique()
        if not g.groupby('date').age.nunique().eq(n).all():raise ValueError('incomplete age grid')
        for date,t in g.groupby('date'):
            paired=t.amount.notna() & t.prediction.notna()
            q=t.loc[paired]
            row=dict(zip(base,key),age='ALL',date=date,amount=q.amount.sum(min_count=1),prediction=q.prediction.sum(min_count=1),is_holiday=t.is_holiday.iloc[0],paired_groups=len(q),total_groups=n,complete_date=bool(paired.all()))
            all_rows.append(row)
    detail=d[KEY+['date','amount','prediction','is_holiday']].copy()
    detail['paired_groups']=(detail.amount.notna() & detail.prediction.notna()).astype(int)
    detail['total_groups']=1;detail['complete_date']=detail.paired_groups.eq(1)
    panel=pd.concat([detail,pd.DataFrame(all_rows)],ignore_index=True)
    rows=[]
    for key,g in panel.groupby(KEY):
        row=dict(zip(KEY,key))
        if not pd.DatetimeIndex(g.date.sort_values()).equals(pd.date_range(row['window_start'],row['window_end'])):raise ValueError('window has gaps')
        event_end=ends[row['event_id']]
        if not row['window_start']<=event_end<=row['window_end']:raise ValueError('event end outside window')
        paired=g.amount.notna() & g.prediction.notna()
        q=g.loc[paired];gap=q.prediction-q.amount
        net=gap.sum() if len(q) else np.nan;gross=gap.clip(lower=0).sum() if len(q) else np.nan;expected=q.prediction.sum() if len(q) else np.nan
        full=bool(g.complete_date.all());eligible=~g.is_holiday
        eligible_full=bool(eligible.any() and g.loc[eligible,'complete_date'].all())
        event=g.loc[g.date.le(event_end)]
        event_expected=event.prediction.sum(min_count=1)
        decline=(event_expected-event.amount.sum())/event_expected if event.complete_date.all() and event_expected>0 else np.nan
        note=f'effective;fixed_pre_event;weekday_mean;exclude_missing;calendar=8/15_only_provisional;full_dates={int(g.complete_date.sum())}/{len(g)};paired_subtotal_dates={len(q)};eligible_complete={eligible_full};case_study;method_selection_pending;unit=provided_unit'
        if row['age']=='ALL':note+=';same_paired_age_groups_daily;group_composition_may_change;recovery_ALL_baseline_match_pending'
        row.update(decline_rate=decline,gross_shortfall=gross if full else np.nan,net_shortfall=net if full else np.nan,net_shortfall_rate=net/expected if full and expected>0 else np.nan,sales_uncertainty_note=note,
                   window_days=len(g),holiday_days=int(g.is_holiday.sum()),complete_dates=int(g.complete_date.sum()),paired_subtotal_days=len(q),complete_window=full,complete_nonholiday=eligible_full,
                   gross_shortfall_paired=gross,net_shortfall_paired=net,expected_paired=expected,net_shortfall_rate_paired=net/expected if expected>0 else np.nan,
                   net_shortfall_nonholiday=net if eligible_full else np.nan,net_rate_nonholiday=net/expected if eligible_full and expected>0 else np.nan,
                   min_paired_groups=int(g.paired_groups.min()),total_groups=int(g.total_groups.iloc[0]))
        for c in ['window_start','window_end']:row[c]=row[c].strftime('%Y-%m-%d')
        rows.append(row)
    diagnostic=pd.DataFrame(rows)
    handoff=diagnostic[KEY+SALES].copy()
    if handoff.duplicated(KEY).any():raise ValueError('duplicate handoff keys')
    return handoff,diagnostic

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily-predictions',type=Path,required=True)
    ap.add_argument('--events',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    handoff,diagnostic=build(pd.read_csv(args.daily_predictions),pd.read_csv(args.events))
    args.output.mkdir(parents=True,exist_ok=True)
    handoff.to_csv(args.output/'sales_handoff.csv',index=False,encoding='utf-8-sig')
    diagnostic.to_csv(args.output/'sales_handoff_diagnostics.csv',index=False,encoding='utf-8-sig')
    print(f'{len(handoff)} unique handoff rows; full metrics blank for incomplete windows; rankings pending')

if __name__=='__main__':main()
