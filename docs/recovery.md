# 폭염 이후 매출 회복 곡선·회복 지표 (1차, 잠정)

관련: #8 (1차 산출) → #11 (민감도 검증). 상태: **잠정**. 회복 기준값은 팀 합의 전이며, 예상 매출은 선하 공통 기준모델 초안과 같은 규칙으로 계산했다.
결과는 기준선 대비 차이이며 폭염의 인과적 피해액이 아니다. 회복은 **그날의 매출 수준 회복**이고 앞서 생긴 누적 부족이 만회되었다는 뜻이 아니다.

## 실행

```bash
# 1) 카드 일별 집계 (대회 제공 데이터1을 로컬에 준비, README의 데이터 준비 참고)
python scripts/prepare_card.py --input data/shinhan/shinhan_card_data1.txt --output data/processed/card
# 2) 기상 사건 (README의 기상자료 명령)
python scripts/label_weather_events.py
# 3) 회복 곡선·지표
python scripts/compute_recovery.py
```

카드 원본·집계와 회복 결과는 모두 로컬에만 두며 `.gitignore`로 제외된다.

## 계산 방법

| 단계 | 내용 |
|---|---|
| 대상 사건 | `weather_events.csv`의 폭염 사건 중 베이스라인이 분석 기간 안에 있는 것 (현재 HEAT03~05). 모두 `case_study`이므로 결과는 탐색용이다 (docs/weather.md) |
| 대상 집단 | 업종 × 고객 연령(10대~60대 이상) 491개 + 업종 전체(`age=ALL`) 85개. `scope`: 선하 기준모델의 주 분석 후보 18개 업종 = `primary`, 나머지 `auxiliary` |
| 예상 매출 | 사건 시작일에 고정. 시작일 전 날짜 중 사건 기간(유형 무관)·잠정 공휴일(8/15)을 뺀 날의 **같은 요일 평균**. 학습 최소 7일·같은 요일 2회 미만이면 예측하지 않음 |
| 실제/예상 비율 | `ratio = amount / expected`. 행이 없는 날짜는 0이 아니라 미관측(NaN) |
| 감소 여부 | 사건 기간 전체의 `event_ratio = Σ실제 / Σ예상`이 회복 기준 이상이면 `no_decline` (회복 대상 아님) |
| 회복일 | 관찰기간(사건 종료 다음 날 = +1)에서 `ratio ≥ RECOVERY_THRESHOLD`가 `CONSECUTIVE_DAYS`일 연속인 첫날. 미관측·예측 불가 날짜는 연속을 끊음 |
| 관찰기간 | `effective`: 다른 사건 전날까지로 절단한 기간 (주 결과). `nominal`: 원래 14일 (다른 사건이 섞임, 민감도 비교용) |

### 잠정 기준값 (팀 합의 필요)

`scripts/compute_recovery.py` 상단 상수로 바꿀 수 있다.

