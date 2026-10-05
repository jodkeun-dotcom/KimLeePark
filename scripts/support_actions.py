"""Unordered support-review categories alongside the provisional Pareto result.

Every industry stays visible, including censored or incomplete observations.
These are proposed follow-up actions, not benefit eligibility or causal losses.
"""
import numpy as np
import pandas as pd

from scripts.prepare_priority import KEY
from scripts.prepare_sales_baseline import bool_column
from scripts.compare_decline_states import comparison_fields


ACTION_RULES = {
    'sales_data_incomplete': {
        'label': '매출 자료·지표 부족',
        'condition': 'eligible window incomplete or an eligible monetary measure unavailable',
        'action': '누락 날짜·연령과 지표 산출 불가 원인을 확인한 뒤 매출 부족 재평가',
        'start': '자료 부족 확인 시 추가 자료 요청',
        'check': '자료 충족 날짜·연령 수, 예상 합이 0인지 여부, 재계산된 순부족률과 회복 상태',
        'caution': '회복이 확인돼도 누적 부족은 미확정; 공란은 피해 없음이나 지원 불필요가 아님',
    },
    'shortfall_recovery_insufficient': {
        'label': '순부족 있음·회복 판단 자료 부족',
        'condition': 'complete eligible positive net shortfall; recovery status insufficient_data',
        'action': '확인된 추정 순부족을 보존하고 회복 관찰 자료 보완',
        'start': '자료 부족 확인 시 추가 관찰 계획 수립',
        'check': '추가 관찰일·결측 여부, 회복 확인 여부, 순부족률',
        'caution': '회복 미확인을 장기 미회복으로 확정하지 않음; 다른 집단보다 낮은 등급이 아님',
    },
    'shortfall_recovery_unconfirmed': {
        'label': '순부족 있음·회복 미확인',
        'condition': 'complete eligible positive net shortfall; recovery status censored',
        'action': '현장 상황·관찰기간 확인과 단기 지원 필요성 검토',
        'start': '관찰창 종료까지 자료를 확보하고 관찰 절단·현장 상황을 확인한 뒤 검토',
        'check': '추가 관찰의 회복 상태, 순부족률, 일별 양의 부족분 합계',
        'caution': '실제 회복시점 미확정; 사건별 관찰기간이 달라 자동 최우선이나 최장 지연으로 해석하지 않음',
    },
    'shortfall_recovered': {
        'label': '순부족 있음·회복 확인',
        'condition': 'complete eligible positive net shortfall; recovery status recovered',
        'action': '매출 흐름 회복 후 남은 누적 부담에 대한 지원 필요성 검토',
        'start': '연속 회복과 관찰창 종료까지의 잔여 순부족을 확인한 뒤 검토',
        'check': '잔여 순부족률·금액, 일별 양의 부족분 합계, 이후 매출 흐름',
        'caution': '일별 매출 흐름 회복은 누적 부족 해소와 다름; Pareto 등급은 비교 가능한 대상 안의 잠정 등급',
    },
    'shortfall_below_decline_threshold': {
        'label': '순부족 있음·사건 감소 기준 미충족',
        'condition': 'complete eligible positive net shortfall; recovery status no_decline',
        'action': '관찰기간의 부족 발생 시점과 계절·업종 등 다른 요인 점검',
        'start': '사건 기간과 관찰기간의 매출 차이를 구분한 뒤 검토',
        'check': '사건 감소율, 기간별 순부족, 기준모델 민감도',
        'caution': 'no_decline은 사건 평균 비율이 기준 이상이라는 뜻; 피해 없음이나 회복 확인을 뜻하지 않음',
    },
    'no_positive_net_shortfall': {
        'label': '양의 순부족 없음·상태 점검',
        'condition': 'complete eligible net shortfall at or below zero',
        'action': '회복 상태·일시적 부족과 이후 매출 흐름 모니터링',
        'start': '완전한 비공휴일 기간의 순부족을 확인한 뒤 상태 점검',
        'check': '양의 일별 부족분 합계, 회복 상태, 이후 순부족 변화',
        'caution': '초과 매출로 상쇄됐어도 일시적 부족·미회복이 남을 수 있음; 지원 제외 확정이 아님',
    },
}


