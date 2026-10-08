# 조은 10월 10일 재실행 검증 기록

관련 이슈 [#19](https://github.com/jodkeun-dotcom/KimLeePark/issues/19). 정리일 2026-10-08. 계산은 10월 6일에 실행했고 10월 7일에 독립 대조했다. 10월 8일에는 현재 main과 노션 9일 초안을 확인했다. 이 날짜를 구분해 기록한다.

2026-10-08 확인한 main `fec31702d4a9f6cf979bf3d6aa682a302e0f09e6`와 동일한 코드를 사용해 데이터 정리부터 AI 재학습·지원 검토표까지 재실행했다. 비교한 CSV 42개는 행·열·값·공란이 모두 같았고 회복 그림 3개도 파일이 일치했다. 조은의 재실행 검증은 완료했으며 팀 통합 발표자료와 발표 연습은 남아 있다.

## 완료 범위

| 확인 항목 | 결과 | 근거 |
|---|---|---|
| 카드·기상·공휴일 날짜 결합 | 68,455행 모두 결합, 카드 값과 공란 보존 | reproducibility_1010.json daily_join |
| 공통 예상 매출 | 연령별 198,364행, ALL 4,420행 재현 | daily_predictions.csv, daily_industry.csv |
| 매출·회복 전달표 연결 | 각각 1,728행, 같은 키로 연결 | common_sales, common_recovery, common_full_join |
| 회복 곡선 | 29,952행 및 사건별 그림 3개 재현 | curves 폴더 |
| 기준모델·AI 비교 | AI를 새로 학습했고 기존 성능표와 예측값 재현 | model 폴더 |
| 성능 독립 점검 | 같은 평가 행에서 MAE·RMSE·WAPE를 별도 재계산해 일치 | 검증 10,742행, 이후 기간 31,125행 |
| 지원 검토 | 기본 255행·18개 설정 4,590행 및 감소율 비교 재현 | priority 폴더 |
| SKT 월별 보조 분석 | 월별 표 재현, 한글 글꼴을 지정해 그림 재생성 | monthly_korean 폴더 |
| 자동 테스트 | 로컬 일반 실행 143개 통과 | 팀 내부 main_tests.log |

CSV 42개 대조는 반올림·공란 대체 없이 수행했다. 자료형 추론 차이는 허용했지만 행·열 순서와 값·공란은 정확히 비교했다. 공개 가능한 행수·열수·파일 해시·일치 여부는 [검증 메타정보](reproducibility_1010.json)에 남겼다. 실제 수치가 담긴 원 검증 기록과 결과는 팀 내부에서 보관한다. 테스트 통과는 GitHub 자동 검사 결과를 뜻하지 않는다. 이번 작업에서 python -O 실행과 S0~S4 45개 설정 전체 재실행은 하지 않았다. 45개 설정은 기존 별도 검증 기록을 참조한다.

월별 그림은 초기 실행에서 한글 글꼴이 빠져 기존 --font 옵션으로 다시 만들었다. 계산표 5개의 값은 그대로이며, 공유본에는 monthly_korean 그림을 사용한다. 분석 코드는 바꾸지 않았다.

## 입력과 버전

| 입력 | 확인 내용 |
|---|---|
| 카드 데이터1 | 원본 바이트가 보존된 압축본에서 다시 정제. 데이터2는 보관 확인했지만 이 주 분석에 사용하지 않음 |
| 기상청 ASOS | 춘천 101번 관측소 원본에서 재정제, 기존 weather.csv와 일치 |
| 특일정보 API XML | 2025년 7~12월 응답 6개로 184일 달력 생성, 공휴일 8일. 선하 확인 조회일은 2026-10-05, 정확한 시각은 미확인 |
| SKT | 월별 자료 18개. 12월 시간대·요일 파일은 앞서 중복 제거한 사본 사용 |
| 제공 패키지 | 카드 2개·SKT 18개·레이아웃 2개 등 22개 해시가 기존 목록과 일치 |

12월 flow_time_pop_202512.csv는 92,545행, flow_wkdy_pop_202512.csv는 121,267행을 앞선 정리에서 제거했다. 이번 실행에서 재차 제거했다고 기록하지 않는다. 두 파일의 손대지 않은 원본 위치는 이번에 확인한 경로에서 검증하지 못했으며, 팀 보관 위치를 확인해야 한다. 다른 SKT 16개와 카드 2개는 압축 해제한 내용도 기록된 원본 해시와 일치한다.

실행 환경은 Python 3.12.14, pandas 2.2.3, numpy 2.5.3, scikit-learn 1.9.1, matplotlib 3.11.2다. 스레드 수는 OMP·OPENBLAS·MKL 모두 1로 고정했다. 기본 의존성은 requirements.txt, AI 평가 의존성은 requirements-analysis.txt에 있다. 아래 버전은 실제 검증 환경 기록이며, 새로운 환경을 아래 명령으로 설치해 검증했다는 뜻은 아니다.

## 분석 기준과 해석

요일 평균, 예상의 95% 이상 3일 연속, 명목 관찰 14일, 사건 병합 간격 2일을 유지했다. 공휴일·불완전 날짜는 회복 연속을 끊는다. HEAT03·04·05 실제 관찰은 13·3·14일이다. 회복 첫날과 3일 연속 확인 완료일을 구분하며 지원 비교에는 확인 완료일까지의 일수를 쓴다.

ALL은 날짜별 모든 입력 연령이 완전한지와 분석 창 전체가 완전한지를 따로 본다. 순부족은 초과 매출과 상쇄하고, 양의 일별 부족분 합계는 양수만 합한다. full·eligible·paired 공란은 유지한다. 연령 상세와 ALL을 합산하지 않는다.

이후 기간 예측 비교는 여름 폭염의 반사실 정확성이나 인과적 피해액을 입증하지 않는다. 관찰기간 내 미확인과 자료 부족은 지원 불필요가 아니다. Pareto 후보 수가 적으므로 상태별 검토를 중심으로 제시한다. SKT 32010은 제공기관 확인 전 잠정 범위이며 일별 방문 감소·회복의 직접 근거로 쓰지 않는다.

## 실행 순서

새 체크아웃에서 검증 대상 커밋 fec31702d4a9f6cf979bf3d6aa682a302e0f09e6을 선택하고 저장소 루트에서 실행한다. 팀 내부에는 같은 커밋의 코드 스냅샷도 보관했다. 아래 명령은 실제 실행 기록에서 경로만 상대경로로 바꾼 것이다. 원자료와 정제 데이터는 공개 저장소에 올리지 않는다. 새 작업 폴더 outputs/issue19/input_snapshot에 card_data1.txt.gz, weather_asos.csv, holiday_xml/의 XML 6개, skt_previously_deduplicated/의 SKT 18개를 준비한다. 기존 결과를 덮어쓰지 않는 새 위치를 사용한다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install pandas==2.2.3 numpy==2.5.3 scikit-learn==1.9.1 matplotlib==3.11.2
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export MPLBACKEND=Agg
python -m unittest discover -s tests
```

```bash
python -m scripts.prepare_card --input outputs/issue19/input_snapshot/card_data1.txt.gz --output outputs/issue19/prepared/card
```

```bash
python -m scripts.prepare_weather --input outputs/issue19/input_snapshot/weather_asos.csv --output outputs/issue19/prepared/weather.csv
```

```bash
python -m scripts.prepare_holiday_calendar --input-dir outputs/issue19/input_snapshot/holiday_xml --output outputs/issue19/prepared/calendar --queried-date 2026-10-05
```

```bash
python -m scripts.label_weather_events --input outputs/issue19/prepared/weather.csv --output outputs/issue19/prepared/events --figure outputs/issue19/prepared/weather_events.png --max-gap-days 2 --observation-days 14
```

```bash
python -m scripts.join_data daily --card outputs/issue19/prepared/card/daily.csv --weather outputs/issue19/prepared/weather.csv --calendar outputs/issue19/prepared/calendar/calendar.csv --output outputs/issue19/prepared/daily_joined.csv
```

결합 후 카드 열을 보존하는 확인 단계:

```bash
python - <<'PY'
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal
p=Path('outputs/issue19/prepared')
card=pd.read_csv(p/'card/daily.csv')
joined=pd.read_csv(p/'daily_joined.csv')
projection=joined[['date','region','industry','age','amount','transactions']]
assert_frame_equal(projection, card, check_dtype=False)
projection.to_csv(p/'analysis_card.csv',index=False,encoding='utf-8-sig')
PY
```

```bash
python -m scripts.run_support_review --card outputs/issue19/prepared/analysis_card.csv --events outputs/issue19/prepared/events/weather_events.csv --windows outputs/issue19/prepared/events/weather_event_windows.csv --calendar outputs/issue19/prepared/calendar/calendar.csv --calendar-metadata outputs/issue19/prepared/calendar/calendar_metadata.json --output outputs/issue19/analysis
```

```bash
python -m scripts.review_recovery_rule_stability --priority-sensitivity outputs/issue19/analysis/priority/priority_sensitivity.csv --output outputs/issue19/stability
```

```bash
python -m scripts.plot_final_recovery_curves --curves outputs/issue19/analysis/common_recovery/recovery_curves_common_baseline.csv --metrics outputs/issue19/analysis/common_recovery/recovery_metrics_common_baseline.csv --output outputs/issue19/curves
```

```bash
python -m scripts.compare_methods --source-dir outputs/issue19/analysis/baseline --output outputs/issue19/methods
```

```bash
python -m scripts.compare_ages --source-dir outputs/issue19/analysis/baseline --output outputs/issue19/ages
```

```bash
python -m scripts.prepare_skt --input outputs/issue19/input_snapshot/skt_previously_deduplicated --output outputs/issue19/prepared/skt
```

```bash
python -m scripts.compare_monthly --card outputs/issue19/prepared/card/daily.csv --profiles outputs/issue19/prepared/skt/profiles.csv --coverage outputs/issue19/prepared/skt/grid_coverage.csv --output outputs/issue19/monthly --prefix 32010
```

한글 그림은 compare_monthly에 --font로 설치된 한글 글꼴 파일을 지정하고 출력 위치를 outputs/issue19/monthly_korean으로 바꾼다. 원 실행과 글꼴 보완은 계산 변경이 아니다. 환경·입력·버전이 바뀌면 기존 해시가 아니라 같은 키·값·공란 및 성능 지표를 다시 대조해야 한다.

## 출처와 변수 설명의 연결

- [카드·SKT 변수](variables.md): 카드 데이터1의 개인카드·춘천 필터, 연령 통합, 금액 단위 보존, SKT 월별 독립 집계와 격자 범위.
- [기상 출처·확보 방법·변수](weather.md): 기상청 ASOS 춘천 101번, 2025년 7~12월, 포털 일자료 CSV와 CP949 원본. 기록된 다운로드일은 2026-10-01.
- [공휴일 출처·조회 방법](holiday_calendar.md): 한국천문연구원 특일정보 getRestDeInfo를 2025년 7~12월 월별 조회. 받은 XML을 사용했고 이번 실행에서 API를 재호출하지 않았다. 빈 응답의 월은 자체 XML이 아닌 파일명·전달자 설명에 의존한다.
- [매출·회복 공통 전달 형식](common_baseline_handoff.md), [순부족·상태별 검토](support_review_actions.md), [팀의 6개 분석 기준](team_criteria_review_1005.md).

2026-10-08 공개 문서화 전 분석 스크립트 26개, 대조표 42개의 실제·참조 파일, 회복 그림 3개, 제공 패키지 22개의 해시가 기존 검증 기록과 같은지 다시 확인했다. 현재 main의 분석 코드가 같아 학습·계산을 중복 실행하지 않았다. 문서 추가는 계산 버전 변경이 아니다.

다음 단계는 [제출 목록](submission_checklist_1010.md)과 [예상 질문](presentation_qa_1010.md)을 사용한 공동 검토다. #18의 표현·정책 제안 합의가 남아 있으므로 전체 업무 완료나 최종 정책 승인을 의미하지 않는다.
