# 팀 자료를 로컬에 준비한 뒤 데이터 결합하기

이 문서는 최신 결합 코드의 입력 조건과 실행 방법을 설명한다. 기상자료는 세은, 공휴일 자료는 선하가 준비한다. 원본·정제 자료는 제공 조건에 맞는 팀 공유 경로로 전달하고 로컬에 배치한다. 공개 저장소에는 코드·문서·메타정보를 공유한다. 아래 기상·달력 경로는 예시이며 실제 파일과 맞춰야 한다.

## 준비

저장소 루트에서 실행한다. Python 3.10 이상과 pandas가 필요하다.

```bash
git pull --ff-only
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

로컬에 변경한 파일이 있다면 먼저 보관한다. 제공 데이터는 [data 폴더 안내](../data/README.md)에 따라 읽는다. 신한카드는 제공받은 원본 TXT 또는 그 압축본을 준비하고, 지역·법인 제외·연령 통합 등 분석용 정제를 거쳐야 아래 결합 입력 형식이 된다. 정제 및 결합 결과는 별도 로컬 폴더에 보관한다.

## 1. 전달받은 파일 확인

- 세은: 기상자료의 실제 경로, 날짜·지역 열, 관측소 선택 기준, 기온·강수량 등의 단위·결측 표시 확인.
- 선하: 공휴일 파일의 실제 경로, 날짜 형식, 공휴일·대체공휴일 포함 범위 확인.
- 분석 기간: 2025-07-01~2025-12-31. 춘천 지역명은 파일 간 동일하게 맞춘다.
- 팀원 파일을 덮어쓰지 않고 필요한 열 이름 변경·지역명 통일을 별도 로컬 사본에 적용한다.
- 사용한 코드의 GitHub 커밋, 로컬 입력 경로, 파일 해시, 출처, 변환 내용을 기록한다. 코드 다운로드만으로 데이터 결합이 완료되는 것은 아니다.

## 2. 일별 결합 입력

모든 파일은 쉼표 구분 UTF-8 CSV를 기준으로 한다.

| 입력 | 필수 열 | 한 행의 기준 |
|---|---|---|
| 카드 | date, region, industry, age, amount, transactions | 날짜×지역×업종×연령 |
| 기상 | date, region 및 기상 측정 변수 | 날짜×지역 |
| 전체 달력 | date, is_holiday | 날짜 |

- date: YYYY-MM-DD. region은 조은 카드 정제 자료 기준 `강원 춘천시`다.
- age: `10대`, `20대`, `30대`, `40대`, `50대`, `60대 이상`.
- is_holiday: 0 또는 1. 공휴일 목록만 받았다면 전체 184일 달력으로 확장한다. 목록의 완전성을 확인하기 전에는 없는 날짜를 비공휴일로 단정하지 않는다.
- 여러 기상 관측소가 있다면 지역 대표 관측소 또는 집계 방식을 정해 한 날짜·지역당 한 행으로 만든다.
- 결측 기상 측정값을 0으로 채우지 않는다. 날짜·지역 행 자체가 누락되면 결합을 중단한다.

```bash
python scripts/join_data.py daily \
  --card data/processed/card/daily.csv \
  --weather data/processed/weather.csv \
  --calendar data/processed/calendar.csv \
  --output data/processed/daily_joined.csv
```

기상·달력 경로를 실제 준비한 파일로 바꿔 실행한다. 날짜/지역 중복, 누락 날짜, 충돌하는 열 이름은 오류로 중단한다. 성공 시 카드 행수와 금액·건수 합계를 보존한다. 측정값 결측이 남아 있으면 분석 전에 별도로 처리 기준을 정한다.

## 3. 월별 SKT 결합

일별 테이블에 월별 SKT 값을 넣지 않는다. 아래 파일은 별도의 월별 비교용이다.

- 카드: month, region, age와 월별 매출 지표.
- SKT: month, prefix, age, scope, grid_value_sum. 월은 문자열 YYYYMM, prefix는 문자열로 읽는다.
- 지역표: prefix, region, status, source. 제공기관 확인 후에만 status를 `confirmed`로 적는다. 확인 근거를 source에 기록한다.
- SKT의 32010은 현재 춘천 후보이며 아직 공식 확인 전이다. 임의로 `confirmed`로 바꾸지 않는다.

```bash
python scripts/join_data.py monthly \
  --card data/processed/card/monthly_age.csv \
  --skt data/processed/skt/monthly_age.csv \
  --mapping data/processed/region_mapping.csv \
  --output data/processed/monthly_joined.csv
```

전체 관측 격자와 공통 격자 결과는 scope로 구분한다. 두 scope에 카드매출이 반복되므로 함께 합산하지 않는다. 격자합은 고유 방문자 수가 아니며 구매전환율의 분모로 사용하지 않는다.

## 현재 검증 범위

가상자료 검사 5개: 일별 행수·금액 보존 및 측정값 결측 유지, 중복 기상행 차단, 달력 누락 차단, 기상 날짜 누락 차단, 미확정 지역표 차단 및 확정표 결합.

실제 기상·공휴일 자료 결합 검증과 춘천 지역코드 확정은 아직 대기 중이다. 팀원 자료를 로컬에 준비한 뒤 이 절차로 실행하고 결합 결과를 확인한다.
