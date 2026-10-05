"""Descriptive decline ordering vs unordered support states; no policy ranking."""
import numpy as np
import pandas as pd

from scripts.prepare_priority import KEY
from scripts.prepare_sales_baseline import bool_column


BANDS = ['top3_including_ties', 'other_available', 'decline_unavailable']


def comparison_fields(detail):
    required = KEY + ['scope', 'decline_rate', 'observation_days', 'consecutive_days',
                      'recovery_status', 'support_review_group', 'support_review_label']
    if missing := set(required) - set(detail):
        raise ValueError(f'comparison columns missing: {sorted(missing)}')
    out = detail.copy()
    if out.empty or out[KEY].isna().any().any() or out.duplicated(KEY).any():
        raise ValueError('empty/missing/duplicate comparison keys')
    if not out.age.eq('ALL').all() or out.scope.isna().any():
        raise ValueError('comparison requires ALL rows and scope')
    decline = pd.to_numeric(out.decline_rate, errors='raise')
    if np.isinf(decline.to_numpy(dtype=float)).any():
        raise ValueError('non-finite decline')
    counts = out[['observation_days', 'consecutive_days']].apply(pd.to_numeric, errors='raise')
    if (not np.isfinite(counts.to_numpy(dtype=float)).all() or
            counts.mod(1).ne(0).any().any() or counts.observation_days.lt(0).any() or
            counts.consecutive_days.lt(1).any()):
        raise ValueError('invalid observation/run days')
    # All finite event declines are ordered, including zero/negative values;
    # eligibility does not depend on post-event money, recovery, or Pareto rank.
    out['decline_rank_all_available'] = decline.groupby(
        [out.event_id, out.region, out.scope]).rank(method='min', ascending=False).astype('Int64')
    out['decline_comparison_band'] = np.where(decline.isna(), 'decline_unavailable',
        np.where(out.decline_rank_all_available.le(3).fillna(False), 'top3_including_ties', 'other_available'))
    # Calendar-only opportunity count, NOT a count of valid observed runs.
    positions = (counts.observation_days - counts.consecutive_days + 1).clip(lower=0).astype(int)
    out['calendar_recovery_start_positions'] = positions
    out['observation_window_constraint'] = np.where(positions.eq(0), 'no_calendar_run',
        np.where(positions.eq(1), 'single_calendar_run', 'multiple_calendar_runs'))
    out['censored_short_window'] = out.recovery_status.eq('censored') & positions.le(1)
    out['observation_constraint_note'] = np.where(positions.le(1),
        '관찰기간 제약: 달력상 연속 회복 시작 기회가 최대 1회; 실제 유효 기회는 공휴일·결측에 따라 달라짐',
        '달력상 여러 시작 기회가 있음; 실제 유효 기회는 공휴일·결측에 따라 달라짐')
    return out


def comparison_tables(detail):
    out = comparison_fields(detail)
    cross = out.groupby(['event_id', 'region', 'scope', 'decline_comparison_band',
                         'support_review_group', 'support_review_label'], sort=True).size().rename(
                             'industry_event_rows').reset_index()
    return out, cross


