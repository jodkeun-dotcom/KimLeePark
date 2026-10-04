import unittest
from unittest import mock
import pandas as pd
from scripts import label_weather_events
from scripts.label_weather_events import add_features, apparent_temp_summer, event_windows, group_events

D = pd.Timestamp


class WeatherEventTests(unittest.TestCase):
    def frame(self, temps, rain=None, snow=None, start='2025-07-10'):
        # 최소습도 50%에서 최고기온 34 → 체감 33.5(폭염), 36 → 35.4(강한 폭염), 20 → 비사건
        n = len(temps)
        return pd.DataFrame(dict(
            date=pd.date_range(start, periods=n), temp_max_c=temps, humidity_min_pct=[50] * n,
            humidity_avg_pct=[70] * n, precip_mm=rain or [None] * n, new_snow_max_cm=snow or [None] * n))

    def test_apparent_temp_rises_with_humidity(self):
        self.assertLess(apparent_temp_summer(33, 30), apparent_temp_summer(33, 70))

    def test_gap_up_to_two_days_merges(self):
        # 사건일 사이 비사건일 2일 → 병합, 3일 → 분리
        df = add_features(self.frame([36, 20, 20, 36, 20, 20, 20, 36], rain=[None, 90] + [None] * 6))
        events = group_events(df)
        heat = events[events.type == '폭염']
        self.assertEqual(heat.event_id.tolist(), ['HEAT01', 'HEAT02'])
        self.assertEqual(heat.duration_days.tolist(), [4, 1])
        self.assertEqual(heat.event_days.tolist(), [2, 1])
        rain = events[events.type == '호우']
        self.assertEqual(rain.analysis_role.tolist(), ['case_study'])

    def test_severe_heatwave_is_parent_attribute(self):
        # 강한 폭염은 폭염 사건 내부의 강도 특성: 사례연구로 두고 부모 사건에 일수를 남긴다
        events = group_events(add_features(self.frame([20] * 8 + [34, 36, 34, 20])))
        severe = events[events.type == '강한 폭염'].iloc[0]
        self.assertEqual((severe.parent_event_id, severe.analysis_role), ('HEAT01', 'case_study'))
        self.assertEqual(events.set_index('event_id').loc['HEAT01', 'severe_event_days'], 1)

    def test_baseline_before_period_excluded(self):
        df = self.frame([36, 20])
        df['date'] = pd.date_range('2025-07-03', periods=2)
        events = group_events(add_features(df))
        heat = events[events.event_id == 'HEAT01'].iloc[0]
        self.assertEqual(heat.analysis_role, 'excluded')
        self.assertIn('베이스라인', heat.exclude_reason)

    def test_no_snow_data_row(self):
        events = group_events(add_features(self.frame([20, 20])))
        snow = events[events.type == '폭설'].iloc[0]
        self.assertEqual((snow.event_id, snow.analysis_role), ('SNOW_NA', 'excluded'))

    def test_missing_snow_is_not_false(self):
        df = add_features(self.frame([20, 20], snow=[None, 6]))
        self.assertTrue(pd.isna(df.is_heavy_snow.iloc[0]))
        self.assertTrue(df.is_heavy_snow.iloc[1])

    def test_windows_are_7_before_and_14_after(self):
        events = group_events(add_features(self.frame([36, 36, 20])))
        windows = event_windows(events[events.event_id == 'HEAT01'])
        self.assertEqual(set(windows.analysis_role), {'statistical'})
        counts = windows.groupby('window').size()
        self.assertEqual((counts['baseline'], counts['event'], counts['observation']), (7, 2, 14))
        self.assertEqual(windows[windows.window == 'baseline'].date.max(), pd.Timestamp('2025-07-09'))

    def test_severe_inside_heatwave_observes_after_parent_ends(self):
        # (a) 7/7~7/9 폭염 중 7/8만 강한 폭염: 강한 폭염은 statistical이 아니고, 폭염이 이어지는 7/9는 관찰 +1일이 아님
        temps = [20] * 6 + [34, 36, 34] + [20] * 22          # 7/1~7/31
        events = group_events(add_features(self.frame(temps, start='2025-07-01')))
        severe = events[events.type == '강한 폭염'].iloc[0]
        self.assertEqual((severe.start_date, severe.parent_event_id), (D('2025-07-08'), 'HEAT01'))
        self.assertNotEqual(severe.analysis_role, 'statistical')
        obs = event_windows(events).query("event_id == @severe.event_id and window == 'observation'")
        self.assertNotIn(D('2025-07-09'), set(obs.date))
        self.assertEqual(obs.loc[obs.day_offset == 1, 'date'].item(), D('2025-07-10'))

    def test_observation_cut_at_next_event(self):
        # (b) 7/17 폭염 후 관찰기간 안 7/21에 다음 폭염 → 7/18~7/20 3일로 절단, MIN_DAYS 미달이면 case_study
        temps = [20] * 7 + [34] + [20] * 3 + [34] + [20] * 20   # 7/10~8/10
        events = group_events(add_features(self.frame(temps))).set_index('event_id')
        first = events.loc['HEAT01']
        self.assertEqual(first.observation_end_effective, D('2025-07-20'))
        self.assertEqual(first.observation_days_effective, 3)
        self.assertEqual(first.analysis_role, 'case_study')
        self.assertIn('관찰기간이 HEAT02(7/21)에서 절단되어 3일', first.exclude_reason)
        obs = event_windows(events.reset_index()).query("event_id == 'HEAT01' and window == 'observation'")
        self.assertEqual((obs.is_effective.sum(), (~obs.is_effective).sum()), (3, 11))
        # 기준값을 낮추면 같은 사건이 정식 비교 대상이 된다 (팀 조정용 상수)
        with mock.patch.object(label_weather_events, 'MIN_DAYS', 3):
            relaxed = group_events(add_features(self.frame(temps))).set_index('event_id')
        self.assertEqual(relaxed.loc['HEAT01', 'analysis_role'], 'statistical')

    def test_rain_day_dropped_from_baseline(self):
        # (c) 폭염 7/17의 베이스라인 7/10~7/16 안 호우일 7/13은 베이스라인 평균 날짜에서 빠진다
        temps = [20] * 7 + [34] + [20] * 24
        rain = [None] * 3 + [90] + [None] * 28
        events = group_events(add_features(self.frame(temps, rain=rain)))
        heat = events.set_index('event_id').loc['HEAT01']
        self.assertEqual(heat.baseline_days_effective, 6)
        base = event_windows(events).query("event_id == 'HEAT01' and window == 'baseline'")
        self.assertEqual(len(base), 7)
        self.assertNotIn(D('2025-07-13'), set(base[base.is_effective].date))
        self.assertEqual(base.set_index('date').loc[D('2025-07-13'), 'overlap_event_id'], 'RAIN01')


if __name__ == '__main__':
    unittest.main()
