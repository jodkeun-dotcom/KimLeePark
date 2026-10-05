"""Recovery sensitivity across event scenarios and recovery rules (issue #11, review only).

Each scenario directory holds the outputs of
  label_weather_events.py --max-gap-days G --observation-days N --output <dir>/weather_events
  prepare_sales_baseline.py ... --output <dir>/baseline
and this script recomputes recovery with compute_recovery_from_baseline.compute (weekday mean,
fixed pre-event, exclude missing, effective windows) for every threshold x consecutive-day rule.

Outputs stay local. Files named *_PRIVATE_REVIEW_ONLY.csv contain industry-level rows and must not
be committed; the other CSVs and the Markdown summary contain counts only.
Ranges across settings are reported instead of confidence intervals (few events).
"""
import argparse
import json
from pathlib import Path

import pandas as pd

import compute_recovery_from_baseline as common

STATUSES = ['no_decline', 'recovered', 'censored', 'insufficient_data']
STATUS_KO = {'no_decline': '감소 없음', 'recovered': '회복', 'censored': '관찰기간 내 회복 미확인',
             'insufficient_data': '자료 부족'}
# 같은 단위 대응 키: 사건 정의(시작·종료일)가 같은 업종×연령. 관찰 끝(window_end)은 시나리오가 바꾸는 값이라 제외한다.
UNIT = ['event_id', 'region', 'industry', 'age', 'window_start', 'event_end']
SETTING = ['scenario', 'threshold', 'consecutive_days']


def parse_scenario(text):
    """'S0:2:14' → ('S0', 2, 14). 이름:병합 간격:관찰일수."""
    parts = text.split(':')
    if len(parts) != 3 or not parts[0]:
        raise ValueError(f'scenario must look like NAME:GAP:DAYS, got {text!r}')
    try:
        gap, days = int(parts[1]), int(parts[2])
    except ValueError as error:
        raise ValueError(f'scenario gap/days must be integers: {text!r}') from error
    return parts[0], gap, days


def load_scenario(directory):
    base = directory / 'baseline'
    events = directory / 'weather_events' / 'weather_events.csv'
    needed = [base / 'daily_predictions.csv', base / 'daily_industry.csv', base / 'run_metadata.json', events]
    missing = [str(p) for p in needed if not p.exists()]
    if missing:
        raise ValueError(f'scenario inputs missing: {missing}')
    metadata = json.loads((base / 'run_metadata.json').read_text(encoding='utf-8-sig'))
    return (pd.read_csv(base / 'daily_predictions.csv'), pd.read_csv(base / 'daily_industry.csv'),
            pd.read_csv(events), metadata)


def recovery_grid(inputs, scenarios, thresholds, runs):
    """시나리오 × 임계값 × 연속일수별 회복 지표 (긴 형식).

    inputs: {scenario name: (predictions, industry, events, metadata)}
    """
    parts = []
    for name, gap, days in scenarios:
        if name not in inputs:
            raise ValueError(f'no inputs for scenario {name}')
        predictions, industry, events, metadata = inputs[name]
        for threshold in thresholds:
            for run in runs:
                _, metrics = common.compute(predictions, industry, events, threshold, run, metadata)
                metrics = metrics.assign(scenario=name, max_gap_days=gap, observation_days=days,
                                         threshold=threshold, consecutive_days=run)
                parts.append(metrics)
    if not parts:
        raise ValueError('no scenario/rule combinations to compute')
    grid = pd.concat(parts, ignore_index=True)
    grid['scope'] = grid.age.eq('ALL').map({True: 'ALL', False: 'age'})
    if not grid.recovery_status.isin(STATUSES).all():
        raise ValueError('unexpected recovery status')
    if grid.duplicated(SETTING + UNIT).any():
        raise ValueError('duplicate unit within a setting')
    return grid


def status_distribution(grid):
    counts = (grid.groupby(SETTING + ['scope', 'recovery_status']).size()
              .unstack('recovery_status', fill_value=0).reindex(columns=STATUSES, fill_value=0).reset_index())
    counts['total'] = counts[STATUSES].sum(axis=1)
    return counts


def against_reference(grid, reference):
    """기준 설정 대비 상태 변화. 같은 UNIT으로 대응되는 행만 비교하고, 대응되지 않는 행은 따로 센다."""
    ref = select(grid, reference)
    if ref.empty:
        raise ValueError(f'reference setting {reference} not in grid')
    ref = ref[UNIT + ['scope', 'recovery_status']].rename(columns={'recovery_status': 'reference_status'})
    merged = grid.merge(ref, on=UNIT + ['scope'], how='left', validate='many_to_one')
    matched = merged[merged.reference_status.notna()]
    changes = (matched.assign(changed=matched.recovery_status.ne(matched.reference_status))
               .groupby(SETTING + ['scope'])
               .agg(matched=('changed', 'size'), changed=('changed', 'sum')).reset_index())
    changes['changed_share'] = changes.changed / changes.matched
    moved = matched[matched.recovery_status.ne(matched.reference_status)]
    transitions = (moved.groupby(SETTING + ['scope', 'reference_status', 'recovery_status']).size()
                   .rename('count').reset_index())
    unmatched = merged[merged.reference_status.isna()]
    return changes, transitions, unmatched.drop(columns='reference_status')


