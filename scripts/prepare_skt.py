"""Clean 18 monthly SKT files and produce prefix-based monthly profiles."""
import argparse
from pathlib import Path
import pandas as pd


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'cleaned').mkdir(exist_ok=True)
    keys = ['BLOCK_CD', 'X_COORD', 'Y_COORD']
    quality, profiles, coverage = [], [], []
    for kind in ['age', 'time', 'wkdy']:
        frames = {}
        for month in [f'2025{m:02d}' for m in range(7, 13)]:
            path = source / f'flow_{kind}_pop_{month}.csv'
            if not path.exists():
                path = path.with_suffix('.csv.gz')
            df = pd.read_csv(path, sep='|', dtype={'STD_YM': str, 'BLOCK_CD': str})
            n = len(df)
            duplicate_count = int(df.duplicated().sum())
            if duplicate_count and not (month == '202512' and kind in ['time', 'wkdy']):
                raise ValueError(f'Unexpected exact duplicates: {path.name}')
            df = df.drop_duplicates()
            if df.isna().any().any() or df.duplicated(['STD_YM'] + keys).any():
                raise ValueError(f'Nulls or conflicting keys: {path.name}')
            if set(df.STD_YM) != {month}:
                raise ValueError(f'Month mismatch: {path.name}')
            values = [c for c in df if c not in ['STD_YM'] + keys]
            df[values] = df[values].apply(pd.to_numeric, errors='raise')
            if (df[values] < 0).any().any():
                raise ValueError(f'Negative values: {path.name}')
            df.to_csv(output / 'cleaned' / f'flow_{kind}_pop_{month}.csv.gz', index=False, compression='gzip', encoding='utf-8-sig')
            quality.append(dict(file=path.name, input_rows=n, removed_rows=duplicate_count, clean_rows=len(df)))
            df['prefix'] = df.BLOCK_CD.str[:5]
            frames[month] = df
        prefixes = sorted(set.union(*(set(df.prefix) for df in frames.values())))
        for prefix in prefixes:
            parts = {m: df.loc[df.prefix.eq(prefix)].set_index(keys) for m, df in frames.items()}
            common = set.intersection(*(set(df.index) for df in parts.values()))
            for month, part in parts.items():
                fixed = part.loc[part.index.isin(common)]
                coverage.append(dict(month=month, type=kind, prefix=prefix, observed_grids=len(part), common_grids=len(fixed)))
                for scope, subset in [('all_observed', part), ('common_6months', fixed)]:
                    if subset.empty:
                        continue  # Unobserved is not zero.
                    totals = subset[values].sum()
                    if kind == 'age':
                        labels = totals.index.str.extract(r'_(10G|20G|30G|40G|50G|60GU)$', expand=False)
                        if labels.isna().any():
                            raise ValueError('Unknown age column')
                        totals = totals.groupby(labels).sum()
                        totals.index = totals.index.map({'10G':'10대','20G':'20대','30G':'30대','40G':'40대','50G':'50대','60GU':'60대 이상'})
                    for variable, value in totals.items():
                        profiles.append(dict(month=month, type=kind, prefix=prefix, scope=scope, variable=variable, grid_value_sum=value, grids=len(subset)))
    pd.DataFrame(quality).to_csv(output / 'quality.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(coverage).to_csv(output / 'grid_coverage.csv', index=False, encoding='utf-8-sig')
    profile = pd.DataFrame(profiles)
    profile.to_csv(output / 'profiles.csv', index=False, encoding='utf-8-sig')
    profile.loc[profile.type.eq('age')].drop(columns='type').rename(columns={'variable':'age'}).to_csv(output / 'monthly_age.csv', index=False, encoding='utf-8-sig')
    print(f'Cleaned {len(quality)} files; removed {sum(r["removed_rows"] for r in quality)} duplicate rows')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.input, args.output)
