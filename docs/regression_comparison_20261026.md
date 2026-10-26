# 회귀모형 비교와 Ridge 보완 실험

## 목적과 범위

업종·고객 연령별 일별 매출 예측을 같은 학습자료와 평가 키에서 비교한다. 기준모형 2종(요일 평균·중앙값), 회귀모형 5종(Ridge·Elastic Net·Random Forest·HistGradientBoosting·Extra Trees)과 별도의 Ridge 상호작용 보완 실험을 포함한다. 보완 실험을 여섯 번째 회귀모형 종류로 세지 않는다.

이는 시간 순서로 나눈 사후 예측 비교다. 10~12월 벤치마크는 이전 작업에서 이미 확인되었고, 최초 Ridge 평가 결과를 본 뒤 상호작용 보완을 설계했다. 따라서 새로운 미열람 테스트로 주장하지 않는다. 이번 후보와 규칙은 suite 실행 전에 고정하고, 후보 선택에는 9월 WAPE만 사용한다. 하이퍼파라미터 동률은 후보 순서로 결정한다. 성능 결과를 보고 탐색 범위를 확대하지 않는다.

회복·지원 계산의 주 기준선은 변경하지 않는다. 예측 성능이 좋은 모형이 폭염이 없었을 때의 매출을 정확히 추정한다는 뜻은 아니며, 피해액이나 지원 순위의 타당성을 입증하지 않는다.

## 공통 조건

- 7~8월 학습 → 9월 검증, 7~9월 재학습 → 10~12월 평가. 각 평가기간 중 재학습 없음.
- 기존 공통 코드의 과거 관측·비사건·비공휴일 학습 행 사용. 공통 기준선의 최소 전체 7일·요일별 2회 등 자격 규칙 유지.
- 기존 기준선 자격을 만족하는 관측 행에서 모든 모형 비교. 누락 실제값을 0으로 채우지 않음.
- 기본 변수: 업종·연령 원핫 인코딩, 요일·주말·월·경과일. 숫자 변수는 학습자료에서 표준화. 요일·월을 수치로 처리하는 기본 선형모형의 제약을 인정한다.
- 매출 원척도를 예측. 음수 예측은 모든 모형에서 0으로 절단하며 절단 전 음수 건수 기록.
- WAPE는 CSV에서 비율(0~1 기준, 1을 초과할 수 있음), 보고 시 100을 곱해 %로 표시. MAE·RMSE는 제공 금액 단위이며 원화가 아님.
- 전체 오차 외에 업종·연령별 오차와 실제합, 과대·과소 예측, 초과 절대오차 기여를 비공개 파일로 저장.

## 모형 설정

| 모형 | 후보 및 설정 |
|---|---|
| Ridge | alpha 0.01, 0.1, 1, 10, 100, 1000, 10000; SVD |
| Ridge 보완 | 같은 alpha 후보; 업종×연령, 업종×요일 원핫 추가; LSQR tol=1e-8 |
| Elastic Net | alpha 0.01, 0.1, 1 × l1_ratio 0.2, 0.8; max_iter=20000, tol=1e-6 |
| Random Forest | 트리 150개, 깊이 12/제한 없음, min_samples_leaf=5, random_state=42 |
| Extra Trees | 트리 150개, 깊이 12/제한 없음, min_samples_leaf=5, random_state=42 |
| HistGradientBoosting | main의 make_ai_model 설정 재사용; 이번 실행에서 튜닝하지 않음 |

Elastic Net 및 suite 모형은 계산 안정성을 위해 target을 1,000,000으로 나누어 학습한 뒤 원단위로 복원한다. 이는 화폐 단위 변환이 아니다. Elastic Net의 alpha는 이 스케일에 의존한다. 기본 Ridge와 보완 Ridge의 계수는 인과효과로 해석하지 않는다. 보완 Ridge는 여러 조합항을 함께 바꾸므로 각 항의 독립 기여를 증명하지 않는다.

## 실행

기존 프로젝트 루트에서 실행한다. Python 3.12.14, numpy 2.5.3, pandas 2.2.3, scikit-learn 1.9.1에서 로컬 검증했다. 같은 환경을 준비하고 스레드 수를 고정한다.

