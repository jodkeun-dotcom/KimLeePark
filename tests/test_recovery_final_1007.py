import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import plot_final_recovery_curves as fc
import review_recovery_rule_stability as rs


def sensitivity_frame(queue_for):
    """두 업종 × 18개 설정. queue_for(industry, model, threshold, run) → (review_queue, priority_tier)."""
    rows = []
    for industry in ['A', 'B']:
        for model in ['weekday_mean', 'weekday_median']:
            for threshold in rs.THRESHOLDS:
                for run in rs.RUNS:
                    queue, tier = queue_for(industry, model, threshold, run)
                    rows.append(dict(event_id='E1', region='R', industry=industry, scope='primary', age='ALL',
                                     model_id=model, recovery_threshold=threshold, consecutive_days=run,
                                     review_queue=queue, recovery_status='recovered', priority_tier=tier))
    return pd.DataFrame(rows)


def b_changes(industry, model, threshold, run):
    # A: 모든 설정에서 같은 상태. B: 기준(평균·0.95·3)은 순위 후보, 임계 1.00과 연속 4일에서는 회복 미확인
    if industry == 'A':
        return 'no_positive_net_shortfall', np.nan
    if threshold == 1.00 or run == 4:
        return 'recovery_unconfirmed_review', np.nan
    return 'ranked_candidate', 1


class RuleStabilityTests(unittest.TestCase):
    def test_reference_and_axes(self):
        units = rs.unit_stability(rs.load_frame(sensitivity_frame(b_changes))).set_index('industry')
        a, b = units.loc['A'], units.loc['B']
        self.assertEqual((a.rule_sensitivity, a.mean_rule_settings_differing), ('stable', 0))
        self.assertFalse(a.rank_sensitive)
        self.assertEqual(b.reference_review_queue, 'ranked_candidate')
        # 평균 기준선의 기준 외 8개 중 임계 1.00(3개) + 연속 4일(임계 0.90·0.95, 2개) = 5개가 다름 → high
        self.assertEqual((b.mean_rule_settings_differing, b.mean_rule_alternatives), (5, 8))
        self.assertEqual(b.rule_sensitivity, 'high')
        self.assertTrue(b.threshold_axis_changes)
        self.assertTrue(b.run_axis_changes)
        # 18개 중 순위 후보 = 평균·중앙값 각 4개(임계 0.90/0.95 × 연속 2/3)
        self.assertEqual((b.all_settings_ranked, b.all_settings_first_tier), (8, 8))
        self.assertTrue(b.rank_sensitive)
        self.assertFalse(b.median_same_rule_differs)

    def test_low_sensitivity_label(self):
        def one_change(industry, model, threshold, run):
            if industry == 'B' and model == 'weekday_mean' and threshold == 0.90 and run == 2:
                return 'below_decline_threshold', np.nan
            return 'no_positive_net_shortfall', np.nan
        units = rs.unit_stability(rs.load_frame(sensitivity_frame(one_change))).set_index('industry')
        self.assertEqual((units.loc['B', 'rule_sensitivity'], units.loc['B', 'mean_rule_settings_differing']),
                         ('low', 1))
        self.assertFalse(units.loc['B', 'threshold_axis_changes'])

    def test_summaries_have_counts_only(self):
        units = rs.unit_stability(rs.load_frame(sensitivity_frame(b_changes)))
        label, by_queue, axes = rs.summaries(units)
        self.assertEqual(label[['stable', 'low', 'high']].iloc[0].tolist(), [1, 0, 1])
        for frame in [label, by_queue, axes]:
            self.assertNotIn('industry', frame.columns)

    def test_incomplete_settings_rejected(self):
        frame = sensitivity_frame(b_changes)
        with self.assertRaises(ValueError):
            rs.load_frame(frame[frame.consecutive_days.ne(4)])
        with self.assertRaises(ValueError):
            rs.load_frame(frame.assign(age='20대'))


