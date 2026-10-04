import unittest
import numpy as np
import pandas as pd
from scripts import prepare_priority
from scripts.compute_recovery import (HANDOFF_KEY, HANDOFF_RECOVERY, compute, expected_sales, handoff, load_daily,
                                      recovery_day)
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

    def test_handoff_keys_unique_when_windows_coincide(self):
        # HEAT02(8/10)는 다음 사건이 없어 effective·nominal 끝이 같다 → 비교용 metrics에서는 공통 키가 겹친다
        _, metrics = compute(load_daily_frame(self.daily), self.events, self.windows)
        both = metrics[metrics.event_id == 'HEAT02']
        self.assertEqual(set(both.window_type), {'effective', 'nominal'})
        self.assertTrue(both.duplicated(HANDOFF_KEY).any())
        out = handoff(metrics)
        self.assertEqual(list(out.columns), HANDOFF_KEY + HANDOFF_RECOVERY)
        self.assertFalse(out.duplicated(HANDOFF_KEY).any())
        self.assertEqual(len(out), (metrics.window_type == 'effective').sum())
        # 주 결과(effective) 값만 담는다: HEAT01 노래방은 절단 창에서 censored (nominal에서는 recovered)
        row = out[(out.event_id == 'HEAT01') & (out.industry == '노래방') & (out.age == '30대')].iloc[0]
        self.assertEqual((row.window_end, row.recovery_status), ('2025-08-09', 'censored'))

    def test_handoff_joins_with_priority_table(self):
        # 결합 형식이 scripts/prepare_priority.py와 같고, 같은 키의 매출 지표와 1:1로 결합된다
        self.assertEqual((HANDOFF_KEY, HANDOFF_RECOVERY), (prepare_priority.KEY, prepare_priority.RECOVERY))
        _, metrics = compute(load_daily_frame(self.daily), self.events, self.windows)
        recovery = roundtrip(handoff(metrics))
        sales = recovery[HANDOFF_KEY].assign(**{c: pd.NA for c in prepare_priority.SALES})
        joined = prepare_priority.join_metrics(sales, recovery)
        self.assertEqual(len(joined), len(recovery))
        # 회귀: 두 창을 담은 metrics에서 열만 추리면 키 중복으로 결합이 중단된다
        with self.assertRaisesRegex(ValueError, 'recovery: missing/duplicate keys'):
            prepare_priority.join_metrics(sales, roundtrip(metrics[HANDOFF_KEY + HANDOFF_RECOVERY]))


def roundtrip(df):
    """prepare_priority.main()처럼 CSV로 저장 후 키를 문자열로 읽는다."""
    import io
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return pd.read_csv(buf, dtype={k: str for k in HANDOFF_KEY})


def load_daily_frame(df):
    """load_daily와 같은 검사·ALL 집계를 메모리 자료에 적용한다."""
    import io
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return load_daily(buf)


if __name__ == '__main__':
    unittest.main()
