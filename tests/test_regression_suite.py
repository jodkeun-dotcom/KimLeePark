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

class ReviewValidationTests(unittest.TestCase):
    def test_metrics_reject_broadcasting(self):
        with self.assertRaises(ValueError):r.metric([1,2],[[1],[2]])
        with self.assertRaises(ValueError):r.metric([1,2],[1])
        with self.assertRaises(ValueError):r.metric([-1],[1])

    def test_saved_ridge_tampering_rejected(self):
        train=sample();x=sample();x['comparison_eligible']=True;x['evaluation_status']='predicted'
        x['baseline_prediction']=x.amount;x['ai_prediction']=x.amount
        m=r.make_ridge(.01).fit(c.features(train),train.amount)
        x['ridge_prediction']=np.maximum(m.predict(c.features(x)),0)
        fresh=x.drop(columns='ridge_prediction')
        s.validate_saved(x,fresh,train,.01)
        changed=x.copy();changed.loc[0,'ridge_prediction']+=100
        with self.assertRaises(ValueError):s.validate_saved(changed,fresh,train,.01)
        changed=x.copy();changed.loc[0,'comparison_eligible']=False
        with self.assertRaises(ValueError):s.validate_saved(changed,fresh,train,.01)

    def test_saved_missing_key_rejected(self):
        x=sample();x.loc[0,'industry']=None
        with self.assertRaises(ValueError):s.validate_saved(x,x,sample(),1)

    def test_paired_blocks_keep_zero_difference(self):
        x=sample();x['baseline_prediction']=x.amount*0.9;x['same']=x.baseline_prediction
        result=s.paired_daily_comparison(x,{'same':'same'},draws=40).iloc[0]
        self.assertEqual(result.delta_wape_vs_mean,0)
        self.assertEqual(result.resampling_p025,0)
        self.assertEqual(result.resampling_p975,0)
        self.assertEqual(result.valid_draws,40)

    def test_resampling_reproducible(self):
        x=sample();x['baseline_prediction']=x.amount*.9;x['other']=x.amount*.8
        a=s.paired_daily_comparison(x,{'other':'other'},draws=40)
        b=s.paired_daily_comparison(x,{'other':'other'},draws=40)
        pd.testing.assert_frame_equal(a,b)
        self.assertGreater(a.iloc[0].delta_wape_vs_mean,0)

if __name__=='__main__':unittest.main()
