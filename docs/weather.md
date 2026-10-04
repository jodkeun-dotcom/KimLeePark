# 기상자료 변수 설명

춘천 ASOS(종관기상관측) 일자료. 카드 일별 자료와 `date + region`으로 결합하기 위한 정제 결과를 설명한다.

## 출처와 원본

| 항목 | 내용 |
|---|---|
| 출처 | 기상청 기상자료개방포털 > 지상 > 종관기상관측(ASOS) > 일자료 |
| 원본 파일 | `data/raw/wether/OBS_ASOS_DD_20261001161226.csv` (2026-10-01 다운로드) |
| 관측소 | 101 춘천 (1개 관측소만 사용) |
| 기간 | 2025-07-01 ~ 2025-12-31, 184일 (날짜 누락·중복 없음) |
| 인코딩 | **CP949**, 한글 열 이름. pandas 기본값(UTF-8)으로는 읽히지 않음 → `encoding='cp949'` |

원본은 변경하지 않는다. 폴더명 `wether`는 현재 경로 그대로 둔다.

## 원본 데이터 받는 방법

기상청 공개자료라 원본과 정제본을 저장소에 포함한다. 카드·SKT 등 대회 제공 자료는 계속 저장소에서 제외한다(`.gitignore`는 아래 두 파일만 예외로 둔다).

| 파일 | 내용 |
|---|---|
| `data/raw/wether/OBS_ASOS_DD_20261001161226.csv` | 포털에서 받은 원본 (CP949) |
| `data/processed/weather.csv` | `prepare_weather.py` 출력 (원본에서 바이트 단위로 동일하게 재생성됨) |

**1) 저장소 파일 사용 (기본):** `git clone` 또는 `git pull` 후 바로 [실행](#실행)의 명령을 돌리면 된다.

**2) 포털에서 직접 받기 (재검증·기간 변경 시):**

