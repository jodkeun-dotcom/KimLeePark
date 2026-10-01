import unittest
import pandas as pd
from scripts.label_weather_events import add_features, apparent_temp_summer, event_windows, group_events


class WeatherEventTests(unittest.TestCase):
    def frame(self, temps, rain=None, snow=None):
        n = len(temps)
        return pd.DataFrame(dict(
            date=pd.date_range('2025-07-10', periods=n), temp_max_c=temps, humidity_min_pct=[50] * n,
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


if __name__ == '__main__':
    unittest.main()
