"""Time-ordered Ridge comparison; output contains private data, do not publish."""
import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from scripts import evaluate_models as common
from scripts import prepare_sales_baseline as baseline
from scripts.prepare_model_comparison import CATEGORICAL, NUMERIC, KEY, SPLITS

ALPHAS = [0.01, 0.1, 1., 10., 100., 1000., 10000.]


def make_ridge(alpha):
    return Pipeline([
        ('features', ColumnTransformer([
            ('categories', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CATEGORICAL),
            ('calendar', StandardScaler(), NUMERIC),
        ])),
        ('model', Ridge(alpha=alpha, solver='svd')),
    ])


def metric(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    if y.ndim != 1 or p.ndim != 1 or y.shape != p.shape:
        raise ValueError('metrics require equal one-dimensional arrays')
    if len(y) == 0 or not np.isfinite(y).all() or not np.isfinite(p).all() or (y < 0).any() or (p < 0).any():
        raise ValueError('empty or non-finite metrics')
    e = y-p
    return dict(rows=len(y), mae=float(np.abs(e).mean()), rmse=float(np.sqrt(np.mean(e**2))),
                wape=float(np.abs(e).sum()/np.abs(y).sum()) if np.abs(y).sum() else None)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def training_rows(card, events, split, calendar):
    start, end, first, _ = SPLITS[split]
    raw = card.loc[card.date.between(start, end)].copy()
    panel, _ = baseline.build_panel(raw, events.loc[events.start_date.le(pd.Timestamp(end))], calendar)
    train = baseline.training_sample(panel, pd.Timestamp(first), 'exclude_missing')
    if train.empty or train.date.max() >= pd.Timestamp(first):
        raise ValueError('invalid training period')
    return train


def select_alpha(train, observed):
    eligible = observed.loc[observed.comparison_eligible]
    if eligible.empty:
        raise ValueError('no common validation cohort')
    results = []
    for alpha in ALPHAS:
        model = make_ridge(alpha).fit(common.features(train), train.amount)
        pred = np.maximum(model.predict(common.features(eligible)), 0)
        results.append(dict(alpha=alpha, **metric(eligible.amount, pred)))
    scores = pd.DataFrame(results)
    if scores.wape.isna().any():
        raise ValueError('WAPE undefined')
    # Deterministic tie-break: smaller alpha. No holdout input accepted here.
    chosen = float(scores.sort_values(['wape', 'alpha']).iloc[0].alpha)
    return chosen, scores


def verify_reference(observed, old_path):
    old = pd.read_csv(old_path, dtype={k:str for k in baseline.KEY}, parse_dates=['date'])
    left = observed.set_index(KEY).sort_index()
    right = old.set_index(KEY).sort_index()
    if not left.index.equals(right.index):
        raise ValueError('reference observation keys differ')
    for col in ['amount', 'baseline_prediction', 'ai_prediction']:
        if not np.allclose(left[col], right[col], rtol=1e-9, atol=1e-6, equal_nan=True):
            raise ValueError('reference predictions differ: '+col)
    if not left.comparison_eligible.equals(right.comparison_eligible):
        raise ValueError('reference eligibility differs')
    return {'keys_match':True, 'amount_and_predictions_match':True, 'eligibility_match':True}


def run(input_dir, output, reference=None):
    if output.exists() and any(output.iterdir()):
        raise ValueError('output must be new/empty')
    paths = {n:input_dir/(n+'.csv') for n in ['card','events','windows','calendar']}
    card = baseline.validate_daily(pd.read_csv(paths['card'], dtype={k:str for k in baseline.KEY}))
    if not card.region.eq('강원 춘천시').all() or not card.date.between('2025-07-01','2025-12-31').all():
        raise ValueError('unexpected region or period')
    events, _ = baseline.load_events(paths['events'], paths['windows'])
    output.mkdir(parents=True, exist_ok=True)
    protocol = dict(version='ridge-20261026-v1', alpha_grid=ALPHAS,
        selection='minimum validation WAPE; tie smaller alpha; frozen before holdout',
        splits=SPLITS, categorical=CATEGORICAL, numeric=NUMERIC,
        encoding='one-hot industry/age; standardized numeric; training fit only',
        target='raw provided amount unit; no log transform', solver='svd',
        interaction_terms=False, negative_predictions='clip at zero for every model',
        training='same observed past non-event/non-holiday rows as shared baseline',
        cohort='shared baseline eligibility fixed before observed evaluation amounts',
        retrospective_evaluation=True,
        caveat='Oct-Dec benchmark already examined in earlier work; not a fresh untouched test. No Ridge tuning on it.',
        source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        input_sha256={n:digest(p) for n,p in paths.items()},
        environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__))
    if reference:
        prior=json.loads((reference/'protocol.json').read_text())
        if protocol['input_sha256'] != prior['input_sha256']:
            raise ValueError('input hashes differ from original model comparison')
    (output/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    scores=[]; audits=[]; reference_checks={}; selected=None
    for split in ['validation','holdout']:
        forecast,audit=common.forecast_split(card,events,split,paths['calendar'])
        observed=common.attach_actuals(card,forecast,split)
        train=training_rows(card,events,split,paths['calendar'])
        if len(train)!=audit['shared_training_rows']:
            raise ValueError('training cohorts differ')
        if reference:
            reference_checks[split]=verify_reference(observed,reference/f'{split}_predictions.csv')
        if split=='validation':
            selected,tuning=select_alpha(train,observed)
            tuning.to_csv(output/'validation_alpha_search.csv',index=False)
            (output/'frozen_selection.json').write_text(json.dumps({'alpha':selected,'selection_period':'September only'},indent=2))
        model=make_ridge(selected).fit(common.features(train),train.amount)
        known=observed.evaluation_status.ne('unseen_training_group')
        observed['ridge_raw_prediction']=np.nan
        observed.loc[known,'ridge_raw_prediction']=model.predict(common.features(observed.loc[known]))
        observed['ridge_prediction']=observed.ridge_raw_prediction.clip(lower=0)
        paired=observed.loc[observed.comparison_eligible].copy()
        if not np.isfinite(paired.ridge_prediction).all():
            raise ValueError('missing Ridge prediction in common cohort')
        # Deterministic independent refit check.
        repeat=make_ridge(selected).fit(common.features(train),train.amount)
        if not np.allclose(repeat.predict(common.features(paired)),paired.ridge_raw_prediction,rtol=1e-12,atol=1e-6):
            raise ValueError('Ridge refit not reproducible')
        pairs={'weekday_mean':'baseline_prediction','hist_gradient_boosting':'ai_prediction','ridge':'ridge_prediction'}
        for scope,col in [('overall',None),('industry','industry'),('age','age')]:
            groups=[('all',paired)] if col is None else paired.groupby(col,sort=True)
            for group, frame in groups:
                for name,predcol in pairs.items():
                    scores.append(dict(split=split,scope=scope,group=str(group),model=name,**metric(frame.amount,frame[predcol])))
        names=model.named_steps['features'].get_feature_names_out()
        pd.DataFrame({'feature':names,'coefficient':model.named_steps['model'].coef_}).to_csv(output/f'{split}_coefficients.csv',index=False)
        observed.to_csv(output/f'{split}_predictions.csv',index=False)
        audit.update(alpha=selected,observed_rows=len(observed),common_rows=len(paired),
                     common_industries=int(paired.industry.nunique()),
                     ridge_negative_before_clip=int(paired.ridge_raw_prediction.lt(0).sum()),ridge_refit_match=True,
                     ridge_intercept=float(model.named_steps['model'].intercept_))
        audits.append(audit)
        print(split,'complete',len(paired),'alpha',selected,flush=True)
    performance=pd.DataFrame(scores)
    performance.to_csv(output/'performance.csv',index=False)
    pd.DataFrame(audits).to_csv(output/'split_audit.csv',index=False)
    (output/'verification.json').write_text(json.dumps(dict(reference_checks=reference_checks,
        ridge_refit_match=True,input_hashes_match=True if reference else None),ensure_ascii=False,indent=2))
    print(performance.loc[performance.scope.eq('overall')].to_string(index=False))
    return performance


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--reference',type=Path)
    args=ap.parse_args()
    run(args.input_dir,args.output,args.reference)
