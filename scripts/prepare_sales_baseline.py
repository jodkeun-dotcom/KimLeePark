"""Exploratory event baselines; daily predictions are local handoff artifacts."""
import argparse
import json
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd

KEY = ['region', 'industry', 'age']
PRIMARY = {'한식', '중식', '일식', '양식', '기타요식', '제과점', '커피전문점',
           '패스트푸드', '편의점', '할인점/슈퍼마켓/양판점', '농수산물', '정육점',
           '기타식품', '주류판매', '영화/공연', '게임방/오락실', '노래방', '종합레저타운/놀이동산'}
MODELS = {'weekday_mean': 'mean', 'weekday_median': 'median'}


def require_columns(frame, columns, name):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f'{name}: missing columns {sorted(missing)}')


def parse_dates(frame, columns, name):
    frame = frame.copy()
    for col in columns:
        frame[col] = pd.to_datetime(frame[col], errors='raise')
        if frame[col].isna().any() or not frame[col].eq(frame[col].dt.normalize()).all():
            raise ValueError(f'{name}: missing or non-daily date in {col}')
    return frame


def bool_column(series, name):
    values = series.astype(str).str.lower().map({'true': True, 'false': False, '1': True, '0': False})
    if values.isna().any():
        raise ValueError(f'{name}: expected true/false or 1/0')
    return values.astype(bool)


def validate_daily(frame, primary=PRIMARY):
    require_columns(frame, ['date', 'amount'] + KEY, 'daily')
    frame = parse_dates(frame, ['date'], 'daily')
    if frame.empty or frame[KEY].isna().any().any() or frame[KEY].apply(lambda s: s.str.strip().eq('')).any().any():
        raise ValueError('daily: empty input or missing group keys')
    if frame.duplicated(['date'] + KEY).any():
        raise ValueError('daily: duplicate date/group keys')
    frame['amount'] = pd.to_numeric(frame.amount, errors='raise')
    if not np.isfinite(frame.amount).all() or frame.amount.lt(0).any():
        raise ValueError('daily: amounts must be finite and nonnegative')
    absent = set(primary) - set(frame.industry)
    if absent:
        raise ValueError(f'primary industries absent from daily input: {sorted(absent)}')
    return frame.sort_values(['date'] + KEY).reset_index(drop=True)


def load_events(events_path, windows_path):
    events = pd.read_csv(events_path, dtype={'event_id': str})
    require_columns(events, ['event_id', 'type', 'start_date', 'end_date', 'analysis_role'], 'events')
    if events.event_id.isna().any() or events.event_id.duplicated().any():
        raise ValueError('events: missing/duplicate event_id')
    # PR #24 includes a dated-less excluded SNOW_NA row. Only it may omit dates.
    missing = events[['start_date', 'end_date']].isna().any(axis=1)
    allowed_undated = events.analysis_role.eq('excluded') & events.type.eq('폭설') & events[['start_date', 'end_date']].isna().all(axis=1)
    if (missing & ~allowed_undated).any():
        raise ValueError('events: only excluded undated snow records may omit dates')
    events = parse_dates(events.loc[~missing], ['start_date', 'end_date'], 'events')
    if events.start_date.gt(events.end_date).any():
        raise ValueError('events: reversed date range')
    windows = pd.read_csv(windows_path, dtype={'event_id': str})
    require_columns(windows, ['event_id', 'date', 'window', 'is_effective'], 'event windows')
    windows = parse_dates(windows, ['date'], 'event windows')
    windows['is_effective'] = bool_column(windows.is_effective, 'is_effective')
    if windows.duplicated(['event_id', 'date']).any() or not windows.event_id.isin(events.event_id).all():
        raise ValueError('event windows: duplicate keys or unknown event')
    if not windows.window.isin(['baseline', 'event', 'observation']).all():
        raise ValueError('event windows: unknown window label')
    # Every dated event needs its exact event dates; every selected heat window must be contiguous.
    for ev in events.itertuples():
        w = windows.loc[windows.event_id.eq(ev.event_id)]
        actual = pd.DatetimeIndex(w.loc[w.window.eq('event'), 'date']).sort_values()
        if not actual.equals(pd.date_range(ev.start_date, ev.end_date)):
            raise ValueError(f'{ev.event_id}: event dates disagree between CSV inputs')
        if not w.loc[w.window.eq('event'), 'is_effective'].all():
            raise ValueError(f'{ev.event_id}: event days unexpectedly ineffective')
        obs = w.loc[w.window.eq('observation')].sort_values('date')
        observation_start = pd.Timestamp(getattr(ev, 'observation_start', ev.end_date + pd.Timedelta(days=1)))
        if len(obs) and not pd.DatetimeIndex(obs.date).equals(pd.date_range(observation_start, obs.date.max())):
            raise ValueError(f'{ev.event_id}: observation mapping has gaps')
        if obs.is_effective.astype(int).diff().gt(0).any():
            raise ValueError(f'{ev.event_id}: effective observation must be a prefix')
    return events, windows


