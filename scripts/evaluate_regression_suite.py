"""Retrospective model comparison. Private outputs; no causal-loss claims."""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from scripts import evaluate_ridge as ridge
from scripts import evaluate_models as common
from scripts import prepare_sales_baseline as baseline
from scripts.prepare_model_comparison import CATEGORICAL, NUMERIC, KEY

# Fixed before this suite evaluates October-December. Validation selection only.
CANDIDATES = {
    'ridge_interactions': [{'alpha':a} for a in ridge.ALPHAS],
    'elastic_net': [{'alpha':a,'l1_ratio':l} for a in [0.01,0.1,1.] for l in [0.2,0.8]],
    'random_forest': [{'max_depth':d} for d in [12,None]],
    'extra_trees': [{'max_depth':d} for d in [12,None]],
}
TARGET_SCALE = 1e6  # numerical scaling only, not a currency conversion


def suite_features(frame, interactions=False):
    out=common.features(frame)
    if interactions:
        # JSON tuples avoid collisions when category names include separators.
        out['industry_age']=[json.dumps([i,a],ensure_ascii=False) for i,a in zip(out.industry,out.age)]
        out['industry_weekday']=[json.dumps([i,int(d)],ensure_ascii=False) for i,d in zip(out.industry,out.weekday)]
    return out


def make_model(name, params):
    cats=CATEGORICAL+(['industry_age','industry_weekday'] if name=='ridge_interactions' else [])
    prep=ColumnTransformer([
        ('categories',OneHotEncoder(handle_unknown='ignore',sparse_output=False),cats),
        ('calendar',StandardScaler(),NUMERIC)])
    if name=='ridge_interactions':
        model=Ridge(alpha=params['alpha'],solver='lsqr',tol=1e-8,max_iter=20000)
    elif name=='elastic_net':
        model=ElasticNet(**params,max_iter=20000,tol=1e-6,selection='cyclic')
    else:
        cls={'random_forest':RandomForestRegressor,'extra_trees':ExtraTreesRegressor}[name]
        model=cls(**params,n_estimators=150,min_samples_leaf=5,max_features=1.0,random_state=42,n_jobs=2)
    return Pipeline([('features',prep),('model',model)])


def fit_predict(name, params, train, target):
    model=make_model(name,params)
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        model.fit(suite_features(train,name=='ridge_interactions'),train.amount/TARGET_SCALE)
    raw=model.predict(suite_features(target,name=='ridge_interactions'))*TARGET_SCALE
    if not np.isfinite(raw).all():
        raise ValueError('nonfinite prediction')
    return np.maximum(raw,0), int((raw<0).sum())


