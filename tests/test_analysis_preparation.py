import unittest

import numpy as np
import pandas as pd

from scripts.compare_monthly import index_july
from scripts.prepare_model_comparison import prepare_features, split_frames, paired_metrics, make_ai_model, CATEGORICAL, NUMERIC
from scripts.prepare_priority import KEY, SALES, RECOVERY, join_metrics


class AnalysisPreparationTests(unittest.TestCase):
    def test_index_is_independent_of_row_order_and_rejects_missing_month(self):
        s = pd.Series([60, 10, 20, 30, 40, 50], index=["202512", "202507", "202508", "202509", "202510", "202511"])
        self.assertEqual(index_july(s).loc["202507"], 100)
        self.assertEqual(index_july(s).loc["202512"], 600)
        with self.assertRaises(ValueError):
            index_july(s.drop("202508"))

    def test_split_boundary_and_unseen_group(self):
        dates = ["2025-07-01", "2025-08-31", "2025-09-01", "2025-09-30", "2025-10-01", "2025-12-31"]
        card = pd.DataFrame({"date": dates, "region": "강원 춘천시", "industry": ["A", "A", "B", "A", "A", "A"], "age": "20대", "amount": 100})
        f = prepare_features(card)
        tr, ev = split_frames(f, "validation")
        self.assertLess(tr.date.max(), ev.date.min())
        self.assertEqual(ev.seen_group_in_train.tolist(), [False, True])
        tr, ev = split_frames(f, "holdout")
        self.assertEqual(str(ev.date.min().date()), "2025-10-01")
        with self.assertRaises(ValueError):
            prepare_features(pd.concat([card, card.iloc[:1]]))

    def test_metrics_require_equal_keys_and_handle_zero_target(self):
        y = pd.DataFrame({"date": ["2025-10-01", "2025-10-02"], "region": "R", "industry": "A", "age": "20대", "amount": [0, 0]})
        b = y.rename(columns={"amount": "prediction"}).copy()
        a = b.copy()
        a["prediction"] = [2, 0]
        scores = paired_metrics(y, b, a)
        self.assertEqual(scores.mae.tolist(), [0, 1])
        self.assertTrue(scores.wape.isna().all())
        with self.assertRaises(ValueError):
            paired_metrics(y, b.iloc[:1], a)

    def test_priority_rejects_window_mismatch_and_duplicate(self):
        keys = dict(zip(KEY, ["HEAT_TEST", "R", "A", "ALL", "2025-08-01", "2025-08-14"]))
        sales = pd.DataFrame([{**keys, **dict(zip(SALES, [.1, 20, 10, .05, "pending"]))}])
        recovery = pd.DataFrame([{**keys, **dict(zip(RECOVERY, [np.nan, "censored", "pending"]))}])
        out = join_metrics(sales, recovery)
        self.assertTrue(out.recovery_days.isna().all())
        self.assertTrue(out.support_priority.isna().all())
        with self.assertRaises(ValueError):
            join_metrics(pd.concat([sales, sales]), recovery)
        recovery.loc[0, "window_end"] = "2025-08-15"
        with self.assertRaises(ValueError):
            join_metrics(sales, recovery)

    def test_priority_rejects_nat_observation_dates(self):
        keys = dict(zip(KEY, ["HEAT_TEST", "R", "A", "ALL", "2025-08-01", "2025-08-14"]))
        sales = pd.DataFrame([{**keys, **dict(zip(SALES, [.1, 20, 10, .05, "pending"]))}])
        recovery = pd.DataFrame([{**keys, **dict(zip(RECOVERY, [np.nan, "censored", "pending"]))}])
        for tables in [("sales",), ("recovery",), ("sales", "recovery")]:
            for columns in [("window_start",), ("window_end",), ("window_start", "window_end")]:
                with self.subTest(tables=tables, columns=columns):
                    inputs = {"sales": sales.copy(), "recovery": recovery.copy()}
                    for table in tables:
                        for column in columns:
                            inputs[table].loc[0, column] = "NaT"
                    with self.assertRaisesRegex(ValueError, f"{tables[0]}: missing observation dates"):
                        join_metrics(inputs["sales"], inputs["recovery"])

    def test_ai_pipeline_runs_on_synthetic_data_only(self):
        n = 50
        card = pd.DataFrame({"date": pd.date_range("2025-07-01", periods=n).strftime("%Y-%m-%d"), "region": "R", "industry": "A", "age": "20대", "amount": np.arange(n) + 100})
        f = prepare_features(card)
        model = make_ai_model()
        model.fit(f.iloc[:40][CATEGORICAL + NUMERIC], f.iloc[:40].amount)
        pred = model.predict(f.iloc[40:][CATEGORICAL + NUMERIC])
        self.assertEqual(len(pred), 10)
        self.assertTrue(np.isfinite(pred).all())


if __name__ == "__main__":
    unittest.main()
