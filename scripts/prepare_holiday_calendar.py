"""Validate six received KASI getRestDeInfo XML responses and build an H2 calendar.

No API call is made. Retrieval time is never inferred from the local file time.
The month of an empty response relies on the supplied filename/request account.
"""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree as ET

FIELDS = ['date', 'is_holiday', 'holiday_name', 'is_substitute', 'is_weekend']
ENDPOINT = 'https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo'


def parse_response(content, month):
    if re.search(rb'(?i)(servicekey|authorization|api[_-]?key|<!DOCTYPE|<!ENTITY)', content):
        raise ValueError('credential marker or unsupported XML declaration')
    root = ET.fromstring(content)
    if root.tag != 'response' or root.findtext('header/resultCode') != '00':
        raise ValueError('not a successful API response')
    body = root.find('body')
    if body is None:
        raise ValueError('missing response body')
    try:
        total, page, size = [int(body.findtext(k)) for k in ['totalCount', 'pageNo', 'numOfRows']]
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid pagination') from exc
    items = body.findall('items/item')
    if page != 1 or size <= 0 or total < 0 or total > size or len(items) != total:
        raise ValueError('incomplete response or unsupported pagination')
    records, keys = [], set()
    for item in items:
        raw_date = item.findtext('locdate', '')
        if not re.fullmatch(r'\d{8}', raw_date):
            raise ValueError('invalid holiday date')
        day = datetime.strptime(raw_date, '%Y%m%d').date()
        name, flag, seq = (item.findtext(k, '').strip() for k in ['dateName', 'isHoliday', 'seq'])
        if day.year != 2025 or day.month != month:
            raise ValueError('response dates differ from supplied month')
        if flag not in ['Y', 'N'] or not name or not seq:
            raise ValueError('missing/invalid holiday fields')
        key = (day, seq)
        if key in keys:
            raise ValueError('duplicate date/sequence item')
        keys.add(key)
        records.append({'date': day.isoformat(), 'holiday_name': name, 'is_holiday': int(flag == 'Y')})
    return records, {'total_count': total, 'page_no': page, 'num_of_rows': size,
                     'month_check': 'item_dates_match' if items else 'empty_response_month_not_echoed'}


def build(input_dir, queried_date=None):
    if queried_date is not None:
        if date.fromisoformat(queried_date).isoformat() != queried_date:
            raise ValueError('query date must be YYYY-MM-DD')
    responses, holidays = [], {}
    for month in range(7, 13):
        filename = f'holiday_2025_{month:02d}.xml'
        content = (input_dir / filename).read_bytes()
        records, pagination = parse_response(content, month)
        responses.append({'file': filename, 'sha256': hashlib.sha256(content).hexdigest(),
                          'bytes': len(content), 'assigned_year': 2025, 'assigned_month': month,
                          'request_parameters_reported': {'solYear': '2025', 'solMonth': f'{month:02d}'},
                          'pagination_in_response': pagination})
        for row in records:
            if row['is_holiday']:
                holidays.setdefault(row['date'], set()).add(row['holiday_name'])
    rows = []
    day = date(2025, 7, 1)
    while day <= date(2025, 12, 31):
        names = sorted(holidays.get(day.isoformat(), set()))
        rows.append({'date': day.isoformat(), 'is_holiday': int(bool(names)),
                     'holiday_name': ';'.join(names), 'is_substitute': int(any('대체공휴일' in n for n in names)),
                     'is_weekend': int(day.weekday() >= 5)})
        day += timedelta(days=1)
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    calendar = buffer.getvalue().encode('utf-8-sig')
    metadata = {'version': 'kasi-received-xml-calendar-v1', 'provider': '한국천문연구원',
                'source_page': 'https://www.data.go.kr/data/15012690/openapi.do', 'endpoint': ENDPOINT,
                'acquisition': 'XML files supplied by teammate; not directly retrieved by this script',
                'queried_date': queried_date,
                'query_date_status': 'teammate_reported_date_only' if queried_date else 'not_confirmed',
                'request_evidence': 'endpoint/year/month reported by teammate; pagination read from response, not an HTTP request log',
                'empty_response_caveat': 'Empty responses do not echo year/month and can have identical hashes; assignment relies on supplied filenames and the teammate account.',
                'start_date': '2025-07-01', 'end_date': '2025-12-31', 'calendar_rows': len(rows),
                'holiday_dates': sum(r['is_holiday'] for r in rows),
                'holiday_rule': 'isHoliday=Y from received getRestDeInfo records; ordinary weekends are separate',
                'substitute_rule': 'dateName contains 대체공휴일',
                'calendar_sha256': hashlib.sha256(calendar).hexdigest(), 'responses': responses}
    return calendar, metadata


def run(input_dir, output, queried_date=None):
    if output.exists() and any(output.iterdir()):
        raise ValueError('use a new output directory')
    calendar, metadata = build(input_dir, queried_date)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'raw').mkdir()
    for record in metadata['responses']:
        dest = output / 'raw' / record['file']
        shutil.copyfile(input_dir / record['file'], dest)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('source XML changed during copy')
    (output / 'calendar.csv').write_bytes(calendar)
    metadata['calendar_generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    (output / 'calendar_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"PASS: {metadata['calendar_rows']} dates, {metadata['holiday_dates']} named holiday dates; query date {metadata['query_date_status']}")
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--queried-date', help='Actual retrieval date reported by the collector, YYYY-MM-DD; omit if unknown')
    args = parser.parse_args()
    run(args.input_dir, args.output, args.queried_date)
