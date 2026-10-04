"""Validated daily card/weather/calendar joins and separate monthly age join."""
import argparse
from pathlib import Path
import pandas as pd


def unique(frame, keys, label):
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f'{label}: null or duplicate keys: {keys}')


def dates(frame):
    frame = frame.copy()
    # Accept canonical dates only; do not let integers become nanoseconds.
    frame['date'] = pd.to_datetime(frame['date'].astype(str), format='%Y-%m-%d', errors='raise')
    return frame


def join_daily(card, weather, calendar):
    card, weather, calendar = map(dates, (card, weather, calendar))
    unique(card, ['date', 'region', 'industry', 'age'], 'card')
    unique(weather, ['date', 'region'], 'weather')
    unique(calendar, ['date'], 'calendar')
    if not calendar['is_holiday'].isin([0, 1]).all():
        raise ValueError('Calendar must explicitly mark every date 0 or 1')
    # Reject accidental overwritten columns, including station-specific duplicates.
    keys = ['date', 'region']
    if (set(card) & set(weather)) - set(keys):
        raise ValueError('Card/weather non-key columns overlap')
    out = card.merge(weather, on=keys, how='left', validate='many_to_one', indicator='weather_match')
    if (set(out) & set(calendar)) - {'date'}:
        raise ValueError('Calendar non-key columns overlap')
    out = out.merge(calendar, on='date', how='left', validate='many_to_one', indicator='calendar_match')
    if not out.calendar_match.eq('both').all():
        raise ValueError('Calendar missing card dates; do not assume non-holidays')
    if not out.weather_match.eq('both').all():
        raise ValueError('Weather missing card date/region keys')
    # Matched weather fields may remain missing; never replace with zero.
    out['weekday'] = out.date.dt.dayofweek
    out['is_weekend'] = out.weekday.ge(5).astype(int)
    if len(out) != len(card):
        raise ValueError('Join changed card row count')
    for column in ['amount', 'transactions']:
        if not out[column].sum() == card[column].sum():
            raise ValueError(f'Join changed {column} total')
    return out


def join_monthly(card, skt, mapping):
    """Join only an explicit provider-confirmed prefix mapping; no daily SKT values."""
    card, skt, mapping = card.copy(), skt.copy(), mapping.copy()
    unique(mapping, ['prefix'], 'mapping')
    if not mapping.status.eq('confirmed').all() or mapping.source.isna().any() or mapping.source.str.strip().eq('').any():
        raise ValueError('Provider-confirmed mapping with source is required')
    unique(card, ['month', 'region', 'age'], 'monthly card')
    unique(skt, ['month', 'prefix', 'age', 'scope'], 'monthly SKT')
    allowed = {'all_observed', 'common_6months'}
    if not set(skt.scope) <= allowed:
        raise ValueError('Unknown grid scope')
    scoped = skt.merge(mapping[['prefix', 'region']], on='prefix', how='inner', validate='many_to_one')
    if scoped.empty:
        raise ValueError('No SKT prefixes match mapping')
    # Per-prefix common-grid panels are formed by the preprocessing step.
    scoped = scoped.groupby(['month', 'region', 'age', 'scope'], as_index=False).grid_value_sum.sum()
    result = scoped.merge(card, on=['month', 'region', 'age'], how='outer', validate='many_to_one', indicator=True)
    if not result._merge.eq('both').all():
        raise ValueError('Monthly age/region coverage differs')
    return result.drop(columns='_merge')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['daily', 'monthly'])
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--weather', type=Path)
    parser.add_argument('--calendar', type=Path)
    parser.add_argument('--skt', type=Path)
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def read(path):
        return pd.read_csv(path, dtype={'month': str, 'prefix': str})
    if args.mode == 'daily':
        if args.weather is None or args.calendar is None:
            parser.error('daily requires --weather and --calendar')
        result = join_daily(read(args.card), read(args.weather), read(args.calendar))
    else:
        if args.skt is None or args.mapping is None:
            parser.error('monthly requires --skt and --mapping')
        result = join_monthly(read(args.card), read(args.skt), read(args.mapping))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding='utf-8-sig')
    print(f'Saved {len(result)} rows: {args.output}')


if __name__ == '__main__':
    main()
