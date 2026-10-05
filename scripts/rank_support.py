"""Provisional industry priorities from matched baseline/recovery inputs.

No weighted score is imposed. Non-dominated layers use decline, net shortfall
rate and confirmed recovery delay within one event and one scope. Censored or
incomplete cases remain in separate review queues, never assigned fake days.
"""
import argparse
import hashlib
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import prepare_sales_baseline as baseline
from scripts.compute_recovery import PRIMARY_INDUSTRIES, recovery_day


def paired_industry(daily, model):
    selected = daily.loc[daily.window_type.eq('effective') &
                         daily.baseline_mode.eq('fixed_pre_event') &
                         daily.missing_policy.eq('exclude_missing') &
                         daily.model_id.eq(model)].copy()
    if selected.empty:
        raise ValueError('missing requested baseline variant')
    # Reuse the shared pairing/sum routine; restore the actual model label.
    aggregate = baseline.industry_daily(selected.assign(model_id='weekday_mean'))
    aggregate['model_id'] = model
    flags = selected[['event_id', 'date', 'is_holiday']].drop_duplicates()
    if flags.duplicated(['event_id', 'date']).any():
        raise ValueError('inconsistent calendar flags')
    return aggregate.merge(flags, on=['event_id', 'date'], validate='many_to_one')


def industry_metrics(industry, events, threshold=.95, consecutive=3,
                     calendar_provenance='unknown_review_required'):
    if not 0 < threshold <= 1 or consecutive < 1:
        raise ValueError('invalid recovery rule')
    event_info = events.set_index('event_id')
    if not event_info.index.is_unique:
        raise ValueError('duplicate event IDs')
    records = []
    for (event_id, region, name), g in industry.groupby(['event_id', 'region', 'industry']):
        g = g.sort_values('date').copy()
        g['date'] = pd.to_datetime(g.date)
        first, last = pd.to_datetime(g.window_start.iloc[0]), pd.to_datetime(g.window_end.iloc[0])
        if not pd.DatetimeIndex(g.date).equals(pd.date_range(first, last)):
            raise ValueError('industry event window has gaps or duplicates')
        ev = event_info.loc[event_id]
        end = pd.Timestamp(ev.end_date)
        event = g.loc[g.phase.eq('event')]
        if not pd.DatetimeIndex(event.date).equals(pd.date_range(pd.Timestamp(ev.start_date), end)):
            raise ValueError('event phase dates disagree')
        valid = g.complete_group_coverage.eq(True)
        event_valid = event.complete_group_coverage.eq(True).all()
        event_denominator = event.prediction_paired.sum()
        decline = 1-event.amount_paired.sum()/event_denominator if event_valid and event_denominator > 0 else np.nan
        eligible = ~g.is_holiday.eq(True)
        complete = bool(eligible.any() and valid.loc[eligible].all())
        q = g.loc[eligible & valid]
        gap = q.prediction_paired-q.amount_paired
        expected = q.prediction_paired.sum()
        net = float(gap.sum()) if complete else np.nan
        gross = float(gap.clip(lower=0).sum()) if complete else np.nan
        rate = net/expected if complete and expected > 0 else np.nan
        obs = g.loc[g.phase.eq('observation')].copy()
        obs['day_offset'] = (obs.date-end).dt.days
        obs['ratio'] = (obs.amount_paired / obs.prediction_paired.where(obs.prediction_paired.gt(0))).where(obs.complete_group_coverage.eq(True))
        if pd.isna(decline):
            status, day, date = 'insufficient_data', None, pd.NaT
        elif 1-decline >= threshold:
            status, day, date = 'no_decline', None, pd.NaT
        else:
            status, day, date = recovery_day(obs, threshold, consecutive)
        records.append({'event_id': event_id, 'region': region, 'industry': name, 'age': 'ALL',
                        'scope': 'primary' if name in PRIMARY_INDUSTRIES else 'auxiliary',
                        'window_start': str(first.date()), 'window_end': str(last.date()),
                        'analysis_role': ev.analysis_role, 'model_id': g.model_id.iloc[0],
                        'recovery_threshold': threshold, 'consecutive_days': consecutive,
                        'decline_rate': decline, 'gross_shortfall_eligible': gross,
                        'net_shortfall_eligible': net, 'net_shortfall_rate_eligible': rate,
                        'complete_eligible_window': complete,
                        'eligible_days': int(eligible.sum()), 'paired_complete_days': len(q),
                        'mean_group_coverage': float(g.group_coverage.mean()),
                        'holiday_excluded_days': int((~eligible).sum()),
                        'total_age_groups': int(g.total_groups.iloc[0]),
                        'recovery_status': status, 'recovery_days': day,
                        'confirmation_days': day + consecutive - 1 if status == 'recovered' else np.nan,
                        'recovery_date': date, 'observation_days': len(obs),
                        'calendar_provenance': calendar_provenance,
                        'recovery_uncertainty_note': f'{ev.analysis_role}; effective window; all input age groups required; calendar={calendar_provenance}; holiday_policy=break; provisional recovery rule'})
    return pd.DataFrame(records)


