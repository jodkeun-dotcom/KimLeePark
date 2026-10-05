# #12: 공통 기준선 전달·회복 연결 검토

관련 #9, #12, #13, PR #29·#30. 팀 리뷰를 위한 추가 실행 경로입니다. 기존 compute_recovery.py를 변경하지 않으며 모델·회복 규칙과 #12 전체 완료를 확정하지 않습니다.

## 문제와 변경

#29는 연령별 실제·예상이 모두 있는 같은 연령 그룹을 날짜별로 합산합니다. #30의 기존 ALL은 관측 연령을 먼저 합산한 뒤 별도 업종 기준선을 학습합니다. 연령 결측이 있으면 두 계산의 학습 표본과 실제·예상 합산 대상이 달라집니다.

compute_recovery_from_baseline.py는 #29의 daily_predictions.csv와 daily_industry.csv를 입력으로 받습니다. 기본 필터는 effective + fixed_pre_event + exclude_missing + weekday_mean입니다. 업종 입력이 연령 입력의 동일 paired 합계인지 먼저 검사하며 키·창·금액·그룹 수·커버리지·사례분류·phase가 다르면 중단합니다. 예상 매출을 자체 재학습하지 않습니다.

회복 계산은 기존 #30의 회복 판정 함수를 재사용합니다. 95%·3일 연속은 잠정 기본값이며 옵션으로 명시할 수 있습니다. 사건기간이 완전하지 않으면 insufficient_data, 사건기간 비율이 기준 이상이면 no_decline, 관찰기간 결측은 연속을 끊습니다. 미회복 일수를 0으로 채우지 않습니다. ALL의 연령 구성 변화는 설명에 표시하며 검증된 인과적 회복으로 확정하지 않습니다.

조은 리뷰 반영: 입력 창의 시작·끝은 사건 목록의 start_date·observation_end_effective와 정확히 같아야 합니다. phase는 공식 end_date를 기준으로 검증하며 analysis_role도 사건 목록과 일치해야 합니다. 짧아진 창이나 임의 사례 분류는 거부합니다.

ALL 회복 판정은 PR #31과 같이 모든 입력 연령의 실제·예상이 갖춰진 날짜만 사용합니다. 사건기간에 일부 연령이 빠지면 insufficient_data이며, 관찰기간의 부분 날짜는 연속을 끊습니다. 원래 paired 합계 값은 보존하고 부분 비율은 ratio_paired_exploratory에만 남깁니다. 이 변경은 공동 승인 전 검토안이며 세은의 확인이 필요합니다.

달력 출처는 --run-metadata의 calendar_provenance에서 읽습니다. 메타정보가 없으면 unknown_review_required로 명시하며 특정 공휴일 달력을 추정하지 않습니다. provisional_2025_08_15_only를 선언하면 실제 공휴일 플래그와 대조하고, daily_rows가 제공되면 입력 행 수도 검증합니다. 메타정보는 선언된 출처이며 달력 전체의 정확성을 자동 승인하지 않습니다.

## 실행

Python 3, pandas, numpy. 저장소 루트에서 실행합니다. 두 입력 파일은 반드시 같은 기준선 실행에서 나온 파일이어야 합니다. 달력의 출처와 사용 방법은 원본 실행의 run_metadata.json도 함께 검토합니다.

