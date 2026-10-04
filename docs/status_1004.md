# 조은 10월 4일 작업 결과

주제: **「폭염 이후, 어떤 업종을 먼저 지원해야 하는가?」**

춘천의 업종·고객 연령별 매출 회복과 누적 매출 부족을 활용한 지원 우선순위 분석. 관련 업무 #10, 후속 검증 #13.

## 현재 상태

| 업무 | 상태 | 근거·남은 일 |
|---|---|---|
| SKT 연령·시간대·요일별 특성과 카드 월별 흐름 비교 | 잠정 분석·그림 작성 완료 | 제공기관 회신 미수신. 32010은 춘천 후보로만 표시 |
| 공통 기준모델 재실행 | 대기 | 선하의 모델 코드·예상 매출을 GitHub에서 아직 확인하지 못함 |
| 세은·선하 결과 결합 키·변수 형식 | 제안서·검사 코드 준비 | 실제 파일과의 호환성 확인은 수신 후 수행 |
| AI 비교 실험 준비 | 완료 | AI 1종 구현, 날짜 분할·입력·공통 지표 계획, 합성자료 실행 검사 |
| 지원 우선순위 표 | 빈 서식 준비 | 실제 감소율·누적 부족·회복·불확실성 미수신. 순위 미산출 |
| 공유 | 코드·설계·상태 문서는 PR로 공유 | 실제 수치·그림은 별도 로컬 공유 묶음. 팀원 전달 완료 여부는 별도 확인 |

**이 단계 전체가 완료된 것은 아니다.** 공통 기준모델 재실행과 팀 실자료 기반 우선순위 초안은 대기 중이다. 실자료 AI 학습과 이후 기간 성능 검증도 아직 수행하지 않았다.

## 월별 비교의 범위

- 카드: 춘천 개인카드 데이터1, 성별·시간대를 합산한 일별 업종·연령 표. 데이터2와 합산하지 않는다.
- SKT: `BLOCK_CD` 앞 5자리 32010. 2026-10-04 사용자 확인상 제공기관의 지역코드 회신을 아직 받지 못했다.
- 각 연령의 카드 월 매출을 달력일 수로 나누고, 카드와 SKT를 각각 7월=100으로 환산한다.
- SKT는 각 자료 종류에서 6개월 공통 격자를 사용하고, 전체 관측 격자 결과도 함께 비교한다. 미관측을 0으로 채우지 않는다.
- 연령·시간대·요일 집계는 서로 다른 표다. 개인 수준으로 연결하거나 종류별 합계를 합산하지 않는다.
- 6개 그림: 전체 월별 추이, 연령별 추이, 시간대 특성, 요일 특성, 격자 관측 범위, 연령 구성 비교.
- 요일 그래프는 해당 월 7개 요일 지표 평균=100이다. 실제 월별 방문 횟수 비중이 아니다.

격자 합계는 고유 방문자 수가 아니며, 카드 매출/격자 합계를 구매 전환율로 해석하지 않는다. 달력일 수 외에 업종 구성·계절·날씨·휴일 차이를 제거하지 않았으므로 월별 추이를 폭염의 인과효과나 일별 회복 결과로 사용하지 않는다.

## 재실행

PR #25의 전처리 코드·로컬 입력을 사용한다. 이 작업 PR은 #25의 `joeun-data-preparation`을 기반으로 하며, 제공 데이터는 로컬에서 준비한다.

```bash
python -m pip install -r requirements-analysis.txt

python scripts/prepare_skt.py --input data/raw/skt --output data/processed/skt
python scripts/prepare_card.py --input data/raw/card/data1.txt --output data/processed/card

python scripts/compare_monthly.py --card data/processed/card/daily.csv --profiles data/processed/skt/profiles.csv --coverage data/processed/skt/grid_coverage.csv --output outputs/joeun_1004/monthly --font /path/to/KoreanFont.ttf
python scripts/prepare_model_comparison.py --card data/processed/card/daily.csv --output outputs/joeun_1004/experiment
python scripts/prepare_priority.py --output outputs/joeun_1004/priority
python -m unittest discover -s tests -v
```

`data1.txt`와 한글 글꼴은 실제 로컬 경로로 바꾼다. macOS 예: `/System/Library/Fonts/AppleSDGothicNeo.ttc`. 출력 경로는 Git 제외 경로인 `outputs/` 안에 둔다. 현재 지역코드 미확정 상태를 표현하는 분석 코드이므로 회신 수신 후에는 출처 기록·범위 재확인 및 재실행을 거쳐 표시를 갱신한다.

## 검증

- 카드 월×연령 36행, SKT 후보 지역 프로파일 444행, 연령별 비교 72행(격자 범위 2종).
- 월별 카드 연령 집계의 날짜 존재 여부와 SKT 월·종류·변수·격자 수 일치 확인. 날짜 존재가 모든 세부 거래의 완전성을 보증하지는 않는다.
- 구성비 합=1, 중복 키·누락 월 방지, 기존 독립 월별 요약과 전체 흐름 일치 확인.
- 기존 결합 검사 5개 + 분석 준비 검사 6개 = **11개 통과**. 관찰 시작일·종료일에 문자열 `NaT`가 들어오는 9가지 입력 조합을 거부하는 회귀 검사를 포함한다. AI 검사에는 합성자료만 사용.
- 실제 자료는 월별 기술통계와 날짜 분할까지만 실행. 기준모델 재실행·실자료 AI 성능·팀 결과 결합 검증은 미실행.
- 그림 6종의 한글·범례·축·잘림 여부 시각 확인.

공개 저장소에는 코드·문서·검증 메타정보를 공유한다. 제공 원본·레이아웃·정제 데이터·수치 결과 CSV·그림 묶음은 로컬에 보관하고 허용된 팀 공유 경로로 전달한다.

## 연결 문서

- [AI 모델 비교 계획](model_comparison_1004.md)
- [팀 결과 결합 형식·지원 우선순위 초안](handoff_priority_1004.md)
