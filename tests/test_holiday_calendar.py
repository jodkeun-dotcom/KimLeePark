import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_holiday_calendar import build, parse_response, run
from scripts.run_support_review import run as run_review


def response(items='', count=0, code='00', page=1, size=100):
    return (f'<response><header><resultCode>{code}</resultCode></header><body><items>{items}</items>'
            f'<numOfRows>{size}</numOfRows><pageNo>{page}</pageNo><totalCount>{count}</totalCount></body></response>').encode()


def item(day='20251005', seq='1', flag='Y'):
    return f'<item><locdate>{day}</locdate><dateName>가상공휴일</dateName><seq>{seq}</seq><isHoliday>{flag}</isHoliday></item>'


class HolidayCalendarTests(unittest.TestCase):
    def sources(self, root):
        for month in range(7, 13):
            (root / f'holiday_2025_{month:02d}.xml').write_bytes(response())
        (root / 'holiday_2025_10.xml').write_bytes(response(item(), 1))

    def test_empty_success_is_preserved_but_does_not_certify_month(self):
        rows, meta = parse_response(response(), 7)
        self.assertEqual(rows, [])
        self.assertEqual(meta['month_check'], 'empty_response_month_not_echoed')

    def test_rejects_api_error_and_partial_pages(self):
        for data in [response(code='20'), response(count=1), response(page=2), response(size=0)]:
            with self.assertRaises(ValueError):
                parse_response(data, 7)

    def test_rejects_wrong_month_duplicate_and_bad_flags(self):
        for data in [response(item(), 1), response(item('20250701') * 2, 2), response(item('20250701', flag='?'), 1)]:
            with self.assertRaises(ValueError):
                parse_response(data, 7)

    def test_rejects_credentials_and_xml_entities(self):
        for data in [b'<ServiceKey>secret</ServiceKey>', b'<!DOCTYPE response><response/>']:
            with self.assertRaises(ValueError):
                parse_response(data, 7)

    def test_full_calendar_keeps_weekends_separate_and_query_date_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.sources(root)
            data, meta = build(root)
            rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
            by_date = {r['date']: r for r in rows}
            self.assertEqual(len(rows), 184)
            self.assertEqual((rows[0]['date'], rows[-1]['date']), ('2025-07-01', '2025-12-31'))
            self.assertEqual((by_date['2025-10-05']['is_holiday'], by_date['2025-10-05']['is_weekend']), ('1', '1'))
            self.assertEqual((by_date['2025-10-12']['is_holiday'], by_date['2025-10-12']['is_weekend']), ('0', '1'))
            self.assertIsNone(meta['queried_date'])

    def test_preserves_raw_bytes_and_collector_reported_date(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.sources(root)
            meta = run(root, root / 'out', '2026-10-05')
            self.assertEqual(meta['query_date_status'], 'teammate_reported_date_only')
            self.assertEqual(meta['queried_date'], '2026-10-05')
            for m in range(7, 13):
                name = f'holiday_2025_{m:02d}.xml'
                self.assertEqual((root / name).read_bytes(), (root / 'out/raw' / name).read_bytes())
            with self.assertRaises(ValueError):
                run(root, root / 'out', '2026-10-05')

    def test_review_rejects_calendar_from_a_different_source_record(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            calendar, metadata = root / 'calendar.csv', root / 'metadata.json'
            calendar.write_text('date,is_holiday\n2025-07-01,0\n')
            metadata.write_text(json.dumps({'version': 'kasi-received-xml-calendar-v1', 'calendar_sha256': 'wrong'}))
            with self.assertRaisesRegex(ValueError, 'calendar differs'):
                run_review(calendar, calendar, calendar, root / 'review', calendar, metadata)


if __name__ == '__main__':
    unittest.main()