def calendar_flags(dates, calendar_path=None):
    if calendar_path is None:
        return pd.Series(pd.DatetimeIndex(dates) == pd.Timestamp('2025-08-15'), index=dates), 'provisional_2025_08_15_only'
    c = pd.read_csv(calendar_path)
    require_columns(c, ['date', 'is_holiday'], 'calendar')
    c = parse_dates(c, ['date'], 'calendar')
    c['is_holiday'] = bool_column(c.is_holiday, 'is_holiday')
    if c.date.duplicated().any():
        raise ValueError('calendar: duplicate dates')
    flags = c.set_index('date').is_holiday.reindex(dates)
    if flags.isna().any():
        raise ValueError('calendar: must cover every input date')
    return flags, 'provided_calendar'


def build_panel(daily, events, calendar_path=None):
    groups = daily[KEY].drop_duplicates()
    dates = pd.date_range(daily.date.min(), daily.date.max())
    flags, provenance = calendar_flags(dates, calendar_path)
    panel = groups.merge(pd.DataFrame({'date': dates}), how='cross').merge(
        daily[['date'] + KEY + ['amount']], on=['date'] + KEY, how='left', validate='one_to_one')
    panel['actual_status'] = np.where(panel.amount.notna(), 'observed', 'missing_row_unknown')
    panel['weekday'] = panel.date.dt.dayofweek
    panel['is_holiday'] = panel.date.map(flags)
    panel['is_event'] = False
    for ev in events.itertuples():
        panel.loc[panel.date.between(ev.start_date, ev.end_date), 'is_event'] = True
    panel['eligible_train'] = ~panel.is_event & ~panel.is_holiday
    return panel, provenance


def training_sample(panel, origin, policy='exclude_missing', retrospective_end=None, masked_dates=()):
    use = panel.eligible_train & panel.date.lt(origin)
    if retrospective_end is not None:
        use = panel.eligible_train & panel.date.between(origin - pd.Timedelta(days=28), retrospective_end + pd.Timedelta(days=28))
        use &= ~panel.date.isin(masked_dates)
    train = panel.loc[use].copy()
    if policy == 'zero_fill_sensitivity':
        train['amount'] = train.amount.fillna(0)
    elif policy == 'exclude_missing':
        train = train.loc[train.amount.notna()]
    else:
        raise ValueError('unknown missing policy')
    if retrospective_end is None and not train.empty and train.date.max() >= origin:
        raise ValueError('fixed baseline training leaks target dates')
    return train


def predict(train, target, min_total=7, min_weekday=2):
    stats = train.groupby(KEY + ['weekday']).amount.agg(['mean', 'median', 'count']).reset_index()
    totals = train.groupby(KEY).agg(train_days=('amount', 'count'), train_start=('date', 'min'), train_end=('date', 'max')).reset_index()
    p = target.merge(stats, on=KEY + ['weekday'], how='left', validate='many_to_one').merge(totals, on=KEY, how='left', validate='many_to_one')
    sufficient = p['count'].ge(min_weekday) & p.train_days.ge(min_total)
    p['prediction_status'] = np.where(p.is_holiday, 'holiday_excluded', np.where(sufficient, 'predicted', 'insufficient_training'))
    p.loc[p.prediction_status.ne('predicted'), ['mean', 'median']] = np.nan
    p['train_days'] = p.train_days.fillna(0).astype(int)
    p['count'] = p['count'].fillna(0).astype(int)
    return p


