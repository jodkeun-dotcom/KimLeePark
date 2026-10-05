"""Mark industries whose support-review state depends on the recovery rule (issue #11, review only).

Input: priority_sensitivity.csv from scripts/rank_support.py (#31): ALL rows for
weekday mean/median x threshold 0.90/0.95/1.00 x consecutive days 2/3/4.

For each event x industry the agreed rule (weekday mean, 0.95, 3 days) is the reference.
Within the agreed baseline (weekday mean) the other 8 recovery rules are compared with it:
- settings_differing: how many of the 8 give a different review_queue
- threshold / run axis: whether changing only the threshold (run 3) or only the run (0.95) changes it
- rule_sensitivity: stable (0), low (1 to HIGH_SHARE of 8 minus one), high (at least HIGH_SHARE of 8)
The median baseline is reported separately (same rule) and is not mixed into the label.

Outputs stay local. *_PRIVATE_REVIEW_ONLY.csv has industry names; the summary CSVs have counts only.
These labels are descriptive. They are not support ranks and do not change the agreed criteria.
"""
import argparse
from pathlib import Path

import pandas as pd

REFERENCE = ('weekday_mean', 0.95, 3)
THRESHOLDS = [0.90, 0.95, 1.00]
RUNS = [2, 3, 4]
SETTINGS = 18        # #31의 요일 평균/중앙값 × 임계 3개 × 연속일수 3개
HIGH_SHARE = 0.5     # 기준 외 8개 규칙 중 절반(4개) 이상에서 상태가 달라지면 'high' (팀 확인 필요)
UNIT = ['event_id', 'region', 'industry', 'scope']
REQUIRED = UNIT + ['age', 'model_id', 'recovery_threshold', 'consecutive_days', 'review_queue',
                   'recovery_status', 'priority_tier']


def load(path):
    return load_frame(pd.read_csv(path))


def load_frame(frame):
    """#31 민감도 표 검사: 업종 전체 행, 18개 설정이 모두 있고 단위별 중복 없음."""
    frame = frame.copy()
    missing = set(REQUIRED) - set(frame)
    if missing:
        raise ValueError(f'priority sensitivity missing columns: {sorted(missing)}')
    if not frame.age.eq('ALL').all():
        raise ValueError('expected industry-level (ALL) rows only')
    frame['recovery_threshold'] = frame.recovery_threshold.round(2)
    setting = ['model_id', 'recovery_threshold', 'consecutive_days']
    if frame.duplicated(UNIT + setting).any():
        raise ValueError('duplicate unit within a setting')
    expected = {(m, t, r) for m in ['weekday_mean', 'weekday_median'] for t in THRESHOLDS for r in RUNS}
    present = set(frame[setting].drop_duplicates().itertuples(index=False, name=None))
    if present != expected:
        raise ValueError(f'expected the 18 #31 settings, got {sorted(present)}')
    counts = frame.groupby(UNIT).size()
    if not counts.eq(len(expected)).all():
        raise ValueError('every unit must appear in all 18 settings')
    return frame


def unit_stability(frame):
    """단위(사건×업종)별 회복 기준 민감도. 기준 = 요일 평균·0.95·3일."""
    model, threshold, run = REFERENCE
    rows = []
    for key, g in frame.groupby(UNIT):
        g = g.set_index(['model_id', 'recovery_threshold', 'consecutive_days'])
        ref = g.loc[REFERENCE]
        mean = g.loc[model]
        others = mean.drop(index=(threshold, run))
        differs = others.review_queue.ne(ref.review_queue)
        by_threshold = mean.xs(run, level='consecutive_days').drop(index=threshold)
        by_run = mean.xs(threshold, level='recovery_threshold').drop(index=run)
        median = g.loc[('weekday_median', threshold, run)]
        ranked_all = g.priority_tier.notna()
        n_high = int(round(HIGH_SHARE * len(others)))
        changed = int(differs.sum())
        rows.append({
            **dict(zip(UNIT, key)),
            'reference_review_queue': ref.review_queue, 'reference_recovery_status': ref.recovery_status,
            'reference_priority_tier': ref.priority_tier,
            'mean_rule_settings_differing': changed, 'mean_rule_alternatives': len(others),
            'mean_rule_queues_seen': ', '.join(sorted(set(mean.review_queue))),
            'threshold_axis_changes': bool(by_threshold.review_queue.ne(ref.review_queue).any()),
            'run_axis_changes': bool(by_run.review_queue.ne(ref.review_queue).any()),
            'rule_sensitivity': 'stable' if changed == 0 else 'high' if changed >= n_high else 'low',
            'mean_rule_ranked_settings': int(mean.priority_tier.notna().sum()),
            'all_settings_ranked': int(ranked_all.sum()),
            'all_settings_first_tier': int(g.priority_tier.eq(1).sum()),
            'median_same_rule_queue': median.review_queue,
            'median_same_rule_differs': bool(median.review_queue != ref.review_queue),
        })
    out = pd.DataFrame(rows)
    # 18개 설정 중 일부에서만 순위 후보가 되는 단위
    out['rank_sensitive'] = out.all_settings_ranked.between(1, SETTINGS - 1)
    return out


def summaries(units):
    """공개 가능한 건수 요약 (업종명 없음)."""
    label = (units.groupby(['event_id', 'scope', 'rule_sensitivity']).size()
             .unstack('rule_sensitivity', fill_value=0).reindex(columns=['stable', 'low', 'high'], fill_value=0)
             .reset_index())
    by_queue = (units.groupby(['scope', 'reference_review_queue', 'rule_sensitivity']).size()
                .unstack('rule_sensitivity', fill_value=0).reindex(columns=['stable', 'low', 'high'], fill_value=0)
                .reset_index())
    axes = (units.groupby(['scope']).agg(units=('industry', 'size'),
                                         threshold_axis_changes=('threshold_axis_changes', 'sum'),
                                         run_axis_changes=('run_axis_changes', 'sum'),
                                         median_same_rule_differs=('median_same_rule_differs', 'sum'),
                                         rank_sensitive=('rank_sensitive', 'sum'),
                                         ever_ranked=('all_settings_ranked', lambda s: int(s.gt(0).sum())))
            .reset_index())
    return label, by_queue, axes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--priority-sensitivity', type=Path,
                        default=Path('outputs/seeun_1007/priority/priority_sensitivity.csv'))
    parser.add_argument('--output', type=Path, default=Path('outputs/seeun_1007/stability'))
    args = parser.parse_args()
    if not args.priority_sensitivity.exists():
        raise ValueError(f'input missing: {args.priority_sensitivity}')
    units = unit_stability(load(args.priority_sensitivity))
    label, by_queue, axes = summaries(units)
    args.output.mkdir(parents=True, exist_ok=True)
    units.to_csv(args.output / 'recovery_rule_stability_PRIVATE_REVIEW_ONLY.csv', index=False, encoding='utf-8-sig')
    label.to_csv(args.output / 'rule_sensitivity_by_event.csv', index=False, encoding='utf-8-sig')
    by_queue.to_csv(args.output / 'rule_sensitivity_by_queue.csv', index=False, encoding='utf-8-sig')
    axes.to_csv(args.output / 'rule_sensitivity_axes.csv', index=False, encoding='utf-8-sig')
    print(label.to_string(index=False))
    print(axes.to_string(index=False))


if __name__ == '__main__':
    main()