def stability(grid, reference):
    """기준 설정의 각 단위가 대응되는 모든 설정에서 같은 상태를 유지한 비율.

    units = all: 기준의 모든 단위, judgeable: 기준에서 자료 부족이 아닌 단위만
    (자료 부족은 기준과 무관하게 유지되기 쉬워 전체 비율을 높인다).
    """
    base = select(grid, reference)
    rows = []
    for units, ref in [('all', base), ('judgeable', base[base.recovery_status.ne('insufficient_data')])]:
        rows.extend(stable_rows(grid, reference, ref[UNIT + ['scope']], units))
    return pd.DataFrame(rows)


def stable_rows(grid, reference, ref, units):
    rows = []
    for label, subset in [('criteria_only', grid[grid.scenario.eq(reference[0])]), ('all_settings', grid)]:
        seen = subset.merge(ref, on=UNIT + ['scope'])
        per_unit = seen.groupby(UNIT + ['scope']).agg(states=('recovery_status', 'nunique'),
                                                      settings=('recovery_status', 'size')).reset_index()
        for scope, g in per_unit.groupby('scope'):
            rows.append({'comparison': label, 'unit_set': units, 'scope': scope, 'units': len(g),
                         'stable_units': int(g.states.eq(1).sum()), 'stable_share': float(g.states.eq(1).mean()),
                         'min_settings_per_unit': int(g.settings.min()), 'max_settings_per_unit': int(g.settings.max())})
    return rows


def recovery_day_range(grid):
    """회복(recovered) 행에 한정한 회복일 최소·중앙값·최대. 판정 불가 행은 포함하지 않는다."""
    rec = grid[grid.recovery_status.eq('recovered')]
    out = (rec.groupby(SETTING + ['scope']).recovery_days
           .agg(recovered='size', min_days='min', median_days='median', max_days='max').reset_index())
    return out


def select(grid, setting):
    scenario, threshold, run = setting
    return grid[grid.scenario.eq(scenario) & grid.threshold.eq(threshold) & grid.consecutive_days.eq(run)]


def summary_markdown(distribution, changes, transitions, stable, days, unmatched, reference):
    def table(frame):
        header = '| ' + ' | '.join(map(str, frame.columns)) + ' |'
        rule = '|' + '---|' * len(frame.columns)
        body = ['| ' + ' | '.join('' if pd.isna(v) else f'{v:.3f}' if isinstance(v, float) else str(v)
                                  for v in row) + ' |' for row in frame.itertuples(index=False)]
        return '\n'.join([header, rule] + body)
    merged = (unmatched.groupby(SETTING + ['scope', 'event_id', 'window_start', 'event_end', 'recovery_status'])
              .size().rename('count').reset_index())
    parts = [
        '# 회복 민감도 요약 (로컬 검토용, 건수·비율만)\n',
        f'기준 설정: {reference[0]}, 임계 {reference[1]}, 연속 {reference[2]}일.\n',
        '## 상태 분포\n', table(distribution), '\n',
        '## 기준 대비 상태 변화 (같은 단위)\n', table(changes), '\n',
        '## 바뀐 유형\n', table(transitions), '\n',
        '## 모든 설정에서 같은 상태를 유지한 비율\n', table(stable), '\n',
        '## 회복일 범위 (회복 행만)\n', table(days), '\n',
        '## 기준과 대응되지 않는 사건 (병합 등)\n', table(merged), '\n',
    ]
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scenario-root', type=Path, default=Path('outputs/seeun_1005to1011/scenarios'))
    parser.add_argument('--scenarios', nargs='+',
                        default=['S0:2:14', 'S1:2:7', 'S2:2:21', 'S3:3:14', 'S4:3:21'],
                        help='NAME:GAP:DAYS, 폴더 이름 = NAME')
    parser.add_argument('--thresholds', nargs='+', type=float, default=[0.90, 0.95, 1.00])
    parser.add_argument('--runs', nargs='+', type=int, default=[2, 3, 4])
    parser.add_argument('--reference', nargs=3, default=['S0', '0.95', '3'], metavar=('SCENARIO', 'THRESHOLD', 'RUN'))
    parser.add_argument('--output', type=Path, default=Path('outputs/seeun_1005to1011'))
    args = parser.parse_args()
    scenarios = [parse_scenario(s) for s in args.scenarios]
    reference = (args.reference[0], float(args.reference[1]), int(args.reference[2]))
    inputs = {name: load_scenario(args.scenario_root / name) for name, _, _ in scenarios}
    grid = recovery_grid(inputs, scenarios, args.thresholds, args.runs)
    distribution = status_distribution(grid)
    changes, transitions, unmatched = against_reference(grid, reference)
    stable = stability(grid, reference)
    days = recovery_day_range(grid)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    grid.to_csv(out / 'recovery_grid_metrics_PRIVATE_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    unmatched.to_csv(out / 'unmatched_events_PRIVATE_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    distribution.to_csv(out / 'status_distribution.csv', index=False, encoding='utf-8-sig')
    changes.to_csv(out / 'reference_changes.csv', index=False, encoding='utf-8-sig')
    transitions.to_csv(out / 'reference_transitions.csv', index=False, encoding='utf-8-sig')
    stable.to_csv(out / 'stability.csv', index=False, encoding='utf-8-sig')
    days.to_csv(out / 'recovery_day_range.csv', index=False, encoding='utf-8-sig')
    (out / 'sensitivity_summary.md').write_text(
        summary_markdown(distribution, changes, transitions, stable, days, unmatched, reference), encoding='utf-8')
    print(f'{len(grid)} rows over {grid[SETTING].drop_duplicates().shape[0]} settings; review only, no rankings')


if __name__ == '__main__':
    main()