def run(input_dir, ridge_dir, output, models=None):
    names = list(CANDIDATES) if models is None else list(models)
    if not names or len(set(names)) != len(names) or set(names) - set(CANDIDATES):
        raise ValueError("unknown/empty/duplicate model selection")
    candidates_by_model = {name: CANDIDATES[name] for name in names}
    if output.exists() and any(output.iterdir()):
        raise ValueError('use new/empty output')
    output.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((ridge_dir/'protocol.json').read_text())
    for key,sha in protocol['input_sha256'].items():
        if ridge.digest(input_dir/(key+'.csv'))!=sha:
            raise ValueError('changed input '+key)
    protocol.update(suite_candidates=candidates_by_model,target_scale=TARGET_SCALE,
        selection='September WAPE, ties candidate order; freeze before holdout',
        retrospective_evaluation=True,
        caution='Original Ridge Oct-Dec result informed interaction idea; entire suite is exploratory retrospective comparison, not fresh confirmation.',
        interaction_experiment='industry_age + industry_weekday; separate from five regression model families',
        forest_settings={'n_estimators':150,'min_samples_leaf':5,'random_state':42,'n_jobs':2},
        source_suite_sha256=ridge.digest(__file__),
        reference_prediction_sha256={split:ridge.digest(ridge_dir/f'{split}_predictions.csv') for split in ['validation','holdout']})
    (output/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    card=baseline.validate_daily(pd.read_csv(input_dir/'card.csv',dtype={k:str for k in baseline.KEY}))
    events,_=baseline.load_events(input_dir/'events.csv',input_dir/'windows.csv')
    selected={}; search=[]; scores=[]; audits=[]
    for split in ['validation','holdout']:
        train=ridge.training_rows(card,events,split,input_dir/'calendar.csv')
        observed=pd.read_csv(ridge_dir/f'{split}_predictions.csv',dtype={k:str for k in baseline.KEY},parse_dates=['date'])
        common_rows=observed.loc[observed.comparison_eligible].copy()
        if common_rows.duplicated(KEY).any(): raise ValueError('duplicate cohort')
        # Median uses exactly the same training eligibility and grouping as mean.
        med=train.groupby(baseline.KEY+['weekday']).amount.median().rename('median_prediction').reset_index()
        common_rows['weekday']=common_rows.date.dt.dayofweek
        common_rows=common_rows.merge(med,on=baseline.KEY+['weekday'],how='left',validate='many_to_one')
        if common_rows.median_prediction.isna().any(): raise ValueError('missing median')
        for name,candidates in candidates_by_model.items():
            if split=='validation':
                evaluated=[]
                for idx,params in enumerate(candidates):
                    pred,neg=fit_predict(name,params,train,common_rows)
                    measures=ridge.metric(common_rows.amount,pred)
                    if measures['wape'] is None: raise ValueError('undefined selection metric')
                    row=dict(model=name,candidate=idx,params=json.dumps(params),negative_count=neg,**measures)
                    search.append(row); evaluated.append((measures['wape'],idx,params,pred,neg))
                    print('candidate',name,params,'done',flush=True)
                best=min(evaluated,key=lambda x:(x[0],x[1]))
                selected[name]=best[2];pred,neg=best[3:]
            else:
                pred,neg=fit_predict(name,selected[name],train,common_rows)
            common_rows[name+'_prediction']=pred
            audits.append(dict(split=split,model=name,negative_before_clip=neg,training_rows=len(train),common_rows=len(common_rows)))
        if split=='validation':
            # Write decision before opening holdout predictions in next loop iteration.
            (output/'frozen_selection.json').write_text(json.dumps(selected,indent=2))
            pd.DataFrame(search).to_csv(output/'validation_search.csv',index=False)
        models={'weekday_mean':'baseline_prediction','weekday_median':'median_prediction','hist_gradient_boosting':'ai_prediction','ridge':'ridge_prediction',
                **{n:n+'_prediction' for n in candidates_by_model}}
        for scope,col in [('overall',None),('industry','industry'),('age','age')]:
            groups=[('all',common_rows)] if col is None else common_rows.groupby(col,sort=True)
            for group, frame in groups:
                for model,predcol in models.items():
                    scores.append(dict(split=split,scope=scope,group=str(group),model=model,**ridge.metric(frame.amount,frame[predcol])))
        # Residual diagnostics for original Ridge on the exact common sample.
        diag=common_rows.copy()
        diag['ridge_abs_error']=(diag.amount-diag.ridge_prediction).abs()
        diag['mean_abs_error']=(diag.amount-diag.baseline_prediction).abs()
        diag['signed_error']=diag.ridge_prediction-diag.amount
        for col in ['industry','age']:
            d=diag.groupby(col).agg(rows=('amount','size'),actual_sum=('amount','sum'),ridge_abs_error=('ridge_abs_error','sum'),mean_abs_error=('mean_abs_error','sum'),signed_error=('signed_error','sum'))
            d['excess_error']=d.ridge_abs_error-d.mean_abs_error
            d['ridge_wape']=d.ridge_abs_error/d.actual_sum
            d['mean_wape']=d.mean_abs_error/d.actual_sum
            d.sort_values('excess_error',ascending=False).to_csv(output/f'{split}_ridge_diagnostics_{col}.csv')
        common_rows.to_csv(output/f'{split}_predictions.csv',index=False)
    perf=pd.DataFrame(scores);perf.to_csv(output/'performance.csv',index=False)
    pd.DataFrame(audits).to_csv(output/'audit.csv',index=False)
    print(perf.loc[perf.scope.eq('overall')].to_string(index=False),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir',type=Path,required=True)
    ap.add_argument('--ridge-dir',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--models',nargs='+',choices=list(CANDIDATES))
    a=ap.parse_args();run(a.input_dir,a.ridge_dir,a.output,a.models)