def event_targets(panel, ev, windows):
    w = windows.loc[windows.event_id.eq(ev.event_id) & windows.window.isin(['event', 'observation'])]
    effective = w.loc[w.is_effective, 'date'].sort_values()
    if len(effective) == 0:
        raise ValueError(f'{ev.event_id}: empty effective window')
    if not pd.DatetimeIndex(effective).equals(pd.date_range(ev.start_date, effective.max())):
        raise ValueError(f'{ev.event_id}: non-contiguous effective window')
    if effective.min() < panel.date.min() or w.date.max() > panel.date.max():
        raise ValueError(f'{ev.event_id}: target window outside daily input range')
    yield 'effective', panel.loc[panel.date.isin(effective)].copy()
    if w.date.max() > effective.max():
        yield 'nominal_overlap_sensitivity', panel.loc[panel.date.isin(w.date)].copy()


def summarize(g, model, ev, window_type, policy, baseline_mode, primary):
    col = MODELS[model]
    paired = g.amount.notna() & g[col].notna()
    eligible = ~g.is_holiday
    q = g.loc[paired]
    full = bool(paired.all())
    eligible_complete = bool(eligible.any() and paired.loc[eligible].all())
    expected = q[col].sum() if len(q) else None
    gap = q[col] - q.amount
    gross = float(gap.clip(lower=0).sum()) if len(q) else None
    net = float(gap.sum()) if len(q) else None
    row = {k: g[k].iloc[0] for k in KEY}
    row.update(event_id=ev.event_id, event_end=ev.end_date.strftime('%Y-%m-%d'), analysis_role=ev.analysis_role,
               window_start=g.date.min().strftime('%Y-%m-%d'), window_end=g.date.max().strftime('%Y-%m-%d'),
               window_type=window_type, missing_policy=policy, baseline_mode=baseline_mode, model_id=model,
               scope='primary' if row['industry'] in primary else 'auxiliary', window_days=len(g),
               eligible_window_days=int(eligible.sum()), holiday_excluded_days=int(g.is_holiday.sum()),
               missing_actual_days=int(g.actual_status.eq('missing_row_unknown').sum()),
               insufficient_training_days=int(g.prediction_status.eq('insufficient_training').sum()),
               paired_days=int(paired.sum()), coverage=float(paired.mean()),
               eligible_coverage=float(paired.sum()/eligible.sum()) if eligible.any() else None,
               complete_window=full, complete_eligible_window=eligible_complete,
               expected_total_paired=float(expected) if expected is not None else None,
               gross_shortfall_paired=gross, net_shortfall_paired=net,
               gross_shortfall_full=gross if full else None, net_shortfall_full=net if full else None,
               net_shortfall_rate_full=net/expected if full and expected > 0 else None,
               net_shortfall_eligible=net if eligible_complete else None,
               net_shortfall_rate_eligible=net/expected if eligible_complete and expected > 0 else None,
               interpretation='baseline_difference_not_causal_damage')
    event_rows = g.loc[g.date.le(ev.end_date)]
    event_q = event_rows.loc[event_rows.amount.notna() & event_rows[col].notna()]
    denom = event_q[col].sum()
    row['decline_rate_event'] = float((denom-event_q.amount.sum())/denom) if len(event_q)==len(event_rows) and denom>0 else None
    if row['paired_days'] > row['eligible_window_days'] or row['paired_days'] > row['window_days']:
        raise ValueError('paired days exceed target window')
    return row


