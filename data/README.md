# 로컬 데이터 준비

공개 저장소에는 전처리·결합 코드, 변수 설명, 파일 목록 메타정보만 공유한다. 공모전 제공 원본·레이아웃과 정제·분석 데이터는 포함하지 않는다. 팀원은 참가 신청 후 제공받은 자료를 로컬에 보관하고, 공유가 필요하면 제공 조건에 맞는 팀 공유 경로를 사용한다.

`data/README.md`와 `data/manifest.json`을 제외한 `data/` 하위 전체는 `.gitignore` 대상이다. `.gitignore`는 과거 커밋에 있는 파일을 지우는 기능이 아니다. 이번 변경은 최신 파일 상태에서 제외하며 과거 Git 기록 삭제를 의미하지 않는다.

## 로컬 입력 폴더

저장소 루트에서 다음을 실행하고 제공받은 파일을 복사한다. 로컬 원본은 그대로 보존한다.

```bash
mkdir -p data/skt data/shinhan data/layouts data/processed
```

| 로컬 경로 | 준비할 자료 |
|---|---|
| `data/skt/flow_age_pop_202507.csv` ~ `202512.csv` | SKT 성연령별 유동인구 6개월 |
| `data/skt/flow_time_pop_202507.csv` ~ `202512.csv` | SKT 시간대별 유동인구 6개월 |
| `data/skt/flow_wkdy_pop_202507.csv` ~ `202512.csv` | SKT 요일별 유동인구 6개월 |
| `data/shinhan/shinhan_card_data1.txt` | 신한카드 데이터1의 로컬 복사본; 다른 이름이면 `--input`에 실제 경로 지정 |
| `data/shinhan/` | 신한카드 데이터2를 별도 보관; 데이터1과 합산하지 않음 |
| `data/layouts/` | 제공기관 설명서 원본을 로컬 보관 |
| `data/processed/` | 전처리 및 결합 코드가 생성하는 출력 |

SKT는 동일한 기본 파일명의 `.csv.gz`도 지원한다. 같은 월·종류의 `.csv`와 `.csv.gz`가 모두 있으면 `.csv`를 먼저 읽으므로 사용할 버전만 준비한다. 신한카드의 `.txt.gz`는 `--input`에 해당 경로를 지정한다.

## 중복 제거와 재실행

기관 안내의 `flow_pop_202512.csv`에 대응해 확인한 실제 시간대 파일명은 `flow_time_pop_202512.csv`다. 전처리 코드는 원본을 덮어쓰지 않고 별도의 정제 결과를 생성한다.

| 파일 | 최초 원본 행수 | 최초 제거한 완전 중복 | 정제 행수 |
|---|---:|---:|---:|
| `flow_time_pop_202512.csv` | 185,090 | 92,545 | 92,545 |
| `flow_wkdy_pop_202512.csv` | 242,534 | 121,267 | 121,267 |

모든 열이 같은 행만 제거한다. 다른 SKT 파일의 중복, 상충하는 키, 결측 또는 음수는 오류로 중단한다. 이미 중복 제거된 파일이면 이번 실행의 추가 제거 행수는 0이다.

```bash
python scripts/prepare_skt.py --input data/skt --output data/processed/skt
python scripts/prepare_card.py --input data/shinhan/shinhan_card_data1.txt --output data/processed/card
```

SKT의 `profiles.csv`, `monthly_age.csv`, `grid_coverage.csv`, `quality.csv`와 카드의 `daily.csv`, `monthly_age.csv`는 위 명령의 로컬 출력이다. 원본과 정제 파일의 구분자 등 세부 형식은 [변수 설명](../docs/variables.md)을 확인한다.

## 메타정보의 범위

`manifest.json`은 최초 파일 검증 기록이다. 파일명·인코딩·구분자·행수·중복 제거 수·파일 해시만 보관하며 실제 관측값이나 설명서 파일은 포함하지 않는다. `file`은 로컬 패키지의 `data/` 상대 경로이며, 목록이 있다고 해당 파일이 저장소에 포함되는 것은 아니다.

`sha256`과 `bytes`는 당시 검증한 패키지 파일 기준이다. gzip을 다시 만들면 압축 설정·메타정보에 따라 값이 달라질 수 있다. SKT·카드의 `source_sha256`은 전처리 전 원본 바이트를 확인할 때 사용한다.

## 외부자료와 해석

기상·공휴일 등 외부 원본도 기본적으로 로컬에 보관하고 출처·수집 방법·조회일을 기록한다. 공모전 제출용 원본 보관과 공개 GitHub 업로드는 구분한다. 공개 배포 가능한 파일을 추가할 때는 별도로 공개 범위를 확인하고 추적 목록을 검토한다.

SKT는 월별 자료이며 격자값 합계는 고유 방문자 수가 아니다. 춘천 후보 지역코드는 제공기관 확인 대기 상태를 유지한다. 실제 카드·기상·달력 연결은 [결합 안내](../docs/data_join.md)를 따른다.