def curve_inputs(status='recovered', observed=5, recovery_days=2.0):
    """사건 2일 + 실제 관찰 observed일. 곡선·지표가 같은 기준(0.95·3일)과 관찰창을 갖는다."""
    dates = pd.date_range('2025-08-01', periods=2 + observed)
    start, end = dates[0].strftime('%Y-%m-%d'), dates[-1].strftime('%Y-%m-%d')
    rows = []
    for i, date in enumerate(dates):
        rows.append(dict(event_id='E1', region='R', industry='한식', age='ALL', date=date.strftime('%Y-%m-%d'),
                         window='event' if i < 2 else 'observation', day_offset=i - 1,
                         ratio=np.nan if i == 3 else 0.8 + 0.1 * i,
                         ratio_paired_exploratory=0.5 + 0.1 * i, is_holiday=i == 4,
                         window_start=start, window_end=end, recovery_threshold=0.95, consecutive_days=3))
    curves = pd.DataFrame(rows)
    metrics = pd.DataFrame([dict(event_id='E1', region='R', industry='한식', age='ALL', window_start=start,
                                 window_end=end, event_end='2025-08-02', observation_days=observed,
                                 observation_days_paired=observed - 1, event_ratio=0.85,
                                 recovery_status=status, recovery_days=recovery_days,
                                 recovery_threshold=0.95, consecutive_days=3)])
    return curves, metrics


class FinalCurveTests(unittest.TestCase):
    def test_panel_data_separates_partial_ratio_and_confirmation(self):
        curves, metrics = curve_inputs()
        data, threshold, run = fc.panel_data(curves, metrics, ['한식'])
        self.assertEqual((threshold, run), (0.95, 3))
        # 판정용 비율이 없는 날만 부분 연령 비율(탐색용)을 남긴다
        self.assertEqual(data.ratio_partial_only.notna().sum(), 1)
        self.assertTrue(data.loc[data.ratio.notna(), 'ratio_partial_only'].isna().all())
        # 연속 확인 완료일 = 회복 첫날 + 연속일수 − 1, 지표 쪽 window_end를 사용
        self.assertEqual(data.confirmation_day.iloc[0], 4)
        self.assertEqual(data.window_end.iloc[0], '2025-08-07')

    def test_short_window_caption_and_rule_checks(self):
        curves, metrics = curve_inputs(status='censored', observed=3, recovery_days=np.nan)
        data, threshold, run = fc.panel_data(curves, metrics, ['한식'])
        self.assertIn('제한적 창', fc.event_caption(data, threshold, run))
        mixed = pd.concat([curves, curves.assign(consecutive_days=2, date='2025-09-01')])
        with self.assertRaises(ValueError):
            fc.panel_data(mixed, metrics, ['한식'])
        with self.assertRaises(ValueError):
            fc.panel_data(curves, metrics.assign(industry='중식'), ['한식'])

    def test_mismatched_rule_or_window_rejected(self):
        # 리뷰 지적: 서로 다른 회복 기준·관찰창의 곡선과 지표를 합치면 그림 전에 실패해야 한다
        curves, metrics = curve_inputs()
        cases = {
            'rule': metrics.assign(recovery_threshold=0.90, consecutive_days=2),
            'window_end': metrics.assign(window_end='2025-08-09'),
            'event_end': metrics.assign(event_end='2025-08-03'),
            'observation_days': metrics.assign(observation_days=4),
            'region': metrics.assign(region='X'),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    fc.panel_data(curves, bad, ['한식'])
        extra = pd.concat([metrics, metrics.assign(event_id='E2')])
        with self.assertRaisesRegex(ValueError, 'different'):
            fc.panel_data(curves, extra, ['한식'])

    def test_plot_writes_figure(self):
        curves, metrics = curve_inputs()
        data, threshold, run = fc.panel_data(curves, metrics, ['한식'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'E1.png'
            fc.plot_event(data, threshold, run, path, ['한식'])
            self.assertGreater(path.stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
