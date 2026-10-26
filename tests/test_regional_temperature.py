import unittest,tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.evaluate_regional_temperature import *

def sample():
    rows=[]
    for i,date in enumerate(pd.date_range('2025-07-01','2025-08-31')):
        for n,region in enumerate(REGIONS):
            rows.append(dict(date=date,region=region,industry='synthetic',age='20대',amount=100+n*20+i%7,tmax=28+i%10,is_holiday=0))
    return pd.DataFrame(rows)

class RegionalTests(unittest.TestCase):
    def test_duplicate_rejected(self):
        d=sample()
        with self.assertRaises(ValueError):paired(pd.concat([d,d.iloc[:1]]))
    def test_pair_removes_both_when_one_missing(self):
        d=sample().iloc[1:];p=paired(d)
        self.assertFalse(p.date.eq(pd.Timestamp('2025-07-01')).any())
        self.assertTrue(p.groupby(PAIR).size().eq(2).all())
    def test_training_scale_unaffected_by_future(self):
        d=sample();tr,ev=make_fold(d,*SPLITS[0][1:]); d.loc[d.date.gt('2025-07-21'),'amount']*=100
        tr2,ev2=make_fold(d,*SPLITS[0][1:]);np.testing.assert_array_equal(tr.scale,tr2.scale);np.testing.assert_array_equal(ev.scale,ev2.scale)
    def test_model0_has_no_temperature_feature(self):
        d=sample();a=features(d,'M0_calendar');d['tmax']+=10
        self.assertEqual(a,features(d,'M0_calendar'))
    def test_negative_metric_rejected(self):
        with self.assertRaises(ValueError):metrics([1],[-1])
    def test_metric_values(self):
        m=metrics([10,20],[8,24]);self.assertAlmostEqual(m['wape'],.2);self.assertEqual(m['mae'],3)
    def test_baseline_order(self):
        tr,ev=make_fold(sample(),*SPLITS[0][1:]);p=baseline(tr,ev);self.assertEqual(len(p),len(ev));self.assertTrue(np.isfinite(p).all())
    def test_wrong_station(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'w.csv';pd.DataFrame({'지점':[108],'일시':['2025-07-01'],'최고기온(°C)':[30]}).to_csv(p,index=False,encoding='cp949')
            with self.assertRaises(ValueError):read_weather(p,400,REGIONS[1])
    def test_actual_pipeline_synthetic(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);d=sample();d[KEY+['amount']].to_csv(t/'card.csv',index=False)
            d[['date','is_holiday']].drop_duplicates().to_csv(t/'cal.csv',index=False)
            for station,region in zip([101,400],REGIONS):
                q=d[d.region.eq(region)][['date','tmax']].rename(columns={'date':'일시','tmax':'최고기온(°C)'})
                q['지점']=station;q.to_csv(t/f'{station}.csv',index=False,encoding='cp949')
            run(t/'card.csv',t/'101.csv',t/'400.csv',t/'cal.csv',t/'out')
            p=pd.read_csv(t/'out/predictions.csv');self.assertEqual(p.model.nunique(),4)
            for _,g in p.groupby(['fold','model']):self.assertTrue(g.groupby(PAIR).size().eq(2).all())
            for _,s in pd.read_csv(t/'out/metrics.csv').iterrows():
                q=p[(p.fold==s.fold)&(p.model==s.model)]
                if s.region!='ALL':q=q[q.region==s.region]
                self.assertAlmostEqual(metrics(q.amount,q.prediction)['wape'],s.wape)

if __name__=='__main__':unittest.main()
