# 선하 공통 기준선·일별 예상 매출 검토 초안

> 최신 상태(2026-10-06): #31의 6개 분석 기준 최종 합의와 #32 공통 연결, 전체 달력 검증이 완료됐습니다. 선하 #12의 최종 결과·검증 범위·재실행 방법은 [최종 검증 정리](issue12_final_validation.md)를 확인하세요. 아래 본문은 #29 당시의 재현 방법과 검토 이력이며 ‘달력/회복 규칙/연결 합의 대기’는 당시 상태입니다. 현재 주 결과는 전체 달력을 명시적으로 전달하고 fixed_pre_event·요일 평균·결측 제외·effective·95%/3일을 사용합니다. 사후 기준선과 공휴일 건너뜀은 비교 옵션이며 고정 연령 구성은 후속 과제입니다.

관련 #9, #8, #10, #12. Draft: 기준선 대비 차이와 회복 분석용 입력을 준비합니다.
폭염의 인과적 피해액, 회복 소요일, 지원 순위를 확정하는 코드가 아닙니다.

## 입력과 실행

Python 3, pandas, numpy가 필요합니다. 저장소 루트에서 실행합니다.

```text
python scripts/label_weather_events.py
python scripts/prepare_sales_baseline.py --daily data/processed/card/daily.csv --events data/processed/weather_events/weather_events.csv --event-windows data/processed/weather_events/weather_event_windows.csv --output outputs/sunha_baseline
# 전체 날짜를 포함한 달력이 준비되면 추가:
# --calendar data/processed/calendar.csv
# 사건 전후 4주 사후 기준선을 비교할 때만 추가:
# --retrospective
python -m unittest discover -s tests -p test_sales_baseline.py -v
python -O -m unittest discover -s tests -p test_sales_baseline.py -v
```

- daily.csv: date, region, industry, age, amount. 날짜×지역×업종×고객 연령별 1행.
- weather_events.csv / weather_event_windows.csv: PR #24의 실제 산출물. 사건 날짜를 코드 상수에 복사하지 않습니다.
- calendar.csv: 분석기간 전체 date, is_holiday(0/1 또는 true/false). 날짜 누락·중복은 오류입니다.
- 달력을 생략하면 기존 #26의 2025-08-15만 제외하는 잠정 처리입니다. run_metadata.json과 보고서에 이를 기록합니다. 전체 달력 확인 완료를 뜻하지 않습니다.
- 금액은 제공 자료 단위를 그대로 사용합니다. 데이터2와 합산하지 않습니다.
- 날짜 결측, 중복 키, 비유한/음수 금액은 ValueError로 중단합니다. python -O에서도 검사가 유지됩니다.
- 주 분석 후보 업종명이 실제 입력에 모두 있는지 확인해 오타를 막습니다. 전체 85개 업종 유지와 후보 분류는 효과 판정이 아닙니다. 그룹 수·산출 행 수는 입력으로 계산합니다.

## 사건·관찰기간

기본 창은 event와 observation 중 is_effective=True인 날짜입니다. observation은 다음 사건 시작 전날까지 절단됩니다. CSV의 analysis_role을 출력에 보존하고 excluded 사건은 계산하지 않습니다. case_study를 자동으로 statistical로 바꾸지 않습니다.

2026-10-04 PR #24가 병합된 main(bf40bcb7)의 기상 계산 코드 기준입니다. 이전 독립 재생성에 사용한 dd31a176과 기상 계산 스크립트의 blob SHA가 같음을 확인했습니다. HEAT03은 8/17, HEAT04는 8/28, HEAT05는 9/12까지입니다. 세 사건 모두 현재 MIN_DAYS=7 기준 case_study이고 정식 통계비교 대상은 0건입니다. 기준 완화 여부는 팀 합의 사항입니다.

