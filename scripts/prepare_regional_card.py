"""Prepare both regions from provider data1 ZIP without modifying source files."""
import argparse,hashlib,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd

REGIONS=['강원 춘천시','서울 강남구']
KEY=['date','region','industry','age']

def run(source, output):
    if output.exists() and any(output.iterdir()):raise ValueError('use new/empty output')
    with zipfile.ZipFile(source) as z:
        candidates=[n for n in z.namelist() if n.endswith('데이터1.txt')]
        if len(candidates)!=1:raise ValueError('expected one data1')
        with z.open(candidates[0]) as f:df=pd.read_csv(f,sep='\t',encoding='cp949',dtype=str)
    required=['TA_YMD','TIME_GB','MCT_SGG_CD','MCT_RY_CD','AGE_CCD','SEX_CCD','TS_AT','USE_CNT']
    if set(required)-set(df):raise ValueError('missing columns')
    rawcounts=df.groupby('MCT_SGG_CD').size().to_dict()
    df=df.loc[df.MCT_SGG_CD.isin(REGIONS)&~df.AGE_CCD.eq('법인')&~df.SEX_CCD.eq('법인')].copy()
    if df[required].isna().any().any():raise ValueError('missing required value')
    df['date']=pd.to_datetime(df.TA_YMD,format='%Y%m%d',errors='raise')
    df['age']=df.AGE_CCD.str.replace(' ','',regex=False).map({f'{i}대':f'{i}대' if i<60 else '60대 이상' for i in range(10,100,10)})
    if df.age.isna().any():raise ValueError('unknown age')
    df=df.rename(columns={'MCT_SGG_CD':'region','MCT_RY_CD':'industry','TS_AT':'amount','USE_CNT':'transactions'})
    for col in ['amount','transactions']:
        df[col]=pd.to_numeric(df[col],errors='raise')
        if not np.isfinite(df[col]).all() or df[col].lt(0).any():raise ValueError('invalid measure')
    if not df.date.between('2025-07-01','2025-12-31').all():raise ValueError('unexpected period')
    daily=df.groupby(KEY,as_index=False)[['amount','transactions']].sum()
    for region in REGIONS:
        for col in ['amount','transactions']:
            if df.loc[df.region.eq(region),col].sum()!=daily.loc[daily.region.eq(region),col].sum():raise ValueError('total mismatch')
    common=set.intersection(*(set(daily.loc[daily.region.eq(region),'industry']) for region in REGIONS))
    output.mkdir(parents=True,exist_ok=True)
    daily.to_csv(output/'regional_card_daily.csv',index=False,encoding='utf-8-sig')
    summary=daily.groupby('region').agg(rows=('amount','size'),industries=('industry','nunique'),dates=('date','nunique'),first=('date','min'),last=('date','max'))
    summary.to_csv(output/'coverage.csv',encoding='utf-8-sig')
    metadata={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'raw_rows_by_region':rawcounts,
              'common_industries':sorted(common),'corporate_excluded':True,'status':'card_prepared_weather_pending',
              'policy':'missing observations not zero-filled; sex/time aggregated; 60+ collapsed'}
    (output/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(summary.to_string());print('common industries',len(common))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.input,a.output)
