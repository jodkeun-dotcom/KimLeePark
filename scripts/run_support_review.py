"""Run PR29/32/31 together with frozen local inputs and a reproducibility record.

This does not fetch holidays or approve a policy. Every output is private review
material. A supplied calendar is not proof of an official API retrieval.
"""
import argparse
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

from scripts import prepare_sales_baseline as baseline
from scripts.prepare_priority import KEY


def file_record(path):
    """Byte identity plus an order/BOM/line-ending insensitive CSV text check.

    Cell strings (including numeric spelling) and duplicate rows are preserved.
    The second digest is not a claim of numerical or statistical equivalence.
    """
    record = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'bytes': path.stat().st_size}
    if path.suffix == '.csv':
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        columns = sorted(frame.columns)
        rows = sorted(frame[columns].itertuples(index=False, name=None))
        content = json.dumps([columns, rows], ensure_ascii=False, separators=(',', ':'))
        record.update(rows=len(frame), columns=columns,
                      csv_text_cells_sha256=hashlib.sha256(content.encode('utf-8')).hexdigest())
    return record


def compare_common(priority, recovery, sales):
    """Require same ALL keys, recovery rule/results and eligible sales measures.

    Full and paired monetary fields are deliberately never substituted for
    eligible fields. Paired gross is comparable only on a complete nonholiday
    window, since the shared baseline excludes predictions on holidays.
    """
    frames = [priority.copy(), recovery.loc[recovery.age.eq('ALL')].copy(),
              sales.loc[sales.age.eq('ALL')].copy()]
    for frame in frames:
        for col in ['window_start', 'window_end']:
            frame[col] = pd.to_datetime(frame[col]).dt.strftime('%Y-%m-%d')
        if frame.empty or frame[KEY].isna().any().any() or frame.duplicated(KEY).any():
            raise ValueError('empty/missing/duplicate comparison keys')
    p, r, s = [f.set_index(KEY).sort_index() for f in frames]
    if not p.index.equals(r.index) or not p.index.equals(s.index):
        raise ValueError('common/priority keys differ')

    def numeric(left, right, label):
        if not np.allclose(pd.to_numeric(left).to_numpy(dtype=float),
                           pd.to_numeric(right).to_numpy(dtype=float),
                           rtol=1e-9, atol=1e-7, equal_nan=True):
            raise ValueError(f'common/priority mismatch: {label}')

    if not p.recovery_status.eq(r.recovery_status).all():
        raise ValueError('common/priority mismatch: recovery_status')
    dates = [pd.to_datetime(f.recovery_date).dt.strftime('%Y-%m-%d').fillna('') for f in [p, r]]
    if not dates[0].eq(dates[1]).all():
        raise ValueError('common/priority mismatch: recovery_date')
    for col in ['recovery_days', 'recovery_threshold', 'consecutive_days']:
        numeric(p[col], r[col], col)
    if not p.recovery_threshold.eq(.95).all() or not p.consecutive_days.eq(3).all():
        raise ValueError('expected base rule 0.95 / 3 days')
    complete = baseline.bool_column(s.complete_nonholiday, 'complete_nonholiday')
    if not baseline.bool_column(p.complete_eligible_window, 'complete_eligible_window').eq(complete).all():
        raise ValueError('common/priority mismatch: completeness')
    for a, b in [('decline_rate', 'decline_rate'),
                 ('net_shortfall_eligible', 'net_shortfall_nonholiday'),
                 ('net_shortfall_rate_eligible', 'net_rate_nonholiday')]:
        numeric(p[a], s[b], a)
    numeric(p.gross_shortfall_eligible, s.gross_shortfall_paired.where(complete), 'gross_shortfall_eligible')
    return {'all_rows_compared': len(p), 'recovery_and_eligible_sales_match': True,
            'full_and_paired_fields_not_used_as_eligible': True,
            'rule': 'weekday_mean;effective;fixed_pre_event;exclude_missing;0.95;3;holiday_break',
            'method_approval': False}


