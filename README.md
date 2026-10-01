# KimLeePark · 김이박

2026 빅콘테스트 AI 데이터분석 분야 **「기후 위기에 따른 취약 상권 영향 분석」** 참가팀.
팀원: 김세은 · 박선하 · 이조은.

## 분석 주제와 데이터 활용

춘천의 극한기상 이후 고객 연령대별 카드매출 회복 속도를 분석한다.

- **주 분석:** 신한카드 일별 매출과 기상자료를 연결하여 매출 감소·회복을 분석한다.
- **보조 분석:** SKT 월별 자료로 연령·시간대·요일별 유동인구 특성을 설명한다.
- **월별 비교:** 카드도 월별·공통 연령대로 집계하여 SKT와 흐름을 비교한다.

기간은 2025년 7~12월. SKT는 월별 집계이므로 특정 폭염 당일 방문 감소나 일별 회복을 확인하는 데 사용할 수 없다. 월별 흐름만으로 기후의 인과효과를 주장하지 않는다.

## 현재 진행상황

10월 1일 조은 담당인 **유동인구 정리, 데이터 결합 코드, 정제 데이터 변수 설명 공유**를 위한 코드다.
전처리·월별 요약과 결합 검사 코드를 작성했다. **실제 기상·공휴일 결합 및 지역코드 확정은 대기 중**이며 매출 회복 분석이나 AI 모델 완료를 뜻하지 않는다.

- [체크리스트](docs/status_1001.md)
- [정제 데이터 변수 설명 및 팀 결합 형식](docs/variables.md)

## 파일 구성

```text
scripts/prepare_skt.py   # 중복 제거, 월별 프로파일, 공통 격자 비교
scripts/prepare_card.py  # 춘천 개인카드 일별·월별 집계
scripts/join_data.py     # 일별 기상·달력 결합 / 별도 월별 SKT 결합
tests/test_join_data.py  # 가상자료로 중복·누락·지역 확인 조건 검증
docs/                   # 변수 설명 및 진행상황
```

## 실행

Python 3.10 이상 환경에서 저장소 루트를 기준으로 실행한다.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/prepare_skt.py --input data/raw/skt --output data/processed/skt
python scripts/prepare_card.py --input data/raw/card/data1.txt --output data/processed/card
```

SKT 입력 파일은 `flow_age_pop_202507.csv` 형식으로 age/time/wkdy 각각 7~12월 총 18개가 필요하다. 실제 12월 시간대 파일명은 `flow_time_pop_202512.csv`다. 원본은 변경하지 않는다.
카드 파일명 `data1.txt`는 배치 예시이며 실제 파일 경로를 전달한다. 기본 인코딩은 CP949, 필요 시 `--encoding utf-8-sig`를 지정한다.

기상·공휴일 자료를 [정해진 형식](docs/variables.md)으로 준비한 뒤 실행한다.

```bash
python scripts/join_data.py daily --card data/processed/card/daily.csv --weather data/processed/weather.csv --calendar data/processed/calendar.csv --output data/processed/daily_joined.csv
```

지역코드가 공식 확인된 후에만 월별 결합을 실행한다.

```bash
python scripts/join_data.py monthly --card data/processed/card/monthly_age.csv --skt data/processed/skt/monthly_age.csv --mapping data/processed/region_mapping.csv --output data/processed/monthly_joined.csv
```

지역표의 `prefix,region,status,source` 중 status는 확인된 코드에 한해 `confirmed`로 기록한다. 32010은 현재 춘천 후보이며 아직 제공기관 확인 전이다. source에 토큰·개인 연락처 등은 넣지 않는다.

## 해석 및 공유 기준

- 60세 이상은 카드와 SKT 모두 같은 연령대로 합산한다.
- SKT 격자합은 고유 방문자 수가 아니다. 카드매출과 나눈 값을 구매전환율로 해석하지 않는다.
- 월별 관측 격자 차이는 전체 격자와 6개월 공통 격자를 비교한다. 미관측은 0으로 채우지 않는다.
- 요일·공휴일·계절에 따른 평소 매출 차이를 고려해야 한다. 회복 판정 기준은 팀에서 별도로 확정한다.
- 공개 저장소에는 공모전 제공 원본·정제 관측값을 포함하지 않는다. 팀원은 허용된 비공개 경로로 자료를 받아 `data/`에 보관한다.
- `.gitignore`는 실수 방지용이며 공개 가능 여부를 보장하지 않는다. 강제 추가하지 않는다.

데이터 출처: 공모전 제공 SK텔레콤 유동인구 및 신한카드 자료. 외부 기상·공휴일 자료 사용 시 출처·수집방법·원본을 별도로 보존한다.