def calculate(panel, events, windows, primary=PRIMARY, retrospective=False):
    daily_parts, summaries, validation = [], [], []
    # Retrospective sensitivity masks all event and effective recovery dates, including nested events.
    mask = windows.loc[windows.window.isin(['event', 'observation']) & windows.is_effective, 'date']
    for ev in events.loc[events.type.eq('폭염') & ~events.analysis_role.eq('excluded')].itertuples():
        for window_type, target in event_targets(panel, ev, windows):
            horizon = (target.date.max() - ev.start_date).days + 1
            if window_type == 'effective':
                origin = ev.start_date - pd.Timedelta(days=horizon)
                train = training_sample(panel, origin)
                check = panel.loc[panel.date.between(origin, ev.start_date-pd.Timedelta(days=1)) & panel.eligible_train].copy()
                pred = predict(train, check)
                q = pred.loc[pred.amount.notna() & pred['mean'].notna() & pred['median'].notna()]
                denom = q.amount.abs().sum()
                validation.append(dict(event_id=ev.event_id, horizon=horizon, candidate_days=check.date.nunique(),
                                       paired_days=q.date.nunique(), paired_rows=len(q), train_days=train.date.nunique(),
                                       mean_wape=float((q.amount-q['mean']).abs().sum()/denom) if denom>0 else None,
                                       median_wape=float((q.amount-q['median']).abs().sum()/denom) if denom>0 else None))
            modes = ['fixed_pre_event'] + (['retrospective_4week_sensitivity'] if retrospective else [])
            for mode in modes:
                for policy in ['exclude_missing', 'zero_fill_sensitivity']:
                    train = training_sample(panel, ev.start_date, policy,
                                            target.date.max() if mode.startswith('retrospective') else None, mask)
                    p = predict(train, target)
                    if policy == 'zero_fill_sensitivity':
                        p['amount'] = p.amount.fillna(0)
                    for model, col in MODELS.items():
                        for _, g in p.groupby(KEY, sort=False):
                            summaries.append(summarize(g, model, ev, window_type, policy, mode, primary))
                        handoff = p[['date'] + KEY + ['amount', 'actual_status', col, 'prediction_status', 'train_start', 'train_end', 'train_days', 'count', 'is_holiday']].rename(columns={col: 'prediction', 'count': 'weekday_train_days'})
                        handoff = handoff.assign(event_id=ev.event_id, window_start=target.date.min(), window_end=target.date.max(),
                                                 window_type=window_type, analysis_role=ev.analysis_role, model_id=model,
                                                 missing_policy=policy, baseline_mode=mode, model_origin=ev.start_date,
                                                 phase=np.where(p.date.le(ev.end_date), 'event', 'observation'))
                        daily_parts.append(handoff)
    if not daily_parts:
        raise ValueError('no non-excluded heat events to analyze')
    daily = pd.concat(daily_parts, ignore_index=True)
    unique = ['event_id', 'window_type', 'baseline_mode', 'missing_policy', 'model_id', 'date'] + KEY
    if daily.duplicated(unique).any():
        raise ValueError('duplicate daily handoff keys')
    return pd.DataFrame(summaries), daily, pd.DataFrame(validation)


def industry_daily(daily):
    """Sum actual and predicted sales over the exact same paired age groups."""
    selected = daily.loc[daily.window_type.eq('effective') & daily.baseline_mode.eq('fixed_pre_event') &
                         daily.missing_policy.eq('exclude_missing') & daily.model_id.eq('weekday_mean')].copy()
    if selected.age.eq('ALL').any():
        raise ValueError('industry aggregation requires age-detail rows only, not mixed ALL rows')
    keys = ['event_id', 'window_start', 'window_end', 'window_type', 'baseline_mode',
            'missing_policy', 'model_id', 'date', 'region', 'industry']
    if selected.duplicated(keys + ['age']).any():
        raise ValueError('duplicate age-detail rows for industry aggregation')
    paired = selected.amount.notna() & selected.prediction.notna()
    selected['amount_paired'] = selected.amount.where(paired)
    selected['prediction_paired'] = selected.prediction.where(paired)
    selected['paired'] = paired.astype(int)
    selected['observed'] = selected.amount.notna().astype(int)
    selected['predicted'] = selected.prediction.notna().astype(int)
    result = selected.groupby(keys, as_index=False, dropna=False).agg(
        amount_paired=('amount_paired', lambda x: x.sum(min_count=1)),
        prediction_paired=('prediction_paired', lambda x: x.sum(min_count=1)),
        paired_groups=('paired', 'sum'), total_groups=('age', 'nunique'),
        observed_groups=('observed', 'sum'), predicted_groups=('predicted', 'sum'),
        analysis_role=('analysis_role', 'first'), phase=('phase', 'first'))
    result['age'] = 'ALL'
    result['group_coverage'] = result.paired_groups / result.total_groups
    result['complete_group_coverage'] = result.paired_groups.eq(result.total_groups)
    result['aggregation_status'] = np.where(result.paired_groups.eq(0), 'no_paired_groups',
                                            np.where(result.complete_group_coverage, 'complete', 'partial'))
    return result


