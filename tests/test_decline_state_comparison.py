import unittest

import numpy as np
import pandas as pd

from scripts.compare_decline_states import comparison_fields, comparison_tables, coverage_tables


class DeclineStateComparisonTests(unittest.TestCase):
    def detail(self):
        return pd.DataFrame({'event_id': 'E', 'region': 'R', 'industry': list('ABCDE'), 'age': 'ALL',
            'window_start': '2025-08-01', 'window_end': '2025-08-02', 'scope': 'primary',
            'decline_rate': [.5, .2, .2, -.1, np.nan], 'observation_days': [3, 2, 4, 3, 0],
            'consecutive_days': 3, 'recovery_status': ['censored', 'insufficient_data', 'recovered', 'no_decline', 'insufficient_data'],
            'support_review_group': 'test', 'support_review_label': '검토', 'priority_tier': [np.nan, np.nan, 1, np.nan, np.nan],
            'decline_only_rank': [np.nan, np.nan, 1, np.nan, np.nan], 'complete_eligible_window': True})

    def test_decline_cohort_includes_unranked_and_negative_declines_without_overwriting(self):
        source = self.detail()
        out = comparison_fields(source)
        pd.testing.assert_frame_equal(out[source.columns], source)
        self.assertEqual(out.decline_rank_all_available.iloc[:4].tolist(), [1, 2, 2, 4])
        self.assertTrue(pd.isna(out.decline_rank_all_available.iloc[4]))
        self.assertEqual(out.decline_comparison_band.tolist(), ['top3_including_ties']*3 + ['other_available', 'decline_unavailable'])

    def test_ties_and_regions_and_scopes_are_kept_separate(self):
        a = self.detail().iloc[:4].copy()
        a['decline_rate'] = [.5, .4, .3, .3]
        b = a.assign(region='R2', decline_rate=.1)
        c = a.assign(scope='auxiliary', industry=list('FGHI'), decline_rate=.9)
        out, cross = comparison_tables(pd.concat([a, b, c], ignore_index=True))
        self.assertTrue(out.decline_comparison_band.eq('top3_including_ties').all())
        self.assertEqual(int(cross.industry_event_rows.sum()), 12)
        self.assertTrue(out.loc[out.region.eq('R2'), 'decline_rank_all_available'].eq(1).all())

    def test_short_window_annotation_does_not_reclassify_recovery(self):
        source = self.detail()
        out = comparison_fields(source)
        self.assertEqual(out.calendar_recovery_start_positions.tolist(), [1, 0, 2, 1, 0])
        self.assertEqual(out.censored_short_window.tolist(), [True, False, False, False, False])
        self.assertTrue(out.recovery_status.eq(source.recovery_status).all())
        self.assertTrue(pd.isna(out.priority_tier.iloc[0]))

    def grid(self):
        rows = []
        for industry in ['A', 'B']:
            for date, phase in [('2025-08-01', 'event'), ('2025-08-02', 'observation')]:
                for age in ['20', '30']:
                    rows.append(dict(event_id='E', region='R', industry=industry, age=age,
                        window_start='2025-08-01', window_end='2025-08-02', date=date, phase=phase,
                        window_type='effective', baseline_mode='fixed_pre_event', missing_policy='exclude_missing',
                        model_id='weekday_mean', amount=80., prediction=100., is_holiday=False))
        return pd.DataFrame(rows)

    def test_known_prediction_share_retains_unobserved_actuals_and_discloses_missing_predictions(self):
        d = self.grid()
        d.loc[d.industry.eq('B') & d.phase.eq('event') & d.age.eq('30'), 'amount'] = np.nan
        d.loc[d.industry.eq('B') & d.phase.eq('observation') & d.age.eq('30'), 'prediction'] = np.nan
        m = self.detail().iloc[:2].copy()
        m['complete_eligible_window'] = [True, False]
        detail, summary = coverage_tables(m, d)
        a, b = detail.iloc[0], detail.iloc[1]
        self.assertEqual(a.all_age_complete_dates, 2)
        self.assertEqual(b.all_age_complete_dates, 0)
        self.assertFalse(b.complete_event_window)
        row = summary.loc[summary.event_id.eq('ALL_EVENTS') & summary.scope.eq('all_scopes')].iloc[0]
        self.assertAlmostEqual(row.judgeable_known_event_prediction_share, .5)
        self.assertAlmostEqual(row.judgeable_known_window_prediction_share, 4/7)
        self.assertAlmostEqual(row.known_window_prediction_cell_fraction, 7/8)
        self.assertEqual(row.recovery_unjudgeable_rows, 1)

    def test_holiday_gap_distinguishes_event_eligible_and_full_period(self):
        d = self.grid()
        d.loc[d.phase.eq('observation'), 'is_holiday'] = True
        d.loc[d.phase.eq('observation'), 'prediction'] = np.nan
        m = self.detail().iloc[:2].copy()
        detail, _ = coverage_tables(m, d)
        self.assertTrue(detail.complete_event_window.all())
        self.assertTrue(detail.complete_nonholiday_window.all())
        self.assertFalse(detail.complete_calendar_window.any())
        self.assertTrue(detail.all_age_complete_dates.eq(1).all())

    def test_no_judgeable_or_no_prediction_is_not_a_fabricated_full_coverage(self):
        d = self.grid().assign(prediction=np.nan)
        m = self.detail().iloc[:2].assign(recovery_status='insufficient_data', complete_eligible_window=False)
        _, summary = coverage_tables(m, d)
        self.assertTrue(summary.judgeable_known_window_prediction_share.isna().all())
        self.assertTrue(summary.known_window_prediction_cell_fraction.eq(0).all())

    def test_rejects_duplicate_keys_bad_days_and_incomplete_grid(self):
        with self.assertRaises(ValueError):
            comparison_fields(pd.concat([self.detail(), self.detail()]))
        with self.assertRaises(ValueError):
            comparison_fields(self.detail().assign(observation_days=2.5))
        with self.assertRaises(ValueError):
            comparison_fields(self.detail().assign(decline_rate=np.inf))
        with self.assertRaises(ValueError):
            coverage_tables(self.detail().iloc[:2], self.grid().iloc[1:])


if __name__ == '__main__':
    unittest.main()
