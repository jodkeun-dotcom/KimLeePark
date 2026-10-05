import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from compare_recovery_definitions import compare
from prepare_sales_handoff import KEY


def fixture():
    rows = []
    for day in range(13, 18):
        rows.append(dict(event_id='E', region='R', industry='A', age='ALL',
                         window_start='2025-08-13', window_end='2025-08-17',
                         date=f'2025-08-{day}', window='event' if day == 13 else 'observation',
                         day_offset=day-13, amount=50. if day == 13 else 100.,
                         prediction=np.nan if day == 15 else 100.,
                         complete_group_coverage=day != 15, is_holiday=day == 15,
                         recovery_threshold=.95, consecutive_days=3))
    curves = pd.DataFrame(rows)
    legacy = curves[KEY].iloc[:1].copy()
    legacy['recovery_status'] = 'insufficient_data'
    legacy['recovery_days'] = np.nan
    return curves, legacy


class Tests(unittest.TestCase):
    def test_holiday_skip_is_review_only_and_preserves_calendar_offset(self):
        curves, legacy = fixture()
        detail, summary = compare(curves, legacy)
        by = detail.set_index('profile')
        self.assertEqual(by.loc['complete_groups_break', 'recovery_status'], 'censored')
        self.assertEqual(by.loc['complete_groups_skip_holidays', 'recovery_status'], 'recovered')
        self.assertEqual(by.loc['complete_groups_skip_holidays', 'recovery_days'], 1)
        self.assertEqual(by.loc['complete_groups_skip_holidays', 'skipped_holiday_days'], 1)
        self.assertIn('not_for_priority', by.loc['complete_groups_skip_holidays', 'recovery_uncertainty_note'])
        self.assertTrue(summary.total.eq(1).all())

    def test_nonholiday_missing_still_breaks_streak(self):
        curves, legacy = fixture()
        curves.loc[curves.date.eq('2025-08-16'), ['amount', 'complete_group_coverage']] = [np.nan, False]
        detail, _ = compare(curves, legacy)
        row = detail.set_index('profile').loc['complete_groups_skip_holidays']
        self.assertEqual(row.recovery_status, 'insufficient_data')

    def test_partial_groups_separated_from_complete_groups(self):
        curves, legacy = fixture()
        curves['is_holiday'] = False
        curves.loc[curves.window.eq('observation'), 'prediction'] = 100.
        curves.loc[curves.window.eq('observation'), 'complete_group_coverage'] = False
        detail, _ = compare(curves, legacy)
        by = detail.set_index('profile')
        self.assertEqual(by.loc['paired_partial_break', 'recovery_status'], 'recovered')
        self.assertEqual(by.loc['complete_groups_break', 'recovery_status'], 'insufficient_data')

    def test_partial_event_rejects_complete_group_claim(self):
        curves, legacy = fixture()
        curves.loc[curves.window.eq('event'), 'complete_group_coverage'] = False
        detail, _ = compare(curves, legacy)
        row = detail.set_index('profile').loc['complete_groups_break']
        self.assertTrue(pd.isna(row.event_ratio))
        self.assertEqual(row.recovery_status, 'insufficient_data')

    def test_mixed_windows_duplicates_and_rules_rejected(self):
        curves, legacy = fixture()
        with self.assertRaises(ValueError):
            compare(pd.concat([curves, curves.iloc[:1]]), legacy)
        legacy['window_end'] = '2025-08-18'
        with self.assertRaises(ValueError):
            compare(curves, legacy)
        curves, legacy = fixture()
        with self.assertRaises(ValueError):
            compare(curves, legacy, threshold=.9)

    def test_missing_calendar_and_gaps_rejected(self):
        curves, legacy = fixture()
        with self.assertRaises(ValueError):
            compare(curves.drop(columns='is_holiday'), legacy)
        with self.assertRaises(ValueError):
            compare(curves.iloc[:-1], legacy)
        with self.assertRaises(ValueError):
            compare(curves, legacy.drop(columns='recovery_status'))


if __name__ == '__main__':
    unittest.main()