```text
python scripts/prepare_sales_handoff.py --daily-predictions outputs/sunha_baseline/daily_predictions.csv --events data/processed/weather_events/weather_events.csv --run-metadata outputs/sunha_baseline/run_metadata.json --output outputs/common_handoff
python scripts/compute_recovery_from_baseline.py --daily-predictions outputs/sunha_baseline/daily_predictions.csv --daily-industry outputs/sunha_baseline/daily_industry.csv --events data/processed/weather_events/weather_events.csv --run-metadata outputs/sunha_baseline/run_metadata.json --threshold 0.95 --consecutive-days 3 --output outputs/common_recovery
python scripts/prepare_priority.py --sales outputs/common_handoff/sales_handoff.csv --recovery outputs/common_recovery/recovery_handoff_common_baseline.csv --output outputs/common_priority
python -m unittest discover -s tests -p test_sales_handoff.py -v
python -m unittest discover -s tests -p test_common_baseline_recovery.py -v
python scripts/compare_recovery_definitions.py --curves outputs/common_recovery/recovery_curves_common_baseline.csv --legacy-handoff outputs/legacy_recovery/recovery_handoff.csv --threshold 0.95 --consecutive-days 3 --output outputs/recovery_sensitivity_review
python -m unittest discover -s tests -p test_recovery_sensitivity.py -v
python scripts/compare_recovery_definitions.py --curves outputs/common_recovery/recovery_curves_common_baseline.csv --legacy-handoff outputs/legacy_recovery/recovery_handoff.csv --scope age_details --output outputs/recovery_sensitivity_review
python scripts/diagnose_recovery_coverage.py --curves outputs/common_recovery/recovery_curves_common_baseline.csv --metrics outputs/common_recovery/recovery_metrics_common_baseline.csv --output outputs/recovery_sensitivity_review
python -m unittest discover -s tests -p test_recovery_coverage.py -v
```

순위는 생성하지 않으며 공동 규칙 검토 대기 상태를 유지합니다. 같은 키로 연결됐다는 사실이 통합 결과의 타당성 승인을 뜻하지 않습니다.

## 회복 파일 선택

이 연결 경로의 --recovery에는 outputs/common_recovery/recovery_handoff_common_baseline.csv만 사용합니다. 같은 실행의 sales_handoff.csv와 1:1 결합하며, 다른 버전·다른 정의의 행을 합치거나 결측 값을 기존 #30 결과로 보충하지 않습니다. 기존 #30 recovery_handoff.csv는 비교·회귀 확인 전용으로 outputs/legacy_recovery 아래 구분해 보관합니다. 동일 KEY만으로는 계산 정의 차이가 검출되지 않으므로 파일과 경로를 함께 확인합니다. 최종 우선순위용 채택은 아직 공동 승인 전입니다.

민감도 실행의 --legacy-handoff는 같은 사건·유효 기간 및 95%·3일 연속으로 만든 기존 #30 전달본이어야 합니다. legacy 전달본에는 기준 옵션 열이 없어 실행 기록과 원본 코드로 별도 확인해야 합니다. 새 곡선에는 사용한 threshold·consecutive_days와 검증된 is_holiday가 포함되며 비교 옵션과 다르면 거부합니다. 민감도 CSV는 REVIEW_ONLY로 명명하고 전달표를 만들지 않습니다. 실제 CSV·개별 업종 결과는 로컬에만 보관합니다.

세은 추가 확인의 전체·사건별 분포와 8/15 민감도는 [recovery_sensitivity_review.md](recovery_sensitivity_review.md)에 정리했습니다. 완전 그룹 기준의 판정 불가 증가를 확인했으며, 고정 연령 구성·공휴일 건너뜀을 기본 규칙으로 자동 채택하지 않습니다.

2차 확인의 예상 매출 비중·결측 원인·한 연령 제외 건수와 연령별 공휴일 비교는 [recovery_coverage_followup.md](recovery_coverage_followup.md)에 정리했습니다. 예상 비중의 분모는 실제 관측과 관계없이 존재하는 연령별 예상값 전부이며, 예상 부재 셀을 포함한 참 전체 매출로 해석하지 않습니다. coverage_causes_PRIVATE_REVIEW_ONLY.csv에는 개별 업종과 알려진 예상 합이 포함되어 로컬·팀 비공개 경로에서만 관리합니다. 공개 문서는 비중과 건수만 담습니다.

