import importlib.util
from pathlib import Path
import unittest
import pandas as pd
import numpy as np
spec=importlib.util.spec_from_file_location('handoff',Path(__file__).parents[1]/'scripts/prepare_sales_handoff.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

def inputs():
    rows=[]
    for date in ['2025-08-01','2025-08-02']:
        for age,actual in [('20대',0.),('30대',200.)]:
            rows.append(dict(event_id='E',region='R',industry='A',age=age,window_start='2025-08-01',window_end='2025-08-02',date=date,amount=actual,prediction=100.,window_type='effective',baseline_mode='fixed_pre_event',missing_policy='exclude_missing',model_id='weekday_mean',is_holiday=False))
    d=pd.DataFrame(rows)
    d['phase']=np.where(d.date.eq('2025-08-01'),'event','observation');d['analysis_role']='case_study'
    return d,pd.DataFrame([dict(event_id='E',start_date='2025-08-01',end_date='2025-08-01',observation_end_effective='2025-08-02',analysis_role='case_study')])

class Checks(unittest.TestCase):
    def test_all_gross_applies_after_age_aggregation(self):
        d,e=inputs();a,q=h.build(d,e)
        self.assertEqual(a.loc[a.age.eq('ALL'),'gross_shortfall'].iloc[0],0)
        self.assertEqual(a.loc[a.age.eq('20대'),'gross_shortfall'].iloc[0],200)
        self.assertEqual(a.loc[a.age.eq('30대'),'net_shortfall'].iloc[0],-200)
    def test_partial_never_claims_full_window(self):
        d,e=inputs();d.loc[0,'amount']=np.nan;a,q=h.build(d,e)
        self.assertTrue(a.loc[a.age.eq('ALL'),'net_shortfall'].isna().all())
        self.assertEqual(q.loc[q.age.eq('ALL'),'net_shortfall_paired'].iloc[0],-100)
        self.assertTrue(a.loc[a.age.eq('ALL'),'decline_rate'].isna().all())
    def test_holiday_full_blank_eligible_available(self):
        d,e=inputs();d.loc[d.date.eq('2025-08-02'),'is_holiday']=True;d.loc[d.is_holiday,'prediction']=np.nan
        a,q=h.build(d,e);self.assertTrue(a.net_shortfall.isna().all());self.assertTrue(q.complete_nonholiday.all())
        self.assertEqual(q.loc[q.age.eq('20대'),'net_shortfall_nonholiday'].iloc[0],100)
    def test_duplicate_and_all_inputs_rejected(self):
        d,e=inputs()
        with self.assertRaises(ValueError):h.build(pd.concat([d,d.iloc[:1]]),e)
        d.loc[0,'age']='ALL'
        with self.assertRaises(ValueError):h.build(d,e)
    def test_other_models_filtered(self):
        d,e=inputs();extra=d.assign(model_id='weekday_median',prediction=9999)
        a,q=h.build(pd.concat([d,extra]),e);self.assertEqual(len(a),3)
        self.assertEqual(a.loc[a.age.eq('20대'),'net_shortfall'].iloc[0],200)
    def test_missing_grid_rejected(self):
        d,e=inputs()
        with self.assertRaises(ValueError):h.build(d.iloc[1:],e)

    def test_official_window_and_phase_rejected(self):
        for col,value in [('start_date','2025-07-31'),('observation_end_effective','2025-08-03')]:
            d,e=inputs();e.loc[0,col]=value
            with self.assertRaises(ValueError):h.build(d,e)
        d,e=inputs();d.loc[0,'phase']='observation'
        with self.assertRaises(ValueError):h.build(d,e)

    def test_role_is_validated_and_reported(self):
        d,e=inputs();e['analysis_role']='statistical'
        with self.assertRaises(ValueError):h.build(d,e)
        d['analysis_role']='statistical';a,_=h.build(d,e)
        self.assertTrue(a.sales_uncertainty_note.str.contains('analysis_role=statistical').all())

    def test_calendar_provenance_is_not_guessed(self):
        d,e=inputs();d.loc[d.date.eq('2025-08-02'),'is_holiday']=True;d.loc[d.is_holiday,'prediction']=np.nan
        a,_=h.build(d,e)
        self.assertTrue(a.sales_uncertainty_note.str.contains('calendar=unknown_review_required').all())
        a,_=h.build(d,e,{'calendar_provenance':'provided_calendar'})
        self.assertTrue(a.sales_uncertainty_note.str.contains('calendar=provided_calendar').all())
        with self.assertRaises(ValueError):h.build(d,e,{'calendar_provenance':'provisional_2025_08_15_only'})
        with self.assertRaises(ValueError):h.build(d,e,{'daily_rows':999})

if __name__=='__main__':unittest.main()
