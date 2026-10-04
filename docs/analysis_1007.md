# 10월 7일 조은 작업: 이후 기간 예측 비교와 지원 우선순위

관련: #13. 기준 main: `5b090d4`. 코드 실행 결과는 로컬 보관하며, 공개 PR에는 코드·방법·가상자료 테스트만 포함한다.

## 진행 범위

- 선하의 기준모델 함수를 재사용해 AI 1종과 날짜 순서에 따른 성능을 비교한다.
- 학습 정보 누출, 같은 평가 대상, 예측 불가 행과 관측 누락을 검사한다.
- 연령별 매출·회복 전달 형식을 연결하고, 업종 전체의 합산 기준 차이를 검사한다.
- 동일 연령 그룹의 실제·예상 매출로 회복을 다시 계산하고 잠정 지원 우선순위를 만든다.
- 모델 평균/중앙값 × 회복 기준 0.90/0.95/1.00 × 연속 2/3/4일의 18개 설정을 비교한다.

사용자가 우선순위 기준 선정을 위임하여 아래 규칙을 선택했다. 세 사람의 공동 검토가 완료됐다는 의미는 아니며 #13을 자동으로 닫지 않는다. 선하 #12·세은 #11의 후속 검증과 교차 검토가 남아 있다.

## 예측 비교 조건

| 용도 | 학습 상한 | 평가 기간 |
|---|---|---|
| 검증 | 2025-08-31 (7월부터) | 2025-09-01~09-30 |
| 고정 설정의 이후 기간 평가 | 2025-09-30 (7월부터) | 2025-10-01~12-31 |

`prepare_sales_baseline.training_sample`과 `predict`를 재사용한다. 기본 비교 대상은 사건·잠정 공휴일을 제외한 같은 과거 관측값으로 학습한 요일 평균이며, 최소 전체 7일·같은 요일 2회 조건도 유지한다. AI는 `prepare_model_comparison.make_ai_model`의 고정 HistGradientBoostingRegressor다. 두 모델이 같은 학습 행을 사용하며 평가 기간 중 재학습하지 않는다.

입력은 업종·연령·요일·주말·월·경과일이다. 당일 실제 매출·결제건수·관측 기상·월 전체 SKT는 입력하지 않는다. 범주 인코더는 학습 자료에서만 적합한다. 미래 사건은 학습 제외일 선정에 사용하지 않는다. 음수 예측은 두 모델 모두 0으로 제한한다.

전체 설정과 입력·소스 해시를 첫 학습 전에 `protocol.json`에 기록한다. 이번 실행에서 초매개변수 탐색을 하지 않으며 보류 기간 점수를 보고 설정을 바꾸지 않는다. 추가 실험은 기존 점수를 반복해 확인한 탐색임을 표시해야 하며, 이미 확인한 10~12월을 새로운 미사용 평가자료로 부르면 안 된다.

평가 대상은 원자료에서 관측된 날짜×지역×업종×연령 행이다. 기준모델의 학습 건수·달력 조건으로 비교 가능 여부를 먼저 정한다. 두 모델의 점수는 같은 키에서 계산하고, 학습 부족·새 집단으로 제외된 행 수와 금액을 `coverage.csv`에 함께 남긴다. 미관측 날짜를 0으로 채우지 않는다. MAE/RMSE는 제공 금액 단위이고 WAPE는 절대오차 합/실제금액 합이다. WAPE를 정확도라고 표현하지 않는다.

전체 달력 #27이 없어 기존 기준모델의 8/15만 제외하는 잠정 설정을 그대로 사용한다. 가을·겨울 공휴일을 정상적으로 통제한 분석은 아니다. 이후 기간 성능은 여름 폭염의 인과적 피해·회복 지표 타당성을 입증하지 않는다.

## 공통 매출과 회복 연결

`prepare_support_inputs`는 연령별 결과를 같은 사건·관찰기간 키로 1:1 연결한다. 불완전한 기간의 paired 부족액은 진단 열에 남기고, 전체 기간 부족액을 대신하지 않는다. 업종 전체의 기존 #30 `age=ALL`과 #29의 paired 집계 차이는 별도 파일로 드러낸다.

`rank_support`는 선하의 업종별 집계 함수를 재사용한다. 같은 날짜에 실제·예상이 모두 있는 같은 연령 그룹만 양쪽에 합산한다. 모든 입력 연령 그룹이 사용된 날짜에서만 회복 비율을 계산한다. 빠진 날짜·집단을 실제 0으로 바꾸지 않는다. 기존 세은 코드를 덮어쓰지 않고 `recovery_day`의 연속 기준을 재사용한다.

