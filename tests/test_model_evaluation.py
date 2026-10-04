import unittest

import numpy as np
import pandas as pd

from scripts.evaluate_models import attach_actuals, features, forecast_split, score_frame
from scripts.prepare_model_comparison import CATEGORICAL, NUMERIC
from scripts.prepare_support_inputs import compare_industry_aggregation, prepare_inputs


class ModelEvaluationTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range('2025-07-01', '2025-12-31')
        self.card = pd.DataFrame({'date': dates, 'region': '강원 춘천시', 'industry': '한식',
                                  'age': '20대', 'amount': 100 + dates.dayofweek * 10})
        self.events = pd.DataFrame({'start_date': pd.to_datetime(['2025-07-15']),
                                    'end_date': pd.to_datetime(['2025-07-17'])})

    def test_future_targets_and_future_event_do_not_change_forecasts(self):
        original, audit = forecast_split(self.card, self.events, 'validation')
        changed = self.card.copy()
        changed.loc[changed.date.ge('2025-09-01'), 'amount'] *= 10000
        future_event = pd.DataFrame({'start_date': pd.to_datetime(['2025-09-10']),
                                     'end_date': pd.to_datetime(['2025-09-20'])})
        second, _ = forecast_split(changed, pd.concat([self.events, future_event]), 'validation')
        pd.testing.assert_frame_equal(original, second)
        self.assertEqual(audit['latest_training_date'], '2025-08-31')
        self.assertEqual(audit['shared_training_rows'], 58)  # 62 days - 3 event days - Aug 15

    def test_unseen_group_is_reported_not_silently_dropped(self):
        forecast, _ = forecast_split(self.card, self.events, 'validation')
        added = self.card.loc[self.card.date.eq('2025-09-01')].assign(industry='new')
        joined = attach_actuals(pd.concat([self.card, added]), forecast, 'validation')
        self.assertEqual(len(joined), 31)
        new = joined.loc[joined.industry.eq('new')].iloc[0]
        self.assertEqual(new.evaluation_status, 'unseen_training_group')
        self.assertFalse(new.comparison_eligible)

    def test_scoring_and_zero_targets_keep_same_keys(self):
        f = self.card.iloc[:2].copy()
        f['amount'] = [0, 0]
        f['baseline_prediction'] = [1, 3]
        f['ai_prediction'] = [0, 2]
        scores = score_frame(f).set_index('model')
        self.assertEqual(scores.loc['shared_baseline', 'mae'], 2)
        self.assertEqual(scores.loc['hist_gradient_boosting', 'mae'], 1)
        self.assertTrue(scores.wape.isna().all())

    def test_features_only_use_declared_known_inputs(self):
        a = features(self.card)
        changed = self.card.assign(amount=9e12, transactions=9e12, skt=9e12, temperature=999)
        pd.testing.assert_frame_equal(a, features(changed))
        self.assertEqual(list(a.columns), CATEGORICAL + NUMERIC)

    def test_forecast_training_values_match_shared_weekday_baseline(self):
        prediction, _ = forecast_split(self.card, self.events, 'validation')
        expected = 100 + prediction.date.dt.dayofweek * 10
        np.testing.assert_allclose(prediction.baseline_prediction, expected)
        self.assertTrue(prediction.comparison_eligible.all())


class IndustryConsistencyTests(unittest.TestCase):
    def test_partial_shortfall_remains_a_diagnostic_not_full_loss(self):
        keys = {'event_id': 'E', 'region': 'R', 'industry': 'A', 'age': '20대',
                'window_start': '2025-08-01', 'window_end': '2025-08-14'}
        sales = pd.DataFrame([{**keys, 'window_type': 'effective', 'baseline_mode': 'fixed_pre_event',
                               'missing_policy': 'exclude_missing', 'model_id': 'weekday_mean',
                               'decline_rate_event': .1, 'gross_shortfall_full': np.nan,
                               'net_shortfall_full': np.nan, 'net_shortfall_rate_full': np.nan,
                               'analysis_role': 'case_study', 'scope': 'primary', 'coverage': .5,
                               'eligible_coverage': .5, 'holiday_excluded_days': 0,
                               'complete_window': False, 'paired_days': 7, 'window_days': 14,
                               'gross_shortfall_paired': 100, 'net_shortfall_paired': 50,
                               'net_shortfall_eligible': np.nan}])
        recovery = pd.DataFrame([{**keys, 'recovery_days': np.nan, 'recovery_status': 'censored',
                                  'recovery_uncertainty_note': 'cut at next event'}])
        result = prepare_inputs(sales, recovery)
        self.assertTrue(result.gross_shortfall.isna().all())
        self.assertEqual(result.gross_shortfall_paired.iloc[0], 100)
        self.assertTrue(result.support_priority.isna().all())
        self.assertTrue(result.recovery_days.isna().all())
        with self.assertRaises(ValueError):
            prepare_inputs(sales, recovery.assign(window_end='2025-08-15'))

    def test_different_pairs_are_flagged_and_missing_is_not_zero(self):
        keys = {'event_id': ['E', 'E'], 'date': ['2025-08-01', '2025-08-02'],
                'region': ['R', 'R'], 'industry': ['A', 'A']}
        paired = pd.DataFrame({**keys, 'amount_paired': [10, np.nan], 'prediction_paired': [20, np.nan]})
        recovery = pd.DataFrame({**keys, 'age': 'ALL', 'is_effective': True,
                                 'amount': [10, 0], 'expected': [21, np.nan]})
        result = compare_industry_aggregation(paired, recovery)
        self.assertEqual(result.actual_agrees.tolist(), [True, False])
        self.assertTrue(result.review_required.all())
        with self.assertRaises(ValueError):
            compare_industry_aggregation(pd.concat([paired, paired.iloc[:1]]), recovery)


if __name__ == '__main__':
    unittest.main()
