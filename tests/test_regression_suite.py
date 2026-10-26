import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from scripts import evaluate_ridge as r
from scripts import evaluate_regression_suite as s
from scripts import evaluate_models as c


def sample():
    dates=pd.date_range('2025-07-01',periods=40)
    return pd.DataFrame({'date':dates,'industry':['A','B']*20,'age':['20','30']*20,'region':'test','amount':np.arange(40)*10.+100})


class RegressionTests(unittest.TestCase):
    def test_metrics_hand_computed(self):
        m=r.metric([10,20],[8,24])
        self.assertAlmostEqual(m['mae'],3)
        self.assertAlmostEqual(m['rmse'],np.sqrt(10))
        self.assertAlmostEqual(m['wape'],.2)
        self.assertIsNone(r.metric([0],[1])['wape'])

    def test_training_scaler_does_not_learn_test_dates(self):
        train=sample();m=r.make_ridge(1).fit(c.features(train),train.amount)
        scaler=m.named_steps['features'].named_transformers_['calendar']
        expected=c.features(train)[r.NUMERIC].mean().to_numpy()
        np.testing.assert_allclose(scaler.mean_,expected)
        future=train.copy();future['date']=future.date+pd.Timedelta(days=120)
        m.predict(c.features(future))
        np.testing.assert_allclose(scaler.mean_,expected)

    def test_unseen_category_finite(self):
        train=sample();future=train.iloc[:2].copy();future['industry']='unseen'
        m=r.make_ridge(1).fit(c.features(train),train.amount)
        self.assertTrue(np.isfinite(m.predict(c.features(future))).all())

    def test_interaction_pairs_do_not_collide(self):
        x=sample().iloc[:2].copy();x['industry']=['A|B','A'];x['age']=['C','B|C']
        out=s.suite_features(x,True)
        self.assertNotEqual(out.industry_age.iloc[0],out.industry_age.iloc[1])

    def test_selection_ignores_ineligible_actuals(self):
        train=sample();target=train.copy();target['date']+=pd.Timedelta(days=62)
        target['comparison_eligible']=True;target.loc[0,'comparison_eligible']=False
        a,first=r.select_alpha(train,target)
        target.loc[0,'amount']=1e20
        b,second=r.select_alpha(train,target)
        self.assertEqual(a,b);pd.testing.assert_frame_equal(first,second)

    def test_reference_mismatch_rejected(self):
        x=sample();x['baseline_prediction']=x.amount;x['ai_prediction']=x.amount;x['comparison_eligible']=True
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'old.csv';x.to_csv(p,index=False)
            r.verify_reference(x,p)
            changed=x.copy();changed.loc[0,'amount']+=1
            with self.assertRaises(ValueError):r.verify_reference(changed,p)

    def test_suite_target_ignored_in_prediction(self):
        train=sample();target=train.iloc[:5].copy()
        p,_=s.fit_predict('ridge_interactions',{'alpha':1.},train,target)
        target['amount']=1e30
        q,_=s.fit_predict('ridge_interactions',{'alpha':1.},train,target)
        np.testing.assert_allclose(p,q)

if __name__=='__main__':unittest.main()