회복 전달본의 recovery_uncertainty_note에 recovery_threshold·consecutive_days·holiday_policy가 남습니다. 현재 결합 코드는 note를 보존하지만 기준값을 자동 검증하지 않으므로 실행 기록을 대조해야 합니다. 기준이 다른 전달본을 같은 키로 섞지 않습니다. 관련 테스트는 30개이며 새 진단의 기본 회복 규칙은 변경하지 않습니다.

## 매출 전달표의 정의

KEY: event_id, region, industry, age, window_start, window_end. SALES는 prepare_priority.py 형식입니다. age=ALL과 실제 고객 연령을 같은 순위 목록에 섞거나 합산하지 않습니다.

- decline_rate: 사건 발생 기간 전체의 (예상 합−실제 합)/예상 합. 전체 날짜·연령 집계가 완전하고 예상 합>0인 경우에만 계산.
- gross_shortfall: 지정 창의 날짜별 max(예상−실제,0) 합. 공휴일 포함 전체 창이 완전할 때만 전달.
- net_shortfall / net_shortfall_rate: 전체 창의 순부족 합과 같은 창의 예상 합 대비 비율. 초과 매출을 차감하며 음수 유지.
- sales_uncertainty_note: 기준선·결측·기간 완전성·단위 및 ALL 연결 검토 사항.

불완전 창의 전달 지표는 공란입니다. 진단 CSV에는 paired 소계와 비공휴일 완전 지표를 따로 남깁니다. 공란은 0이 아닙니다. HEAT03은 잠정 8/15 예측 제외 때문에 달력기간 전체가 완전할 수 없습니다. 완전/비공휴일/부분 지표를 같은 이름으로 혼용하지 않습니다.

ALL 부족분 합계는 날짜별 연령 합산 이후 양수 처리를 합니다. 연령별 양의 부족분을 먼저 더하는 방식과 다릅니다. 금액은 제공 단위이며 임의로 원 단위로 환산하지 않습니다.

## 검증과 리뷰 요청

검사 18개는 일반 실행과 python -O에서 통과했습니다. 업종 상쇄, 부분 창의 전체 지표 공란, 공휴일·비공휴일 구분, 필터·중복·누락 검사, 공급 값 일치, 잘못된 ALL 값/키 거부와 우선순위 연결을 검사합니다. 추가 회귀 검사는 공식 창·phase·분류 불일치 거부, 실제 달력 출처 표시, 부분 연령만으로 회복 판정 금지, 완전한 3일 연속 회복을 포함합니다.

로컬 실제 자료에서는 연령별 요약 1,473행이 #29와 일치했고, 전달표 1,728행이 기존 회복 전달본과 1:1 결합됐습니다. 새 경로도 실제 재실행했습니다. 곡선 29,952행 중 ALL 4,420행의 실제·예상값이 공급된 업종 CSV와 일치하고, 연령별 회복 상태·일수 1,473행이 기존 경로와 유지됐습니다. 새 회복 전달본 1,728행도 매출 전달표와 1:1 결합됐습니다. 순위는 계산하지 않았으며 실제 수치·정제 자료는 공개 PR에 포함하지 않습니다.

- 세은: 공통 입력 경로의 회복 판정, ALL의 변동하는 그룹 구성·공휴일 영향, 기존 경로 대비 결과 변화를 검토.
- 수정 후 ALL 회복 상태·일수 255행은 PR #31의 완전 그룹 판정 결과와 일치했습니다. 이는 두 구현의 일치 검증이며 공동 규칙 승인을 뜻하지 않습니다. 전체 main 테스트는 이번 로컬 실행 범위에 포함하지 않았습니다.
- 조은: KEY·SALES·RECOVERY 형식, 완전/부분 지표 구분과 공란 처리, 우선순위 입력 해석을 검토.
- 공동: 전체 달력, 평균/중앙값 선택, 기준선·회복 기준·우선순위 규칙 합의.

실제 산출물 교체와 #12 완료는 이 리뷰·공동 확인 후 판단합니다. 기존 결과는 이전 버전으로 보관합니다.