절단 전 명목 창이 더 길면 nominal_overlap_sensitivity로 따로 출력합니다. 이 창에는 다음 사건이 섞일 수 있으며 회복 주 결과나 서로 합산할 부족액으로 쓰지 않습니다. CSV 사이의 사건 날짜 일치·중복·관찰기간 연속성을 검사합니다. 강한 폭염의 관찰 시작은 부모 사건 종료 뒤라는 #24 규칙을 유지합니다.

## 학습과 검증

기본 fixed_pre_event는 사건 시작일 이전의 비사건·비공휴일 자료만 사용합니다. 사건 후 재학습하지 않습니다. 같은 그룹의 요일 평균과 중앙값을 함께 출력하며 전체 관측 7일·동일 요일 2회는 탐색용 잠정 조건입니다.

사전 고정 검증은 유효 창과 같은 길이를 사건 직전에 배치합니다. 그 검증 시작 이전 자료만 학습하고 남은 비사건·비공휴일 관측을 평가합니다. fixed_validation.csv에 후보 날짜·평가 날짜·행 수와 두 WAPE를 함께 기록합니다. 사전자료가 부족하거나 일부 날짜만 평가되므로 평균/중앙값을 자동 선택·승인하지 않습니다. 학습일에는 이전 사건의 회복 영향이 남을 수 있습니다.

--retrospective를 선택하면 사건 시작 전 28일부터 해당 창 종료 후 28일까지의 비사건·비공휴일 자료로 사후 기준선도 계산합니다. 모든 사건과 유효 회복기간을 마스킹합니다. baseline_mode=retrospective_4week_sensitivity로 명시하며 기본값과 섞지 않습니다. 미래 실제 매출을 사용하므로 사전 예측이나 AI의 이후 기간 성능 평가에 사용할 수 없습니다. 사건 사이 간격이 짧아 학습 부족이 계속될 수 있고 계절 변화도 섞일 수 있습니다.

## 빈 행과 공휴일: 각각 따로 표시

원자료 레이아웃을 읽었지만, 거기에 업종×연령×일자의 행 부재가 0매출인지 비공개/마스킹인지 확정하는 규정은 확인되지 않았습니다. 필드 NULL=N은 행 부재의 의미를 설명하지 않습니다. 제공기관 확인 전 기본값은 exclude_missing입니다.

모든 그룹을 입력 시작~종료일의 전체 날짜에 펼칩니다. zero_fill_sensitivity는 학습과 대상 양쪽의 빈 행을 0으로 가정한 별도 대안입니다. 원자료를 수정하지 않고 실제로 0이 관측된 행과 구분합니다. missing_policy_sensitivity.csv에는 각 방식의 합계·커버리지와 차이를 함께 남깁니다. 계산 가능한 날짜가 달라질 수 있으므로 같은 표본에서의 인과효과로 해석하지 않습니다. 기본 학습을 유지한 채 대상만 0으로 채운 결과가 아닙니다.

공휴일은 두 방법 모두 예측하지 않습니다. 그래서 8/15가 들어가는 HEAT03은 구조적으로 달력기간 전체 complete_window=False입니다. 사전자료 부족만이 원인이라고 설명하지 않습니다.

- window_days / coverage / complete_window: 공휴일 포함 전체 달력기간.
- eligible_window_days / eligible_coverage / complete_eligible_window: 공휴일을 뺀 기간.
- holiday_excluded_days, insufficient_training_days, missing_actual_days: 각각 공휴일 제외·학습 부족·빈 실제 행 수. 서로 겹칠 수 있어 단순 합산하지 않습니다.
- *_full은 달력기간 전체가 완전할 때만 값이 있습니다. 비공휴일 전체 완성 값은 *_eligible이며 전체 기간 손실과 다릅니다.
- *_paired는 실제·예상이 둘 다 있는 날짜의 소계입니다. 불완전 창을 전체 결과로 사용하지 않습니다.

## 세은에게 전달할 일별 예상 매출

daily_predictions.csv를 로컬로 출력합니다. 같은 날짜라도 사건별 고정 모델과 창이 다르므로 단순 날짜 키만으로 중복 제거하거나 평균내지 않습니다.

