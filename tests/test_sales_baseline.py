import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location('baseline', Path(__file__).parents[1]/'scripts/prepare_sales_baseline.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def daily():
    dates = pd.date_range('2025-07-01', '2025-09-30')
    return pd.DataFrame({'date': dates, 'region': 'R', 'industry': 'A', 'age': '20대', 'amount': 100.0})


def events():
    return pd.DataFrame({'event_id': ['HEAT_A', 'HEAT_B'], 'type': ['폭염', '폭염'],
                         'start_date': pd.to_datetime(['2025-08-01', '2025-08-18']),
                         'end_date': pd.to_datetime(['2025-08-04', '2025-08-19']),
                         'analysis_role': ['case_study', 'case_study']})


def windows(ev):
    rows = []
    for e in ev.itertuples():
        for day in pd.date_range(e.start_date, e.end_date+pd.Timedelta(days=14)):
            rows.append(dict(event_id=e.event_id, date=day, window='event' if day<=e.end_date else 'observation',
                             is_effective=not (e.event_id=='HEAT_A' and day>=pd.Timestamp('2025-08-18'))))
    return pd.DataFrame(rows)


class BaselineTests(unittest.TestCase):
    def panel(self, source=None):
        return b.build_panel(b.validate_daily(daily() if source is None else source, primary=set()), events())[0]

    def test_fixed_baseline_ignores_future_amounts(self):
        origin = pd.Timestamp('2025-08-01')
        p1 = self.panel()
        altered = daily(); altered.loc[altered.date>=origin, 'amount'] = 1e9
        p2 = self.panel(altered)
        train1, train2 = b.training_sample(p1, origin), b.training_sample(p2, origin)
        a = b.predict(train1, p1.loc[p1.date.ge(origin)])
        c = b.predict(train2, p2.loc[p2.date.ge(origin)])
        pd.testing.assert_series_equal(a['mean'], c['mean'])
        self.assertTrue(a.train_end.dropna().lt(origin).all())

    def test_partial_full_null_and_paired_bound(self):
        d = daily().loc[lambda x: x.date.ne(pd.Timestamp('2025-08-02'))]
        summaries, _, _ = b.calculate(self.panel(d), events(), windows(events()), primary=set())
        row = summaries.loc[summaries.event_id.eq('HEAT_A') & summaries.missing_policy.eq('exclude_missing')].iloc[0]
        self.assertFalse(row.complete_window)
        self.assertTrue(pd.isna(row.net_shortfall_full))
        self.assertTrue(summaries.paired_days.le(summaries.window_days).all())
        self.assertTrue(summaries.paired_days.le(summaries.eligible_window_days).all())

    def test_missing_zero_sensitivity_preserves_provenance(self):
        d = daily().loc[lambda x: x.date.ne(pd.Timestamp('2025-08-02'))]
        _, handoff, _ = b.calculate(self.panel(d), events(), windows(events()), primary=set())
        rows = handoff.loc[handoff.date.eq('2025-08-02') & handoff.model_id.eq('weekday_mean')]
        self.assertTrue(rows.actual_status.eq('missing_row_unknown').all())
        self.assertTrue(rows.loc[rows.missing_policy.eq('exclude_missing'), 'amount'].isna().all())
        self.assertTrue(rows.loc[rows.missing_policy.eq('zero_fill_sensitivity'), 'amount'].eq(0).all())

    def test_holiday_full_and_nonholiday_are_distinct(self):
        results, handoff, _ = b.calculate(self.panel(), events(), windows(events()), primary=set())
        r = results.loc[results.event_id.eq('HEAT_A') & results.window_type.eq('effective')].iloc[0]
        self.assertEqual(r.holiday_excluded_days, 1)
        self.assertFalse(r.complete_window)
        self.assertTrue(r.complete_eligible_window)
        self.assertTrue(pd.isna(r.net_shortfall_full))
        self.assertEqual(r.net_shortfall_eligible, 0)
        self.assertTrue(handoff.loc[handoff.date.eq('2025-08-15'), 'prediction'].isna().all())

    def test_effective_cutoff_and_nominal_are_separate(self):
        targets = dict(b.event_targets(self.panel(), next(events().itertuples()), windows(events())))
        self.assertEqual(targets['effective'].date.max(), pd.Timestamp('2025-08-17'))
        self.assertEqual(targets['nominal_overlap_sensitivity'].date.max(), pd.Timestamp('2025-08-18'))

    def test_primary_typo_rejected(self):
        with self.assertRaisesRegex(ValueError, 'primary industries absent'):
            b.validate_daily(daily(), {'typo'})

    def test_invalid_amount_duplicate_and_nat_rejected(self):
        for value in [np.nan, np.inf, -1]:
            d = daily(); d.loc[0, 'amount'] = value
            with self.assertRaises(ValueError): b.validate_daily(d, set())
        with self.assertRaises(ValueError): b.validate_daily(pd.concat([daily(), daily().iloc[:1]]), set())
        d = daily(); d.loc[0, 'date'] = pd.NaT
        with self.assertRaises(ValueError): b.validate_daily(d, set())

    def test_retrospective_masks_event_and_recovery_and_is_labeled(self):
        p = self.panel(); ev = events(); w = windows(ev)
        mask = w.loc[w.is_effective, 'date']
        train = b.training_sample(p, pd.Timestamp('2025-08-01'), retrospective_end=pd.Timestamp('2025-08-17'), masked_dates=mask)
        self.assertFalse(train.date.isin(mask).any())
        self.assertTrue(train.date.gt(pd.Timestamp('2025-08-17')).any())
        r, d, _ = b.calculate(p, ev, w, primary=set(), retrospective=True)
        self.assertIn('retrospective_4week_sensitivity', set(d.baseline_mode))

    def test_calendar_requires_complete_unique_binary_input(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'calendar.csv'
            pd.DataFrame({'date': ['2025-07-01'], 'is_holiday': [0]}).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'cover every'): b.calendar_flags(pd.date_range('2025-07-01', periods=2), path)
            pd.DataFrame({'date': ['2025-07-01'], 'is_holiday': ['maybe']}).to_csv(path, index=False)
            with self.assertRaises(ValueError): b.calendar_flags(pd.date_range('2025-07-01', periods=1), path)

    def test_external_windows_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ep, wp = Path(td)/'events.csv', Path(td)/'windows.csv'
            events().to_csv(ep, index=False); w = windows(events()); w.to_csv(wp, index=False)
            ev, win = b.load_events(ep, wp)
            self.assertEqual(len(ev), 2)
            w = w.loc[~(w.event_id.eq('HEAT_A') & w.date.eq('2025-08-02'))]; w.to_csv(wp, index=False)
            with self.assertRaisesRegex(ValueError, 'event dates disagree'): b.load_events(ep, wp)

    def test_nested_heat_observation_starts_after_parent(self):
        ev = events().iloc[:1].copy()
        ev['event_id'] = 'SHEAT_A'; ev['type'] = '강한 폭염'
        ev['end_date'] = pd.Timestamp('2025-08-01')
        ev['observation_start'] = pd.Timestamp('2025-08-05')
        win = pd.DataFrame([dict(event_id='SHEAT_A', date=pd.Timestamp('2025-08-01'), window='event', is_effective=True)] +
                           [dict(event_id='SHEAT_A', date=dt, window='observation', is_effective=True) for dt in pd.date_range('2025-08-05', '2025-08-18')])
        with tempfile.TemporaryDirectory() as td:
            ep, wp = Path(td)/'events.csv', Path(td)/'windows.csv'
            ev.to_csv(ep, index=False); win.to_csv(wp, index=False)
            a, c = b.load_events(ep, wp)
            self.assertEqual(a.observation_start.iloc[0], '2025-08-05')
            self.assertEqual(len(c), 15)

    def test_report_and_outputs_dynamic_and_parseable(self):
        r, d, v = b.calculate(self.panel(), events(), windows(events()), primary=set())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td); b.write_outputs(out, r, d, v, 'test_calendar')
            text = (out/'baseline_report.md').read_text(encoding='utf-8')
            self.assertIn('그룹 1개', text)
            self.assertFalse(any(line.startswith('    ') for line in text.splitlines()))
            read = pd.read_csv(out/'daily_predictions.csv')
            self.assertEqual(len(read), len(d))
            self.assertIn('missing_policy_sensitivity.csv', [p.name for p in out.iterdir()])


if __name__ == '__main__':
    unittest.main()