사건 기간 자료가 불완전하면 감소율·회복을 확정하지 않는다. 회복은 첫 기준 충족일과 연속 충족을 확인한 날을 구분한다. 예를 들어 +3일부터 3일 연속이면 회복 첫날은 +3일, 확인 시점은 +5일이다. 미회복·관찰 부족에는 임의의 일수를 채우지 않는다.

## 선택한 지원 우선순위 규칙

1. **같은 사건 안에서 비교**한다. 주 분석 18개 업종과 나머지 보조 업종을 분리하고, 서로 다른 사건의 부족액·순위를 합산하지 않는다.
2. **자료 조건부터 확인**한다. 사건~유효 관찰기간의 비공휴일 모두에서 전체 입력 연령 그룹의 실제·예상 매출이 짝지어져야 한다. 공휴일 제외 기간 지표이며 전체 기간 손실액이 아니다.
3. **남아 있는 양의 순부족**을 지원 검토 조건으로 둔다. 초과 매출로 상쇄된 경우는 별도 표시에 남긴다. 양의 일별 부족분 합계도 보조 열로 보존한다.
4. 감소가 회복 기준을 넘고 회복을 확인한 대상에서 **감소율·예상 매출 대비 순부족률·회복 확인 지연**을 비교한다. 세 지표가 모두 같거나 나쁘고 하나 이상 더 나쁜 업종이 있으면 그 업종을 앞 등급에 둔다. 이를 반복하는 Pareto 등급이며 임의의 가중치가 없다. 같은 등급을 억지로 1~N위로 나누지 않는다.
5. **회복 미확인·관찰 부족·매출 자료 부족은 별도 확인 대상**이다. 순위 공란을 낮은 지원 필요성이나 0점으로 읽으면 안 된다. 관찰 종료로 인한 미확인과 실제 회복 지연을 섞지 않는다.
6. 동일한 순위 가능 대상에서 감소율만의 순위(동률 최소 순위)를 계산한다. Pareto 등급과 순위 번호를 직접 빼지 않고 실제 순서가 뒤집힌 업종 쌍만 기록한다. 후보가 하나뿐이면 차별성 검증이 불가능하다고 명시한다.
7. 18개 설정의 분류·등급을 비교한다. 순위 가능 횟수와 전체 설정 중 첫 등급 횟수를 함께 표시한다. 설정 빈도는 확률·통계적 신뢰도가 아니며, 후보 집합이 달라질 수 있음을 함께 읽는다.

공동 검토 전 잠정 분석이다. 엄격한 자료 조건으로 순위를 매길 대상이 적으면 기준을 사후에 낮춰 결과를 만들지 않는다. 자료 부족 대상은 추가 확인으로 전달한다.

## 재현

저장소 루트에서 `python -m pip install -r requirements-analysis.txt` 후 실행한다. 제공 카드자료는 로컬에 준비한다.

```bash
python scripts/label_weather_events.py
python -m scripts.prepare_sales_baseline --daily data/processed/card/daily.csv --events data/processed/weather_events/weather_events.csv --event-windows data/processed/weather_events/weather_event_windows.csv --output outputs/sunha_baseline
python scripts/compute_recovery.py

python -m scripts.evaluate_models --card data/processed/card/daily.csv --events data/processed/weather_events/weather_events.csv --windows data/processed/weather_events/weather_event_windows.csv --output outputs/joeun_1007/model_v1

python -m scripts.prepare_support_inputs --sales outputs/sunha_baseline/event_shortfall.json --recovery data/processed/recovery/recovery_handoff.csv --industry outputs/sunha_baseline/daily_industry.csv --curves data/processed/recovery/recovery_curves.csv --output outputs/joeun_1007/integration

python -m scripts.rank_support --daily outputs/sunha_baseline/daily_predictions.csv --events data/processed/weather_events/weather_events.csv --output outputs/joeun_1007/priority_v1
python -m unittest discover -s tests -v
```

모델·우선순위 실행은 기존 결과가 있는 폴더를 거부한다. 기존 평가를 보존하고 새 실험 폴더를 명시한다. 모델 비교에 달력을 제공할 경우 전체 184일 자료를 준비하고 선하의 기준모델에도 같은 달력을 전달해야 한다.

산출물은 `performance.csv`, `coverage.csv`, `split_audit.csv`, 예측 상세, `support_inputs_age_PROVISIONAL.csv`, `industry_aggregation_check.csv`, `support_priority_PROVISIONAL.csv`, `priority_sensitivity.csv`, `rank_reversals.csv`, 설정 JSON과 그림이다. 모두 `.gitignore`가 적용되는 `outputs/`에 두며 수치 CSV·그림·입력은 공개 저장소에 커밋하지 않는다.
