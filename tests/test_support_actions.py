import unittest

import numpy as np
import pandas as pd

from scripts.support_actions import add_support_actions


class SupportActionTests(unittest.TestCase):
    def rows(self):
        return pd.DataFrame({
            'event_id': 'E', 'region': 'R', 'industry': list('ABCDEF'), 'age': 'ALL', 'scope': 'primary',
            'window_start': '2025-08-01', 'window_end': '2025-08-07',
            'complete_eligible_window': [False, True, True, True, True, True],
            'net_shortfall_eligible': [np.nan, 10, 10, 10, 10, -5],
            'net_shortfall_rate_eligible': [np.nan, .1, .1, .1, .1, -.05],
            'gross_shortfall_eligible': [np.nan, 15, 15, 15, 15, 15],
            'recovery_status': ['recovered', 'insufficient_data', 'censored', 'recovered', 'no_decline', 'censored'],
            'recovery_days': [2., np.nan, np.nan, 2., np.nan, np.nan],
            'priority_tier': [np.nan, np.nan, np.nan, 1., np.nan, np.nan],
            'scenario': 'base',
        })

    def test_every_row_retained_without_reassigning_financial_values_or_ranks(self):
        source = self.rows()
        out = add_support_actions(source)
        pd.testing.assert_frame_equal(out[source.columns], source)
        self.assertEqual(out.support_review_group.tolist(), ['sales_data_incomplete',
            'shortfall_recovery_insufficient', 'shortfall_recovery_unconfirmed', 'shortfall_recovered',
            'shortfall_below_decline_threshold', 'no_positive_net_shortfall'])
        self.assertTrue(out.support_review_order.eq('unordered_categories_not_funding_rank').all())
        self.assertTrue(out.suggested_action.notna().all())
        self.assertTrue(out.assessment_as_of.eq(out.window_end).all())

    def test_censored_is_visible_with_no_fabricated_recovery_day_or_rank(self):
        row = add_support_actions(self.rows()).iloc[2]
        self.assertTrue(pd.isna(row.recovery_days))
        self.assertTrue(pd.isna(row.priority_tier))
        self.assertIn('단기 지원 필요성 검토', row.suggested_action)
        self.assertIn('관찰 절단', row.suggested_start_condition)
        self.assertIn('실제 회복시점 미확정', row.support_review_caution)

    def test_incomplete_monetary_values_never_mean_no_shortfall(self):
        frame = self.rows()
        frame.loc[3, 'net_shortfall_eligible'] = np.nan
        frame.loc[0, ['net_shortfall_eligible', 'net_shortfall_rate_eligible', 'gross_shortfall_eligible']] = 0
        out = add_support_actions(frame)
        self.assertEqual(out.loc[0, 'support_review_group'], 'sales_data_incomplete')
        self.assertEqual(out.loc[3, 'support_review_group'], 'sales_data_incomplete')

    def test_recovery_insufficient_keeps_known_positive_monetary_evidence(self):
        frame = self.rows().assign(decline_rate=np.nan)
        row = add_support_actions(frame).iloc[1]
        self.assertEqual(row.net_shortfall_eligible, 10)
        self.assertEqual(row.support_review_group, 'shortfall_recovery_insufficient')

    def test_nonpositive_net_does_not_erase_gross_shortfall_or_censoring(self):
        row = add_support_actions(self.rows()).iloc[5]
        self.assertEqual(row.recovery_status, 'censored')
        self.assertEqual(row.gross_shortfall_eligible, 15)
        self.assertIn('지원 제외 확정이 아님', row.support_review_caution)

    def test_no_decline_does_not_become_recovered(self):
        row = add_support_actions(self.rows()).iloc[4]
        self.assertEqual(row.support_review_group, 'shortfall_below_decline_threshold')
        self.assertTrue(pd.isna(row.priority_tier))
        self.assertIn('회복 확인을 뜻하지 않음', row.support_review_caution)

    def test_duplicate_keys_and_unknown_status_rejected_but_scenarios_retained(self):
        a = self.rows()
        with self.assertRaises(ValueError):
            add_support_actions(pd.concat([a, a], ignore_index=True))
        b = pd.concat([a, a.assign(scenario='alternative')], ignore_index=True)
        self.assertEqual(len(add_support_actions(b)), 12)
        with self.assertRaisesRegex(ValueError, 'unknown recovery'):
            add_support_actions(a.assign(recovery_status='unsupported'))

    def test_bad_numeric_values_rejected_and_boolean_strings_parsed(self):
        a = self.rows()
        a['complete_eligible_window'] = a.complete_eligible_window.astype(str)
        self.assertEqual(add_support_actions(a).iloc[0].support_review_group, 'sales_data_incomplete')
        a.loc[2, 'net_shortfall_rate_eligible'] = -.1
        with self.assertRaisesRegex(ValueError, 'sign differs'):
            add_support_actions(a)
        a = self.rows()
        a.loc[2, 'net_shortfall_eligible'] = np.inf
        with self.assertRaisesRegex(ValueError, 'invalid eligible'):
            add_support_actions(a)


if __name__ == '__main__':
    unittest.main()
