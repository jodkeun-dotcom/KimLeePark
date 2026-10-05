import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json

import numpy as np
import pandas as pd

from scripts.run_support_review import compare_common, file_record, run


class ReviewBundleTests(unittest.TestCase):
    def frames(self):
        keys = {'event_id': ['E1', 'E2'], 'region': ['R', 'R'], 'industry': ['한식', '한식'],
                'age': ['ALL', 'ALL'], 'window_start': ['2025-08-01'] * 2,
                'window_end': ['2025-08-17'] * 2}
        p = pd.DataFrame({**keys, 'recovery_status': ['recovered', 'censored'],
                          'recovery_days': [3., np.nan], 'recovery_date': ['2025-08-04', None],
                          'recovery_threshold': [.95] * 2, 'consecutive_days': [3] * 2,
                          'complete_eligible_window': [True, False], 'decline_rate': [.5, .4],
                          'net_shortfall_eligible': [20., np.nan],
                          'net_shortfall_rate_eligible': [.2, np.nan],
                          'gross_shortfall_eligible': [25., np.nan]})
        r = p[list(keys) + ['recovery_status', 'recovery_days', 'recovery_date',
                           'recovery_threshold', 'consecutive_days']].copy()
        s = pd.DataFrame({**keys, 'complete_nonholiday': [True, False], 'decline_rate': [.5, .4],
                          'net_shortfall_nonholiday': [20., np.nan], 'net_rate_nonholiday': [.2, np.nan],
                          'gross_shortfall_paired': [25., 12.],
                          'net_shortfall': [np.nan, np.nan], 'gross_shortfall': [np.nan, np.nan]})
        return p, r, s

    def test_eligible_uses_complete_nonholiday_not_full_or_paired_subtotal(self):
        p, r, s = self.frames()
        self.assertEqual(compare_common(p, r, s)['all_rows_compared'], 2)
        p.loc[1, 'gross_shortfall_eligible'] = 12.
        with self.assertRaisesRegex(ValueError, 'gross_shortfall_eligible'):
            compare_common(p, r, s)

    def test_rejects_different_recovery_results_or_rule(self):
        for col, value in [('recovery_days', 4), ('recovery_date', '2025-08-05'),
                           ('recovery_status', 'censored'), ('recovery_threshold', .9),
                           ('consecutive_days', 2)]:
            with self.subTest(column=col):
                p, r, s = self.frames()
                r.loc[0, col] = value
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    compare_common(p, r, s)

    def test_rejects_missing_duplicate_and_different_window_keys(self):
        p, r, s = self.frames()
        for other in [r.iloc[:1], pd.concat([r, r.iloc[:1]]), r.assign(window_end='2025-08-16')]:
            with self.assertRaises(ValueError):
                compare_common(p, other, s)

    def test_rejects_changed_sales_value_and_completeness(self):
        for col, value in [('net_shortfall_nonholiday', 21.), ('complete_nonholiday', False)]:
            p, r, s = self.frames()
            s.loc[0, col] = value
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                compare_common(p, r, s)

    def test_csv_digest_distinguishes_bytes_from_cell_identity(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.csv', Path(d) / 'b.csv'
            a.write_bytes(b'x,y\n1,A\n2,B\n')
            b.write_bytes('\ufeffy,x\r\nB,2\r\nA,1\r\n'.encode('utf-8'))
            one, two = file_record(a), file_record(b)
            self.assertNotEqual(one['sha256'], two['sha256'])
            self.assertEqual(one['csv_text_cells_sha256'], two['csv_text_cells_sha256'])
            b.write_text('x,y\n1,A\n1,A\n2,B\n', encoding='utf-8')
            self.assertNotEqual(one['csv_text_cells_sha256'], file_record(b)['csv_text_cells_sha256'])

    def test_refuses_to_overwrite_previous_run(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            marker = output / 'existing.txt'
            marker.write_text('preserve')
            with self.assertRaisesRegex(ValueError, 'new output directory'):
                run(Path('missing'), Path('missing'), Path('missing'), output)
            self.assertEqual(marker.read_text(), 'preserve')

    def test_failed_stage_preserves_snapshot_and_never_claims_completion(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'input.csv'
            source.write_text('date,amount\n2025-08-01,10\n', encoding='utf-8')
            output = root / 'new_run'
            with patch('scripts.run_support_review.subprocess.run', return_value=SimpleNamespace(returncode=1)):
                with self.assertRaisesRegex(RuntimeError, 'baseline failed'):
                    run(source, source, source, output)
            record = json.loads((output / 'review_run.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['stages'][0]['status'], 'failed')
            self.assertNotIn('consistency_checks', record)
            self.assertIsNone(record['calendar_api_retrieved_at'])
            self.assertEqual((output / 'inputs/card.csv').read_bytes(), source.read_bytes())


if __name__ == '__main__':
    unittest.main()