고유 키: event_id + window_type + baseline_mode + missing_policy + model_id + date + region + industry + age.

| 열 | 의미 |
|---|---|
| date, region, industry, age | 날짜·지역·원본 업종·고객 연령 |
| amount, prediction | 실제 매출(정책에 따라 가정 0 포함)·예상 매출, 같은 제공 단위 |
| actual_status | observed / missing_row_unknown. 0가정에서도 원래 빈 행 표시는 보존 |
| prediction_status | predicted / holiday_excluded / insufficient_training |
| train_start, train_end, train_days, weekday_train_days | 그룹의 실제 학습 범위·학습 관측 수·같은 요일 관측 수 |
| model_origin, model_id, baseline_mode | 고정 시점·평균/중앙값·사전/사후 기준 구분 |
| event_id, window_start, window_end, window_type, phase | 사건·관찰기간·주 창/중첩 비교 창·event/observation |
| analysis_role, missing_policy, is_holiday | #24의 사례분류·빈 행 처리 가정·공휴일 여부 |

예상 불가·실제 미관측·학습일 없음은 빈 CSV 셀로 저장합니다. 0은 관측 0 또는 zero_fill_sensitivity 가정일 때만 쓰며 actual_status와 missing_policy로 구분합니다.

회복 계산은 기본적으로 effective + fixed_pre_event + exclude_missing을 선택하고 model_id를 명시해야 합니다. 공휴일과 실제/예상 결측을 어떻게 회복 판단에서 다룰지는 세은과 공동 합의 전입니다. 서로 다른 사건·관찰기간을 섞지 않습니다.

### 업종 전체 회복 곡선용 daily_industry.csv

세은의 임시 기본 선택인 effective + fixed_pre_event + exclude_missing + weekday_mean만 별도로 집계합니다. 원래 연령별 CSV는 그대로 유지합니다. 사건·창·모델을 섞지 않고 날짜×지역×업종별로 실제·예상이 모두 있는 동일한 고객 연령 그룹만 양쪽에서 함께 합산합니다.

- amount_paired / prediction_paired: 같은 paired 연령 그룹의 실제/예상 합계. 사용 가능한 그룹이 0이면 두 값 모두 빈칸이고 0으로 채우지 않습니다.
- paired_groups / total_groups: 합계에 쓴 그룹 수 / 해당 업종의 전체 입력 연령 그룹 수. 그룹 수는 고객 수가 아닙니다.
- observed_groups / predicted_groups: 실제/예상이 각각 있는 그룹 수. 합계의 표본은 paired_groups입니다.
- group_coverage / complete_group_coverage: 연령 그룹 커버리지와 전체 그룹 사용 여부. partial 합계는 전체 업종의 완전한 매출이 아닙니다.
- aggregation_status: complete / partial / no_paired_groups. age=ALL은 이 집계 표의 표기입니다. 연령 상세와 합산하면 중복됩니다.

고유 키는 event_id + window_start + window_end + window_type + baseline_mode + missing_policy + model_id + date + region + industry입니다. 날짜마다 paired 그룹 구성이 달라질 수 있으므로 회복 곡선에서 구성 변화와 group_coverage도 함께 확인합니다. 이 출력 추가가 회복 기준의 공동 합의를 뜻하지는 않습니다.

## 출력과 해석

- event_shortfall.json: 사건×그룹×모델×창×가정별 요약.
- daily_predictions.csv: 회복 곡선·일수 계산에 연결할 일별 예상값.
- daily_industry.csv: 기본 필터의 동일 paired 연령 그룹만 합산한 업종별 일별 표와 그룹 커버리지.
- fixed_validation.csv: 제한된 사전 검증의 오차와 평가 가능한 범위.
- method_sensitivity.csv: 평균/중앙값 비교와 비공휴일 순부족률 차이.
- retrospective_sensitivity.csv: 선택형 사후 기준선을 켠 경우에만 사전/사후 기준의 차이와 각각의 계산 가능 범위.
- missing_policy_sensitivity.csv: 빈 행 제외/0가정 비교와 각 커버리지.
- baseline_report.md / run_metadata.json: 동적으로 계산한 현황·출처·한계.

