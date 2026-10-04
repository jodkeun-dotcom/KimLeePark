"""Recovery curves and recovery days of card sales after heatwave events (provisional, issue #8).

Inputs
- card daily table (date, region, industry, age, amount) from prepare_card.py (PR #25)
- weather_events.csv / weather_event_windows.csv from scripts/label_weather_events.py

Expected sales follow Sunha's provisional common baseline (PR, docs/sales_baseline_review.md):
same-weekday mean of earlier non-event days, fixed at the event start. Replace `expected_sales`
when the team baseline is finalised. Results are baseline gaps, not causal heat damage.
Numeric outputs stay local (data/processed/, outputs/) and are not committed.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

# ── 잠정 기준값: 팀 합의 전 (#8 → 민감도 검증 #11) ──────────────────────
RECOVERY_THRESHOLD = 0.95   # 실제/예상 매출 비율이 이 값 이상이면 '평상시 수준'으로 본다
CONSECUTIVE_DAYS = 3        # 위 기준을 연속으로 충족해야 하는 관찰일 수 (첫날이 회복일)
MIN_TRAIN_DAYS = 7          # 기준선 학습 최소 관측일 (선하 기준모델과 동일)
MIN_WEEKDAY_OBS = 2         # 같은 요일 최소 관측 횟수 (선하 기준모델과 동일)
HOLIDAYS = ['2025-08-15']   # 잠정 공휴일 (PR #26 목록). calendar.csv(#27) 수신 후 교체
TARGET_TYPES = {'폭염'}      # 회복을 계산할 사건 유형. 강한 폭염은 부모 폭염의 속성(PR #24)
ALL_AGES = 'ALL'            # 업종 전체 집계의 age 값 (handoff_priority_1004.md 형식)
# 선하 기준모델의 주 분석 후보 18개 업종 (외식·식품·방문형 여가). 분류는 효과 판정이 아니다.
PRIMARY_INDUSTRIES = {
    '한식', '중식', '일식', '양식', '기타요식', '제과점', '커피전문점', '패스트푸드', '편의점',
    '할인점/슈퍼마켓/양판점', '농수산물', '정육점', '기타식품', '주류판매', '영화/공연', '게임방/오락실',
    '노래방', '종합레저타운/놀이동산'}
KEYS = ['region', 'industry', 'age']
# 팀 결합 형식 (scripts/prepare_priority.py의 KEY, RECOVERY와 같아야 함 — tests/test_recovery.py에서 확인)
HANDOFF_KEY = ['event_id', 'region', 'industry', 'age', 'window_start', 'window_end']
HANDOFF_RECOVERY = ['recovery_days', 'recovery_status', 'recovery_uncertainty_note']
HANDOFF_WINDOW = 'effective'   # 우선순위 결합에 넘기는 주 결과. nominal은 민감도 비교용으로 metrics에만 둔다


def load_daily(path):
    d = pd.read_csv(path, parse_dates=['date'], dtype={'region': str, 'industry': str, 'age': str})
    if missing := {'date', 'amount', *KEYS} - set(d):
        raise ValueError(f'Missing columns: {sorted(missing)}')
    if d.duplicated(['date'] + KEYS).any():
        raise ValueError('Duplicate date/region/industry/age rows')
    if d.amount.lt(0).any() or not np.isfinite(d.amount).all():
        raise ValueError('Amounts must be finite and non-negative')
    # 업종 전체(age=ALL): 그날 관측된 연령 행의 합. 행이 없는 날은 0이 아니라 미관측으로 둔다.
    total = d.groupby(['date', 'region', 'industry'], as_index=False).amount.sum().assign(age=ALL_AGES)
    return pd.concat([d[['date', *KEYS, 'amount']], total], ignore_index=True)


def event_spans(events):
    dated = events.dropna(subset=['start_date'])
    return list(zip(pd.to_datetime(dated.start_date), pd.to_datetime(dated.end_date)))


def expected_sales(daily, start, spans, dates):
    """사건 시작 전 비사건일의 같은 요일 평균으로 dates의 예상 매출을 만든다 (시작일에 고정).

    반환: KEYS + date + expected. 학습 조건(전체 MIN_TRAIN_DAYS일, 요일별 MIN_WEEKDAY_OBS회) 미달 그룹·요일은 NaN.
    """
    excluded = np.zeros(len(daily), dtype=bool)
    for s, e in spans:
        excluded |= daily.date.between(s, e).to_numpy()
    excluded |= daily.date.isin(pd.to_datetime(HOLIDAYS)).to_numpy()
    train = daily[(daily.date < start) & ~excluded].assign(weekday=lambda x: x.date.dt.dayofweek)
    stats = train.groupby(KEYS + ['weekday']).amount.agg(['mean', 'count']).reset_index()
    n = train.groupby(KEYS).amount.count().rename('train_days').reset_index()
    grid = daily[KEYS].drop_duplicates().merge(pd.DataFrame({'date': dates}), how='cross')
    grid['weekday'] = grid.date.dt.dayofweek
    grid = grid.merge(stats, on=KEYS + ['weekday'], how='left').merge(n, on=KEYS, how='left')
    ok = grid['count'].ge(MIN_WEEKDAY_OBS) & grid.train_days.ge(MIN_TRAIN_DAYS)
    grid['expected'] = grid['mean'].where(ok)
    grid['train_days'] = grid.train_days.fillna(0).astype(int)
    holiday = grid.date.isin(pd.to_datetime(HOLIDAYS))
    grid.loc[holiday, 'expected'] = np.nan   # 공휴일은 요일 평균으로 예측하지 않는다
    return grid[KEYS + ['date', 'expected', 'train_days']]


def recovery_day(obs, threshold=None, run=None):
    """관찰일(날짜순, 유효 구간만)에서 회복 첫날을 찾는다.

    ratio ≥ threshold가 run일 연속이면 그 첫날이 회복일. 미관측·예측 불가 날짜는 연속을 끊는다.
    반환 (status, day_offset, date). 기간 안에 못 찾으면 censored (회복일을 임의로 채우지 않음).
    """
    threshold = RECOVERY_THRESHOLD if threshold is None else threshold
    run = CONSECUTIVE_DAYS if run is None else run
    streak = 0
    for i, r in enumerate(obs.itertuples()):
        streak = streak + 1 if pd.notna(r.ratio) and r.ratio >= threshold else 0
        if streak == run:
            first = obs.iloc[i - run + 1]
            return 'recovered', int(first.day_offset), first.date
    if obs.ratio.notna().sum() < run:
        return 'insufficient_data', None, pd.NaT
    return 'censored', None, pd.NaT


def compute(daily, events, windows):
    """사건 × 업종 × 연령(+ALL)별 회복 곡선(긴 형식)과 회복 지표 표."""
    events = events.copy()
    for c in ['start_date', 'end_date', 'observation_start', 'observation_end', 'observation_end_effective']:
        events[c] = pd.to_datetime(events[c])
    windows = windows.assign(date=pd.to_datetime(windows.date))
    spans = event_spans(events)
    targets = events[events.type.isin(TARGET_TYPES) & events.baseline_in_period.eq(True)]
    curves, metrics = [], []
    for ev in targets.itertuples():
        w = windows[(windows.event_id == ev.event_id) & windows.window.isin(['event', 'observation'])]
        exp = expected_sales(daily, ev.start_date, spans, w.date.unique())
        c = (exp.merge(w[['date', 'window', 'day_offset', 'is_effective', 'ineffective_reason']], on='date')
             .merge(daily, on=['date'] + KEYS, how='left'))
        c['ratio'] = c.amount / c.expected.where(c.expected > 0)
        c.insert(0, 'event_id', ev.event_id)
        curves.append(c)
        for key, g in c.groupby(KEYS):
            g = g.sort_values('date')
            during = g[g.window == 'event']
            paired = during.dropna(subset=['amount', 'expected'])
            event_ratio = paired.amount.sum() / paired.expected.sum() if paired.expected.sum() > 0 else np.nan
            notes = []
            for window_type, end in [('effective', ev.observation_end_effective), ('nominal', ev.observation_end)]:
                obs = g[(g.window == 'observation') & (g.date <= end)]
                if pd.isna(event_ratio) or len(paired) < len(during):
                    status, day, date = 'insufficient_data', None, pd.NaT
                elif event_ratio >= RECOVERY_THRESHOLD:
                    status, day, date = 'no_decline', None, pd.NaT    # 사건 기간에 기준 이하로 떨어지지 않음
                else:
                    status, day, date = recovery_day(obs)
                notes = uncertainty_notes(ev, g, during, paired, obs, window_type)
                metrics.append({
                    'event_id': ev.event_id, **dict(zip(KEYS, key)),
                    'window_type': window_type, 'window_start': ev.start_date.date(), 'window_end': pd.Timestamp(end).date(),
                    'event_end': ev.end_date.date(), 'analysis_role': ev.analysis_role,
                    'scope': 'primary' if key[1] in PRIMARY_INDUSTRIES else 'auxiliary',
                    'train_days': int(g.train_days.iloc[0]), 'event_days_paired': len(paired), 'event_days': len(during),
                    'event_ratio': event_ratio, 'observation_days': len(obs),
                    'observation_days_paired': int(obs.ratio.notna().sum()),
                    'recovery_status': status, 'recovery_days': day, 'recovery_date': date,
                    'recovery_threshold': RECOVERY_THRESHOLD, 'consecutive_days': CONSECUTIVE_DAYS,
                    'recovery_uncertainty_note': '; '.join(notes),
                })
    curves = pd.concat(curves, ignore_index=True) if curves else pd.DataFrame()
    metrics = pd.DataFrame(metrics)
    if not metrics.empty:
        metrics['recovery_days'] = metrics.recovery_days.astype('Int64')
    return curves, metrics


def uncertainty_notes(ev, g, during, paired, obs, window_type):
    notes = []
    if ev.analysis_role != 'statistical':
        notes.append(f'사건 분류 {ev.analysis_role}: {ev.exclude_reason}')
    if window_type == 'nominal' and (obs.ineffective_reason.fillna('') != '').any():
        notes.append('명목 관찰기간: 다른 사건이 섞인 날짜 포함 (민감도 비교용)')
    if len(paired) < len(during):
        notes.append(f'사건 기간 {len(during)}일 중 실제·예상 모두 있는 날 {len(paired)}일')
    if obs.amount.isna().any():
        notes.append(f'관찰기간 미관측 {int(obs.amount.isna().sum())}일 (0으로 채우지 않음)')
    if obs.expected.isna().any() & obs.amount.notna().any():
        notes.append('일부 관찰일 예측 불가 (학습 요일 부족 또는 잠정 공휴일)')
    if int(g.train_days.iloc[0]) < 14:
        notes.append(f'기준선 학습일 {int(g.train_days.iloc[0])}일')
    return notes


def plot_curves(curves, metrics, path, industries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    korean = [f for f in ('AppleGothic', 'Malgun Gothic', 'NanumGothic') if f in installed]
    plt.rcParams.update({'font.family': korean[:1] or ['DejaVu Sans'], 'axes.unicode_minus': False})
    ink, muted, grid, line = '#1f1f1e', '#6b6a64', '#e4e3dc', '#2a78d6'
    events = list(dict.fromkeys(curves.event_id))
    data = curves[(curves.age == ALL_AGES) & curves.industry.isin(industries)]
    cols = 6
    for event in events:
        rows = int(np.ceil(len(industries) / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.4, rows * 1.9 + 0.9), sharex=True, sharey=True)
        for ax, industry in zip(axes.flat, industries):
            g = data[(data.event_id == event) & (data.industry == industry)].sort_values('date')
            # 사건 기간을 0 이하(마지막 사건일 = 0)에, 관찰기간을 +1부터 놓는다
            x = np.where(g.window == 'event', g.day_offset - ((g.window == 'event').sum() - 1), g.day_offset)
            ax.axvspan(x.min() - 0.5, 0.5, color=grid, alpha=0.6, linewidth=0)          # 사건 기간
            eff = g.is_effective.to_numpy()
            ax.plot(x, g.ratio.where(eff), color=line, linewidth=2)
            ax.plot(x, g.ratio.where(~eff | np.r_[~eff[1:], False]), color=muted, linewidth=1, linestyle=(0, (1, 1.5)))
            for y in (1.0, RECOVERY_THRESHOLD):
                ax.axhline(y, color=muted, linewidth=0.8, linestyle='--' if y < 1 else '-')
            m = metrics[(metrics.event_id == event) & (metrics.industry == industry) & (metrics.age == ALL_AGES)
                        & (metrics.window_type == 'effective')]
            if len(m) and m.recovery_status.iloc[0] == 'recovered':
                ax.axvline(m.recovery_days.iloc[0], color=ink, linewidth=1)
            status = m.recovery_status.iloc[0] if len(m) else '-'
            label = {'recovered': f'+{m.recovery_days.iloc[0]}일 회복' if len(m) else '', 'censored': '관찰 내 미회복',
                     'no_decline': '감소 없음', 'insufficient_data': '자료 부족'}.get(status, status)
            ax.set_title(f'{industry}\n{label}', fontsize=8, color=ink, loc='left')
            ax.spines[['top', 'right']].set_visible(False)
            ax.spines[['left', 'bottom']].set_color(grid)
            ax.tick_params(colors=muted, labelsize=7)
            ax.set_ylim(0, 2)
        for ax in list(axes.flat)[len(industries):]:
            ax.set_visible(False)
        fig.suptitle(f'{event} 업종별 실제/예상 매출 비율 (업종 전체, 잠정 기준선)\n'
                     f'회색 띠 = 사건 기간, x = 관찰 일수(+1 = 사건 종료 다음 날), 파란 실선 = 유효 관찰, 회색 점선 = 다른 사건 이후 절단, '
                     f'점선 = 회복 기준 {RECOVERY_THRESHOLD:.0%}, 세로선 = 회복일 ({CONSECUTIVE_DAYS}일 연속)',
                     x=0.01, ha='left', fontsize=9, color=ink)
        fig.tight_layout()
        path.mkdir(parents=True, exist_ok=True)
        fig.savefig(path / f'recovery_curves_{event}.png', dpi=130)
        plt.close(fig)


def handoff(metrics):
    """지원 우선순위 결합(prepare_priority.join_metrics)용 전달본: 주 결과 창만, 공통 키 + 회복 열.

    recovery_metrics.csv는 effective·nominal을 함께 담아, 두 창의 끝이 같은 사건(예: HEAT05)은 공통 키가 겹친다.
    창 구분 없이 중복을 지우면 주 결과와 민감도 결과가 섞이므로 window_type을 명시적으로 고른다.
    """
    out = metrics.loc[metrics.window_type == HANDOFF_WINDOW, HANDOFF_KEY + HANDOFF_RECOVERY].copy()
    for c in ['window_start', 'window_end']:
        out[c] = pd.to_datetime(out[c]).dt.strftime('%Y-%m-%d')
    if out[HANDOFF_KEY].isna().any().any() or out.duplicated(HANDOFF_KEY).any():
        raise ValueError('recovery handoff: missing/duplicate keys')
    return out.reset_index(drop=True)


def run(daily_path, events_path, windows_path, output, figures):
    daily = load_daily(daily_path)
    events = pd.read_csv(events_path)
    windows = pd.read_csv(windows_path)
    curves, metrics = compute(daily, events, windows)
    output.mkdir(parents=True, exist_ok=True)
    curves.to_csv(output / 'recovery_curves.csv', index=False, encoding='utf-8-sig')
    metrics.to_csv(output / 'recovery_metrics.csv', index=False, encoding='utf-8-sig')
    handoff(metrics).to_csv(output / 'recovery_handoff.csv', index=False, encoding='utf-8-sig')
    plot_curves(curves, metrics, figures, sorted(PRIMARY_INDUSTRIES & set(daily.industry)))
    summary = (metrics[metrics.age == ALL_AGES].groupby(['event_id', 'window_type', 'scope']).recovery_status
               .value_counts().unstack(fill_value=0))
    print(summary.to_string())
    return curves, metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--daily', type=Path, default=Path('data/processed/card/daily.csv'))
    parser.add_argument('--events', type=Path, default=Path('data/processed/weather_events/weather_events.csv'))
    parser.add_argument('--windows', type=Path, default=Path('data/processed/weather_events/weather_event_windows.csv'))
    parser.add_argument('--output', type=Path, default=Path('data/processed/recovery'))
    parser.add_argument('--figures', type=Path, default=Path('outputs/recovery'))
    args = parser.parse_args()
    run(args.daily, args.events, args.windows, args.output, args.figures)