def pareto_layers(values):
    """Larger is worse for every dimension. Ties share a layer."""
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError('Pareto ranking requires finite measures')
    result = np.zeros(len(x), dtype=int)
    pending = list(range(len(x)))
    layer = 1
    while pending:
        front = []
        for i in pending:
            dominated = any(np.all(x[j] >= x[i]-1e-12) and np.any(x[j] > x[i]+1e-12)
                            for j in pending if j != i)
            if not dominated:
                front.append(i)
        if not front:
            raise ValueError('no Pareto front found')
        result[front] = layer
        pending = [i for i in pending if i not in front]
        layer += 1
    return result


def rank_metrics(metrics):
    out = metrics.copy()
    out['priority_tier'] = pd.Series(pd.NA, index=out.index, dtype='Int64')
    out['decline_only_rank'] = pd.Series(pd.NA, index=out.index, dtype='Int64')
    # Order of checks is deliberate; an unknown loss cannot be called zero.
    out['review_queue'] = 'data_incomplete'
    complete = out.complete_eligible_window & out.decline_rate.notna() & out.net_shortfall_rate_eligible.notna()
    positive = complete & out.net_shortfall_rate_eligible.gt(0)
    out.loc[complete & ~positive, 'review_queue'] = 'no_positive_net_shortfall'
    out.loc[positive & out.recovery_status.eq('no_decline'), 'review_queue'] = 'below_decline_threshold'
    out.loc[positive & out.recovery_status.eq('censored'), 'review_queue'] = 'recovery_unconfirmed_review'
    out.loc[positive & out.recovery_status.eq('insufficient_data'), 'review_queue'] = 'recovery_data_insufficient'
    candidates = positive & out.decline_rate.gt(0) & out.recovery_status.eq('recovered') & out.confirmation_days.notna()
    out.loc[candidates, 'review_queue'] = 'ranked_candidate'
    dimensions = ['decline_rate', 'net_shortfall_rate_eligible', 'confirmation_days']
    for _, g in out.loc[candidates].groupby(['event_id', 'scope']):
        out.loc[g.index, 'priority_tier'] = pareto_layers(g[dimensions])
        out.loc[g.index, 'decline_only_rank'] = g.decline_rate.rank(method='min', ascending=False).astype('Int64')
    return out


def stability_table(scenarios):
    keys = ['event_id', 'region', 'industry', 'scope']
    rows = []
    for key, g in scenarios.groupby(keys):
        ranks = g.priority_tier.dropna()
        rows.append({**dict(zip(keys, key)), 'scenarios': len(g), 'rankable_scenarios': len(ranks),
                     'first_tier_scenarios': int(ranks.eq(1).sum()),
                     'tier_min_when_rankable': int(ranks.min()) if len(ranks) else None,
                     'tier_max_when_rankable': int(ranks.max()) if len(ranks) else None,
                     'first_tier_fraction_all_scenarios': float(ranks.eq(1).sum()/len(g)),
                     'classification_changes': int(g.review_queue.nunique())})
    return pd.DataFrame(rows)


