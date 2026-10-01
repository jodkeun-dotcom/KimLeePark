# 공모전 제공 데이터

사용자 요청에 따라 SKT 18개 데이터 파일, 신한카드 2개 데이터 파일과 두 기관의 레이아웃 설명서를 포함한다. CSV/TXT는 파일 크기를 줄이기 위해 gzip으로 압축했다. pandas에서 압축을 풀지 않고 읽을 수 있다.

## 구성

| 경로 | 내용 | 처리 |
|---|---|---|
| skt/flow_age_pop_202507.csv.gz ~ 202512 | 성연령별 유동인구 6개월 | 원본 내용 그대로 압축 |
| skt/flow_time_pop_202507.csv.gz ~ 202512 | 시간대별 유동인구 6개월 | 12월만 완전 중복 제거 |
| skt/flow_wkdy_pop_202507.csv.gz ~ 202512 | 요일별 유동인구 6개월 | 12월만 완전 중복 제거 |
| shinhan/shinhan_card_data1.txt.gz | 신한카드 데이터1 | 원본 내용 그대로 압축 |
| shinhan/shinhan_card_data2.txt.gz | 신한카드 데이터2 | 원본 내용 그대로 압축 |
| layouts/skt_layout.xlsx | SKT 테이블 정의서 | 원본과 동일 |
| layouts/shinhan_layout.xlsx | 신한카드 레이아웃 | 원본과 동일 |
| manifest.json | 파일별 원본명·행수·인코딩·SHA-256 | 검증 기록 |

## 12월 중복 제거

안내에서 언급한 `flow_pop_202512.csv`에 대응하는 실제 제공 시간대 파일명은 `flow_time_pop_202512.csv`다. 저장소에서는 실제 파일명을 유지했다.

| 파일 | 원본 행수 | 제거한 완전 중복 | 최종 행수 |
|---|---:|---:|---:|
| flow_time_pop_202512.csv.gz | 185,090 | 92,545 | 92,545 |
| flow_wkdy_pop_202512.csv.gz | 242,534 | 121,267 | 121,267 |

모든 열이 같은 행만 제거했고 최초 등장 행과 원래 순서를 유지했다. 두 파일은 문자열로 읽어 값을 변환하지 않고 처리했으며, 압축 결과를 다시 읽어 정확히 일치하는지 확인했다. 다른 SKT 파일의 중복은 0건이었다. 모든 SKT 파일에서 기준년월·소지역코드·좌표 키의 중복이 남지 않는지 확인했다.

신한카드는 지역·법인·연령 필터를 적용하지 않은 원본이다. 데이터1과 데이터2를 합산하지 않는다. 이번 데이터 폴더는 기존의 춘천 개인카드 분석용 정제 결과와 구별한다.

## 읽기

```python
import pandas as pd

skt = pd.read_csv(
    "data/skt/flow_time_pop_202512.csv.gz",
    sep="|", encoding="utf-8-sig",
    dtype={"STD_YM": str, "BLOCK_CD": str},
)
card = pd.read_csv(
    "data/shinhan/shinhan_card_data1.txt.gz",
    sep="\t", encoding="cp949",
    dtype={"TA_YMD": str},
)
```

SKT는 월별 자료이고, 격자 합계는 고유 방문자 수가 아니다. 지역코드의 춘천 대응은 제공기관 확인 대기 상태를 유지한다. 기상·공휴일 자료는 이 제공 데이터에 포함되지 않는다.

원본 파일은 로컬에서 변경하지 않았다. 중복 제거한 두 파일 외에는 압축 해제 후 SHA-256이 원본과 같은지 검증했다.