def coverage_tables(detail, daily):
    """Separate date completeness, period completeness, and known-prediction share.

    Shares include available age-level predictions even if actuals are missing.
    Missing predictions remain unknown; shares are not citywide sales coverage.
    """
    d = daily.loc[daily.window_type.eq('effective') & daily.baseline_mode.eq('fixed_pre_event') &
                  daily.missing_policy.eq('exclude_missing') & daily.model_id.eq('weekday_mean')].copy()
    groups = [c for c in KEY if c != 'age']
    m = detail.copy()
    for f in [d, m]:
        for c in ['window_start', 'window_end']:
            f[c] = pd.to_datetime(f[c], errors='raise').dt.strftime('%Y-%m-%d')
    if d.empty or d.age.eq('ALL').any() or d[KEY + ['date']].isna().any().any() or d.duplicated(KEY + ['date']).any():
        raise ValueError('invalid daily age grid')
    if m.empty or m[KEY].isna().any().any() or m.duplicated(KEY).any() or not m.age.eq('ALL').all():
        raise ValueError('invalid metric keys')
    for c in ['amount', 'prediction']:
        d[c] = pd.to_numeric(d[c], errors='raise')
        if not np.isfinite(d[c].dropna()).all() or d[c].dropna().lt(0).any():
            raise ValueError('invalid monetary value')
    d['date'] = pd.to_datetime(d.date, errors='raise')
    d['is_holiday'] = bool_column(d.is_holiday, 'is_holiday')
    if not d.phase.isin(['event', 'observation']).all():
        raise ValueError('invalid phase')
    membership = d[groups].drop_duplicates().merge(m[groups], how='outer', on=groups, indicator=True)
    if not membership._merge.eq('both').all():
        raise ValueError('coverage keys differ')
    rows = []
    for key, g in d.groupby(groups):
        if (not pd.DatetimeIndex(g.date.drop_duplicates().sort_values()).equals(pd.date_range(key[-2], key[-1])) or
                not g.groupby('date').age.nunique().eq(g.age.nunique()).all()):
            raise ValueError('incomplete date/age grid')
        if g.groupby('date')[['phase', 'is_holiday']].nunique().gt(1).any().any():
            raise ValueError('conflicting date metadata')
        paired = g.amount.notna() & g.prediction.notna()
        complete_by_date = paired.groupby(g.date).all()
        event = g.phase.eq('event')
        eligible = ~g.is_holiday
        if not event.any():
            raise ValueError('event phase missing')
        row = dict(zip(groups, key))
        row.update(age='ALL', input_age_groups=g.age.nunique(),
                   calendar_days=len(complete_by_date), all_age_complete_dates=int(complete_by_date.sum()),
                   complete_event_window=bool(paired.loc[event].all()),
                   complete_calendar_window=bool(paired.all()),
                   complete_nonholiday_window=bool(eligible.any() and paired.loc[eligible].all()))
        for phase, take in [('event', event), ('window', pd.Series(True, index=g.index))]:
            row[f'known_{phase}_prediction_sum'] = g.loc[take, 'prediction'].sum(min_count=1)
            row[f'known_{phase}_prediction_cells'] = int(g.loc[take, 'prediction'].notna().sum())
            row[f'{phase}_prediction_cells'] = int(take.sum())
        rows.append(row)
    coverage = m[KEY + ['scope', 'recovery_status', 'decline_rate', 'complete_eligible_window']].merge(
        pd.DataFrame(rows), on=KEY, validate='one_to_one')
    if not bool_column(coverage.complete_eligible_window, 'complete_eligible_window').eq(coverage.complete_nonholiday_window).all():
        raise ValueError('eligible completeness differs')
    coverage['recovery_judgeable'] = coverage.recovery_status.ne('insufficient_data')
    summaries = []
    for event_id, group in [('ALL_EVENTS', coverage), *list(coverage.groupby('event_id'))]:
        for scope, g in [('all_scopes', group), *list(group.groupby('scope'))]:
            available = g.recovery_judgeable
            row = dict(event_id=event_id, scope=scope, industry_event_rows=len(g),
                       recovery_unjudgeable_rows=int((~available).sum()),
                       recovery_unjudgeable_fraction=float((~available).mean()),
                       decline_available_rows=int(g.decline_rate.notna().sum()),
                       event_complete_rows=int(g.complete_event_window.sum()),
                       eligible_complete_rows=int(g.complete_nonholiday_window.sum()),
                       calendar_complete_rows=int(g.complete_calendar_window.sum()))
            for phase in ['event', 'window']:
                col = f'known_{phase}_prediction_sum'
                numerator = g.loc[available, col].sum(min_count=1) if available.any() else 0.
                denominator = g[col].sum(min_count=1)
                row[f'judgeable_known_{phase}_prediction_numerator'] = numerator
                row[f'known_{phase}_prediction_denominator'] = denominator
                row[f'judgeable_known_{phase}_prediction_share'] = numerator / denominator if denominator > 0 else np.nan
                row[f'known_{phase}_prediction_cell_fraction'] = g[f'known_{phase}_prediction_cells'].sum()/g[f'{phase}_prediction_cells'].sum()
            summaries.append(row)
    return coverage, pd.DataFrame(summaries)


def write_comparison(detail, daily, output):
    result, cross = comparison_tables(detail)
    coverage, summary = coverage_tables(result, daily)
    for name, frame in [('decline_rank_vs_state.csv', result), ('decline_state_crosstab.csv', cross),
                        ('all_completeness_detail.csv', coverage), ('comparison_coverage.csv', summary)]:
        frame.to_csv(output / name, index=False, encoding='utf-8-sig')
    plot_comparison(cross, output)


def plot_comparison(cross, output):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt, font_manager
    from matplotlib.ticker import MaxNLocator
    selected = cross.loc[cross.scope.eq('primary')].copy()
    if selected.empty:
        return
    labels = {'top3_including_ties': '감소율 상위 3위·동률 포함', 'other_available': '그 외 계산 가능',
              'decline_unavailable': '감소율 계산 불가'}
    selected['비교군'] = selected.event_id + ' · ' + selected.decline_comparison_band.map(labels)
    matrix = selected.pivot_table(index='비교군', columns='support_review_label', values='industry_event_rows', fill_value=0)
    order = [f'{event} · {labels[band]}' for event in sorted(selected.event_id.unique()) for band in BANDS]
    matrix = matrix.reindex(order, fill_value=0)
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    family = next((f for f in ['AppleGothic', 'Malgun Gothic', 'NanumGothic'] if f in fonts), 'DejaVu Sans')
    with plt.rc_context({'font.family': family, 'axes.unicode_minus': False}):
        fig, ax = plt.subplots(figsize=(14, 7))
        matrix.plot.barh(stacked=True, ax=ax, colormap='Set2')
        ax.invert_yaxis()
        ax.set_ylabel('')
        ax.set_xlabel('사건×업종 행 수')
        ax.set_title('감소율 순위와 지원 검토 상태 — 순위 우수성·예산 순서 비교 아님')
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False, fontsize=9)
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout()
        fig.savefig(output / 'decline_state_comparison.png', dpi=150)
        plt.close(fig)
