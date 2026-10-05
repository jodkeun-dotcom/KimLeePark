import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import prepare_sales_baseline as b
import compute_recovery_from_baseline as c
import compute_recovery as r
import prepare_priority as p
from test_sales_handoff import inputs
import prepare_sales_handoff as h

class Tests(unittest.TestCase):
    def data(self):
        d,e=inputs();d['analysis_role']='case_study';d['phase']=np.where(d.date.eq('2025-08-01'),'event','observation')
        return d,b.industry_daily(d),e
    def test_uses_supplied_values_and_joins(self):
        d,i,e=self.data();curves,metrics=c.compute(d,i,e,run=1)
        self.assertEqual(curves.loc[curves.age.eq('ALL'),'prediction'].tolist(),[200,200])
        self.assertEqual(curves.loc[curves.age.eq('20대'),'amount'].tolist(),[0,0])
        sales,_=h.build(d,e);joined=p.join_metrics(sales,r.handoff(metrics))
        self.assertEqual(len(joined),3);self.assertTrue(joined.support_priority.isna().all())
    def test_mismatched_values_or_keys_rejected(self):
        d,i,e=self.data();i.loc[0,'prediction_paired']+=1
        with self.assertRaises(ValueError):c.compute(d,i,e)
        d,i,e=self.data()
        with self.assertRaises(ValueError):c.compute(d,i.iloc[:1],e)
    def test_missing_group_is_not_zero_and_is_disclosed(self):
        d,i,e=self.data();d.loc[0,'amount']=np.nan;i=b.industry_daily(d)
        curves,metrics=c.compute(d,i,e,run=1)
        allcurve=curves.loc[curves.age.eq('ALL')].sort_values('date')
        self.assertEqual(allcurve.prediction.tolist(),[100,200])
        self.assertIn('partial_group_dates=1',metrics.loc[metrics.age.eq('ALL'),'recovery_uncertainty_note'].iloc[0])
        self.assertEqual(metrics.loc[metrics.age.eq('20대'),'recovery_status'].iloc[0],'insufficient_data')
    def test_invalid_recovery_rule_rejected(self):
        d,i,e=self.data()
        for threshold,run in [(np.nan,3),(0,3),(.95,0)]:
            with self.assertRaises(ValueError):c.compute(d,i,e,threshold,run)

    def test_official_metadata_rejected_before_recovery(self):
        for col,value in [('start_date','2025-07-31'),('observation_end_effective','2025-08-03'),('analysis_role','statistical')]:
            d,i,e=self.data();e.loc[0,col]=value
            with self.assertRaises(ValueError):c.compute(d,i,e)
        d,i,e=self.data();d.loc[0,'phase']='observation';i=b.industry_daily(d)
        with self.assertRaises(ValueError):c.compute(d,i,e)

    def coverage_case(self):
        d,e=inputs();rows=[]
        for date in pd.date_range('2025-08-01','2025-08-04'):
            for age in ['20대','30대']:
                row=d.iloc[0].to_dict();row.update(date=date.strftime('%Y-%m-%d'),age=age,window_end='2025-08-04',phase='event' if date.day==1 else 'observation',amount=50. if date.day==1 else (100. if age=='20대' else np.nan))
                rows.append(row)
        e['observation_end_effective']='2025-08-04'
        return pd.DataFrame(rows),e

    def test_partial_groups_do_not_create_recovery(self):
        d,e=self.coverage_case();curves,metrics=c.compute(d,b.industry_daily(d),e)
        obs=curves.loc[curves.age.eq('ALL') & curves.window.eq('observation')]
        self.assertTrue(obs.ratio.isna().all());self.assertTrue(obs.ratio_paired_exploratory.eq(1.).all())
        self.assertEqual(metrics.loc[metrics.age.eq('ALL'),'recovery_status'].iloc[0],'insufficient_data')
        self.assertTrue(metrics.loc[metrics.age.eq('ALL'),'recovery_days'].isna().all())

    def test_complete_groups_recover_after_three_days(self):
        d,e=self.coverage_case();d.loc[d.phase.eq('observation'),'amount']=100.
        _,metrics=c.compute(d,b.industry_daily(d),e)
        self.assertEqual(metrics.loc[metrics.age.eq('ALL'),'recovery_status'].iloc[0],'recovered')
        self.assertEqual(metrics.loc[metrics.age.eq('ALL'),'recovery_days'].iloc[0],1)

    def test_incomplete_event_cannot_claim_no_decline(self):
        d,e=self.coverage_case();d.loc[d.phase.eq('event') & d.age.eq('30대'),'amount']=np.nan;d.loc[d.phase.eq('event') & d.age.eq('20대'),'amount']=100.
        _,metrics=c.compute(d,b.industry_daily(d),e)
        self.assertEqual(metrics.loc[metrics.age.eq('ALL'),'recovery_status'].iloc[0],'insufficient_data')
        self.assertTrue(metrics.loc[metrics.age.eq('ALL'),'event_ratio'].isna().all())

    def test_recovery_reports_actual_provenance(self):
        d,i,e=self.data();_,m=c.compute(d,i,e,run_metadata={'calendar_provenance':'provided_calendar'})
        self.assertTrue(m.recovery_uncertainty_note.str.contains('calendar=provided_calendar').all())

if __name__=='__main__':unittest.main()
