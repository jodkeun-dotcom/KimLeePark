"""Prepare Chuncheon personal-card daily and monthly tables from Shinhan data1."""
import argparse
from pathlib import Path
import pandas as pd


def prepare(source, output, encoding='cp949'):
    df = pd.read_csv(source, sep='\t', encoding=encoding, dtype=str)
    required = ['TA_YMD','MCT_SGG_CD','MCT_RY_CD','AGE_CCD','SEX_CCD','TIME_GB','TS_AT','USE_CNT']
    if set(required) - set(df):
        raise ValueError('Expected data1 including TIME_GB; do not pass data2')
    df = df.loc[df.MCT_SGG_CD.eq('강원 춘천시') & ~df.AGE_CCD.eq('법인') & ~df.SEX_CCD.eq('법인')].copy()
    if df.empty or df[required].isna().any().any():
        raise ValueError('Empty input or missing required values')
    df['date'] = pd.to_datetime(df.TA_YMD, format='%Y%m%d', errors='raise')
    if not df.date.between('2025-07-01','2025-12-31').all():
        raise ValueError('Dates outside analysis period')
    age_map = {f'{a}대': (f'{a}대' if a < 60 else '60대 이상') for a in range(10,100,10)}
    df['age'] = df.AGE_CCD.str.replace(' ','',regex=False).map(age_map)
    if df.age.isna().any():
        raise ValueError('Unknown age category')
    df = df.rename(columns={'MCT_SGG_CD':'region','MCT_RY_CD':'industry','TS_AT':'amount','USE_CNT':'transactions'})
    measures = ['amount','transactions']
    df[measures] = df[measures].apply(pd.to_numeric, errors='raise')
    if (df[measures] < 0).any().any():
        raise ValueError('Negative card measures')
    daily = df.groupby(['date','region','industry','age'],as_index=False)[measures].sum()
    monthly_source = daily.assign(month=daily.date.dt.strftime('%Y%m'))
    monthly = monthly_source.groupby(['month','region','age'],as_index=False).agg(amount=('amount','sum'),transactions=('transactions','sum'),observed_days=('date','nunique'))
    monthly['calendar_days'] = pd.to_datetime(monthly.month,format='%Y%m').dt.days_in_month
    monthly['amount_per_calendar_day'] = monthly.amount / monthly.calendar_days
    for col in measures:
        if daily[col].sum() != df[col].sum() or monthly[col].sum() != df[col].sum():
            raise ValueError('Aggregation total mismatch')
    output.mkdir(parents=True,exist_ok=True)
    daily.to_csv(output/'daily.csv',index=False,encoding='utf-8-sig')
    monthly.to_csv(output/'monthly_age.csv',index=False,encoding='utf-8-sig')
    print(f'Saved daily {len(daily)}, monthly {len(monthly)} rows')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--encoding',default='cp949')
    args=parser.parse_args()
    prepare(args.input,args.output,args.encoding)