def run(card, events, windows, output, calendar=None):
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('use a new output directory; previous runs must be preserved')
    inputs = {'card': Path(card), 'events': Path(events), 'windows': Path(windows)}
    if calendar is not None:
        inputs['calendar'] = Path(calendar)
        baseline.calendar_flags(pd.date_range('2025-07-01', '2025-12-31'), calendar)
    records = {name: file_record(path) for name, path in inputs.items()}
    root = Path(__file__).resolve().parents[1]
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted((root / 'scripts').glob('*.py'))}
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / 'inputs'
    frozen.mkdir()
    for name, path in inputs.items():
        target = frozen / f'{name}.csv'
        shutil.copyfile(path, target)
        if file_record(target) != records[name]:
            raise ValueError('input changed during snapshot')
    stamp = lambda: datetime.now(timezone.utc).isoformat()
    manifest = {'version': 'support-review-v1', 'status': 'running', 'started_at_utc': stamp(),
                'calendar_status': 'supplied_calendar_api_evidence_not_verified' if calendar else 'provisional_2025_08_15_only',
                'calendar_api_retrieved_at': None,
                'note': 'This is an analysis run time, not the original/API query time. No policy approval.',
                'inputs': records, 'source_sha256': sources,
                'environment': {'python': sys.version.split()[0], **{name: importlib.metadata.version(name)
                                for name in ['pandas', 'numpy', 'scikit-learn', 'matplotlib']}},
                'stages': []}
    manifest_path = output / 'review_run.json'

    def save():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    def stage(name, script, arguments, module=False):
        command = [sys.executable] + (['-m', f'scripts.{script}'] if module else [str(root / 'scripts' / f'{script}.py')]) + arguments
        entry = {'name': name, 'started_at_utc': stamp(), 'status': 'running',
                 'command': ['python'] + (['-m', f'scripts.{script}'] if module else [f'scripts/{script}.py']) + arguments}
        manifest['stages'].append(entry)
        save()
        # Logs and input snapshots stay in this private output directory.
        with (output / f'{name}.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                                    env=environment, check=False)
        entry.update(finished_at_utc=stamp(), returncode=result.returncode,
                     status='passed' if result.returncode == 0 else 'failed')
        save()
        if result.returncode:
            raise RuntimeError(f'{name} failed; inspect its local log')
        print(f'PASS: {name}', flush=True)

    import os
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(root) + os.pathsep + environment.get('PYTHONPATH', '')
    cal = ['--calendar', 'inputs/calendar.csv'] if calendar else []
    save()
    try:
        stage('baseline', 'prepare_sales_baseline', ['--daily', 'inputs/card.csv', '--events', 'inputs/events.csv',
              '--event-windows', 'inputs/windows.csv', '--output', 'baseline'] + cal, module=True)
        common = ['--daily-predictions', 'baseline/daily_predictions.csv', '--events', 'inputs/events.csv',
                  '--run-metadata', 'baseline/run_metadata.json']
        stage('sales', 'prepare_sales_handoff', common + ['--output', 'common_sales'])
        stage('recovery', 'compute_recovery_from_baseline', common + ['--daily-industry', 'baseline/daily_industry.csv',
              '--threshold', '0.95', '--consecutive-days', '3', '--output', 'common_recovery'])
        stage('join_full', 'prepare_priority', ['--sales', 'common_sales/sales_handoff.csv',
              '--recovery', 'common_recovery/recovery_handoff_common_baseline.csv', '--output', 'common_full_join'])
        stage('model', 'evaluate_models', ['--card', 'inputs/card.csv', '--events', 'inputs/events.csv',
              '--windows', 'inputs/windows.csv', '--output', 'model'] + cal, module=True)
        stage('priority', 'rank_support', ['--daily', 'baseline/daily_predictions.csv', '--events', 'inputs/events.csv',
              '--run-metadata', 'baseline/run_metadata.json', '--output', 'priority'], module=True)
        checks = compare_common(pd.read_csv(output / 'priority/support_priority_PROVISIONAL.csv'),
                  pd.read_csv(output / 'common_recovery/recovery_metrics_common_baseline.csv'),
                  pd.read_csv(output / 'common_sales/sales_handoff_diagnostics.csv'))
        for name, record in records.items():
            if file_record(frozen / f'{name}.csv') != record:
                raise ValueError('frozen input changed during run')
        if any(hashlib.sha256((root / name).read_bytes()).hexdigest() != sha for name, sha in sources.items()):
            raise ValueError('analysis source changed during run')
        manifest.update(status='completed_review_only', finished_at_utc=stamp(), consistency_checks=checks,
                        outputs={str(p.relative_to(output)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                                             'bytes': p.stat().st_size}
                                 for p in sorted(output.rglob('*')) if p.is_file() and p != manifest_path and frozen not in p.parents})
        save()
        return manifest
    except Exception as exc:
        manifest.update(status='failed', finished_at_utc=stamp(), error=type(exc).__name__)
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['card', 'events', 'windows', 'output']:
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--calendar', type=Path)
    args = parser.parse_args()
    run(args.card, args.events, args.windows, args.output, args.calendar)