def plot_results(base, scenarios, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator
    from matplotlib import font_manager
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams['font.family'] = next((f for f in ['AppleGothic', 'Malgun Gothic', 'NanumGothic'] if f in fonts), 'DejaVu Sans')
    plt.rcParams['axes.unicode_minus'] = False
    labels = {'ranked_candidate': '순위 비교 가능', 'recovery_unconfirmed_review': '회복 미확인',
              'recovery_data_insufficient': '회복 관찰 부족', 'data_incomplete': '매출 자료 부족',
              'no_positive_net_shortfall': '양의 순부족 없음', 'below_decline_threshold': '감소 기준 미충족'}
    colors = ['#236d82', '#cf8c33', '#d9be8c', '#c47d82', '#b6b6b6', '#81a690']
    primary = base.loc[base.scope.eq('primary')]
    counts = primary.groupby(['event_id', 'review_queue']).size().unstack(fill_value=0).reindex(columns=labels, fill_value=0)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    counts.rename(columns=labels).plot.barh(stacked=True, color=colors, ax=ax)
    ax.set_xlabel('사건별 주 분석 업종 수 (18개)')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylabel('')
    ax.set_title('지원 우선순위에 앞서 확인할 자료·회복 상태')
    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False)
    ax.spines[['top', 'right']].set_visible(False)
    fig.tight_layout()
    fig.savefig(output/'priority_coverage.png', dpi=150)
    plt.close(fig)
    s = scenarios.loc[scenarios.scope.eq('primary')].copy()
    focus = s.loc[s.review_queue.isin(['ranked_candidate', 'recovery_unconfirmed_review']), ['event_id', 'industry']].drop_duplicates()
    s = s.merge(focus, on=['event_id', 'industry'], validate='many_to_one')
    if s.empty:
        return
    status_order = list(labels)
    s['status_code'] = s.review_queue.map({k: i for i, k in enumerate(status_order)})
    s['row_label'] = s.event_id + ' · ' + s.industry
    matrix = s.pivot(index='row_label', columns='scenario', values='status_code')
    fig, ax = plt.subplots(figsize=(12, max(6, len(matrix)*.55+3)))
    ax.imshow(matrix, cmap=ListedColormap(colors), vmin=-.5, vmax=len(colors)-.5, aspect='auto')
    short = [c.replace('weekday_mean_threshold', '평균 ').replace('weekday_median_threshold', '중앙값 ').replace('_run', ' / 연속 ') for c in matrix.columns]
    ax.set_xticks(range(len(short)), short, rotation=65, ha='right', fontsize=8)
    ax.set_yticks(range(len(matrix)), matrix.index, fontsize=9)
    fig.suptitle('18개 설정에서의 대상 분류 변화 (빈도는 확률·신뢰도가 아님)', y=.98)
    fig.legend(handles=[Patch(color=c, label=labels[k]) for c, k in zip(colors, status_order)],
               loc='upper center', bbox_to_anchor=(.55, .93), ncol=3, frameon=False, fontsize=8)
    fig.tight_layout(rect=[0, 0, 1, .81])
    fig.savefig(output/'priority_sensitivity.png', dpi=150)
    plt.close(fig)


