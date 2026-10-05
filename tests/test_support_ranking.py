import unittest

import numpy as np
import pandas as pd

from scripts.rank_support import industry_metrics, pareto_layers, rank_metrics, stability_table


class SupportRankingTests(unittest.TestCase):
    def test_pareto_layers_preserve_ties_and_units(self):
        values = np.array([[.5, .2, 2], [.4, .1, 1], [.1, .4, 5], [.5, .2, 2]])
        np.testing.assert_array_equal(pareto_layers(values), [1, 2, 1, 1])
        np.testing.assert_array_equal(pareto_layers(values * [100, 1000, 1]), [1, 2, 1, 1])
        with self.assertRaises(ValueError):
            pareto_layers([[np.nan, 1, 2]])

    def test_censored_and_incomplete_never_receive_fake_rank_or_days(self):
        d = pd.DataFrame({'event_id': 'E', 'scope': 'primary',
                          'complete_eligible_window': [True, True, False, True],
                          'decline_rate': [.2]*4, 'net_shortfall_rate_eligible': [.1, .1, np.nan, -.1],
                          'recovery_status': ['recovered', 'censored', 'recovered', 'recovered'],
                          'confirmation_days': [5, np.nan, 3, 4]})
        r = rank_metrics(d)
        self.assertEqual(r.review_queue.tolist(), ['ranked_candidate', 'recovery_unconfirmed_review', 'data_incomplete', 'no_positive_net_shortfall'])
        self.assertEqual(r.priority_tier.notna().tolist(), [True, False, False, False])
        self.assertTrue(pd.isna(r.confirmation_days.iloc[1]))

    def test_ranks_are_within_same_event_and_scope(self):
        d = pd.DataFrame({'event_id': ['E1', 'E1', 'E2'], 'scope': ['primary', 'auxiliary', 'primary'],
                          'complete_eligible_window': True, 'decline_rate': [.1, .8, .9],
                          'net_shortfall_rate_eligible': [.1, .8, .9], 'recovery_status': 'recovered',
                          'confirmation_days': [3, 10, 14]})
        r = rank_metrics(d)
        self.assertEqual(r.priority_tier.tolist(), [1, 1, 1])
        self.assertEqual(r.decline_only_rank.tolist(), [1, 1, 1])

    def test_common_aggregate_recovery_and_incomplete_loss(self):
        dates = pd.date_range('2025-08-01', periods=7)
        d = pd.DataFrame({'event_id': 'E', 'region': 'R', 'industry': '한식', 'date': dates,
                          'window_start': dates[0], 'window_end': dates[-1],
                          'phase': ['event'] + ['observation']*6,
                          'amount_paired': [50, 50, 100, 100, 100, 100, 100],
                          'prediction_paired': 100, 'complete_group_coverage': True,
                          'is_holiday': False, 'group_coverage': 1., 'total_groups': 2,
                          'model_id': 'weekday_mean'})
        events = pd.DataFrame({'event_id': ['E'], 'start_date': ['2025-08-01'],
                               'end_date': ['2025-08-01'], 'analysis_role': ['case_study']})
        row = industry_metrics(d, events, calendar_provenance='provided_calendar').iloc[0]
        self.assertEqual(row.calendar_provenance, 'provided_calendar')
        self.assertIn('calendar=provided_calendar', row.recovery_uncertainty_note)
        self.assertNotIn('provisional calendar', row.recovery_uncertainty_note)
        self.assertEqual((row.recovery_days, row.confirmation_days), (2, 4))
        self.assertEqual(row.net_shortfall_eligible, 100)
        self.assertEqual(row.recovery_observed_days, 6)
        self.assertEqual(row.observation_holiday_days, 0)
        self.assertEqual(row.observation_nonholiday_unavailable_days, 0)
        self.assertAlmostEqual(row.net_shortfall_rate_eligible, 100/700)
        d.loc[6, 'complete_group_coverage'] = False
        row = industry_metrics(d, events).iloc[0]
        self.assertFalse(row.complete_eligible_window)
        self.assertTrue(pd.isna(row.net_shortfall_eligible))
        self.assertEqual(row.recovery_observed_days, 5)
        self.assertEqual(row.observation_nonholiday_unavailable_days, 1)

    def test_stability_counts_unrankable_scenarios_in_denominator(self):
        d = pd.DataFrame({'event_id': 'E', 'region': 'R', 'industry': 'A', 'scope': 'primary',
                          'priority_tier': [1, 2, np.nan],
                          'review_queue': ['ranked_candidate', 'ranked_candidate', 'data_incomplete']})
        row = stability_table(d).iloc[0]
        self.assertEqual((row.scenarios, row.rankable_scenarios), (3, 2))
        self.assertAlmostEqual(row.first_tier_fraction_all_scenarios, 1/3)


if __name__ == '__main__':
    unittest.main()