```bash
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
python -m scripts.evaluate_ridge \
  --input-dir data/private/model_inputs \
  --reference outputs/prior_model \
  --output outputs/ridge_comparison/ridge
python -m scripts.evaluate_regression_suite \
  --input-dir data/private/model_inputs \
  --ridge-dir outputs/ridge_comparison/ridge \
  --output outputs/ridge_comparison/suite
python -m unittest discover -s tests -p 'test_regression_suite.py' -v
```

입력 폴더에는 `card.csv`, `events.csv`, `windows.csv`, `calendar.csv`가 필요하다. 기존 공통 분석의 `analysis/inputs` 산출물 형식을 그대로 사용한다. reference에는 기존 `protocol.json`, `validation_predictions.csv`, `holdout_predictions.csv`를 둔다. reference 옵션은 과거 실행과 입력 해시·키·예측값·자격을 대조하며, 없으면 생략할 수 있으나 과거 실행 대조 완료로 표시되지 않는다.

이미 내용이 있는 출력 폴더에는 덮어쓰지 않는다. 재현 확인은 새 출력 폴더에서 다시 실행한 후 결과 CSV와 선택 설정을 비교한다.

## 산출물 및 보관

- `performance.csv`: 전체·업종·연령별 동일 표본 성능
- `validation_alpha_search.csv` / `validation_search.csv`: 검증기간 후보 결과
- `frozen_selection.json`: 9월 자료로 고정한 설정
- `*_predictions.csv`: 실제·예상값과 비교 자격 (비공개)
- `*_ridge_diagnostics_*.csv`: 오차 원인 점검용 집계 (비공개)
- `protocol.json`, `verification.json`, audit CSV: 입력·코드 버전, 재학습·대조 기록

공개 저장소에는 코드·가상자료 테스트·방법론·검증 기록만 게시한다. 실제 수치, 예측값, 계수, 원본·정제자료, 개인 경로와 팀 내부 ZIP은 비공개로 보관한다. 검증 기록은 `regression_verification_20261026.md`를 참고한다.

## 팀 리뷰 요청

선하: 학습·평가 표본, 변수 처리, WAPE·MAE·RMSE, 평균/중앙값 선택의 목적을 검토한다.
세은: 사후 예측 비교의 해석 범위, 회복·누적 부족 기준선과의 구분을 검토한다.
기준선을 바꾸려면 별도 결정과 사건별 재계산·수치 대조가 필요하다. 이 PR만으로 회복·지원 결과를 교체하지 않는다.

## 재검토 보완 (2026-10-26)

저장 예측파일을 사용할 때 원본 입력 해시뿐 아니라 전체 관측 키·실제값·평가 자격·평균/HGB 재학습 예측을 대조한다. 기본 Ridge도 재학습하여 비교 표본의 예측과 검증기간 alpha 선택을 확인한다. 잘못된 예측이나 누락·중복 키는 분석을 중단한다. 지표 입력의 차원과 길이도 검사하여 배열 자동 확장에 의한 잘못된 계산을 막는다.

모형별 전체·월별·업종별·연령별 오차와 평가 제외 사유를 제시한다. 요일 평균 대비 WAPE 차이는 같은 날짜의 모든 업종·연령을 함께 묶어 7일 이동 블록으로 500회 재표집한 2.5~97.5 백분위 범위를 병기한다. 이는 고정된 예측값에서 관측일 구성에 따른 변동을 보여주는 기술적 범위다. 모형 선택·재학습 불확실성을 포함하는 신뢰구간, 모집단 유의성 검정, 인과적 피해 추론으로 해석하지 않는다.

변수 선택은 평가기간을 이용한 반복 탐색 대신 명시한 기본 변수와 별도 조합항 보완을 비교한다. 전체 원척도 오차는 큰 매출 그룹에 영향을 받으므로 업종·연령별 분모와 오차를 함께 읽는다. 특정 연령의 큰 오차는 그 연령의 취약성이나 인과효과가 아니다.
