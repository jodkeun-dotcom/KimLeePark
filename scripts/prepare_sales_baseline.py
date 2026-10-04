"""Exploratory baselines only: no validated causal damage or recovery estimates."""
def main():
    from pathlib import Path
    import pandas as pd
    import numpy as np

    import argparse
    parser=argparse.ArgumentParser(description='Provisional fixed-origin baseline checks and shortfall estimates.')
    parser.add_argument('--daily',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    source=args.daily

    d=pd.read_csv(source,parse_dates=['date'],dtype={'region':str,'industry':str,'age':str})
    keys=['region','industry','age']
    required=set(keys+['date','amount'])
    if not required.issubset(d.columns):raise ValueError('Missing required daily columns')
    if set(d.region)!={'강원 춘천시'}:raise ValueError('Expected Chuncheon region only')
    if d.date.min()!=pd.Timestamp('2025-07-01') or d.date.max()!=pd.Timestamp('2025-12-31'):raise ValueError('Expected July-December 2025 input')
    if d.date.nunique()!=184:raise ValueError('Input dates do not span all 184 days')

    assert not d.duplicated(['date']+keys).any()
    assert d[keys+['date']].notna().all().all()
    assert np.isfinite(d.amount).all() and d.amount.ge(0).all()
    periods=[('2025-07-01','2025-07-01'),('2025-07-07','2025-07-09'),('2025-07-20','2025-07-20'),
    ('2025-07-23','2025-08-04'),('2025-08-18','2025-08-25'),('2025-08-29','2025-08-29')]
    events=[('HEAT03','2025-07-23','2025-08-04'),('HEAT04','2025-08-18','2025-08-25'),('HEAT05','2025-08-29','2025-08-29')]
    primary={'한식','중식','일식','양식','기타요식','제과점','커피전문점','패스트푸드','편의점','할인점/슈퍼마켓/양판점','농수산물','정육점','기타식품','주류판매','영화/공연','게임방/오락실','노래방','종합레저타운/놀이동산'}
    d['weekday']=d.date.dt.dayofweek
    d['event_day']=False
    for s,e in periods:d.loc[d.date.between(s,e),'event_day']=True
    d['holiday_provisional']=d.date.eq(pd.Timestamp('2025-08-15'))
    d['eligible']=~d.event_day & ~d.holiday_provisional
    d['scope']=d.industry.map(lambda x:'주 분석' if x in primary else '보조 탐색')
    groups=d[keys].drop_duplicates()
    report='''# 실제 분석 방식에 맞춘 고정 기준선 검증

    모델: 같은 요일의 과거 평균/중앙값. 사건 시작 전에 고정하여 사건 종료 후 14일까지 예측하는 설계를 점검합니다.
    모든 85개 업종을 유지합니다. 학습 최소 요일 관측 2회·전체 7일은 탐색용 잠정값입니다.
    자료: 로컬 daily.csv, PR #24 문서 사건 목록, PR #26의 8/15 잠정 공휴일 목록.
    기상 사건 CSV와 전체 calendar.csv는 미수신입니다. 이전 사건 후 회복 영향은 아직 학습에서 제외하지 않습니다.

    ## 1. 동일 길이의 사건 전 검증 창

    폭염 실제 매출은 '폭염이 없었을 매출'의 정답이 아니므로, 실제 사건 전의 같은 길이 창을 검증용으로 잡았습니다.
    각 창 시작 전 자료만 학습하고 창 안에서 재학습하지 않습니다. 평가할 때 다른 폭염·호우일과 잠정 공휴일은 제외합니다.
    따라서 점수는 전체 장기 예측 정확도가 아니라 남은 비사건 관측일의 제한된 점수입니다.

    | 대상 | 고정 시작일 | 검증 종료 | 요구 길이 | 남은 비사건 날짜 | 학습 후보 날짜 | 평가 가능 여부 |
    |---|---|---|---:|---:|---:|---|
    '''
    scores=[]
    for event,s,e in events:
        start,end=pd.Timestamp(s),pd.Timestamp(e)
        horizon=(end-start).days+1+14
        origin=start-pd.Timedelta(days=horizon)
        finish=start-pd.Timedelta(days=1)
        train=d.loc[(d.date<origin)&d.eligible]
        target=d.loc[d.date.between(origin,finish)&d.eligible]
        assert train.empty or train.date.max()<origin
        assert target.empty or target.date.min()>=origin
        status='学習資料不足' if train.empty else '部分評価のみ'
        report+=f'| {event} | {origin:%Y-%m-%d} | {finish:%Y-%m-%d} | {horizon} | {target.date.nunique()} | {train.date.nunique()} | '+('학습자료 없음' if train.empty else '부분 평가만 가능')+' |\n'
        if train.empty:continue
        weekday=train.groupby(keys+['weekday']).amount.agg(['mean','median','count']).reset_index()
        total=train.groupby(keys).amount.count().rename('total_n').reset_index()
        p=target.merge(weekday,on=keys+['weekday'],how='left',validate='many_to_one').merge(total,on=keys,how='left',validate='many_to_one')
        p['paired']=p['count'].ge(2)&p.total_n.ge(7)&p['mean'].notna()&p['median'].notna()
        for scope,part in p.groupby('scope'):
            q=part.loc[part.paired]
            denom=q.amount.abs().sum()
            metric=lambda col:float((q.amount-q[col]).abs().sum()/denom) if denom>0 else None
            scores.append(dict(event=event,scope=scope,rows=len(part),paired=len(q),days=q.date.nunique(),mean=metric('mean'),median=metric('median')))
    report+='''
    | 대상 | 범위 | 후보 행 | 공통 평가 행 | 평가 날짜 | 평균 WAPE | 중앙값 WAPE |
    |---|---|---:|---:|---:|---:|---:|
    '''
    for r in scores:
        fmt=lambda v:'계산 불가' if v is None else f'{v:.1%}'
        report+=f"| {r['event']} | {r['scope']} | {r['rows']} | {r['paired']} | {r['days']} | {fmt(r['mean'])} | {fmt(r['median'])} |\n"
    report+='''
    ## 2. 실제 사건에서 계산 가능한 범위

    아래는 오차 검증이 아니라 모델 입력의 관측 충족 점검입니다. 미래 실제 매출은 사용하지 않았습니다.
    전체 491개 그룹을 사건+14일 창에 펼쳐 모든 요일을 예측할 수 있는지 확인합니다.

    | 사건 | 사건+관찰 종료 | 전체 요일 예측 가능한 그룹 | 중첩되는 다른 사건 | 결제해석 제한 |
    |---|---|---:|---|---|
    '''
    for event,s,e in events:
        start,end=pd.Timestamp(s),pd.Timestamp(e)
        finish=end+pd.Timedelta(days=14)
        train=d.loc[(d.date<start)&d.eligible]
        n=train.groupby(keys).amount.count().reindex(pd.MultiIndex.from_frame(groups),fill_value=0)
        weekday=train.groupby(keys+['weekday']).amount.count().unstack('weekday',fill_value=0).reindex(columns=range(7),fill_value=0).reindex(n.index,fill_value=0)
        possible=int(((n>=7)&weekday.min(axis=1).ge(2)).sum())
        overlap=[name for name,ss,ee in events if name!=event and pd.Timestamp(ss)<=finish and pd.Timestamp(ee)>=start]
        report+=f'| {event} | {finish:%Y-%m-%d} | {possible} / 491 | '+(', '.join(overlap) if overlap else '목록상 없음')+' | 인과적 피해액으로 해석 불가 |\n'
    report+='''
    ## 검증 결론과 PR 준비 상태

    날짜 순서와 고정 모델 계산은 점검했습니다. 그러나 요구 길이 전체의 비사건 검증은 확보되지 않았습니다.
    HEAT03은 동일 길이 검증 창 시작이 데이터 시작 이전입니다. 다른 사건도 평가 창에 폭염이 들어가 일부 날짜만 평가합니다.
    또한 HEAT04 관찰기간에는 HEAT05가 들어오므로 회복·부족 지표를 독립 사건 결과로 단순 해석하면 안 됩니다.

    현재는 '검증 완료된 예상 매출 모델'로 PR을 올릴 근거가 부족합니다.
    올릴 수 있는 범위는 입력 점검·탐색 기준선·자료 부족 결과를 재현하는 Draft이며, 실제 손실 산출 완성본과 구분해야 합니다.
    먼저 팀에 6월 이전 자료 가능 여부, 회복일 학습 사용, 중첩 사건 분리·절단, 공휴일 자료 수신을 확인합니다.
    평균/중앙값 중 낮은 점수를 선택하는 것만으로 이 설계 문제를 해결할 수 없습니다.
    '''
    (args.output/'fixed_validation.md').write_text(report,encoding='utf-8')
    print(scores)
    print('PASS: input keys, finite targets, fixed-origin training dates; full-horizon validation remains limited')

    import json
    windows=[('HEAT03','2025-07-23','2025-08-04','2025-08-18','exploratory_short_history'),
    ('HEAT04','2025-08-18','2025-08-25','2025-08-28','truncated_before_next_event'),
    ('HEAT04','2025-08-18','2025-08-25','2025-09-08','original_overlap_sensitivity'),
    ('HEAT05','2025-08-29','2025-08-29','2025-09-12','prior_recovery_contamination_possible')]
    results=[]
    for event,s,e,f,window_type in windows:
        start,end,finish=map(pd.Timestamp,[s,e,f])
        train=d.loc[(d.date<start)&d.eligible]
        assert train.empty or train.date.max()<start
        stats=train.groupby(keys+['weekday']).amount.agg(['mean','median','count']).reset_index()
        totals=train.groupby(keys).amount.count().rename('train_n').reset_index()
        dates=pd.DataFrame({'date':pd.date_range(start,finish)})
        grid=groups.merge(dates,how='cross')
        grid['weekday']=grid.date.dt.dayofweek
        grid=grid.merge(stats,on=keys+['weekday'],how='left',validate='many_to_one').merge(totals,on=keys,how='left',validate='many_to_one')
        grid=grid.merge(d[['date']+keys+['amount']],on=['date']+keys,how='left',validate='one_to_one')
        # Full calendar remains unverified. This is only the prior holiday list relevant to these windows.
        valid=grid['count'].ge(2)&grid.train_n.ge(7)&~grid.date.eq(pd.Timestamp('2025-08-15'))
        for name in ['mean','median']:grid.loc[~valid,name]=np.nan
        for key,g in grid.groupby(keys):
            row=dict(zip(keys,key))
            row.update(event_id=event,window_start=s,window_end=f,event_end=e,window_type=window_type,
                       scope='primary' if row['industry'] in primary else 'auxiliary',
                       window_days=len(g),observed_days=int(g.amount.notna().sum()),
                       train_days=int(g.train_n.iloc[0]) if pd.notna(g.train_n.iloc[0]) else 0,
                       interpretation='provisional_baseline_difference_not_causal_heat_damage')
            for model,col in [('weekday_mean','mean'),('weekday_median','median')]:
                p=g.loc[g.amount.notna()&g[col].notna()]
                complete=len(p)==len(g)
                expected=p[col].sum(min_count=1)
                gap=p[col]-p.amount
                event_rows=p.loc[p.date.le(end)]
                event_complete=len(event_rows)==(end-start).days+1
                event_expected=event_rows[col].sum(min_count=1)
                event_decline=(event_expected-event_rows.amount.sum())/event_expected if event_complete and pd.notna(event_expected) and event_expected>0 else None
                record={**row,'model_id':model,'paired_days':len(p),'complete_window':complete,
                    'expected_total_paired':float(expected) if pd.notna(expected) else None,
                    'gross_shortfall_paired':float(gap.clip(lower=0).sum()) if len(p) else None,
                    'net_shortfall_paired':float(gap.sum()) if len(p) else None,
                    'gross_shortfall_full':float(gap.clip(lower=0).sum()) if complete else None,
                    'net_shortfall_full':float(gap.sum()) if complete else None,
                    'net_shortfall_rate_full':float(gap.sum()/expected) if complete and expected>0 else None,
                    'decline_rate_event':float(event_decline) if event_decline is not None else None,
                    'status':'complete_provisional' if complete else 'partial' if len(p) else 'insufficient_data'}
                results.append(record)
    table=pd.DataFrame(results)
    assert len(table)==4*491*2
    assert (table.paired_days<=table.window_days).all()
    assert table.loc[~table.complete_window,'net_shortfall_full'].isna().all()
    out=args.output
    # JSON nulls preserve unavailable values, no NaN literals.
    records=json.loads(table.to_json(orient='records',force_ascii=False))
    (out/'잠정_기준선대비부족분.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    report='''# 6단계: 현재 자료로 계산 가능한 기준선 대비 부족분

    상태: 실제 로컬 daily.csv로 계산한 잠정 결과. 검증 완료된 폭염 피해액이나 지원 순위가 아닙니다.
    전체 85개 업종·491개 조합을 유지했습니다. 사건 시작 전 자료로 요일 평균·중앙값을 고정합니다.
    이전 비사건일에는 이전 폭염의 회복 영향이 남을 수 있으며, 전체 공휴일 달력은 미검증입니다.
    잠정 최소 학습조건은 전체 7일·동일 요일 2회입니다. 자료가 없는 날짜는 0으로 채우지 않습니다.

    7월 HEAT03은 탐색 사례입니다. HEAT04는 8/28까지의 절단 창과 원래 9/8까지 창을 별도로 계산합니다.
    HEAT03 원래 관찰 마지막 날인 8/18에도 다음 사건이 시작하므로 그 창 역시 중첩 한계가 있습니다.
    창별 합계를 서로 합산하면 같은 매출을 중복 계산할 수 있습니다.

    ## 요일 평균 기준 계산 가능 범위

    | 사건 | 기간 끝 | 범위 | 전체 기간 계산 가능 | 일부 날짜만 가능 | 계산 불가 |
    |---|---|---|---:|---:|---:|
    '''
    for (event,end,scope),p in table.loc[table.model_id.eq('weekday_mean')].groupby(['event_id','window_end','scope'],sort=False):
        c=p.status.value_counts()
        report+=f"| {event} | {end} | {'주 분석' if scope=='primary' else '보조 탐색'} | {c.get('complete_provisional',0)} | {c.get('partial',0)} | {c.get('insufficient_data',0)} |\n"
        print(event,end,scope,c.to_dict())
    report+='''
    ## 결과 파일 읽기

    - gross_shortfall: 부족한 날짜만 더한 부족분 합계.
    - net_shortfall: 초과 매출까지 차감한 순누적 부족. 음수도 허용합니다.
    - paired: 실제·예상 매출이 모두 있는 날짜의 소계. 전체 창의 결과로 사용하지 않습니다.
    - full: 모든 날짜가 계산 가능할 때만 값이 있습니다. 불완전한 창은 null입니다.
    - decline_rate_event: 사건 발생 기간 전체가 계산 가능할 때만 산출한 감소율. 관찰 창의 부족률과 구분합니다.
    - scope: 주 분석/보조 탐색. model_id: 평균/중앙값 비교 후보입니다.

    회복일은 아직 계산하지 않았습니다. 미수신 공휴일 캘린더와 사건 CSV 확인, 회복 기준 합의가 필요합니다.
    실제 수치 JSON은 로컬 검토용이며 공개 GitHub에 올리지 않습니다.
    PR에 올릴 코드에는 잠정 설정과 검증 한계를 명시해야 합니다. 이슈 #9 전체 완료나 확정 지원 순위로 보고하지 않습니다.
    '''
    (out/'6단계_잠정계산범위.md').write_text(report,encoding='utf-8')
    print('PASS: 3928 model/group/window records; partial windows have null full totals')

    d=pd.DataFrame(json.loads((out/'잠정_기준선대비부족분.json').read_text(encoding='utf-8')))
    key=['event_id','region','industry','age','window_start','window_end','window_type','scope']
    a=d.loc[d.model_id.eq('weekday_mean')]
    b=d.loc[d.model_id.eq('weekday_median')]
    p=a.merge(b,on=key,suffixes=('_mean','_median'),validate='one_to_one')
    p['complete_pair']=p.complete_window_mean&p.complete_window_median
    p['shortfall_sign_changed']=np.nan
    p['net_rate_difference_pp']=np.nan
    v=p.complete_pair&p.net_shortfall_rate_full_mean.notna()&p.net_shortfall_rate_full_median.notna()
    p.loc[v,'shortfall_sign_changed']=(np.sign(p.loc[v,'net_shortfall_full_mean'])!=np.sign(p.loc[v,'net_shortfall_full_median'])).astype(float)
    p.loc[v,'net_rate_difference_pp']=(p.loc[v,'net_shortfall_rate_full_mean']-p.loc[v,'net_shortfall_rate_full_median']).abs()*100
    # A 10pp gap is a review flag, not a statistically validated uncertainty interval.
    p['review_flag']=np.where(~v,'full_window_unavailable',np.where(p.shortfall_sign_changed.eq(1),'sign_changed',np.where(p.net_rate_difference_pp.gt(10),'gap_over_10pp','smaller_method_difference')))
    report='''# 7단계: 기준선 방법에 따른 결과 민감도

    비교: 같은 그룹·사건·관찰기간의 요일 평균과 요일 중앙값. 전체 창 계산이 양쪽 모두 가능하고 예상 매출 합이 양수인 경우만 비율을 비교합니다.
    순누적 부족률 = (예상−실제 합) / 예상 매출 합. 양수는 부족, 음수는 초과입니다.
    부호 변화에는 한 방법의 값이 0인 경우도 포함합니다. 두 방법의 차이는 신뢰구간이나 폭염 효과의 불확실성 전체를 뜻하지 않습니다.
    10%p 차이는 확인할 사례를 표시하기 위한 임시 기준입니다. 방법별 예상 매출 분모가 달라질 수 있습니다.

    | 사건 | 창 끝 | 범위 | 전체 창 비교 가능 | 부호 변화 | 차이 중앙값(%p) | 차이 최대(%p) | 10%p 초과 |
    |---|---|---|---:|---:|---:|---:|---:|
    '''
    for (event,end,scope),g in p.groupby(['event_id','window_end','scope'],sort=False):
        q=g.loc[g.net_rate_difference_pp.notna()]
        fmt=lambda x:'—' if pd.isna(x) else f'{x:.1f}'
        report+=f"| {event} | {end} | {'주 분석' if scope=='primary' else '보조 탐색'} | {len(q)} | {int(q.shortfall_sign_changed.eq(1).sum())} | {fmt(q.net_rate_difference_pp.median())} | {fmt(q.net_rate_difference_pp.max())} | {int(q.net_rate_difference_pp.gt(10).sum())} |\n"
        print(event,end,scope,'pairs',len(q),'sign changes',int(q.shortfall_sign_changed.eq(1).sum()),'median_pp',q.net_rate_difference_pp.median(),'over10',int(q.net_rate_difference_pp.gt(10).sum()))
    report+='''
    ## 주 분석에서 우선 확인할 사례

    지원 순위가 아니라 방법 선택에 민감한 사례입니다. 두 기준선 모두 음수이면 '피해'로 표현하지 않습니다.

    | 사건 | 창 끝 | 업종 | 연령 | 평균 기준 순부족률 | 중앙값 기준 순부족률 | 차이(%p) | 부호 변화 |
    |---|---|---|---|---:|---:|---:|---|
    '''
    top=p.loc[p.scope.eq('primary')&v].sort_values(['shortfall_sign_changed','net_rate_difference_pp'],ascending=False).head(15)
    for x in top.itertuples():
        report+=f'| {x.event_id} | {x.window_end} | {x.industry} | {x.age} | {x.net_shortfall_rate_full_mean:.1%} | {x.net_shortfall_rate_full_median:.1%} | {x.net_rate_difference_pp:.1f} | '+('있음' if x.shortfall_sign_changed else '없음')+' |\n'
    report+='''
    ## 관찰기간 선택에 따른 차이

    HEAT04의 8/28 종료 창은 다음 사건 전까지, 9/8 종료 창은 다음 폭염이 섞인 원래 기간입니다.
    두 창은 길이가 달라 부족액 차이를 모델 오류나 다음 폭염의 인과효과로 해석할 수 없습니다.
    창 비교도 양쪽 기간 전체가 관측된 동일 그룹으로 제한합니다.

    '''
    x=d.loc[d.event_id.eq('HEAT04')&d.model_id.eq('weekday_mean')&d.complete_window]
    t=x.loc[x.window_end.eq('2025-08-28')].merge(x.loc[x.window_end.eq('2025-09-08')],on=['region','industry','age','scope'],suffixes=('_short','_long'),validate='one_to_one')
    for scope,g in t.groupby('scope'):
        valid=g.net_shortfall_rate_full_short.notna()&g.net_shortfall_rate_full_long.notna()
        g=g.loc[valid]
        changes=(np.sign(g.net_shortfall_full_short)!=np.sign(g.net_shortfall_full_long)).sum()
        delta=(g.net_shortfall_rate_full_short-g.net_shortfall_rate_full_long).abs()*100
        report+=f"- {'주 분석' if scope=='primary' else '보조 탐색'}: 동일 그룹 {len(g)}개, 부호 변화 {int(changes)}개, 순부족률 차이 중앙값 {delta.median():.1f}%p.\n"
        print('window',scope,len(g),'sign changes',int(changes),'median_pp',delta.median())
    report+='''
    ## 다음 판단

    방법이나 관찰기간에 따라 부호가 바뀌는 그룹은 확정 부족 업종으로 선정하지 않습니다.
    중앙값을 선택해 더 큰 피해액이 나오는 결과만 취하지 않습니다. 사전 검증상 요일 평균을 잠정 주 기준으로 유지하고 중앙값은 비교 자료로 남깁니다.
    평균 기준 자체도 사전자료 부족·회복 영향 혼입·공휴일 미검증의 제한을 갖습니다.
    7월은 부분 결과만 있으며 전체 창의 방법 비교는 불가합니다.
    다음 제출 준비에서는 모델·기간·결측 상태와 이 민감도 결과를 함께 문서화해야 합니다. 팀 공통 기준과 회복 계산 연결은 아직 합의·확인할 사항입니다.
    '''
    (out/'7단계_기준선민감도.md').write_text(report,encoding='utf-8')
    cols=key+['complete_pair','net_shortfall_rate_full_mean','net_shortfall_rate_full_median','shortfall_sign_changed','net_rate_difference_pp','review_flag']
    (out/'기준선_민감도_로컬결과.json').write_text(json.dumps(json.loads(p[cols].to_json(orient='records',force_ascii=False)),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    assert len(p)==4*491
    assert p.loc[~p.complete_pair,'net_rate_difference_pp'].isna().all()
    print('PASS: unique matching group/window keys and unavailable full-window comparisons')

if __name__ == "__main__":
    main()
