"""Final recovery curves under the agreed criteria (issue #11 deliverable, figures stay local).

Input: compute_recovery_from_baseline.py outputs (common baseline: fixed pre-event weekday mean,
exclude missing, effective windows) run with threshold 0.95 and 3 consecutive days.
One figure per heat event with the 18 primary industries (industry total, age=ALL):
- solid line: actual/expected ratio on dates where every input age group is paired (used for judgement)
- grey dots: partial-age ratio on other dates (exploratory only, never used for judgement)
- dashed line: recovery threshold; vertical lines: recovery first day and confirmation day
Figures contain industry-level card results, so they are shared only through the team channel.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PRIMARY = ['한식', '중식', '일식', '양식', '기타요식', '제과점', '커피전문점', '패스트푸드', '편의점',
           '할인점/슈퍼마켓/양판점', '농수산물', '정육점', '기타식품', '주류판매', '영화/공연', '게임방/오락실',
           '노래방', '종합레저타운/놀이동산']
STATUS_KO = {'no_decline': '사건 감소 기준 미충족', 'recovered': '회복', 'censored': '관찰기간 내 회복 미확인',
             'insufficient_data': '자료 부족'}
UNIT = ['event_id', 'region', 'industry', 'age']
CURVE_COLUMNS = UNIT + ['date', 'window', 'day_offset', 'ratio', 'ratio_paired_exploratory', 'is_holiday',
                        'window_start', 'window_end', 'recovery_threshold', 'consecutive_days']
METRIC_COLUMNS = UNIT + ['window_start', 'window_end', 'event_end', 'observation_days', 'observation_days_paired',
                         'event_ratio', 'recovery_status', 'recovery_days', 'recovery_threshold', 'consecutive_days']


def single_rule(frame, name):
    rules = frame[['recovery_threshold', 'consecutive_days']].drop_duplicates()
    if len(rules) != 1:
        raise ValueError(f'{name} must come from a single recovery rule')
    return round(float(rules.recovery_threshold.iloc[0]), 6), int(rules.consecutive_days.iloc[0])


def check_same_windows(c, m):
    """곡선과 지표가 같은 단위·관찰창에서 나왔는지 확인한다. 하나라도 다르면 그림을 만들지 않는다."""
    units = c[UNIT].drop_duplicates().merge(m[UNIT], on=UNIT, how='outer', indicator=True)
    if not units._merge.eq('both').all():
        raise ValueError('curves and metrics cover different event/region/industry/age units')
    derived = c.groupby(UNIT).agg(curve_window_start=('window_start', 'first'), curve_window_end=('window_end', 'first'),
                                  curve_starts=('window_start', 'nunique'), curve_ends=('window_end', 'nunique'),
                                  curve_event_end=('date', lambda d: d[c.loc[d.index, 'window'].eq('event')].max()),
                                  curve_observation_days=('window', lambda w: int(w.eq('observation').sum())))
    if derived.curve_starts.gt(1).any() or derived.curve_ends.gt(1).any():
        raise ValueError('curves have more than one window per unit')
    joined = m.set_index(UNIT).join(derived, how='inner')
    for left, right in [('window_start', 'curve_window_start'), ('window_end', 'curve_window_end')]:
        if not pd.to_datetime(joined[left]).eq(pd.to_datetime(joined[right])).all():
            raise ValueError(f'curves and metrics disagree on {left}')
    if not pd.to_datetime(joined.event_end).eq(joined.curve_event_end).all():
        raise ValueError('curves and metrics disagree on event_end')
    if not joined.observation_days.astype(int).eq(joined.curve_observation_days).all():
        raise ValueError('curves and metrics disagree on observation_days')


def panel_data(curves, metrics, industries=PRIMARY):
    """그림용 자료: 업종 전체(ALL) 곡선과 사건별 지표를 합친다."""
    for frame, columns, name in [(curves, CURVE_COLUMNS, 'curves'), (metrics, METRIC_COLUMNS, 'metrics')]:
        missing = set(columns) - set(frame)
        if missing:
            raise ValueError(f'{name} missing columns: {sorted(missing)}')
    c = curves[curves.age.eq('ALL') & curves.industry.isin(industries)].copy()
    m = metrics[metrics.age.eq('ALL') & metrics.industry.isin(industries)].copy()
    if c.empty or m.empty:
        raise ValueError('no industry-total rows for the selected industries')
    threshold, run = single_rule(c, 'curves')
    if single_rule(m, 'metrics') != (threshold, run):
        raise ValueError('curves and metrics use different recovery rules')
    if m.duplicated(UNIT).any():
        raise ValueError('duplicate event/region/industry/age metrics')
    c['date'] = pd.to_datetime(c.date)
    check_same_windows(c, m)
    c['is_holiday'] = c.is_holiday.astype(str).str.lower().eq('true')
    # 판정에 쓰지 않는 부분 연령 날짜의 비율은 탐색용으로만 따로 둔다
    c['ratio_partial_only'] = c.ratio_paired_exploratory.where(c.ratio.isna())
    # 창·기준이 같음을 확인했으므로 지표 열은 곡선과 겹치지 않는 것만 붙인다
    extra = [col for col in METRIC_COLUMNS if col not in c or col in UNIT]
    c = c.merge(m[extra], on=UNIT, how='left', validate='many_to_one')
    rd = pd.to_numeric(c.recovery_days, errors='coerce')
    c['confirmation_day'] = rd + run - 1
    return c.sort_values(['event_id', 'industry', 'date']), threshold, run


def event_caption(g, threshold, run):
    first = g.iloc[0]
    days = int(first.observation_days)
    text = (f'{first.event_id}: 사건 종료 {first.event_end}, 실제 관찰 {days}일(~{first.window_end}). '
            f'회복 = 실제/예상 ≥ {threshold:.0%}가 {run}일 연속인 첫날')
    if days <= run:
        text += f'. 관찰 {days}일 창: 첫 관찰일부터 {run}일 모두 충족해야 회복으로 인정되는 제한적 창(다음 사건으로 절단)'
    return text


def plot_event(g, threshold, run, path, industries=PRIMARY):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    korean = [f for f in ('AppleGothic', 'Malgun Gothic', 'NanumGothic') if f in installed]
    ink, muted, grid, line, mark = '#1f1f1e', '#6b6a64', '#e4e3dc', '#2a78d6', '#eb6834'
    present = [i for i in industries if i in set(g.industry)]
    cols = 6
    rows = int(np.ceil(len(present) / cols))
    with plt.rc_context({'font.family': korean[:1] or ['DejaVu Sans'], 'axes.unicode_minus': False}):
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.5, rows * 2.1 + 1.1), sharex=True, sharey=True)
        for ax, industry in zip(axes.flat, present):
            h = g[g.industry.eq(industry)]
            event_x = h.loc[h.window.eq('event'), 'day_offset']
            ax.axvspan(event_x.min() - 0.5, 0.5, color=grid, alpha=0.7, linewidth=0)
            for x in h.loc[h.is_holiday, 'day_offset']:
                ax.axvline(x, color=muted, linewidth=0.6, linestyle=':')
            ax.plot(h.day_offset, h.ratio, color=line, linewidth=2, marker='o', markersize=2.5)
            ax.scatter(h.day_offset, h.ratio_partial_only, color=muted, s=6, alpha=0.6)
            ax.axhline(threshold, color=muted, linewidth=0.8, linestyle='--')
            ax.axhline(1.0, color=muted, linewidth=0.6)
            status = h.recovery_status.iloc[0]
            label = STATUS_KO.get(status, status)
            if status == 'recovered':
                first, confirm = h.recovery_days.iloc[0], h.confirmation_day.iloc[0]
                ax.axvline(first, color=mark, linewidth=1.2)
                ax.axvline(confirm, color=mark, linewidth=0.8, linestyle='--')
                label = f'회복 첫날 +{int(first)}일 (확인 +{int(confirm)}일)'
            ax.set_title(f'{industry}\n{label}', fontsize=8, color=ink, loc='left')
            ax.spines[['top', 'right']].set_visible(False)
            ax.spines[['left', 'bottom']].set_color(grid)
            ax.tick_params(colors=muted, labelsize=7)
            ax.set_ylim(0, 2)
        for ax in list(axes.flat)[len(present):]:
            ax.set_visible(False)
        fig.suptitle(event_caption(g, threshold, run) + '\n'
                     '회색 띠 = 사건 기간(마지막 사건일 = 0), x = 사건 종료 후 일수, 파란 실선 = 모든 연령이 갖춰진 날의 실제/예상 비율(판정에 사용), '
                     '회색 점 = 일부 연령만 있는 날(참고용), 점선 = 회복 기준, 주황 실선/점선 = 회복 첫날/연속 확인 완료일, 세로 점선 = 공휴일',
                     x=0.01, ha='left', fontsize=8.5, color=ink)
        fig.tight_layout()
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=140)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--curves', type=Path,
                        default=Path('outputs/seeun_1007/common_recovery/recovery_curves_common_baseline.csv'))
    parser.add_argument('--metrics', type=Path,
                        default=Path('outputs/seeun_1007/common_recovery/recovery_metrics_common_baseline.csv'))
    parser.add_argument('--output', type=Path, default=Path('outputs/seeun_1007/curves'))
    args = parser.parse_args()
    for path in [args.curves, args.metrics]:
        if not path.exists():
            raise ValueError(f'input missing: {path}')
    data, threshold, run = panel_data(pd.read_csv(args.curves), pd.read_csv(args.metrics))
    args.output.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output / 'final_recovery_curves_PRIVATE_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    for event, g in data.groupby('event_id'):
        plot_event(g, threshold, run, args.output / f'final_recovery_curves_{event}.png')
    print(f'{data.event_id.nunique()} events, {data.industry.nunique()} industries; figures in {args.output}')


if __name__ == '__main__':
    main()