def add_support_actions(metrics):
    required = KEY + ['scope', 'recovery_status', 'complete_eligible_window',
                      'net_shortfall_eligible', 'net_shortfall_rate_eligible', 'gross_shortfall_eligible']
    if missing := set(required) - set(metrics):
        raise ValueError(f'support review missing columns: {sorted(missing)}')
    out = metrics.copy()
    keys = KEY + (['scenario'] if 'scenario' in out else [])
    if out.empty or out[keys].isna().any().any() or out.duplicated(keys).any():
        raise ValueError('empty/missing/duplicate support-review keys')
    if not out.age.eq('ALL').all():
        raise ValueError('support actions currently cover industry ALL only')
    if not out.recovery_status.isin(['recovered', 'censored', 'insufficient_data', 'no_decline']).all():
        raise ValueError('unknown recovery status')
    complete = bool_column(out.complete_eligible_window, 'complete_eligible_window')
    monetary = out[['net_shortfall_eligible', 'net_shortfall_rate_eligible', 'gross_shortfall_eligible']].apply(pd.to_numeric, errors='raise')
    if np.isinf(monetary.to_numpy(dtype=float)).any() or monetary.gross_shortfall_eligible.dropna().lt(0).any():
        raise ValueError('invalid eligible monetary values')
    known = complete & monetary.notna().all(axis=1)
    positive = known & monetary.net_shortfall_eligible.gt(0)
    if not monetary.loc[known, 'net_shortfall_eligible'].gt(0).eq(monetary.loc[known, 'net_shortfall_rate_eligible'].gt(0)).all():
        raise ValueError('net shortfall sign differs from its rate')
    group = pd.Series('sales_data_incomplete', index=out.index)
    group.loc[known & ~positive] = 'no_positive_net_shortfall'
    names = {'recovered': 'shortfall_recovered', 'censored': 'shortfall_recovery_unconfirmed',
             'insufficient_data': 'shortfall_recovery_insufficient', 'no_decline': 'shortfall_below_decline_threshold'}
    group.loc[positive] = out.loc[positive, 'recovery_status'].map(names)
    out['support_review_group'] = group
    for field, source in [('support_review_label', 'label'), ('suggested_action', 'action'),
                          ('suggested_start_condition', 'start'), ('monitoring_metrics', 'check'),
                          ('support_review_caution', 'caution')]:
        out[field] = group.map({name: values[source] for name, values in ACTION_RULES.items()})
    out['assessment_as_of'] = out.window_end
    out['support_review_order'] = 'unordered_categories_not_funding_rank'
    out['duration_and_reassessment'] = '지원기간 미산정; 추가 관측 자료 확보 시 재평가'
    out['policy_status'] = 'proposed_action; effectiveness_and_funding_not_validated'
    return out


def write_support_review(base, scenarios, output):
    detail = comparison_fields(add_support_actions(base))
    sensitive = add_support_actions(scenarios)
    summary = detail.groupby(['event_id', 'scope', 'support_review_group', 'support_review_label'], sort=True).size().rename('industry_event_rows').reset_index()
    detail.to_csv(output / 'support_review_PROVISIONAL.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(output / 'support_review_summary.csv', index=False, encoding='utf-8-sig')
    sensitive[KEY + ['scope', 'scenario', 'support_review_group', 'support_review_label']].to_csv(
        output / 'support_review_sensitivity.csv', index=False, encoding='utf-8-sig')
    plot_support_review(detail, output)
    return detail


def plot_support_review(detail, output):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt, font_manager
    from matplotlib.ticker import MaxNLocator
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    family = next((f for f in ['AppleGothic', 'Malgun Gothic', 'NanumGothic'] if f in fonts), 'DejaVu Sans')
    with plt.rc_context({'font.family': family, 'axes.unicode_minus': False}):
        primary = detail.loc[detail.scope.eq('primary')]
        if primary.empty:
            return
        counts = primary.groupby(['event_id', 'support_review_group']).size().unstack(fill_value=0).reindex(columns=ACTION_RULES, fill_value=0)
        fig, ax = plt.subplots(figsize=(13, 4.8))
        counts.rename(columns={k: v['label'] for k, v in ACTION_RULES.items()}).plot.barh(
            stacked=True, ax=ax, color=['#b4b4b4', '#bda586', '#c38145', '#3b7e91', '#a5b397', '#86999b'])
        ax.set_title('상태별 지원 검토 대상 — 범주 간 지원 순위 아님')
        ax.set_xlabel('사건별 주 분석 업종 수'); ax.set_ylabel('')
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False, fontsize=9)
        fig.tight_layout()
        fig.savefig(output / 'support_review_overview.png', dpi=150)
        plt.close(fig)