같은 출력 폴더에 사후 비교를 켠 뒤 꺼서 재실행하면, 이 스크립트가 관리하는 retrospective_sensitivity.csv만 삭제합니다. 다른 사용자 파일은 보존합니다. 메타정보에 retrospective_enabled와 현재 실행의 output_files를 기록해 과거 파일과 혼동하지 않도록 합니다.

부족분 합계는 max(예상−실제,0)의 합이고 순누적 부족은 초과 매출까지 차감한 합입니다. 음수를 허용합니다. 고객 연령 비교이며 사업주 연령·1인당 소비나 춘천 전체 손실액으로 확대하지 않습니다. 보고서는 들여쓰기 없는 Markdown이며 입력 규모나 특정 모델 선택을 고정 결론으로 쓰지 않습니다.

## 리뷰 대응·검증과 남은 일

세은 리뷰 #29의 코드·문서 5~9번을 반영했습니다. 방법 1~4번은 빈 행 처리 비교, 공휴일 원인·커버리지 분리, 선택형 사후 민감도, #24 외부 산출물과 절단 창 연결로 대응했습니다. 기본 모델을 사후 모델로 교체하거나 결측을 실제 0으로 확정하지 않습니다.

가상자료 검사는 고정 모델의 미래 매출 무사용, 부분 창 full=null, paired≤window, 공휴일 분모 구분, 결측 정책 출처, 외부 창 호환성, 입력 검증, 사후 마스킹, 동적 보고서·CSV 재읽기를 확인합니다. 로컬 실자료 실행과 출력 키·범위·결측 불변조건을 추가 점검합니다. 코드 통과가 모델 타당성 승인인 것은 아닙니다.

2026-10-04 수정본 검증: 가상자료 unittest 12개가 일반 실행과 python -O에서 모두 통과했습니다. PR #24 산출물을 재생성해 실제 카드자료로 기본·0가정·선택형 사후 민감도를 실행했습니다. 일별 키 중복 없음, 사전 모델 학습 종료일<고정일, 공휴일 예측 결측, 빈 행 정책 표시, 사례분류와 HEAT03 절단일을 확인했습니다. 이전 결과와 기간·가정이 동일한 네 창은 기존 계산값과 일치했습니다. 변경된 HEAT03 유효 창은 이전 8/18 창과 별도 결과입니다.

.gitignore는 병합된 main 것을 그대로 유지하며 이 PR의 별도 변경에서 제외합니다. README/manifest와 공개 기상 2개 파일 예외, 데이터 확장자·outputs 제외 규칙을 보존합니다. 원본·정제 데이터와 수치 결과는 커밋하지 않습니다. 실제 분석 결과는 허용된 팀 경로로 공유하고 PR에는 코드·문서·가상자료 테스트만 올립니다.

추가 재리뷰 대응: 옵션 켜기→끄기 실행의 이전 파일 제거·사용자 파일 보존·메타정보 일치, 업종 집계의 비대칭 결측·관측 0·paired 0건·기본 필터 분리 검사를 추가했습니다. 총 15개 검사가 일반 실행과 python -O에서 통과합니다. 이전 사건의 유효 회복일을 사전 학습에서 제외하는 별도 변형은 선택 제안이며 아직 추가하지 않았습니다. 현재 기준과의 차이 및 학습 부족 처리를 팀과 먼저 합의할 사항으로 남깁니다.

남은 일: 빈 행 의미에 대한 제공기관 확인, 전체 공휴일 달력, 학습일·중첩 창·모델·회복 기준 공동 합의, 세은의 회복 코드에서 CSV 수신·재실행, 조은의 동일 평가조건·결합 형식 연결. #9는 완료로 닫지 않습니다. 기존 노션 결과표는 이전 계산 버전이며 이번 수정 후 산출물로 검토·교체하기 전 최신 결과로 쓰지 않습니다.
