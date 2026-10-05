"""Legacy PR30 comparison only; use run_support_review for PR32 integration.

The --curves input uses the old PR30 'expected' schema. Do not pass PR32 curves
or replace missing common-baseline values with this historical comparison.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.prepare_priority import KEY, SALES, RECOVERY, join_metrics


def prepare_inputs(summary, recovery):
    selected = summary.loc[summary.window_type.eq('effective') &
                           summary.baseline_mode.eq('fixed_pre_event') &
                           summary.missing_policy.eq('exclude_missing') &
                           summary.model_id.eq('weekday_mean')].copy()
    if selected.empty or selected.age.eq('ALL').any():
        raise ValueError('expected age-detail shared baseline rows')
    sales = selected[KEY].copy()
    sales['decline_rate'] = selected.decline_rate_event
    # Incomplete-window paired sums are diagnostics, never presented as full loss.
    sales['gross_shortfall'] = selected.gross_shortfall_full
    sales['net_shortfall'] = selected.net_shortfall_full
    sales['net_shortfall_rate'] = selected.net_shortfall_rate_full
    sales['sales_uncertainty_note'] = [
        f'case role={role}; coverage={coverage:.4f}; holiday days={holidays}; '
        f'full-window complete={complete}; provisional baseline; team review pending'
        for role, coverage, holidays, complete in zip(selected.analysis_role, selected.coverage,
                                                     selected.holiday_excluded_days, selected.complete_window)]
    r = recovery.loc[recovery.age.ne('ALL'), KEY + RECOVERY].copy()
    for frame in [sales, r, selected]:
        for col in ['window_start', 'window_end']:
            frame[col] = pd.to_datetime(frame[col], errors='raise').dt.strftime('%Y-%m-%d')
    out = join_metrics(sales, r)
    diagnostics = ['analysis_role', 'scope', 'coverage', 'eligible_coverage', 'paired_days',
                   'window_days', 'holiday_excluded_days', 'complete_window',
                   'gross_shortfall_paired', 'net_shortfall_paired', 'net_shortfall_eligible']
    out = out.merge(selected[KEY + diagnostics], on=KEY, validate='one_to_one')
    out['review_status'] = 'provisional_age_detail; awaiting joint rules and issues 11/12'
    out['priority_uncertainty_note'] = 'No agreed ranking rule. No final ranks calculated.'
    return out


def compare_industry_aggregation(industry, curves):
    """Expose differences between paired-age totals and existing ALL recovery.

    This is a diagnostic only. Do not silently replace Seeun's recovery model.
    """
    a = industry.copy()
    b = curves.loc[curves.age.eq('ALL') & curves.is_effective.eq(True)].copy()
    keys = ['event_id', 'date', 'region', 'industry']
    for f in [a, b]:
        f['date'] = pd.to_datetime(f.date)
        if f.duplicated(keys).any():
            raise ValueError('duplicate industry comparison keys')
    out = a.merge(b[keys + ['amount', 'expected']], on=keys, how='outer',
                  validate='one_to_one', indicator=True)
    if not out._merge.eq('both').all():
        raise ValueError('industry/recovery date keys differ')
    out['actual_agrees'] = np.isclose(out.amount_paired, out.amount, rtol=1e-9, atol=1e-9, equal_nan=True)
    out['expected_agrees'] = np.isclose(out.prediction_paired, out.expected, rtol=1e-9, atol=1e-9, equal_nan=True)
    out['review_required'] = ~(out.actual_agrees & out.expected_agrees)
    return out.drop(columns='_merge')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sales', type=Path, required=True)
    parser.add_argument('--recovery', type=Path, required=True)
    parser.add_argument('--industry', type=Path, required=True)
    parser.add_argument('--curves', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = prepare_inputs(pd.read_json(args.sales), pd.read_csv(args.recovery, dtype={k: str for k in KEY}))
    audit = compare_industry_aggregation(pd.read_csv(args.industry), pd.read_csv(args.curves))
    args.output.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output / 'support_inputs_age_PROVISIONAL.csv', index=False, encoding='utf-8-sig')
    audit.to_csv(args.output / 'industry_aggregation_check.csv', index=False, encoding='utf-8-sig')
    print(f'{len(out)} age-detail rows; ranks blank; {int(audit.review_required.sum())}/{len(audit)} industry/date rows need review')
