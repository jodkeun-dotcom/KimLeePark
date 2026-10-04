import unittest
import pandas as pd
from scripts.join_data import join_daily, join_monthly


class JoinTests(unittest.TestCase):
    def setUp(self):
        self.card = pd.DataFrame(dict(date=['2025-07-01']*2, region=['가상지역']*2, industry=['A','B'], age=['20대']*2, amount=[10,20], transactions=[1,2]))
        self.weather = pd.DataFrame(dict(date=['2025-07-01'], region=['가상지역'], temperature=[None]))
        self.calendar = pd.DataFrame(dict(date=['2025-07-01'],is_holiday=[0]))

    def test_totals_and_missing_measure_preserved(self):
        result = join_daily(self.card,self.weather,self.calendar)
        self.assertEqual(len(result),2)
        self.assertEqual(result.amount.sum(),30)
        self.assertTrue(result.temperature.isna().all())

    def test_duplicate_weather_rejected(self):
        with self.assertRaises(ValueError):
            join_daily(self.card,pd.concat([self.weather,self.weather]),self.calendar)

    def test_missing_calendar_rejected(self):
        with self.assertRaises(ValueError):
            join_daily(self.card,self.weather,self.calendar.iloc[:0])

    def test_missing_weather_rejected(self):
        with self.assertRaises(ValueError):
            join_daily(self.card,self.weather.iloc[:0],self.calendar)

    def test_monthly_mapping_gate_and_multiple_scopes(self):
        card = pd.DataFrame(dict(month=['202507'],region=['가상지역'],age=['20대'],amount=[30]))
        skt = pd.DataFrame(dict(month=['202507']*2,prefix=['00000']*2,age=['20대']*2,scope=['all_observed','common_6months'],grid_value_sum=[5,4]))
        mapping = pd.DataFrame(dict(prefix=['00000'],region=['가상지역'],status=['pending'],source=['가상 테스트']))
        with self.assertRaises(ValueError):
            join_monthly(card,skt,mapping)
        mapping['status']='confirmed'
        result=join_monthly(card,skt,mapping)
        self.assertEqual(len(result),2)
        self.assertEqual(result.grid_value_sum.tolist(),[5,4])


if __name__=='__main__':
    unittest.main()
