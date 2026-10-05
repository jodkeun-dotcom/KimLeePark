"""Review-only ALL recovery comparisons; never emits a priority handoff."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import compute_recovery as recovery
import prepare_sales_baseline as baseline
from prepare_sales_handoff import KEY

STATUSES = ['no_decline', 'recovered', 'censored', 'insufficient_data']
PROFILES = [
    ('paired_partial_break', False, False),
    ('complete_groups_break', True, False),
    ('paired_partial_skip_holidays', False, True),
    ('complete_groups_skip_holidays', True, True),
]


def compare(curves, legacy, threshold=.95, run=3):
    if not np.isfinite(threshold) or threshold <= 0 or isinstance(run, bool) or not isinstance(run, int) or run < 1:
        raise ValueError('invalid recovery rule')
    required = KEY + ['date', 'window', 'day_offset', 'amount', 'prediction',
                      'complete_group_coverage', 'is_holiday', 'recovery_threshold', 'consecutive_days']
    if missing := set(required) - set(curves):
        raise ValueError(f'curve columns missing: {sorted(missing)}')
    if missing := set(KEY + ['recovery_status', 'recovery_days']) - set(legacy):
        raise ValueError(f'legacy columns missing: {sorted(missing)}')
    d = curves.loc[curves.age.eq('ALL')].copy()
    old = legacy.loc[legacy.age.eq('ALL')].copy()
    if d.empty or old.empty:
        raise ValueError('no ALL rows')
    for frame in [d, old]:
        if frame[KEY].isna().any().any():
            raise ValueError('missing keys')
        for col in ['window_start', 'window_end']:
            frame[col] = pd.to_datetime(frame[col], errors='raise').dt.strftime('%Y-%m-%d')
    d['date'] = pd.to_datetime(d.date, errors='raise')
    if d.date.isna().any() or d.duplicated(KEY + ['date']).any() or old.duplicated(KEY).any():
        raise ValueError('duplicate or missing dates/keys')
    if not d.window.isin(['event', 'observation']).all():
        raise ValueError('invalid phase')
    for col in ['complete_group_coverage', 'is_holiday']:
        d[col] = baseline.bool_column(d[col], col)
    if not pd.to_numeric(d.recovery_threshold).eq(threshold).all() or not pd.to_numeric(d.consecutive_days).eq(run).all():
        raise ValueError('curve rule differs from comparison rule')
    for col in ['amount', 'prediction']:
        d[col] = pd.to_numeric(d[col], errors='raise')
        if not np.isfinite(d[col].dropna()).all() or d[col].dropna().lt(0).any():
            raise ValueError('invalid amounts')
    if not old.recovery_status.isin(STATUSES).all():
        raise ValueError('unknown legacy status')
    membership = d[KEY].drop_duplicates().merge(old[KEY], on=KEY, how='outer', indicator=True)
    if not membership._merge.eq('both').all():
        raise ValueError('legacy and common ALL keys/windows differ')
    # Legacy handoff omits rule metadata: caller must verify threshold/run provenance.
    records = []
    for key, g in d.groupby(KEY):
        g = g.sort_values('date').copy()
        if not pd.DatetimeIndex(g.date).equals(pd.date_range(key[-2], key[-1])):
            raise ValueError('curve window has gaps')
        event = g.loc[g.window.eq('event')]
        obs = g.loc[g.window.eq('observation')]
        if event.empty or (not obs.empty and obs.date.min() <= event.date.max()):
            raise ValueError('invalid event/observation order')
        if not pd.to_numeric(g.day_offset).eq((g.date - event.date.max()).dt.days).all():
            raise ValueError('incorrect day offsets')
        for name, complete, skip in PROFILES:
            valid_event = event.amount.notna() & event.prediction.notna()
            if complete:
                valid_event &= event.complete_group_coverage
            q = event.loc[valid_event]
            denominator = q.prediction.sum()
            event_ratio = q.amount.sum() / denominator if valid_event.all() and denominator > 0 else np.nan
            evaluation = obs.copy()
            skipped = int(evaluation.is_holiday.sum()) if skip else 0
            if skip:
                evaluation = evaluation.loc[~evaluation.is_holiday].copy()
            evaluation['ratio'] = evaluation.amount / evaluation.prediction.where(evaluation.prediction.gt(0))
            if complete:
                evaluation['ratio'] = evaluation.ratio.where(evaluation.complete_group_coverage)
            if pd.isna(event_ratio):
                status, day, date = 'insufficient_data', None, pd.NaT
            elif event_ratio >= threshold:
                status, day, date = 'no_decline', None, pd.NaT
            else:
                status, day, date = recovery.recovery_day(evaluation, threshold, run)
            row = dict(zip(KEY, key))
            row.update(profile=name, recovery_status=status, recovery_days=day,
                       recovery_date=date, event_ratio=event_ratio,
                       event_complete_days=int(event.complete_group_coverage.sum()),
                       event_days=len(event), observation_days=len(obs),
                       observation_complete_days=int(obs.complete_group_coverage.sum()),
                       skipped_holiday_days=skipped,
                       recovery_uncertainty_note=f'review_only;holiday_policy={"skip" if skip else "break"};skipped_holiday_days={skipped};calendar_days_offset;not_for_priority')
            records.append(row)
    results = pd.DataFrame(records)
    legacy_rows = old[KEY + ['recovery_status', 'recovery_days']].copy()
    legacy_rows['profile'] = 'legacy30_separate_ALL'
    legacy_rows['recovery_uncertainty_note'] = 'comparison_only;legacy_rule_provenance_must_match;not_for_priority'
    results = pd.concat([results, legacy_rows], ignore_index=True)
    summary = results.groupby(['event_id', 'profile']).recovery_status.value_counts().unstack(fill_value=0)
    summary = summary.reindex(columns=STATUSES, fill_value=0).reset_index()
    summary['total'] = summary[STATUSES].sum(axis=1)
    return results, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curves', type=Path, required=True)
    parser.add_argument('--legacy-handoff', type=Path, required=True)
    parser.add_argument('--threshold', type=float, default=.95)
    parser.add_argument('--consecutive-days', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    detail, summary = compare(pd.read_csv(args.curves, low_memory=False), pd.read_csv(args.legacy_handoff), args.threshold, args.consecutive_days)
    args.output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(args.output / 'ALL_recovery_sensitivity_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(args.output / 'ALL_status_distribution_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
