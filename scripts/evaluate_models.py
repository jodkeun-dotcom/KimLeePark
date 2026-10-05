"""Issue #13: fixed, time-ordered comparison with the shared baseline.

Actual numeric outputs are local. Forecast evaluation does not validate causal
heat losses or select a support-priority rule.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import prepare_sales_baseline as baseline
from scripts.prepare_model_comparison import (
    CATEGORICAL, NUMERIC, KEY, SPLITS, make_ai_model, paired_metrics,
)


def features(frame):
    out = frame[CATEGORICAL].copy()
    date = pd.to_datetime(frame.date)
    out['weekday'] = date.dt.dayofweek
    out['is_weekend'] = out.weekday.ge(5).astype(int)
    out['month_number'] = date.dt.month
    out['day_index'] = (date - pd.Timestamp('2025-07-01')).dt.days
    return out[CATEGORICAL + NUMERIC]


def forecast_split(card, events, split, calendar=None):
    """Fit both models to identical past rows; never use evaluation amounts.

    Predict the full known-group/date grid. Baseline eligibility depends only
    on past counts and calendar flags, not on observed evaluation amounts.
    """
    start, end, first, last = SPLITS[split]
    raw_train = card.loc[card.date.between(start, end)].copy()
    if raw_train.empty:
        raise ValueError('empty training period')
    past_events = events.loc[events.start_date.le(pd.Timestamp(end))].copy()
    panel, provenance = baseline.build_panel(raw_train, past_events, calendar)
    train = baseline.training_sample(panel, pd.Timestamp(first), 'exclude_missing')
    if train.empty or train.date.max() >= pd.Timestamp(first):
        raise ValueError('empty or non-past training sample')
    groups = raw_train[baseline.KEY].drop_duplicates()
    dates = pd.date_range(first, last)
    flags, _ = baseline.calendar_flags(dates, calendar)
    target = groups.merge(pd.DataFrame({'date': dates}), how='cross')
    target['weekday'] = target.date.dt.dayofweek
    target['is_holiday'] = target.date.map(flags)
    p = baseline.predict(train, target)
    model = make_ai_model()
    model.fit(features(train), train.amount)
    p['ai_prediction'] = np.maximum(model.predict(features(p)), 0)
    p['baseline_prediction'] = p['mean'].clip(lower=0)
    p['comparison_eligible'] = p.prediction_status.eq('predicted')
    if not np.isfinite(p.ai_prediction).all():
        raise ValueError('non-finite AI prediction')
    if not np.isfinite(p.loc[p.comparison_eligible, 'baseline_prediction']).all():
        raise ValueError('eligible baseline prediction missing')
    if p.duplicated(KEY).any():
        raise ValueError('duplicate forecast keys')
    out = p[KEY + ['baseline_prediction', 'ai_prediction', 'prediction_status',
                   'comparison_eligible', 'train_days', 'count']].copy()
    audit = {'split': split, 'training_start': start, 'training_end': end,
             'evaluation_start': first, 'evaluation_end': last,
             'raw_training_rows': len(raw_train), 'shared_training_rows': len(train),
             'shared_training_days': int(train.date.nunique()),
             'latest_training_date': str(train.date.max().date()),
             'known_training_groups': len(groups), 'forecast_grid_rows': len(out),
             'calendar_provenance': provenance,
             'training_policy': 'same observed pre-origin non-event/non-holiday rows',
             'retraining': 'none within evaluation period'}
    return out, audit


def attach_actuals(card, forecast, split):
    _, _, first, last = SPLITS[split]
    actual = card.loc[card.date.between(first, last), KEY + ['amount']].copy()
    if actual.empty or actual.duplicated(KEY).any():
        raise ValueError('empty or duplicate evaluation observations')
    out = actual.merge(forecast, on=KEY, how='left', validate='one_to_one', indicator=True)
    out['evaluation_status'] = out.prediction_status.fillna('unseen_training_group')
    out['comparison_eligible'] = out.comparison_eligible.eq(True)
    if not out.loc[out.comparison_eligible, '_merge'].eq('both').all():
        raise ValueError('eligible observation has no forecast')
    return out.drop(columns='_merge')


def score_frame(frame):
    if frame.empty:
        return pd.DataFrame(columns=['model', 'rows', 'mae', 'rmse', 'wape'])
    actual = frame[KEY + ['amount']]
    b = frame[KEY + ['baseline_prediction']].rename(columns={'baseline_prediction': 'prediction'})
    a = frame[KEY + ['ai_prediction']].rename(columns={'ai_prediction': 'prediction'})
    return paired_metrics(actual, b, a)


def score_by_group(observed, split):
    common = observed.loc[observed.comparison_eligible].copy()
    if common.empty:
        raise ValueError('no comparable observed rows')
    common['month'] = common.date.dt.strftime('%Y-%m')
    parts = [score_frame(common).assign(split=split, scope='overall', group='all')]
    for scope, cols in [('month', ['month']), ('industry', ['industry']),
                        ('age', ['age']), ('industry_age', ['industry', 'age'])]:
        for value, group in common.groupby(cols, sort=True):
            values = value if isinstance(value, tuple) else (value,)
            parts.append(score_frame(group).assign(split=split, scope=scope,
                                                  group=json.dumps(values, ensure_ascii=False)))
    return pd.concat(parts, ignore_index=True)


def coverage_rows(observed, split):
    records = []
    for status, frame in observed.groupby('evaluation_status'):
        records.append({'split': split, 'status': status, 'observed_rows': len(frame),
                        'observed_amount': float(frame.amount.sum()),
                        'fraction_of_observed_rows': len(frame) / len(observed)})
    return records


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plot_scores(scores, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels = {'shared_baseline': 'Shared weekday mean', 'hist_gradient_boosting': 'AI: gradient boosting'}
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, metric in zip(axes, ['mae', 'rmse', 'wape']):
        values = scores.loc[scores.scope.eq('overall')].pivot(index='split', columns='model', values=metric)
        values = values.reindex(['validation', 'holdout'])
        values.rename(columns=labels).plot.bar(ax=ax, color=['#246887', '#c57538'], rot=0)
        ax.set_title(metric.upper())
        ax.set_xlabel('')
        ax.set_ylabel('Ratio' if metric == 'wape' else 'Provided amount unit')
        ax.spines[['top', 'right']].set_visible(False)
        if metric != 'mae':
            ax.get_legend().remove()
        else:
            ax.legend(fontsize=8)
    fig.suptitle('Same past training rows and same observed evaluation keys')
    fig.tight_layout()
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def run(card_path, events_path, windows_path, output, calendar=None):
    if output.exists() and any(output.iterdir()):
        raise ValueError('use a new output directory; preserve previous evaluation runs')
    card = baseline.validate_daily(pd.read_csv(card_path, dtype={k: str for k in baseline.KEY}))
    if card.region.nunique() != 1 or not card.region.eq('강원 춘천시').all():
        raise ValueError('this protocol supports Chuncheon only')
    if not card.date.between('2025-07-01', '2025-12-31').all():
        raise ValueError('card dates outside study period')
    events, _ = baseline.load_events(events_path, windows_path)
    model_parameters = make_ai_model().named_steps['model'].get_params()
    source_dir = Path(__file__).parent
    protocol = {'version': '1007-fixed-v1', 'baseline': 'shared weekday_mean; min_total=7; min_weekday=2',
                'ai_parameters': model_parameters, 'splits': SPLITS,
                'features': CATEGORICAL + NUMERIC, 'negative_predictions': 'clip both models at zero',
                'missing_actual': 'not zero-filled; score observed rows only',
                'common_cohort': 'training-count/calendar eligibility, determined before evaluation amounts',
                'hyperparameter_search': False, 'holdout_tuning': False,
                'primary_metrics': ['mae', 'rmse', 'wape'],
                'calendar_status': 'provided_calendar' if calendar else 'provisional_08_15_only',
                'selection_status': 'weekday_mean used as Joeun-requested analysis baseline; joint interpretation review pending',
                'input_sha256': {name: digest(path) for name, path in
                                 [('card', card_path), ('events', events_path), ('windows', windows_path)]},
                'source_sha256': {name: digest(source_dir / name) for name in
                                  ['evaluate_models.py', 'prepare_model_comparison.py', 'prepare_sales_baseline.py']}}
    if calendar:
        protocol['input_sha256']['calendar'] = digest(calendar)
    output.mkdir(parents=True, exist_ok=True)
    # Save the identical settings for both periods BEFORE any model fit or score.
    (output / 'protocol.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding='utf-8')
    scores, coverage, audits = [], [], []
    for split in ['validation', 'holdout']:
        forecast, audit = forecast_split(card, events, split, calendar)
        observed = attach_actuals(card, forecast, split)
        scored = score_by_group(observed, split)
        scores.append(scored)
        coverage.extend(coverage_rows(observed, split))
        audit.update(observed_evaluation_rows=len(observed),
                     comparable_observed_rows=int(observed.comparison_eligible.sum()),
                     unobserved_forecast_grid_rows=int(len(forecast)-len(observed.loc[observed.evaluation_status.ne('unseen_training_group')])))
        audits.append(audit)
        observed.to_csv(output / f'{split}_predictions.csv', index=False, encoding='utf-8-sig')
    scores = pd.concat(scores, ignore_index=True)
    scores.to_csv(output / 'performance.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(coverage).to_csv(output / 'coverage.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(audits).to_csv(output / 'split_audit.csv', index=False, encoding='utf-8-sig')
    plot_scores(scores, output / 'performance.png')
    print(scores.loc[scores.scope.eq('overall')].to_string(index=False))
    return scores, audits


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--windows', type=Path, required=True)
    parser.add_argument('--calendar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.card, args.events, args.windows, args.output, args.calendar)
