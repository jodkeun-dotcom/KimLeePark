# 최종 산출물과 코드 대응 목록

관련 #19. 2026-10-08 정리. 경로는 재실행 폴더 안의 상대경로이며, 주요 결과는 팀 내부 공유본에만 담았고, 이 문서의 경로는 공개 결과 파일 링크가 아니다. 전체 중간 산출물은 로컬 실행 폴더에 보존한다.

| 산출물 | 생성 코드 | 주요 입력 | 용도 |
|---|---|---|---|
| prepared/card/daily.csv | prepare_card.py | 카드 데이터1 | 날짜·업종·연령별 일매출 |
| prepared/weather.csv | prepare_weather.py | ASOS 원본 | 날짜별 기상 |
| prepared/calendar/calendar.csv | prepare_holiday_calendar.py | API XML 6개 | 공휴일 처리 |
| prepared/events/weather_events.csv, weather_event_windows.csv | label_weather_events.py | 기상 | 사건·관찰창 |
| prepared/daily_joined.csv | join_data.py daily | 카드·기상·달력 | 날짜 결합 검증 |
| analysis/baseline/daily_predictions.csv, daily_industry.csv | prepare_sales_baseline.py | 카드·사건·창·달력 | 공통 예상 매출 |
| analysis/common_sales/sales_handoff*.csv | prepare_sales_handoff.py | 같은 기준선 | full·eligible·paired 부족과 진단 |
| analysis/common_recovery/recovery_*.csv | compute_recovery_from_baseline.py | 같은 연령별·ALL 기준선 | 회복 곡선·상태·일수 |
| analysis/common_full_join/support_priority_DRAFT.csv | prepare_priority.py | 매출·회복 전달표 | 1대1 연결, 순위 공란 유지 |
| analysis/model/performance.csv, coverage.csv, split_audit.csv | evaluate_models.py / prepare_model_comparison.py | 카드·사건·전체 달력 | AI·기준모델 공통 표본 성능 |
| analysis/priority/support_review_PROVISIONAL.csv | rank_support.py / support_actions.py | 공통 예상값·사건·메타정보 | 모든 사건×업종의 상태·제안 조치 |
| analysis/priority/decline_rank_vs_state.csv, decline_state_crosstab.csv | compare_decline_states.py | 같은 우선순위 결과 | 감소율 순위와 상태별 범주 비교 |
| analysis/priority/priority_sensitivity.csv | rank_support.py | 평균·중앙값과 회복 규칙 | 18개 설정 |
| curves/final_recovery_curves_HEAT03~05.png | plot_final_recovery_curves.py | 같은 기준의 곡선·지표 | 18업종×3사건 최종 곡선 |
| stability/recovery_rule_stability_PRIVATE_REVIEW_ONLY.csv | review_recovery_rule_stability.py | 18개 설정 결과 | 회복 규칙에 따른 검토 상태 변화 |
| methods/method_comparison_detail.csv | compare_methods.py | 공통 기준선 | 기준선 방법 비교 |
| ages/age_comparison_detail.csv, support/industry_summary.csv | compare_ages.py | 공통 기준선 | 같은 업종·같은 날짜의 연령 비교 |
| prepared/skt/profiles.csv, grid_coverage.csv | prepare_skt.py | SKT 18개 | 월별 독립 집계 특성 |
| monthly_korean/*.csv 및 그림 6개 | compare_monthly.py | 카드·SKT·격자 범위 | 월별 보조 비교, 지역 잠정 |

run_support_review.py는 공통 기준선·매출·회복·모델·우선순위를 순서대로 실행하고 기본 지표 일치를 검사한다. 전체 실행 명령은 reproducibility_1010.md에 있다.

## 9일 노션 초안 현황

팀 비공개 공유 공간의 7회차 회의 페이지에서 아래 7개 첨부를 확인했다. 10일 항목은 조은·세은·선하 모두 비어 있었다. 이는 해당 페이지의 확인 시점 현황이며 다른 경로에 파일이 없다는 뜻은 아니다. 노션 내용은 수정하지 않았다.

| 담당 | 9일 초안 | 연결할 검증 근거 | 확인 상태 |
|---|---|---|---|
| 조은 | joeun_report_1009_reviewed.docx | model 성능, 월별 SKT, priority | 업로드 확인. 기존 검토본 보존 |
| 조은 | joeun_slides_1009_reviewed_final.pptx | priority 비교 | 업로드 확인. 기존 3장 검토본 |
| 조은 | support_action_plan_1009_reviewed.docx | 상태별 제안·공동 실행안 | 업로드 확인. 정책 공동 검토 대기 |
| 세은 | report_1009_recovery.docx | common_recovery, stability | 내려받아 주요 숫자 재집계 대조 |
| 세은 | slides_1009_recovery.pptx | 회복·시점·대표 곡선 | 4장. 본문 3장+팀 내부 부록 1장 |
| 선하 | 선하_Issue15_보고서_초안.docx | fixed_validation, ages, priority | 내려받아 주요 표 대조 |
| 선하 | 선하_Issue15_슬라이드_초안.pptx | 부족 산식·연령·지원 지표 | 3장. 설명용 가상 예시와 실제 결과 구분 |

세은의 감소 확인 304개, 회복 99개, 미확인 205개 및 회복 첫날 +3일 이내 57개·+7일 이내 88개가 재집계와 맞았다. 회복 99개 중 비공휴일 순부족이 계산되는 90개에서 37개가 양수인 것도 확인했다. 선하의 사건별 사전 검증 오차와 연령 완전성 표 역시 재실행 값과 맞았다. 첨부 전체의 모든 문장을 검증했다는 뜻은 아니다.

## 통합 전 보완할 표현

1. 세은 보고서 요약·슬라이드 1장의 “세 사건 모두 2~3주 간격”은 “서로 가까운 시기에 이어진 3개 사례이며 실제 관찰기간은 13·3·14일”로 정리한다. 사건 종료부터 다음 시작 전까지의 기간과 사건 시작일 간 간격을 혼용하지 않는다.
2. 세은 슬라이드 3장의 “회복해도 41% 누적 부족”은 “회복 확인 99개 중 부족 계산 가능 90개에서 37개(41%)에 순부족 잔존”으로 분모를 적는다. 보고서에는 이미 이 분모가 있다.
3. “지원 시작 사건 중~종료 후 3일”은 초기 상황 확인·지원 검토의 제안으로 표시한다. 관찰 종료까지 계산한 최종 부족·회복 결과를 사건 중에 이미 알 수 있었던 것처럼 쓰지 않는다. 당시 확보 가능한 값으로 재평가하는 절차를 구분한다.
4. 세은 보고서가 근거로 적은 plot_recovery_timing.py와 해당 요약 CSV는 현재 main 코드 스냅샷에 없다. 이번에 동일 핵심 숫자를 기존 회복·매출 표로 별도 재집계했지만, 대표 그림까지 완전히 재현하려면 그 생성 코드·요약표를 팀 비공개 제출본에 추가하거나 최종 보고서 출처를 재현 가능한 현재 코드로 맞춘다.
5. 세은 부록 4장은 업종명이 포함된 팀 내부용이다. 공개 GitHub 업로드 범위와 대회 심사용 제출 범위는 별도로 확인한다. 원본 첨부는 수정하지 않고 통합본에서 반영 여부를 기록한다.

## 보관 위치 구분

코드·방법·변수 설명·버전 정보는 공개 GitHub에 공유할 수 있다. 제공 원본·레이아웃·정제값·개별 업종 금액·결과 그림과 현재 팀 내부 ZIP은 허용된 비공개 경로에서 관리한다. 파일명이 PROVISIONAL 또는 DRAFT여도 무조건 옛 결과라는 뜻은 아니다. 실행 버전·입력 달력·공동 기준을 함께 확인한다.

## #18에서 새로 확인한 연결 사항

[선하의 1차 점검](https://github.com/jodkeun-dotcom/KimLeePark/issues/18#issuecomment-6041935702)과 [조은의 수정 방향 제안](https://github.com/jodkeun-dotcom/KimLeePark/issues/18#issuecomment-6049415984)을 확인했다. 두 댓글의 의견을 팀 전체 동의 완료로 기록하지 않는다.

- 세은의 “85개 업종 × 6연령” 설명에는 실제 입력 조합 491개와 3사건 합계 1,473행을 병기한다. 모든 가능한 조합이 관측됐다고 읽히지 않게 한다.
- 사건 중~종료 후 3일 이내 안내·접수·긴급 수요 확인과, 관찰창 종료·현장 확인 후 누적 부족·회복을 활용하는 상태별 지원 검토를 구분하는 안이 제시됐다. 실제 지원 개시 조건은 공동 결정 사항이다.
- 회복 설명의 +7/+14일은 사건 종료일 기준, 조은의 운영 점검 7일·필요 시 14일은 개별 검토 착수 기준이다. 사건 종료일·검토 착수일·실제 지원 시작일을 따로 기록하며 이 일정은 제안이다.
- 57/99·88/99는 회복 확인 대상만의 회복 첫날 분포다. 기존 팀 기준에서 k일 내 회복 비율 도입을 보류했으므로 본문·부록 추가 여부와 사용 범위는 공동 확인 전이다. 정책 시점의 직접 근거·전체 회복 확률로 사용하지 않는다. 사용한다면 HEAT04 제외 결과도 함께 표시한다.
- 선하의 사건 직전 검증과 조은의 9월 검증·10~12월 이후 평가를 별도 표로 유지한다. 서로 다른 기간·대상 오차를 같은 평가로 합치지 않는다.

계산·재현 검증은 완료됐지만 최신 통합본의 문구 반영·각 담당자 확인과 공동 발표 연습은 남아 있다.