| 상수 | 값 | 의미 |
|---|---|---|
| `RECOVERY_THRESHOLD` | 0.95 | 실제/예상 매출 비율이 95% 이상이면 평상시 수준 |
| `CONSECUTIVE_DAYS` | 3 | 위 기준을 3일 연속 충족해야 회복 (일별 변동으로 하루만 넘는 경우 제외) |
| `MIN_TRAIN_DAYS`, `MIN_WEEKDAY_OBS` | 7, 2 | 선하 기준모델 초안과 동일 |
| `HOLIDAYS` | 2025-08-15 | 잠정. `calendar.csv`(#27) 수신 후 교체 |

## recovery_status

| 값 | 뜻 | recovery_days |
|---|---|---|
| `recovered` | 관찰기간 안에서 회복 기준 충족 | 회복 첫날의 관찰 일수 (+1 = 사건 종료 다음 날) |
| `censored` | 감소했으나 관찰기간이 끝날 때까지 회복을 확인하지 못함. 관찰 종료·절단 때문일 수 있으며 **실제 회복 지연과 구분해야 함** | 빈칸 (임의로 채우지 않음) |
| `no_decline` | 사건 기간에 기준 이하로 떨어지지 않음 | 빈칸 |
| `insufficient_data` | 사건 기간 예측·관측이 빠지거나 관찰기간 유효 관측이 연속 기준보다 적음 | 빈칸 |

## 출력 (로컬)

| 파일 | 내용 |
|---|---|
| `data/processed/recovery/recovery_metrics.csv` | 사건 × 업종 × 연령(+ALL) × `window_type`별 회복 지표 (주 결과·민감도 비교용) |
| `data/processed/recovery/recovery_handoff.csv` | **지원 우선순위 결합용 전달본.** `window_type = effective`만, 공통 키 + `recovery_days`, `recovery_status`, `recovery_uncertainty_note` |
| `data/processed/recovery/recovery_curves.csv` | 사건 기간 + 명목 관찰 14일의 날짜별 실제·예상·비율 (`is_effective`로 절단 구분) |
| `outputs/recovery/recovery_curves_HEAT0X.png` | 주 분석 18개 업종의 업종 전체 회복 곡선 |

### 전달본과 비교용 파일

`recovery_metrics.csv`는 `effective`와 `nominal`을 함께 담는다. 두 창의 끝이 같은 사건(다음 사건이 없는 HEAT05)은 공통 키 `event_id + region + industry + age + window_start + window_end`가 두 번 나오므로, 이 파일을 그대로 `scripts/prepare_priority.py`에 넣으면 `recovery: missing/duplicate keys`로 중단된다. 결합에는 `recovery_handoff.csv`를 쓴다.

```bash
python scripts/prepare_priority.py --sales <선하 사건별 매출 지표 CSV> --recovery data/processed/recovery/recovery_handoff.csv --output outputs/priority
```

전달본은 `effective`(주 결과)를 명시적으로 선택해 만든다. 창 구분 없이 중복을 지우면 주 결과와 민감도 결과가 섞이므로 그렇게 하지 않는다. 키 중복·공란이 있으면 `compute_recovery.py`가 오류로 멈춘다. `nominal` 결과가 필요하면 `recovery_metrics.csv`에서 `window_type`으로 골라 별도로 비교한다.

`recovery_metrics.csv` 주요 열:

| 열 | 내용 |
|---|---|
| event_id, region, industry, age | 결합 키. 업종 전체는 `age=ALL` (전체와 연령별을 같은 순위에 섞지 않음) |
| window_type, window_start, window_end | `effective`/`nominal`, 사건 시작일, 관찰 끝 날짜. 조은 handoff 형식의 `window_start + window_end` 키와 맞춤 |
| event_end, analysis_role, scope | 사건 종료일, 기상 사건 분류, 주 분석/보조 |
| train_days | 기준선 학습 관측일 수 |
| event_days, event_days_paired, event_ratio | 사건 일수, 실제·예상이 모두 있는 일수, 사건 기간 실제/예상 비율 |
| observation_days, observation_days_paired | 관찰기간 일수, 비율 계산 가능한 일수 |
| recovery_status, recovery_days, recovery_date | 위 표 참고 |
| recovery_threshold, consecutive_days | 사용한 기준값 |
| recovery_uncertainty_note | 사건 분류·절단·미관측·예측 불가·짧은 학습기간 등 |

## 해석 한계

- 현재 폭염 사건은 모두 `case_study`다(베이스라인 겹침·관찰기간 절단, docs/weather.md). 사건 수가 3건이라 신뢰구간을 제시하지 않는다.
- 7월(HEAT03)의 기준선은 7/1~7/22 중 장마철 비사건일로 학습되어 평상시 매출을 낮게 잡았을 수 있다. 80mm 미만 강우일은 사건이 아니라 학습에 포함된다.
- 이전 사건 이후 회복 중인 날짜도 학습에 포함된다(선하 초안과 동일).
- 예상 매출은 이 스크립트의 `expected_sales`로 자체 계산한다. 공동 분석 전에는 선하 PR #29의 `daily_predictions.csv`에서 모델·창·결측 처리 가정을 명시적으로 골라 연동하거나, 같은 값인지 검증해야 한다.
- 카드 자료는 소액·소건수 행이 없는 경우가 있어, 업종 전체(`ALL`)는 그날 관측된 연령 행의 합이다.
- HEAT04의 `effective` 관찰기간은 3일이라 대부분 `censored` 또는 판단 보류가 된다. `nominal` 결과는 다음 폭염(HEAT05)이 섞인 값이다.
- 관찰기간·기준값에 따른 변화는 #11에서 민감도 표로 정리한다.
