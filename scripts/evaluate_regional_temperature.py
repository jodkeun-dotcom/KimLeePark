"""Exploratory two-region summer sales comparison; not causal heat damage."""
import argparse, hashlib, json, platform
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import Ridge

REGIONS = ['강원 춘천시', '서울 강남구']
KEY = ['date','region','industry','age']
PAIR = ['date','industry','age']
GROUP = ['region','industry','age']
SPLITS = [('validation','2025-07-21','2025-07-22','2025-08-04'),
          ('evaluation_1','2025-08-04','2025-08-05','2025-08-18'),
          ('evaluation_2','2025-08-18','2025-08-19','2025-08-31')]
ALPHAS = [0.1, 1., 10., 100.]

def unique(df, key):
    if df[key].isna().any().any() or df.duplicated(key).any():
        raise ValueError('missing or duplicate key: '+str(key))

def paired(df):
    unique(df, KEY)
    if not set(df.region).issubset(REGIONS): raise ValueError('unexpected region')
    return df.loc[df.groupby(PAIR).region.transform('nunique').eq(2)].copy()

def read_weather(path, station, region):
    d=pd.read_csv(path,encoding='cp949')
    if set(d['지점'].dropna().astype(int)) != {station}: raise ValueError('wrong station')
    d=d.rename(columns={'일시':'date','최고기온(°C)':'tmax'})
    d['date']=pd.to_datetime(d.date,errors='raise'); d['region']=region
    unique(d,['date']); d['tmax']=pd.to_numeric(d.tmax,errors='raise')
    if ((d.tmax.dropna() < -50) | (d.tmax.dropna() > 60)).any(): raise ValueError('temperature range')
    if not d.date.between('2025-07-01','2025-12-31').all(): raise ValueError('weather date range')
    return d[['date','region','tmax']]

def features(df, model):
    rows=[]
    for r in df.itertuples():
        # Tuple JSON avoids ambiguous concatenated category names.
        cell=json.dumps([r.region,r.industry,r.age],ensure_ascii=False)
        rw=json.dumps([r.region,r.date.dayofweek],ensure_ascii=False)
        f={'cell':cell,'region_weekday':rw,'trend':(r.date-pd.Timestamp('2025-07-01')).days/30,
           'holiday':float(r.is_holiday)}
        t=(r.tmax-30)/5; h=max(r.tmax-33,0)/5
        if model != 'M0_calendar': f.update(temp=t,excess33=h)
        if model == 'M2_interactions':
            f['temp_region_'+r.region]=t; f['heat_region_'+r.region]=h
            f['temp_industry_'+r.industry]=t; f['heat_industry_'+r.industry]=h
        rows.append(f)
    return rows

def metrics(y,p):
    y=np.asarray(y,float); p=np.asarray(p,float)
    if y.ndim!=1 or y.shape!=p.shape or not len(y) or not np.isfinite(y).all() or not np.isfinite(p).all():raise ValueError('invalid metrics input')
    if (y<0).any() or (p<0).any():raise ValueError('negative value')
    e=p-y
    return {'n':len(y),'wape':float(np.abs(e).sum()/y.sum()) if y.sum()>0 else None,
            'mae':float(np.abs(e).mean()),'rmse':float(np.sqrt((e**2).mean()))}

def make_fold(df,end,start,stop):
    tr=df[df.date.le(end)].copy(); ev=df[df.date.between(start,stop)].copy()
    if tr.date.max()>=ev.date.min():raise ValueError('temporal leakage')
    stats=tr.groupby(GROUP).amount.agg(['mean','size']).reset_index().rename(columns={'mean':'scale'})
    stats=stats[(stats['size']>=7)&(stats.scale>0)]
    # Require both regions to have sufficient past observations for each cell.
    stats=stats[stats.groupby(['industry','age']).region.transform('nunique').eq(2)]
    tr=tr.merge(stats[GROUP+['scale']],on=GROUP,validate='many_to_one')
    ev=ev.merge(stats[GROUP+['scale']],on=GROUP,validate='many_to_one')
    tr=paired(tr);ev=paired(ev)
    if tr.empty or ev.empty:raise ValueError('empty eligible fold')
    return tr,ev

def fit_predict(tr,ev,model,alpha):
    v=DictVectorizer(); x=v.fit_transform(features(tr,model)); z=v.transform(features(ev,model))
    m=Ridge(alpha=alpha,solver='lsqr',tol=1e-8,max_iter=20000)
    # Normalize by cell mean estimated from training only, so large Gangnam cells do not dominate fitting.
    m.fit(x,tr.amount.to_numpy()/tr.scale.to_numpy())
    p=np.maximum(m.predict(z),0)*ev.scale.to_numpy()
    return p,m,v

def regional_score(ev,p):
    return float(np.mean([metrics(ev.loc[ev.region.eq(r),'amount'],p[ev.region.eq(r)])['wape'] for r in REGIONS]))

def baseline(tr,ev):
    a=tr.assign(weekday=tr.date.dt.dayofweek).groupby(GROUP+['weekday']).amount.mean().rename('p').reset_index()
    e=ev.assign(weekday=ev.date.dt.dayofweek).merge(a,on=GROUP+['weekday'],how='left',validate='many_to_one')
    return e.p.fillna(e.scale).to_numpy()

