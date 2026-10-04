import unittest
import numpy as np
import pandas as pd
from scripts.compute_recovery import compute, expected_sales, load_daily, recovery_day
from scripts.label_weather_events import add_features, event_windows, group_events

D = pd.Timestamp


def weather(heat_days):
    dates = pd.date_range('2025-07-01', '2025-09-30')
    return pd.DataFrame(dict(
        date=dates, temp_max_c=[34 if d in heat_days else 20 for d in dates], humidity_min_pct=50,
        humidity_avg_pct=70, precip_mm=np.nan, new_snow_max_cm=np.nan))


def card(amounts):
    """{업종: {날짜: 금액}} 외 날짜는 100. 연령 30대 한 그룹."""
    dates = pd.date_range('2025-07-01', '2025-09-30')
    rows = [dict(date=d, region='강원 춘천시', industry=i, age='30대', amount=a.get(d, 100))
            for i, a in amounts.items() for d in dates]
    return pd.DataFrame(rows)


class RecoveryDayTests(unittest.TestCase):
    def obs(self, ratios):
        return pd.DataFrame({'date': pd.date_range('2025-08-04', periods=len(ratios)),
                             'day_offset': range(1, len(ratios) + 1), 'ratio': ratios})

    def test_first_day_of_consecutive_run(self):
        status, day, date = recovery_day(self.obs([0.8, 0.96, 0.97, 0.5, 0.96, 0.96, 0.99]), 0.95, 3)
        self.assertEqual((status, day, date), ('recovered', 5, D('2025-08-08')))

    def test_missing_day_breaks_run_and_is_not_filled(self):
        status, day, _ = recovery_day(self.obs([0.96, np.nan, 0.97, 0.98]), 0.95, 3)
        self.assertEqual((status, day), ('censored', None))

    def test_too_few_observed_days_is_insufficient(self):
        status, _, _ = recovery_day(self.obs([np.nan, 0.7, np.nan]), 0.95, 3)
        self.assertEqual(status, 'insufficient_data')


class RecoveryComputeTests(unittest.TestCase):
    def setUp(self):
        heat = {D('2025-08-01'), D('2025-08-02'), D('2025-08-03'), D('2025-08-10')}
        self.events = group_events(add_features(weather(heat)))
        self.windows = event_windows(self.events)
        drop = {d: 50 for d in pd.date_range('2025-08-01', '2025-08-03')}
        self.daily = card({
            '한식': {**drop, D('2025-08-04'): 60, D('2025-08-05'): 60},            # 8/6부터 회복
            '노래방': {**drop, **{d: 50 for d in pd.date_range('2025-08-04', '2025-08-09')}},  # 다음 사건 전 미회복
            '편의점': {D('2025-07-29'): 1000},                                     # 베이스라인 이상치만 있고 감소 없음
        })

    def metric(self, metrics, industry, window_type='effective', age='30대'):
        m = metrics[(metrics.industry == industry) & (metrics.age == age) & (metrics.window_type == window_type)
                    & (metrics.event_id == 'HEAT01')]
        return m.iloc[0]

    def test_recovery_status_and_days(self):
        _, metrics = compute(load_daily_frame(self.daily), self.events, self.windows)
        self.assertEqual((self.metric(metrics, '한식').recovery_status, self.metric(metrics, '한식').recovery_days),
                         ('recovered', 3))
        # 효과 관찰기간은 다음 사건(8/10) 전날 8/9에서 절단 → 회복일을 채우지 않고 censored
        self.assertEqual(self.metric(metrics, '노래방').recovery_status, 'censored')
        self.assertEqual(str(self.metric(metrics, '노래방').window_end), '2025-08-09')
        # 명목 관찰기간(민감도용)에서는 다음 사건 이후 회복이 잡히며 그 사실을 note에 남긴다
        nominal = self.metric(metrics, '노래방', 'nominal')
        self.assertEqual(nominal.recovery_status, 'recovered')
        self.assertIn('명목 관찰기간', nominal.recovery_uncertainty_note)
        self.assertEqual(self.metric(metrics, '편의점').recovery_status, 'no_decline')

    def test_industry_total_row(self):
        _, metrics = compute(load_daily_frame(self.daily), self.events, self.windows)
        self.assertEqual(self.metric(metrics, '한식', age='ALL').recovery_days, 3)

    def test_expected_uses_only_prior_non_event_days(self):
        daily = load_daily_frame(self.daily)
        spans = [(D('2025-08-01'), D('2025-08-03')), (D('2025-08-10'), D('2025-08-10'))]
        exp = expected_sales(daily, D('2025-08-01'), spans, pd.date_range('2025-08-01', '2025-08-17'))
        hansik = exp[(exp.industry == '한식') & (exp.age == '30대')]
        # 사건일(50)·사건 이후 값은 학습에 쓰지 않으므로 예상 매출은 평상시 100
        self.assertTrue(np.allclose(hansik.expected.dropna(), 100))
        # 잠정 공휴일 8/15는 예측하지 않는다
        self.assertTrue(hansik.set_index('date').expected.isna()[D('2025-08-15')])


def load_daily_frame(df):
    """load_daily와 같은 검사·ALL 집계를 메모리 자료에 적용한다."""
    import io
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return load_daily(buf)


if __name__ == '__main__':
    unittest.main()
