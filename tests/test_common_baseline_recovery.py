import sys
from pathlib import Path
import unittest
import numpy as np
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

if __name__=='__main__':unittest.main()