def run(daily_path, events_path, output, run_metadata=None):
    if output.exists() and any(output.iterdir()):
        raise ValueError('use a new output directory')
    daily = pd.read_csv(daily_path, parse_dates=['date', 'window_start', 'window_end'])
    events = pd.read_csv(events_path)
    metadata = json.loads(run_metadata.read_text(encoding='utf-8-sig')) if run_metadata else {}
    if not isinstance(metadata, dict):
        raise ValueError('run metadata must be an object')
    provenance = metadata.get('calendar_provenance', 'unknown_review_required')
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError('invalid calendar provenance')
    if 'daily_rows' in metadata and metadata['daily_rows'] != len(daily):
        raise ValueError('run metadata row count differs')
    daily['is_holiday'] = baseline.bool_column(daily.is_holiday, 'is_holiday')
    if provenance == 'provisional_2025_08_15_only' and not daily.is_holiday.eq(daily.date.eq(pd.Timestamp('2025-08-15'))).all():
        raise ValueError('calendar flags differ from declared provisional calendar')
    scenarios = []
    for model in ['weekday_mean', 'weekday_median']:
        industry = paired_industry(daily, model)
        for threshold, days in product([.90, .95, 1.0], [2, 3, 4]):
            result = rank_metrics(industry_metrics(industry, events, threshold, days, provenance))
            result['scenario'] = f'{model}_threshold{threshold:.2f}_run{days}'
            scenarios.append(result)
    scenarios = pd.concat(scenarios, ignore_index=True)
    base = scenarios.loc[scenarios.scenario.eq('weekday_mean_threshold0.95_run3')].copy()
    stability = stability_table(scenarios)
    base = base.merge(stability, on=['event_id', 'region', 'industry', 'scope'], validate='one_to_one')
    # Grades are partial orders, not a fabricated total rank. Record only real inversions.
    changes = []
    for (event, scope), g in base.loc[base.review_queue.eq('ranked_candidate')].groupby(['event_id', 'scope']):
        for a in g.itertuples():
            for b in g.itertuples():
                if a.decline_only_rank < b.decline_only_rank and a.priority_tier > b.priority_tier:
                    changes.append({'event_id': event, 'scope': scope, 'decline_higher_industry': a.industry,
                                    'priority_higher_industry': b.industry, 'reason': 'net shortfall rate and/or recovery confirmation delay; Pareto layer difference'})
    output.mkdir(parents=True, exist_ok=True)
    base.to_csv(output/'support_priority_PROVISIONAL.csv', index=False, encoding='utf-8-sig')
    scenarios.to_csv(output/'priority_sensitivity.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(changes, columns=['event_id', 'scope', 'decline_higher_industry', 'priority_higher_industry', 'reason']).to_csv(output/'rank_reversals.csv', index=False, encoding='utf-8-sig')
    rules = {'version': '1007-pareto-v1', 'status': 'analyst-selected provisional policy; not collective approval',
             'input_sha256': {'daily': hashlib.sha256(daily_path.read_bytes()).hexdigest(),
                              'events': hashlib.sha256(events_path.read_bytes()).hexdigest()},
             'comparison_groups': ['event_id', 'scope'], 'main_scope': 'primary (18 predefined industries)',
             'metrics': ['decline_rate', 'net_shortfall_rate_eligible', 'confirmation_days'],
             'weights': None, 'tie_rule': 'same Pareto layer; no forced total order',
             'coverage_rule': 'all input age groups paired on every nonholiday day of the event/effective window',
             'censored_rule': 'separate recovery_unconfirmed_review queue; no imputed delay',
             'monetary_scope': 'eligible nonholiday days only; never full-window or city-wide damage',
             'base_recovery_rule': {'threshold': .95, 'consecutive_days': 3},
             'sensitivity': {'baseline': ['mean', 'median'], 'threshold': [.9, .95, 1.0], 'consecutive_days': [2, 3, 4]},
             'rank_reversals': len(changes), 'calendar_status': provenance,
             'holiday_policy': 'break consecutive recovery; exclude from monetary eligible window'}
    if run_metadata:
        rules['input_sha256']['baseline_run_metadata'] = hashlib.sha256(run_metadata.read_bytes()).hexdigest()
    (output/'priority_rules.json').write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')
    plot_results(base, scenarios, output)
    print(base.groupby(['event_id', 'scope', 'review_queue']).size().to_string())
    print(f'Rank inversions relative to decline-only ordering: {len(changes)}')
    return base, scenarios


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daily', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--run-metadata', type=Path, help='Metadata from the same baseline run; does not certify API provenance')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.daily, args.events, args.output, args.run_metadata)