def run(card,chuncheon,gangnam,calendar,output):
    if output.exists() and any(output.iterdir()): raise ValueError('use fresh output directory')
    c=pd.read_csv(card);c['date']=pd.to_datetime(c.date,errors='raise');unique(c,KEY)
    if set(c.region)!=set(REGIONS) or not np.isfinite(c.amount).all() or c.amount.lt(0).any():raise ValueError('invalid card data')
    cal=pd.read_csv(calendar);cal['date']=pd.to_datetime(cal.date,errors='raise');unique(cal,['date'])
    if not cal.is_holiday.isin([0,1]).all():raise ValueError('invalid holiday flag')
    w=pd.concat([read_weather(chuncheon,101,REGIONS[0]),read_weather(gangnam,400,REGIONS[1])])
    dates=pd.date_range('2025-07-01','2025-12-31')
    quality=[]
    for r in REGIONS:
        q=w[w.region.eq(r)]
        quality.append({'region':r,'missing_dates':[x.strftime('%Y-%m-%d') for x in dates.difference(q.date)],
                        'missing_tmax_dates':q.loc[q.tmax.isna(),'date'].dt.strftime('%Y-%m-%d').tolist()})
    summer=c[c.date.between('2025-07-01','2025-08-31')].copy()
    d=summer.merge(w,on=['date','region'],how='left',validate='many_to_one').merge(cal[['date','is_holiday']],on='date',how='left',validate='many_to_one')
    if d[['tmax','is_holiday']].isna().any().any():raise ValueError('incomplete summer weather/calendar')
    d=paired(d).sort_values(KEY).reset_index(drop=True)
    output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame([{'region':r,'summer_observed_rows':len(summer[summer.region.eq(r)]),'paired_rows':len(d[d.region.eq(r)])} for r in REGIONS]).to_csv(output/'coverage.csv',index=False)
    w.to_csv(output/'weather_standardized.csv',index=False)
    preds=[];scores=[];grid=[];selection={};support=[];sens=[];fold_coverage=[]
    models=['M0_calendar','M1_temperature','M2_interactions']
    for fold,end,start,stop in SPLITS:
        tr,ev=make_fold(d,end,start,stop)
        for r in REGIONS:
            fold_coverage.append({'fold':fold,'region':r,'paired_candidate_rows':int((d.region.eq(r)&d.date.between(start,stop)).sum()),'eligible_rows':int(ev.region.eq(r).sum()),'outside_training_temp_range_rows':int((ev.region.eq(r)&((ev.tmax<tr.loc[tr.region.eq(r),'tmax'].min())|(ev.tmax>tr.loc[tr.region.eq(r),'tmax'].max()))).sum())})
        for phase,z in [('train',tr),('evaluation',ev)]:
            for r in REGIONS:
                q=z[z.region.eq(r)].drop_duplicates('date')
                support.append({'fold':fold,'phase':phase,'region':r,'days':len(q),'hot33_days':int(q.tmax.ge(33).sum()),'tmax_min':q.tmax.min(),'tmax_max':q.tmax.max(),
                                'rows':int(z.region.eq(r).sum()),'cell_count':len(z[z.region.eq(r)][['industry','age']].drop_duplicates())})
        for model in ['weekday_mean']+models:
            if model=='weekday_mean': p=baseline(tr,ev);alpha=None
            else:
                if fold=='validation':
                    candidates=[]
                    for a in ALPHAS:
                        p,_,_=fit_predict(tr,ev,model,a);s=regional_score(ev,p)
                        grid.append({'model':model,'alpha':a,'validation_macro_regional_wape':s});candidates.append((s,a))
                    selection[model]=min(candidates)[1]
                alpha=selection[model];p,m,v=fit_predict(tr,ev,model,alpha)
                # Descriptive +1C response only where modified temperatures stay in each region's training range.
                if model=='M2_interactions' and fold!='validation':
                    lo=tr.groupby('region').tmax.min();hi=tr.groupby('region').tmax.max()
                    mask=(ev.tmax>=ev.region.map(lo))&(ev.tmax+1<=ev.region.map(hi))
                    base=paired(ev[mask]).copy(); changed=base.copy();changed['tmax']+=1
                    if len(base):
                        p0=np.maximum(m.predict(v.transform(features(base,model))),0)
                        p1=np.maximum(m.predict(v.transform(features(changed,model))),0)
                        tmp=base[['date','region','industry','age']].copy();tmp['delta_per_training_cell_mean']=p1-p0;tmp['fold']=fold;sens.append(tmp)
            out=ev[KEY+['amount','tmax','scale']].copy();out['prediction']=p;out['fold']=fold;out['model']=model;preds.append(out)
            for r in REGIONS+['ALL']:
                mask=np.ones(len(ev),bool) if r=='ALL' else ev.region.eq(r).to_numpy()
                scores.append({'fold':fold,'region':r,'model':model,'alpha':alpha,**metrics(ev.amount.to_numpy()[mask],p[mask])})
        print('completed',fold,flush=True)
    pd.concat(preds).to_csv(output/'predictions.csv',index=False)
    pd.DataFrame(scores).to_csv(output/'metrics.csv',index=False)
    pd.DataFrame(grid).to_csv(output/'validation_grid.csv',index=False)
    pd.DataFrame(support).to_csv(output/'support.csv',index=False)
    pd.DataFrame(fold_coverage).to_csv(output/'fold_coverage.csv',index=False)
    if sens:
        s=pd.concat(sens);s.to_csv(output/'temperature_response_rows.csv',index=False)
        s.groupby(['fold','region','industry']).delta_per_training_cell_mean.agg(['mean','size']).to_csv(output/'temperature_response_by_industry.csv')
    metadata={'selection':selection,'splits':SPLITS,'weather_quality':quality,'input_hashes':{k:hashlib.sha256(Path(p).read_bytes()).hexdigest() for k,p in {'card':card,'chuncheon':chuncheon,'gangnam':gangnam,'calendar':calendar}.items()},
              'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__},
              'purpose':'exploratory observed-temperature association, not weather forecast, causal damage, tourism mechanism, or recovery baseline replacement'}
    (output/'run_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['card','chuncheon','gangnam','calendar','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.card,a.chuncheon,a.gangnam,a.calendar,a.output)
