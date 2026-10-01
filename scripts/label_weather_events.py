"""Label heatwave / heavy-rain / heavy-snow events on Chuncheon ASOS daily weather.

Input: data/processed/weather.csv from scripts/prepare_weather.py.
Event thresholds are applied directly because official warnings are not
available at the Chuncheon level (see docs/weather.md).
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

PERIOD = ('2025-07-01', '2025-12-31')
SUMMER_MONTHS = range(5, 10)        # 기상청 여름철 체감온도 적용 기간: 5~9월
BASELINE_DAYS, OBSERVATION_DAYS = 7, 14
MAX_GAP_DAYS = 2                    # 같은 유형 사건 사이 비사건일이 2일 이내면 하나의 사건으로 병합
CASE_STUDY_TYPES = {'호우'}          # 사건 수가 적어 정식 통계비교 대신 사례연구로 다루는 유형
NO_DATA_TYPES = {'폭설'}             # 원자료에 값이 없어 판정 불가한 유형
REQUIRED = {
    'temp_max_c': '최고기온', 'humidity_min_pct': '최소 상대습도', 'humidity_avg_pct': '평균 상대습도',
    'precip_mm': '일강수량', 'new_snow_max_cm': '일 최심신적설', 'wind_avg_ms': '평균 풍속',
}
# (flag 열, event_id 접두어, 유형명, 기준값 열)
EVENT_TYPES = [
    ('is_heatwave', 'HEAT', '폭염', 'apparent_temp_max_c'),
    ('is_severe_heatwave', 'SHEAT', '강한 폭염', 'apparent_temp_max_c'),
    ('is_heavy_rain', 'RAIN', '호우', 'precip_mm'),
    ('is_heavy_snow', 'SNOW', '폭설', 'new_snow_max_cm'),
]


def wet_bulb_stull(ta, rh):
    """습구온도(°C). Stull (2011), J. Appl. Meteor. Climatol. 50, 2267-2269."""
    return (ta * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
            + np.arctan(ta + rh) - np.arctan(rh - 1.67633)
            + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)


def apparent_temp_summer(ta, rh):
    """기상청 여름철 체감온도(°C), 2022년 개정식 (기상자료개방포털 '체감온도' 산출식).

    체감온도 = -0.2442 + 0.55399*Tw + 0.45535*Ta - 0.0022*Tw^2 + 0.00278*Tw*Ta + 3.0
    Ta: 기온(°C), Tw: 습구온도(°C, Stull 추정식)
    """
    tw = wet_bulb_stull(ta, rh)
    return -0.2442 + 0.55399 * tw + 0.45535 * ta - 0.0022 * tw ** 2 + 0.00278 * tw * ta + 3.0


def missing_report(df):
    """필수 열 존재 여부와 날짜별 결측 열 목록."""
    columns = pd.DataFrame([
        {'column': c, 'name': n, 'present': c in df, 'missing_days': int(df[c].isna().sum()) if c in df else len(df)}
        for c, n in REQUIRED.items()])
    by_date = df[['date']].copy()
    by_date['missing_columns'] = df.drop(columns='date').isna().apply(
        lambda row: ', '.join(row.index[row]), axis=1)
    return columns, by_date


def add_features(df):
    df = df.copy()
    summer = df.date.dt.month.isin(SUMMER_MONTHS)
    # 일자료에는 시간별 기온·습도가 없으므로 '일 최고 체감온도'를 최고기온 + 최소 상대습도로 근사한다.
    # 최소습도 시각은 대개 최고기온 시각 부근(2025년 7~9월 중앙값 차이 약 20분)이다.
    df['apparent_temp_max_c'] = apparent_temp_summer(df.temp_max_c, df.humidity_min_pct).where(summer).round(1)
    # [민감도 분석용 대안] 평균 습도 기준. 최고기온 시각의 습도를 과대평가해 폭염일이 21일 → 49일로 늘어난다.
    # 민감도 분석 시 주석을 해제하고 아래 판정 열의 기준 열을 바꿔 다시 실행한다.
    # df['apparent_temp_max_avg_rh_c'] = apparent_temp_summer(df.temp_max_c, df.humidity_avg_pct).where(summer).round(1)

    df['is_heatwave'] = df.apparent_temp_max_c.ge(33)
    df['is_severe_heatwave'] = df.apparent_temp_max_c.ge(35)
    # 기상청 일자료의 강수 빈칸은 무강수일이므로 호우 아님(False)으로 본다.
    df['is_heavy_rain'] = df.precip_mm.ge(80)
    # 신적설 값이 없는 날은 판정 불가(<NA>). 미관측을 '폭설 아님'으로 두지 않는다.
    df['is_heavy_snow'] = df.new_snow_max_cm.ge(5).astype('boolean').mask(df.new_snow_max_cm.isna())
    df['is_any_event'] = df[['is_heatwave', 'is_heavy_rain']].any(axis=1) | df.is_heavy_snow.fillna(False)
    return df


EVENT_COLUMNS = [
    'event_id', 'type', 'start_date', 'end_date', 'duration_days', 'event_days', 'peak_value', 'peak_variable',
    'baseline_start', 'baseline_end', 'observation_start', 'observation_end']


def group_events(df):
    """같은 유형 사건일을 묶는다. 유형별로 따로 묶으며 강한 폭염은 폭염의 부분집합이다.

    사건일 사이 비사건일이 MAX_GAP_DAYS 이하이면 같은 사건으로 병합한다
    (예: 7/23, 7/26 → 사이 비사건일 2일 → 한 사건 7/23~7/26).
    """
    start, end = map(pd.Timestamp, PERIOD)
    rows = []
    for flag, prefix, label, value in EVENT_TYPES:
        days = df.loc[df[flag].fillna(False).astype(bool), ['date', value]].sort_values('date')
        if days.empty:
            continue
        # 직전 사건일과의 날짜 차이가 MAX_GAP_DAYS + 1을 넘으면 새 사건 시작
        days['run'] = days.date.diff().dt.days.gt(MAX_GAP_DAYS + 1).cumsum()
        for n, (_, run) in enumerate(days.groupby('run'), 1):
            s, e = run.date.min(), run.date.max()
            rows.append({
                'event_id': f'{prefix}{n:02d}', 'type': label, 'start_date': s, 'end_date': e,
                'duration_days': (e - s).days + 1,   # 병합된 사이 날짜 포함 기간
                'event_days': len(run),              # 실제 기준을 넘은 날 수
                'peak_value': run[value].max(), 'peak_variable': value,
                'baseline_start': s - pd.Timedelta(days=BASELINE_DAYS), 'baseline_end': s - pd.Timedelta(days=1),
                'observation_start': e + pd.Timedelta(days=1), 'observation_end': e + pd.Timedelta(days=OBSERVATION_DAYS),
            })
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    any_event = df.set_index('date').is_any_event

    def event_days(a, b):
        return int(any_event.loc[a:b].sum())
    events['baseline_in_period'] = events.baseline_start.ge(start)
    events['observation_in_period'] = events.observation_end.le(end)
    events['baseline_event_days'] = [event_days(a, b) for a, b in zip(events.baseline_start, events.baseline_end)]
    events['observation_event_days'] = [event_days(a, b) for a, b in zip(events.observation_start, events.observation_end)]
    events = assign_roles(events)

    # 판정 불가 유형은 사건이 없어도 결과 파일에 '데이터 없음' 행으로 남긴다.
    for flag, prefix, label, _ in EVENT_TYPES:
        if label in NO_DATA_TYPES and df[flag].isna().all():
            events.loc[len(events), ['event_id', 'type', 'analysis_role', 'exclude_reason']] = [
                f'{prefix}_NA', label, 'excluded', '데이터 없음: 적설 열이 전 기간 결측이라 판정 불가']
    # 빈 행 추가로 실수형이 된 정수·불리언 열 복원
    ints = ['duration_days', 'event_days', 'baseline_event_days', 'observation_event_days']
    events[ints] = events[ints].astype('Int64')
    events[['baseline_in_period', 'observation_in_period']] = events[['baseline_in_period', 'observation_in_period']].astype('boolean')
    return events


def assign_roles(events):
    """analysis_role: statistical(정식 통계비교) / case_study(사례연구 후보) / excluded(제외)."""
    events = events.copy()
    events['analysis_role'] = 'statistical'
    events['exclude_reason'] = ''
    case = events.type.isin(CASE_STUDY_TYPES)
    events.loc[case, 'analysis_role'] = 'case_study'
    events.loc[case, 'exclude_reason'] = '사례연구 후보: 사건 수가 적어 정식 통계비교 제외'
    # 베이스라인이 카드 자료 시작일 이전에 걸리면 비교 기준이 없으므로 자동 제외(사례연구보다 우선)
    out = ~events.baseline_in_period.astype(bool)
    events.loc[out, 'analysis_role'] = 'excluded'
    events.loc[out, 'exclude_reason'] = [
        f'베이스라인 {b:%Y-%m-%d}~{e:%Y-%m-%d}이 카드 자료 시작일({PERIOD[0]}) 이전에 걸림'
        for b, e in zip(events.baseline_start[out], events.baseline_end[out])]
    return events


def event_windows(events):
    """사건별 날짜 매핑(긴 형식): 카드 일별 자료와 date로 결합해 기간별 비교에 쓴다."""
    parts = []
    for ev in events.dropna(subset=['start_date']).itertuples():   # 날짜 없는 '데이터 없음' 행 제외
        for window, a, b in [('baseline', ev.baseline_start, ev.baseline_end),
                             ('event', ev.start_date, ev.end_date),
                             ('observation', ev.observation_start, ev.observation_end)]:
            dates = pd.date_range(a, b)
            parts.append(pd.DataFrame({'event_id': ev.event_id, 'type': ev.type, 'analysis_role': ev.analysis_role,
                                       'window': window, 'date': dates,
                                       'day_offset': (dates - (ev.start_date if window != 'observation' else ev.end_date)).days}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=['event_id', 'type', 'analysis_role', 'window', 'date', 'day_offset'])


def plot_timeline(df, events, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import font_manager
    # OS별 한글 폰트 중 설치된 것 하나를 사용 (macOS / Windows / Linux)
    installed = {f.name for f in font_manager.fontManager.ttflist}
    korean = [f for f in ('AppleGothic', 'Malgun Gothic', 'NanumGothic') if f in installed]
    plt.rcParams.update({'font.family': korean[:1] or ['DejaVu Sans'], 'axes.unicode_minus': False})
    ink, muted, grid = '#1f1f1e', '#6b6a64', '#e4e3dc'
    colors = {'폭염': '#2a78d6', '강한 폭염': '#eb6834', '호우': '#1baf7a', '폭설': '#eda100'}  # 범주형 고정 순서
    fig, axes = plt.subplots(3, 1, figsize=(12, 7.5), sharex=True, gridspec_kw={'height_ratios': [2, 2, 1.6]})
    ax_t, ax_p, ax_e = axes
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines[['left', 'bottom']].set_color(grid)
        ax.tick_params(colors=muted, labelsize=9)
        ax.grid(axis='y', color=grid, linewidth=0.8)
        ax.set_axisbelow(True)

    ax_t.plot(df.date, df.apparent_temp_max_c, color=ink, linewidth=1.5)
    for th, label in [(33, '폭염 33℃'), (35, '강한 폭염 35℃')]:
        ax_t.axhline(th, color=muted, linewidth=1, linestyle='--')
        ax_t.text(df.date.max(), th + 0.15, label, ha='right', va='bottom', fontsize=8, color=muted)
    ax_t.set_ylabel('일 최고 체감온도(℃)\n(5~9월만 산출)', fontsize=9, color=muted)

    ax_p.bar(df.date, df.precip_mm.fillna(0), width=0.8, color=colors['호우'])
    ax_p.axhline(80, color=muted, linewidth=1, linestyle='--')
    ax_p.text(df.date.max(), 81, '호우 80mm', ha='right', va='bottom', fontsize=8, color=muted)
    ax_p.set_ylabel('일강수량(mm)', fontsize=9, color=muted)

    lanes = [label for _, _, label, _ in EVENT_TYPES]
    dated = events.dropna(subset=['start_date'])
    for i, label in enumerate(lanes):
        for ev in dated[dated.type == label].itertuples():
            # 정식 비교 대상은 진한 막대, 제외·사례연구는 옅은 빗금 막대
            main = ev.analysis_role == 'statistical'
            ax_e.barh(i, ev.duration_days, left=ev.start_date - pd.Timedelta(hours=12), height=0.6,
                      color=colors[label], alpha=1 if main else 0.35, hatch=None if main else '///',
                      edgecolor='white', linewidth=2)
            # 사건 시작일에 맞춰 막대 위에 왼쪽 정렬 (가까운 사건끼리 겹치지 않도록)
            ax_e.text(ev.start_date - pd.Timedelta(hours=12), i - 0.36, ev.event_id,
                      ha='left', va='bottom', fontsize=6.5, color=muted)
    ax_e.text(df.date.min(), lanes.index('폭설'), '  적설 자료 없음(판정 불가·분석 제외)', va='center', fontsize=8, color=muted)
    ax_e.text(df.date.max(), len(lanes) - 0.55, '진한 막대: 정식 비교 대상 / 옅은 빗금: 제외·사례연구',
              ha='right', va='bottom', fontsize=8, color=muted)
    ax_e.set_yticks(range(len(lanes)), [f'{l} ({(dated.type == l).sum()}건)' for l in lanes], fontsize=9, color=ink)
    ax_e.set_ylim(len(lanes) - 0.4, -0.6)
    ax_e.grid(axis='y', visible=False)
    ax_e.grid(axis='x', color=grid, linewidth=0.8)
    ax_e.xaxis.set_major_locator(mdates.MonthLocator())
    ax_e.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    fig.suptitle('춘천 기상 이벤트 타임라인 (ASOS 101, 2025-07~12)', x=0.01, ha='left', fontsize=12, color=ink)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run(source, output, figure):
    df = pd.read_csv(source, parse_dates=['date'])
    columns, by_date = missing_report(df)
    df = add_features(df)
    events = group_events(df)
    windows = event_windows(events)
    dated = events.dropna(subset=['start_date'])
    counts = pd.DataFrame({'type': [label for _, _, label, _ in EVENT_TYPES]})
    counts['events'] = counts.type.map(dated.type.value_counts()).fillna(0).astype(int)
    counts['event_days'] = counts.type.map(dated.groupby('type').event_days.sum()).fillna(0).astype(int)
    for role in ['statistical', 'case_study', 'excluded']:
        counts[role] = counts.type.map(dated[dated.analysis_role == role].type.value_counts()).fillna(0).astype(int)
    counts['judgeable'] = [not df[flag].isna().all() for flag, *_ in EVENT_TYPES]
    counts['status'] = np.select(
        [~counts.judgeable, counts.type.isin(CASE_STUDY_TYPES)],
        ['데이터 없음 - 분석 제외', '사례연구 후보 - 정식 통계비교 제외'], '정식 통계비교')

    output.mkdir(parents=True, exist_ok=True)
    df.to_csv(output / 'weather_daily_events.csv', index=False, encoding='utf-8-sig')
    events.to_csv(output / 'weather_events.csv', index=False, encoding='utf-8-sig')
    windows.to_csv(output / 'weather_event_windows.csv', index=False, encoding='utf-8-sig')
    counts.to_csv(output / 'weather_event_counts.csv', index=False, encoding='utf-8-sig')
    by_date.to_csv(output / 'weather_missing_by_date.csv', index=False, encoding='utf-8-sig')
    plot_timeline(df, events, figure)

    print('필수 열 점검\n', columns.to_string(index=False))
    print('\n이벤트 건수\n', counts.to_string(index=False))
    print('\n사건 목록\n', events.drop(columns=['peak_variable']).to_string(index=False))
    return df, events, windows, counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('data/processed/weather.csv'))
    parser.add_argument('--output', type=Path, default=Path('data/processed/weather_events'))
    parser.add_argument('--figure', type=Path, default=Path('outputs/weather_event_timeline.png'))
    args = parser.parse_args()
    run(args.input, args.output, args.figure)
