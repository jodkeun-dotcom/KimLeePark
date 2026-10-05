"""Review-only coverage causes and one-age removal counts; no cohort selection."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import prepare_sales_baseline as baseline
from prepare_sales_handoff import KEY

GROUP = [col for col in KEY if col != 'age']


def diagnose(curves, metrics):
    required = KEY + ['date', 'window', 'amount', 'prediction', 'actual_status', 'is_holiday']
    if missing := set(required) - set(curves):
        raise ValueError(f'curve columns missing: {sorted(missing)}')
    if missing := set(KEY + ['recovery_status']) - set(metrics):
        raise ValueError(f'metric columns missing: {sorted(missing)}')
    d = curves.loc[~curves.age.eq('ALL')].copy()
    m = metrics.loc[metrics.age.eq('ALL')].copy()
    if d.empty or m.empty or not m.recovery_status.isin(['no_decline', 'recovered', 'censored', 'insufficient_data']).all():
        raise ValueError('missing data or invalid recovery status')
    for frame in [d, m]:
        if frame[KEY].isna().any().any():
            raise ValueError('missing keys')
        for col in ['window_start', 'window_end']:
            frame[col] = pd.to_datetime(frame[col]).dt.strftime('%Y-%m-%d')
    d['date'] = pd.to_datetime(d.date)
    d['is_holiday'] = baseline.bool_column(d.is_holiday, 'is_holiday')
    if d.duplicated(KEY + ['date']).any() or m.duplicated(KEY).any():
        raise ValueError('duplicate keys')
    if not d.window.isin(['event', 'observation']).all():
        raise ValueError('invalid window')
    if d.groupby('date').is_holiday.nunique().gt(1).any():
        raise ValueError('inconsistent calendar flags')
    for col in ['amount', 'prediction']:
        d[col] = pd.to_numeric(d[col], errors='raise')
        if not np.isfinite(d[col].dropna()).all() or d[col].dropna().lt(0).any():
            raise ValueError('invalid amounts')
    expected_actual_status = np.where(d.amount.notna(), 'observed', 'missing_row_unknown')
    if not d.actual_status.eq(expected_actual_status).all():
        raise ValueError('actual status differs from row availability')
    membership = d[GROUP].drop_duplicates().merge(m[GROUP], on=GROUP, how='outer', indicator=True)
    if not membership._merge.eq('both').all():
        raise ValueError('metrics and curves differ')
    statuses = m.set_index(GROUP).recovery_status
    records = []
    for key, g in d.groupby(GROUP):
        if g.groupby('date').window.nunique().gt(1).any():
            raise ValueError('inconsistent event phase')
        if not pd.DatetimeIndex(g.date.drop_duplicates().sort_values()).equals(pd.date_range(key[-2], key[-1])):
            raise ValueError('window has gaps')
        if not g.groupby('date').age.nunique().eq(g.age.nunique()).all():
            raise ValueError('age grid incomplete')
        g = g.copy()
        g['missing'] = g.amount.isna() | g.prediction.isna()
        event = g.loc[g.window.eq('event')]
        eligible = g.loc[~g.is_holiday]
        if event.empty:
            raise ValueError('missing event phase')
        # Ties: lexical age label, frozen for all dates. No group is actually removed.
        counts = eligible.groupby('age').missing.sum()
        worst = sorted(counts.index[counts.eq(counts.max())].astype(str))[0]
        remaining = g.loc[g.age.ne(worst)]
        event_remaining = remaining.loc[remaining.window.eq('event')]
        eligible_remaining = remaining.loc[~remaining.is_holiday]
        event_missing = bool(event.missing.any())
        has_prediction_missing = bool(event.prediction.isna().any())
        has_actual_missing = bool(event.amount.isna().any())
        cause = ('both_types' if has_prediction_missing and has_actual_missing else
                 'prediction_only' if has_prediction_missing else
                 'actual_row_only' if has_actual_missing else 'event_complete')
        row = dict(zip(GROUP, key))
        row.update(recovery_status=statuses[key], event_missing_cause=cause,
                   event_prediction_only_cells=int((event.prediction.isna() & event.amount.notna()).sum()),
                   event_actual_only_cells=int((event.amount.isna() & event.prediction.notna()).sum()),
                   event_both_missing_cells=int((event.amount.isna() & event.prediction.isna()).sum()),
                   event_complete=not event_missing,
                   eligible_window_complete=not bool(eligible.missing.any()),
                   calendar_window_complete=not bool(g.missing.any()),
                   diagnostic_removed_age=worst, total_age_groups=g.age.nunique(),
                   newly_event_complete=bool(event_missing and not event_remaining.empty and not event_remaining.missing.any()),
                   newly_eligible_window_complete=bool(eligible.missing.any() and not eligible_remaining.empty and not eligible_remaining.missing.any()),
                   newly_calendar_window_complete=bool(g.missing.any() and not remaining.empty and not remaining.missing.any()),
                   known_event_prediction_sum=event.prediction.sum(min_count=1),
                   known_window_prediction_sum=g.prediction.sum(min_count=1),
                   predicted_event_cells=int(event.prediction.notna().sum()), event_cells=len(event),
                   predicted_window_cells=int(g.prediction.notna().sum()), window_cells=len(g))
        records.append(row)
    detail = pd.DataFrame(records)
    shares = []
    for label, g in [('ALL_EVENTS', detail), *list(detail.groupby('event_id'))]:
        available = g.recovery_status.ne('insufficient_data')
        row = dict(event_id=label, total=len(g), decidable=int(available.sum()))
        for phase in ['event', 'window']:
            col = f'known_{phase}_prediction_sum'
            denominator = g[col].sum(min_count=1)
            numerator = g.loc[available, col].sum(min_count=1)
            row[f'decidable_known_{phase}_prediction_share'] = numerator / denominator if denominator > 0 else np.nan
            row[f'known_{phase}_prediction_cell_coverage'] = g[f'predicted_{phase}_cells'].sum() / g[f'{phase}_cells'].sum()
        shares.append(row)
    return detail, pd.DataFrame(shares)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curves', type=Path, required=True)
    parser.add_argument('--metrics', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    detail, shares = diagnose(pd.read_csv(args.curves, low_memory=False), pd.read_csv(args.metrics))
    args.output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(args.output / 'coverage_causes_PRIVATE_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    shares.to_csv(args.output / 'coverage_shares_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    print(shares.to_string(index=False))


if __name__ == '__main__':
    main()