1. [기상자료개방포털](https://data.kma.go.kr) 접속 (다운로드 시 로그인 필요할 수 있음)
2. **지상 → 종관기상관측(ASOS) → 일자료**
3. 지점: **춘천(101)**, 기간: **2025-07-01 ~ 2025-12-31**
4. 자료 항목: **전체 선택**
5. 조회 후 **CSV 다운로드**
6. 받은 파일을 `data/raw/wether/`에 저장. 파일명(`OBS_ASOS_DD_<다운로드시각>.csv`)이 다르면 아래 명령의 `--input`을 실제 파일명으로 바꾼다.

열 구성이 달라지면(항목 일부만 선택 등) `prepare_weather.py`가 `Unexpected ASOS columns` 오류로 중단한다.

## 실행

저장소 루트에서 순서대로 실행한다. README의 명령과 같다.

```bash
python scripts/prepare_weather.py --input data/raw/wether/OBS_ASOS_DD_20261001161226.csv --output data/processed/weather.csv
python scripts/label_weather_events.py   # 입력 data/processed/weather.csv → data/processed/weather_events/, outputs/
```

출력은 쉼표 구분 UTF-8 BOM CSV. 확인용 노트북: [notebook/data_read.ipynb](../notebook/data_read.ipynb)

처리 내용:

- 한글 열 이름 → 영문 snake_case (아래 표). 예상 열과 다르면 오류로 중단.
- `region` 추가: 관측소 101 → `강원 춘천시` (카드 자료 region 값과 동일).
- `date`를 YYYY-MM-DD로 통일, 분석 기간 전체 날짜가 정확히 한 번씩 있는지 검사.
- 결측(빈칸)은 **0으로 채우지 않는다.**

## 변수

키: `date + region` (하루 한 행).

| 변수 | 원본 열 | 단위 / 비고 |
|---|---|---|
| date | 일시 | YYYY-MM-DD |
| region | (추가) | 강원 춘천시 |
| station_id / station_name | 지점 / 지점명 | 101 / 춘천 |
| temp_avg_c | 평균기온 | °C |
| temp_min_c / temp_min_time | 최저기온 / 시각 | °C / hhmi |
| temp_max_c / temp_max_time | 최고기온 / 시각 | °C / hhmi |
| precip_mm | 일강수량 | mm. 빈칸 108일 |
| precip_duration_hr | 강수 계속시간 | hr. 값 1일뿐이라 사용 비권장 |
| precip_max_10min_mm / _time | 10분 최다 강수량 / 시각 | mm / hhmi |
| precip_max_1h_mm / _time | 1시간 최다강수량 / 시각 | mm / hhmi |
| wind_avg_ms | 평균 풍속 | m/s |
| wind_max_ms / wind_max_dir_deg / wind_max_time | 최대 풍속 / 풍향 / 시각 | m/s / 도(16방위) / hhmi |
| wind_gust_max_ms / wind_gust_dir_deg / wind_gust_time | 최대 순간 풍속 / 풍향 / 시각 | m/s / 도(16방위) / hhmi |
| wind_dir_mode_deg | 최다풍향 | 도(16방위) |
| wind_run_100m | 풍정합 | 100m |
| dew_point_avg_c | 평균 이슬점온도 | °C |
| humidity_avg_pct | 평균 상대습도 | % |
| humidity_min_pct / humidity_min_time | 최소 상대습도 / 시각 | % / hhmi |
| vapor_pressure_avg_hpa | 평균 증기압 | hPa |
| cloud_total_avg / cloud_low_mid_avg | 평균 전운량 / 중하층운량 | 1/10 (0~10) |
| new_snow_max_cm / _time | 일 최심신적설 / 시각 | cm. 전 기간 빈칸 |
| snow_depth_max_cm / _time | 일 최심적설 / 시각 | cm. 전 기간 빈칸 |
| new_snow_3h_sum_cm | 합계 3시간 신적설 | cm. 전 기간 빈칸 |
| remarks | 기사 | 전 기간 빈칸 |
| fog_duration_hr | 안개 계속시간 | hr. 전 기간 빈칸 |

`*_time`은 hhmi 정수로 앞자리 0이 빠져 있다(332 = 03:32, 2400 = 24:00).

## 주의사항

- **강수 빈칸:** 기상청 일자료는 강수가 없는 날을 빈칸으로 둔다(값 있는 76일 중 13일은 0.0 = 미량 강수 기록). 정제 파일은 빈칸을 그대로 두므로, 무강수일=0으로 볼지는 분석 시 명시적으로 결정한다.
- **적설·안개·기사:** 이 기간 춘천 자료에는 값이 전혀 없다. 12월에도 적설이 비어 있으므로 "눈이 없었다"로 해석하지 않는다. 적설이 필요하면 별도 자료를 확인한다.
- **음수 시각:** 2025-10-16 `precip_max_1h_time = -2351` 1건. 원본 값 그대로 두었으며 의미는 기상청 기준 확인 필요.
- 관측소 1곳의 값을 춘천시 전체 대표값으로 사용한다는 가정이다.
- 극한기상 사건 정의는 아래 [이벤트 라벨링](#이벤트-라벨링) 기준을 따른다.

## 이벤트 라벨링

```bash
python scripts/label_weather_events.py   # 입력 data/processed/weather.csv
```

공식 기상특보는 춘천 단독 집계가 없어 아래 임계값을 직접 적용한다.

| 유형 | 기준 | flag 열 | event_id |
|---|---|---|---|
| 폭염 | 일 최고 체감온도 ≥ 33℃ | is_heatwave | HEAT01~ |
| 강한 폭염 | 일 최고 체감온도 ≥ 35℃ | is_severe_heatwave | SHEAT01~ |
| 호우 | 일강수량 ≥ 80mm | is_heavy_rain | RAIN01~ |
| 폭설 | 일 최심신적설 ≥ 5cm | is_heavy_snow | SNOW01~ |

### 체감온도

기상청 여름철 체감온도(2022 개정, 기상자료개방포털 체감온도 산출식):

```
체감온도 = -0.2442 + 0.55399·Tw + 0.45535·Ta − 0.0022·Tw² + 0.00278·Tw·Ta + 3.0
Tw(습구온도) = Ta·atan[0.151977(RH+8.313659)^½] + atan(Ta+RH) − atan(RH−1.67633)
             + 0.00391838·RH^1.5·atan(0.023101·RH) − 4.686035      (Stull, 2011)
```

- 기상청 공식은 시간별 기온·습도로 계산한다. 일자료에는 시간별 값이 없어 **Ta = 최고기온, RH = 최소 상대습도**로 일 최고 체감온도를 근사한다(`apparent_temp_max_c`). 2025년 7~9월 최고기온 시각과 최소습도 시각의 중앙값 차이는 약 20분이다.
- **최소습도 기준을 메인으로 채택**(팀 결정). 평균 습도 버전은 폭염일이 21일 → 49일로 늘어나며, 민감도 분석용 대안으로 코드에 주석 처리해 남겨두었다(`add_features`). 정확한 값이 필요하면 ASOS **시간자료**로 다시 계산한다.
- 여름철 식 적용 기간인 5~9월만 산출하고 10~12월은 빈칸이다.

### 사건 묶기와 분석 대상

- 같은 유형 사건일 사이의 비사건일이 **2일 이내**면 하나의 사건으로 병합한다(예: 7/23, 7/26 → 사건 7/23~7/26). 3일 이상 끊기면 별도 사건이다. 병합 후 event_id를 유형별 시간순으로 다시 매긴다.
- `duration_days`는 병합된 사이 날짜를 포함한 기간, `event_days`는 실제 기준을 넘은 날 수다.
- 강한 폭염은 폭염의 부분집합이므로 두 목록에 모두 나타난다. 강한 폭염 사건은 `parent_event_id`에 자신을 포함하는 폭염 사건을, 폭염 사건은 `severe_event_days`에 강한 폭염 일수를 기록한다. 강도 정보는 부모 폭염 사건의 속성으로 분석한다.
#### 베이스라인·관찰기간과 사건 겹침

다른 사건이 섞인 날을 평상시나 회복기로 쓰지 않도록 아래 기준을 적용한다. "다른 사건 기간"은 유형에 관계없이 다른 사건의 시작일~종료일(병합된 사이 날짜 포함)이다.

| 구간 | 명목 기간 | 유효 기간 | 열 |
|---|---|---|---|
| 베이스라인 | 시작일 전 7일 (−7 ~ −1일) | 다른 사건 기간과 분석 기간(7/1) 이전 날짜를 **빼고** 남은 날 | `baseline_days_effective`, `baseline_overlap` |
| 관찰기간(회복 측정) | 종료일 다음 날부터 14일 (+1 ~ +14일) | 다른 사건 기간과 처음 만나는 날(새 사건 발생)의 **전날까지로 절단** | `observation_end_effective`, `observation_days_effective`, `observation_cut_by` |

- 강한 폭염의 회복은 **부모 폭염 사건 종료 다음 날**부터 관찰한다. 예: SHEAT01(7/8)은 HEAT02(7/7~7/9)가 끝난 7/10이 관찰 +1일이며, 폭염이 이어지는 7/9는 관찰기간이 아니다.
- 유효 베이스라인 또는 유효 관찰일수가 **`MIN_DAYS`(기본 7일)** 보다 적으면 `case_study`로 내리고 `exclude_reason`에 사유를 적는다(예: `관찰기간이 HEAT05(8/29)에서 절단되어 3일 < 7일`). `MIN_DAYS`는 `scripts/label_weather_events.py` 상단 상수이며 팀 합의에 따라 조정한다.
- 베이스라인 7일과 `MIN_DAYS` 7일이 같으므로, 현재 기준에서는 베이스라인에 다른 사건 기간이 하루라도 있으면 정식 비교에서 빠진다.

#### analysis_role과 exclude_reason

| analysis_role | 조건 | exclude_reason |
|---|---|---|
| statistical | 정식 통계비교 대상 (아래 조건에 하나도 해당하지 않음) | (빈칸) |
| excluded | 베이스라인이 2025-07-01 이전에 걸림(자동 제외, 가장 우선) | 베이스라인 날짜 범위 기재 |
| case_study | 호우: 사건 1건이라 정식 통계비교 제외 | 사례연구 후보 |
| case_study | 강한 폭염: 항상 일반 폭염 사건 안에 있어 독립 회복 사건으로 비교하지 않음 | 부모 폭염 사건 ID 기재 |
| case_study | 유효 베이스라인 또는 유효 관찰일수 < `MIN_DAYS` | 남은 일수와 겹친 사건·절단 지점 기재 |
| excluded | 폭설: 적설 데이터 없음 (`SNOW_NA` 행, 날짜 빈칸) | 데이터 없음 |

- 사유가 여럿이면 `exclude_reason`에 `; `로 모두 적는다.
- `baseline_event_days`, `observation_event_days`: 명목 기간 안의 폭염·호우·폭설 판정일 수(참고용).
- 정식 비교는 `weather_events.csv`에서 `analysis_role == 'statistical'`인 사건을 고르고, `weather_event_windows.csv`에서 `is_effective == True`인 날짜만 쓴다.

### 출력

| 파일 | 내용 |
|---|---|
| `data/processed/weather_events/weather_daily_events.csv` | 일별 정제자료 + 체감온도 + flag 열 |
| `data/processed/weather_events/weather_events.csv` | 사건 목록 (아래 열 설명) |
| `data/processed/weather_events/weather_event_windows.csv` | 사건 × 날짜 매핑. 카드 일별 자료와 date로 결합 (아래 열 설명) |
| `data/processed/weather_events/weather_event_counts.csv` | 유형별 사건 수·일수, 역할별 건수, 판정 가능 여부 |
| `data/processed/weather_events/weather_missing_by_date.csv` | 날짜별 결측 열 목록 |
| `outputs/weather_event_timeline.png` | 체감온도·강수·이벤트 타임라인. 사건 막대 아래에 베이스라인·관찰기간을 실선(유효)과 회색 점선(제외·절단)으로 표시 |

`data/processed/weather_events/`와 `outputs/`는 스크립트로 재생성하므로 저장소에 포함하지 않는다.

`weather_events.csv` 열:

| 열 | 내용 |
|---|---|
| event_id, type | 사건 ID, 유형 |
| start_date, end_date, duration_days, event_days | 시작·종료일, 병합 사이 날짜 포함 기간, 기준 초과일 수 |
| peak_value, peak_variable | 사건 중 최고값과 그 변수 |
| baseline_start, baseline_end | 명목 베이스라인 (시작일 −7 ~ −1일) |
| observation_start, observation_end | 명목 관찰기간 (+1 ~ +14일). 강한 폭염은 부모 사건 종료일 기준 |
| baseline_in_period, observation_in_period | 명목 기간이 분석 기간(2025-07-01~12-31) 안에 있는지 |
| baseline_event_days, observation_event_days | 명목 기간 안의 사건 판정일 수 (참고용) |
| parent_event_id | 강한 폭염을 포함하는 폭염 사건 ID |
| severe_event_days | 폭염 사건 안의 강한 폭염 일수 (강도 속성) |
| baseline_days_effective | 다른 사건 기간·분석 기간 밖을 뺀 베이스라인 일수 |
| baseline_overlap | 베이스라인에서 뺀 다른 사건과 날짜 (예: `RAIN01 7/20`) |
| observation_end_effective, observation_days_effective | 절단 후 관찰기간 종료일과 일수 |
| observation_cut_by | 관찰기간을 절단한 사건과 날짜 (예: `HEAT05(8/29)`) |
| analysis_role, exclude_reason | 위 표 참고 |

`weather_event_windows.csv` 열:

| 열 | 내용 |
|---|---|
| event_id, type, analysis_role | 사건 정보 |
| window | baseline / event / observation |
| date | 날짜. 명목 기간의 모든 날짜를 남긴다 |
| day_offset | baseline·event는 시작일 기준(−7 ~ −1, 0 ~), observation은 회복 시작 기준(+1 = observation_start) |
| is_effective | 비교에 쓰는 날이면 True. 겹침으로 제외되거나 절단 이후인 날은 False |
| overlap_event_id | 그 날짜와 겹치는 다른 사건 ID |
| ineffective_reason | False인 이유 (`다른 사건 기간(RAIN01)`, `관찰 절단: HEAT05(8/29)에서 새 사건`, `분석 기간 밖`) |

### 결과 (2025-07~12, MIN_DAYS = 7)

| event_id | 유형 | 기간 | 기준 초과일 | 최고값 | 유효 베이스라인 | 유효 관찰기간 | analysis_role |
|---|---|---|---|---|---|---|---|
| HEAT01 | 폭염 | 7/1 | 1 | 33.4℃ | 0일 (6월) | 7/2~7/6, 5일 (HEAT02에서 절단) | excluded (베이스라인 6월) |
| HEAT02 | 폭염 | 7/7~7/9 | 3 | 35.8℃ | 5일 (6/30 기간 밖, HEAT01 7/1 제외) | 7/10~7/19, 10일 (RAIN01에서 절단) | excluded (베이스라인 6/30 포함) |
| HEAT03 | 폭염 | 7/23~8/4 | 10 | 35.5℃ | 6일 (RAIN01 7/20 제외) | 8/5~8/17, 13일 (HEAT04에서 절단) | case_study (베이스라인 6일) |
| HEAT04 | 폭염 | 8/18~8/25 | 6 | 34.1℃ | 7일 | 8/26~8/28, 3일 (HEAT05에서 절단) | case_study (관찰 3일) |
| HEAT05 | 폭염 | 8/29 | 1 | 33.4℃ | 3일 (HEAT04 8/22~8/25 제외) | 8/30~9/12, 14일 | case_study (베이스라인 3일) |
| SHEAT01 | 강한 폭염 | 7/8 | 1 | 35.8℃ | 5일 | 7/10~7/19, 10일 (HEAT02 종료 후, RAIN01에서 절단) | case_study (HEAT02 내부 강도 특성) |
| SHEAT02 | 강한 폭염 | 7/28 | 1 | 35.5℃ | 2일 | 8/5~8/17, 13일 (HEAT03 종료 후, HEAT04에서 절단) | case_study (HEAT03 내부 강도 특성) |
| RAIN01 | 호우 | 7/20 | 1 | 94.7mm | 7일 | 7/21~7/22, 2일 (HEAT03에서 절단) | case_study (사례연구 후보, 관찰 2일) |
| SNOW_NA | 폭설 | - | - | - | - | - | excluded (데이터 없음) |

- **현재 기준(MIN_DAYS = 7)에서 정식 통계비교 대상은 0건이다.** 7~8월 폭염·호우가 2~3주 간격으로 이어져 깨끗한 베이스라인 7일과 관찰 7일을 함께 확보한 사건이 없다.
- `MIN_DAYS`를 낮추면: 6일 이하 → HEAT03 1건, 3일 이하 → HEAT03~05 3건이 정식 비교 대상이 된다. 기준값은 팀 합의가 필요하다.
- 강한 폭염 2건은 각각 1일이며 폭염 HEAT02·HEAT03 안에 있다. 독립 회복 사건으로 비교하지 않고 사례연구로 두며, 강도는 부모 사건의 `severe_event_days`(HEAT02 1일, HEAT03 1일)로 반영한다.