def write_outputs(output, results, daily, validation, provenance):
    output.mkdir(parents=True, exist_ok=True)
    retrospective_enabled = bool(results.baseline_mode.eq('retrospective_4week_sensitivity').any())
    # Remove only the optional file owned by this script, preserving unrelated user files.
    if not retrospective_enabled:
        (output/'retrospective_sensitivity.csv').unlink(missing_ok=True)
    records = json.loads(results.to_json(orient='records', force_ascii=False))
    (output/'event_shortfall.json').write_text(json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    daily.to_csv(output/'daily_predictions.csv', index=False, encoding='utf-8-sig', na_rep='')
    industry = industry_daily(daily)
    industry.to_csv(output/'daily_industry.csv', index=False, encoding='utf-8-sig', na_rep='')
    validation.to_csv(output/'fixed_validation.csv', index=False, encoding='utf-8-sig', na_rep='')
    key = ['event_id', 'window_start', 'window_end', 'window_type', 'baseline_mode', 'missing_policy'] + KEY
    mean = results.loc[results.model_id.eq('weekday_mean')]
    median = results.loc[results.model_id.eq('weekday_median')]
    methods = mean.merge(median, on=key, suffixes=('_mean', '_median'), validate='one_to_one')
    methods['net_rate_difference_pp'] = (methods.net_shortfall_rate_eligible_mean-methods.net_shortfall_rate_eligible_median).abs()*100
    available = methods.net_shortfall_rate_eligible_mean.notna() & methods.net_shortfall_rate_eligible_median.notna()
    methods['shortfall_sign_changed'] = pd.Series(pd.NA, index=methods.index, dtype='boolean')
    methods.loc[available, 'shortfall_sign_changed'] = np.sign(methods.loc[available, 'net_shortfall_eligible_mean']).ne(np.sign(methods.loc[available, 'net_shortfall_eligible_median']))
    methods.to_csv(output/'method_sensitivity.csv', index=False, encoding='utf-8-sig', na_rep='')
    policy_keys = ['event_id', 'window_start', 'window_end', 'window_type', 'baseline_mode', 'model_id'] + KEY
    missing = results.loc[results.missing_policy.eq('exclude_missing')].merge(
        results.loc[results.missing_policy.eq('zero_fill_sensitivity')], on=policy_keys, suffixes=('_exclude', '_zero'), validate='one_to_one')
    # Compare sums on each policy's available dates; coverage is retained so these are not same-support effects.
    missing['net_shortfall_paired_difference'] = missing.net_shortfall_paired_zero-missing.net_shortfall_paired_exclude
    missing.to_csv(output/'missing_policy_sensitivity.csv', index=False, encoding='utf-8-sig', na_rep='')
    if retrospective_enabled:
        mode_keys = ['event_id', 'window_start', 'window_end', 'window_type', 'model_id', 'missing_policy'] + KEY
        modes = results.loc[results.baseline_mode.eq('fixed_pre_event')].merge(
            results.loc[results.baseline_mode.eq('retrospective_4week_sensitivity')], on=mode_keys, suffixes=('_fixed', '_retrospective'), validate='one_to_one')
        modes['eligible_rate_difference_pp'] = (modes.net_shortfall_rate_eligible_fixed-modes.net_shortfall_rate_eligible_retrospective).abs()*100
        modes.to_csv(output/'retrospective_sensitivity.csv', index=False, encoding='utf-8-sig', na_rep='')
    base = results.loc[results.baseline_mode.eq('fixed_pre_event') & results.missing_policy.eq('exclude_missing') & results.model_id.eq('weekday_mean')]
    lines = [dedent(f'''\
        # 잠정 기준선 계산·검증 보고서

        그룹 {daily[KEY].drop_duplicates().shape[0]}개, 업종 {daily.industry.nunique()}개.
        달력 출처: {provenance}. 실제 일별 CSV 행 수: {len(daily)}.
        기본 결과는 fixed_pre_event + exclude_missing + effective이며 평균/중앙값 선택은 팀 합의 전입니다.
        정식 비교 대상 수는 입력 사건 CSV의 analysis_role을 따릅니다. 사례연구를 정식 비교로 올리지 않습니다.

        | 사건 | 창 | 끝 | 달력일 | 비공휴일 | 전체 완료 그룹 | 비공휴일 완료 그룹 | 공휴일 제외 | 학습 부족 행 |
        |---|---|---|---:|---:|---:|---:|---:|---:|
        ''')]
    for (event, window, end), g in base.groupby(['event_id', 'window_type', 'window_end']):
        lines.append(f'| {event} | {window} | {end} | {g.window_days.iloc[0]} | {g.eligible_window_days.iloc[0]} | {int(g.complete_window.sum())} | {int(g.complete_eligible_window.sum())} | {g.holiday_excluded_days.iloc[0]} | {g.insufficient_training_days.sum()} |\n')
    lines.append(dedent('''
        ## 해석과 남은 일
        - full은 공휴일을 포함한 달력기간 전체입니다. 공휴일 예측을 제외하므로 공휴일 포함 창은 full=null입니다.
        - eligible은 비공휴일 전체이며 full과 다른 지표입니다. coverage와 eligible_coverage를 함께 확인합니다.
        - HEAT03의 계산 불가는 공휴일 제외와 학습·실제 관측 부족을 분리해 읽습니다.
        - 사전 검증은 남은 비사건 날짜의 부분 점수입니다. 한 방법을 자동 승인하거나 선택하지 않습니다.
        - zero_fill_sensitivity는 빈 행을 0으로 가정한 대안입니다. 원자료 결측 의미가 확인됐다는 뜻이 아닙니다.
        - retrospective는 미래 매출을 쓰는 사후 민감도입니다. 사전 예측·AI 평가와 섞지 않습니다. 계절 변화가 섞일 수 있습니다.
        - 회복일·지원 순위와 인과적 피해액은 계산하지 않습니다. 실제 결과는 허용된 팀 경로로 공유합니다.
        '''))
    (output/'baseline_report.md').write_text(''.join(lines), encoding='utf-8')
    outputs = ['event_shortfall.json', 'daily_predictions.csv', 'daily_industry.csv', 'fixed_validation.csv',
               'method_sensitivity.csv', 'missing_policy_sensitivity.csv', 'baseline_report.md', 'run_metadata.json']
    if retrospective_enabled:
        outputs.append('retrospective_sensitivity.csv')
    (output/'run_metadata.json').write_text(json.dumps({'calendar_provenance': provenance, 'daily_rows': len(daily),
        'group_count': daily[KEY].drop_duplicates().shape[0], 'summary_rows': len(results),
        'retrospective_enabled': retrospective_enabled, 'output_files': outputs,
        'industry_rows': len(industry), 'industry_filter': {'window_type': 'effective', 'baseline_mode': 'fixed_pre_event',
            'missing_policy': 'exclude_missing', 'model_id': 'weekday_mean'},
        'industry_aggregation': 'same_paired_age_groups_only'}, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daily', type=Path, default=Path('data/processed/card/daily.csv'))
    parser.add_argument('--events', type=Path, default=Path('data/processed/weather_events/weather_events.csv'))
    parser.add_argument('--event-windows', type=Path, default=Path('data/processed/weather_events/weather_event_windows.csv'))
    parser.add_argument('--calendar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--retrospective', action='store_true', help='Add explicitly post-event 4-week sensitivity (not forecasting)')
    args = parser.parse_args()
    daily = validate_daily(pd.read_csv(args.daily, dtype={k: str for k in KEY}))
    events, windows = load_events(args.events, args.event_windows)
    panel, provenance = build_panel(daily, events, args.calendar)
    results, handoff, validation = calculate(panel, events, windows, retrospective=args.retrospective)
    write_outputs(args.output, results, handoff, validation, provenance)
    print(f'PASS: {len(results)} summary rows, {len(handoff)} daily rows; exploratory outputs remain local')


if __name__ == '__main__':
    main()
