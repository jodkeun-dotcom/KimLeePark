import sys
from pathlib import Path
import unittest
import pandas as pd
import numpy as np
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from diagnose_recovery_coverage import diagnose
from prepare_sales_handoff import KEY


def fixture():
    rows=[]
    for industry in ['A', 'B']:
        for date in ['2025-08-01', '2025-08-02']:
            for age in ['20', '30']:
                rows.append(dict(event_id='E', region='R', industry=industry, age=age,
                                 window_start='2025-08-01', window_end='2025-08-02',date=date,
                                 window='event' if date.endswith('01') else 'observation',
                                 amount=50., prediction=100., actual_status='observed', is_holiday=False))
    d=pd.DataFrame(rows)
    m=d[KEY].drop_duplicates().loc[lambda x:x.age.eq('20')].assign(age='ALL',recovery_status=['recovered','insufficient_data'])
    return d,m


class Tests(unittest.TestCase):
    def test_expected_share_includes_predictions_without_actual_rows(self):
        d,m=fixture();mask=d.industry.eq('B') & d.age.eq('30')
        d.loc[mask,'amount']=np.nan;d.loc[mask,'actual_status']='missing_row_unknown'
        detail,share=diagnose(d,m)
        self.assertEqual(share.iloc[0].decidable_known_event_prediction_share,.5)
        self.assertEqual(share.iloc[0].known_event_prediction_cell_coverage,1.)
        bad=detail.set_index('industry').loc['B']
        self.assertEqual(bad.event_missing_cause,'actual_row_only')
        self.assertTrue(bad.newly_event_complete);self.assertTrue(bad.newly_eligible_window_complete)

    def test_prediction_and_both_missing_causes(self):
        d,m=fixture();mask=d.industry.eq('B') & d.age.eq('30')
        d.loc[mask,'prediction']=np.nan
        detail,_=diagnose(d,m)
        self.assertEqual(detail.set_index('industry').loc['B'].event_missing_cause,'prediction_only')
        d.loc[mask,'amount']=np.nan;d.loc[mask,'actual_status']='missing_row_unknown'
        detail,_=diagnose(d,m);bad=detail.set_index('industry').loc['B']
        self.assertEqual(bad.event_missing_cause,'both_types');self.assertEqual(bad.event_both_missing_cells,1)

    def test_removal_is_fixed_and_cannot_remove_last_group(self):
        d,m=fixture();mask=d.industry.eq('B') & ((d.date.str.endswith('01')&d.age.eq('20'))|(d.date.str.endswith('02')&d.age.eq('30')))
        d.loc[mask,'prediction']=np.nan
        detail,_=diagnose(d,m);self.assertFalse(detail.set_index('industry').loc['B'].newly_eligible_window_complete)
        d=d.loc[d.age.eq('20')].copy();d.loc[d.industry.eq('B'),'prediction']=np.nan
        detail,_=diagnose(d,m);self.assertFalse(detail.set_index('industry').loc['B'].newly_event_complete)

    def test_holiday_distinguishes_eligible_and_calendar_windows(self):
        d,m=fixture();obs=d.date.str.endswith('02');d.loc[obs,'is_holiday']=True;d.loc[obs,'prediction']=np.nan
        d.loc[d.industry.eq('B')&d.age.eq('30'),'prediction']=np.nan
        detail,_=diagnose(d,m);bad=detail.set_index('industry').loc['B']
        self.assertTrue(bad.newly_eligible_window_complete);self.assertFalse(bad.newly_calendar_window_complete)

    def test_bad_status_keys_and_age_grid_rejected(self):
        d,m=fixture();d.loc[0,'actual_status']='missing_row_unknown'
        with self.assertRaises(ValueError):diagnose(d,m)
        d,m=fixture()
        with self.assertRaises(ValueError):diagnose(d.iloc[1:],m)
        with self.assertRaises(ValueError):diagnose(d,m.iloc[:1])
        m.loc[m.industry.eq('B'),'recovery_status']='unknown'
        with self.assertRaises(ValueError):diagnose(d,m)


if __name__=='__main__':
    unittest.main()
