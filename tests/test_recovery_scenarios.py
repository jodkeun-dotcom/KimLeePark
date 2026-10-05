import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import compare_recovery_scenarios as sc
import label_weather_events as lw
import prepare_sales_baseline as baseline
from test_sales_handoff import inputs

D = pd.Timestamp


def weather(temps, start='2025-07-10'):
    # 최소습도 50%에서 최고기온 34 → 체감 33.5(폭염), 20 → 비사건
    n = len(temps)
    return lw.add_features(pd.DataFrame(dict(
        date=pd.date_range(start, periods=n), temp_max_c=temps, humidity_min_pct=[50] * n,
        humidity_avg_pct=[70] * n, precip_mm=[None] * n, new_snow_max_cm=[None] * n)))


def heat(events):
    return events[events.type.eq('폭염')]


class EventScenarioTests(unittest.TestCase):
    def test_default_options_match_module_defaults(self):
        df = weather([20] * 7 + [34] + [20] * 3 + [34] + [20] * 20)
        default = lw.group_events(df)
        explicit = lw.group_events(df, lw.MAX_GAP_DAYS, lw.OBSERVATION_DAYS)
        pd.testing.assert_frame_equal(default, explicit)
        pd.testing.assert_frame_equal(lw.event_windows(default), lw.event_windows(explicit))

    def test_gap_three_merges_events(self):
        # 7/17, 7/21 폭염: 사이 비사건일 3일 → 기본(2일)은 두 사건, 3일이면 한 사건 7/17~7/21
        df = weather([20] * 7 + [34] + [20] * 3 + [34] + [20] * 20)
        self.assertEqual(heat(lw.group_events(df)).event_id.tolist(), ['HEAT01', 'HEAT02'])
        merged = heat(lw.group_events(df, max_gap_days=3))
        self.assertEqual(len(merged), 1)
        merged = merged.iloc[0]
        self.assertEqual((merged.event_id, merged.start_date, merged.end_date, merged.event_days),
                         ('HEAT01', D('2025-07-17'), D('2025-07-21'), 2))

    def test_observation_length_and_cut(self):
        # 7/17 폭염 하나: 관찰 7일이면 7/18~7/24, 21일이면 7/18~8/7. 다음 사건이 있으면 길이와 관계없이 그 전날 절단
        single = weather([20] * 7 + [34] + [20] * 30)
        for days in [7, 21]:
            ev = lw.group_events(single, observation_days=days).set_index('event_id').loc['HEAT01']
            self.assertEqual(ev.observation_end, D('2025-07-17') + pd.Timedelta(days=days))
            self.assertEqual(ev.observation_days_effective, days)
            obs = lw.event_windows(lw.group_events(single, observation_days=days)).query(
                "event_id == 'HEAT01' and window == 'observation'")
            self.assertEqual(len(obs), days)
        two = weather([20] * 7 + [34] + [20] * 3 + [34] + [20] * 30)
        for days in [7, 14, 21]:
            ev = lw.group_events(two, observation_days=days).set_index('event_id').loc['HEAT01']
            self.assertEqual((ev.observation_end_effective, ev.observation_days_effective), (D('2025-07-20'), 3))

    def test_invalid_scenario_values_rejected(self):
        df = weather([20, 34, 20])
        with self.assertRaises(ValueError):
            lw.group_events(df, max_gap_days=-1)
        with self.assertRaises(ValueError):
            lw.group_events(df, observation_days=0)
        with self.assertRaises(ValueError):
            sc.parse_scenario('S0:2')


def unit(event, industry, age, status, days=None, scenario='S0', threshold=0.95, run=3, event_end='2025-08-03'):
    return dict(event_id=event, region='R', industry=industry, age=age, window_start='2025-08-01',
                event_end=event_end, scenario=scenario, threshold=threshold, consecutive_days=run,
                recovery_status=status, recovery_days=days, scope='ALL' if age == 'ALL' else 'age')


class ComparisonTests(unittest.TestCase):
    def grid(self):
        rows = [
            unit('E1', 'A', 'ALL', 'censored'), unit('E1', 'B', 'ALL', 'no_decline'), unit('E1', 'A', '20대', 'recovered', 2),
            unit('E1', 'A', 'ALL', 'recovered', 5, run=2), unit('E1', 'B', 'ALL', 'no_decline', run=2),
            unit('E1', 'A', '20대', 'recovered', 1, run=2),
            # S3: 사건 종료일이 달라진 병합 사건은 같은 단위로 대응되지 않는다
            unit('E1', 'A', 'ALL', 'insufficient_data', scenario='S3', event_end='2025-08-07'),
        ]
        return pd.DataFrame(rows)

    def test_status_changes_against_reference(self):
        changes, transitions, unmatched = sc.against_reference(self.grid(), ('S0', 0.95, 3))
        run2 = changes[(changes.consecutive_days == 2) & (changes.scope == 'ALL')].iloc[0]
        self.assertEqual((run2.matched, run2.changed), (2, 1))
        moved = transitions.iloc[0]
        self.assertEqual((moved.reference_status, moved.recovery_status, moved['count']), ('censored', 'recovered', 1))
        self.assertEqual(unmatched.scenario.tolist(), ['S3'])
        reference = changes[(changes.consecutive_days == 3) & (changes.scenario == 'S0')]
        self.assertTrue(reference.changed.eq(0).all())

    def test_stability_and_distribution(self):
        grid = self.grid()
        stable = sc.stability(grid, ('S0', 0.95, 3)).set_index(['comparison', 'unit_set', 'scope'])
        self.assertEqual(stable.loc[('criteria_only', 'all', 'ALL'), 'stable_units'], 1)
        self.assertEqual(stable.loc[('criteria_only', 'all', 'ALL'), 'units'], 2)
        self.assertEqual(stable.loc[('criteria_only', 'all', 'age'), 'stable_share'], 1.0)
        # 자료 부족이 아닌 기준 단위만 따로 센다
        self.assertEqual(stable.loc[('criteria_only', 'judgeable', 'ALL'), 'units'], 2)
        dist = sc.status_distribution(grid).set_index(sc.SETTING + ['scope'])
        self.assertEqual(dist.loc[('S0', 0.95, 3, 'ALL'), ['censored', 'no_decline', 'total']].tolist(), [1, 1, 2])

    def test_recovery_day_range_uses_recovered_rows_only(self):
        days = sc.recovery_day_range(self.grid()).set_index(sc.SETTING + ['scope'])
        self.assertEqual(days.loc[('S0', 0.95, 2, 'ALL'), ['recovered', 'min_days', 'max_days']].tolist(), [1, 5, 5])
        self.assertNotIn(('S3', 0.95, 3, 'ALL'), days.index)

    def test_recovery_grid_runs_every_rule(self):
        d, e = inputs()
        d['analysis_role'] = 'case_study'
        d['phase'] = np.where(d.date.eq('2025-08-01'), 'event', 'observation')
        data = {'S0': (d, baseline.industry_daily(d), e, None)}
        grid = sc.recovery_grid(data, [('S0', 2, 14)], [0.9, 1.0], [1, 2])
        self.assertEqual(grid[sc.SETTING].drop_duplicates().shape[0], 4)
        self.assertEqual(set(grid.scope), {'ALL', 'age'})
        self.assertTrue(grid.recovery_status.isin(sc.STATUSES).all())
        with self.assertRaises(ValueError):
            sc.recovery_grid(data, [('S9', 2, 14)], [0.95], [3])


if __name__ == '__main__':
    unittest.main()
