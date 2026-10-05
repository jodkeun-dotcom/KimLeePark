# #11 마무리: 회복 기준에 따른 순위·상태 안정성과 회복 곡선 최종안

관련: #11 (10/7), #13·#31(병합), #33. 상태: **검토용**. 아래는 건수만 담는다. 업종명이 들어간 표와 그림은 `outputs/seeun_1007/` 아래에 로컬로만 만들고 팀 내부로 공유한다.

- 기준: 2026-10-06 최종 동의한 6개 분석 기준(`docs/team_criteria_review_1005.md`). 공통 기준선(사건 시작 전 고정 요일 평균·결측 제외·effective), 회복 95% 이상 3일 연속(공휴일·불완전 날짜는 연속을 끊음), 관찰 14일·병합 간격 2일.
- 회복은 그날 매출 수준의 회복이며 누적 부족 만회가 아니다. 기준선 대비 차이이며 인과적 폭염 피해액이 아니다. 자료 부족·사건 감소 기준 미충족·관찰기간 내 회복 미확인은 지원 불필요를 뜻하지 않는다.
- 달력: 8/15만 제외한 잠정 달력(`provisional_2025_08_15_only`). #31에서 확인한 대로 가장 늦은 관찰 종료일(9/19)까지는 전체 공휴일 달력과 학습 패널·공휴일 표시가 같으므로 여름 사건 결과는 같다.

## 1. 회복 기준에 따라 상태·순위가 크게 달라지는 업종 표시

#31의 `priority_sensitivity.csv`(사건×업종 255행 × 18개 설정: 요일 평균/중앙값 × 임계 0.90/0.95/1.00 × 연속 2/3/4일)를 그대로 사용한다. 합의 기준(요일 평균·0.95·3일)을 기준 상태로 두고, **같은 요일 평균 기준선 안에서 나머지 8개 회복 규칙**을 적용했을 때 지원 검토 상태(`review_queue`)가 몇 번 달라지는지 센다.

| 표시 (`rule_sensitivity`) | 조건 |
|---|---|
| stable | 8개 규칙 모두 기준과 같은 상태 |
| low | 1~3개 규칙에서 상태가 다름 |
| high | **4개 이상(절반 이상)** 규칙에서 상태가 다름 — "크게 달라짐" |

함께 기록하는 열: 임계값만 바꿨을 때(연속 3일 고정) 바뀌는지(`threshold_axis_changes`), 연속일수만 바꿨을 때(임계 0.95 고정) 바뀌는지(`run_axis_changes`), 같은 규칙에서 중앙값 기준선이면 바뀌는지(`median_same_rule_differs`), 18개 설정 중 순위 후보·1등급 횟수(`all_settings_ranked`, `all_settings_first_tier`), 일부 설정에서만 순위 후보가 되는지(`rank_sensitive`).

### 결과

| 사건 | 범위 | stable | low | high |
|---|---|---:|---:|---:|
| HEAT03 | 주 분석 | 17 | 0 | 1 |
| HEAT04 | 주 분석 | 14 | 2 | 2 |
| HEAT05 | 주 분석 | 18 | 0 | 0 |
| HEAT03~05 | 보조 탐색 | 201 | 0 | 0 |

| 범위 | 기준 상태 (`review_queue`) | stable | low | high |
|---|---|---:|---:|---:|
| 주 분석 | 매출 자료·지표 부족 | 22 | 0 | 0 |
| 주 분석 | 양의 순부족 없음 | 22 | 0 | 0 |
| 주 분석 | 양의 순부족·사건 감소 기준 미충족 | 5 | 2 | 0 |
| 주 분석 | 양의 순부족·회복 미확인 | 0 | 0 | 2 |
| 주 분석 | 순위 후보(양의 순부족·회복 확인) | 0 | 0 | 1 |

- **매출 자료 부족**과 **양의 순부족 없음**은 회복 규칙과 관계없이 정해지는 상태라 모두 stable이다. 회복 규칙이 실제로 영향을 주는 주 분석 10행(양의 순부족이 있고 자료가 완전한 행) 중 **5행의 상태가 바뀐다**(high 3, low 2).
- 순위 후보 1행(HEAT03)은 요일 평균 9개 규칙 중 3개, 18개 설정 중 6개에서만 후보이고 후보일 때는 모두 1등급이다(#31의 "18개 중 6개 유지"와 같은 행). 임계값과 연속일수 어느 쪽을 바꿔도 상태가 바뀐다.
- 회복 미확인 2행(HEAT04)은 모두 high다. HEAT04의 실제 관찰기간이 3일이라 연속일수·임계값에 따라 회복·미확인·감소 기준 미충족이 바뀐다. 이 중 1행은 다른 설정에서 순위 후보가 된다(18개 중 4개).
- 사건 감소 기준 미충족 2행(HEAT04)은 임계값만 바꿀 때 바뀐다(low). 이 중 1행은 다른 설정에서 순위 후보가 된다(18개 중 2개).
- 같은 규칙에서 중앙값 기준선으로 바꿨을 때 상태가 달라지는 행은 주 분석 1, 보조 탐색 1행이다.
- 따라서 **업종별 결론은 stable 행에서만 강하게 말하고, high·low 행은 "회복 기준에 민감"으로 표시**한다. 특히 순위 후보 1행은 단일 설정 결과로 순위를 확정하지 않는다.

## 2. 회복 곡선 최종안

합의 기준(공통 기준선·0.95·3일·관찰 14일)으로 `compute_recovery_from_baseline.py`를 실행한 곡선에서, 사건별로 주 분석 18개 업종의 업종 전체(ALL) 곡선을 그린다.

| 표시 | 뜻 |
|---|---|
| 파란 실선 | 모든 입력 연령이 갖춰진 날의 실제/예상 비율. **회복 판정에 쓰는 값** |
| 회색 점 | 일부 연령만 있는 날의 비율. 참고용이며 판정에 쓰지 않음 |
| 회색 띠 | 사건 기간(마지막 사건일 = 0). x축은 사건 종료 후 일수 |
| 점선 | 회복 기준 95% |
| 주황 실선 / 점선 | 회복 첫날 / 연속 확인 완료일(= 회복 첫날 + 2일) |
| 세로 점선 | 공휴일(8/15, HEAT03 관찰 +11일). 연속을 끊는다 |

그림 제목에 사건 종료일과 **실제 관찰일수**를 적는다. HEAT04(실제 관찰 3일)는 "첫 관찰일부터 3일 모두 충족해야 회복으로 인정되는 제한적 창(다음 사건으로 절단)"을 함께 표시하고 원래 판정은 그대로 둔다.

주 분석 18개 업종의 사건별 상태(업종 전체, 합의 기준):

| 사건 | 실제 관찰 | 사건 감소 기준 미충족 | 회복 | 관찰기간 내 회복 미확인 | 자료 부족 |
|---|---:|---:|---:|---:|---:|
| HEAT03 | 13일 | 10 | 1 | 1 | 6 |
| HEAT04 | 3일 | 8 | 0 | 2 | 8 |
| HEAT05 | 14일 | 12 | 2 | 1 | 3 |

보고서·슬라이드용으로 대표 업종을 고르고 다듬는 작업은 #14(10/9)에서 한다. 이 그림이 그 기준본이다.

## 재현

```bash
# 시나리오 S0(관찰 14일·간격 2일, main 기본값) 사건과 기준선 — PR #33 docs/recovery_sensitivity_1007.md의 S0 명령과 같다
python scripts/label_weather_events.py --output outputs/seeun_1005to1007/scenarios/S0/weather_events \
  --figure outputs/seeun_1005to1007/scenarios/S0/weather_event_timeline.png
python scripts/prepare_sales_baseline.py --daily data/processed/card/daily.csv \
  --events outputs/seeun_1005to1007/scenarios/S0/weather_events/weather_events.csv \
  --event-windows outputs/seeun_1005to1007/scenarios/S0/weather_events/weather_event_windows.csv \
  --output outputs/seeun_1005to1007/scenarios/S0/baseline
B=outputs/seeun_1005to1007/scenarios/S0
# 1) #31 우선순위·18개 설정 → 회복 기준 안정성
python -m scripts.rank_support --daily $B/baseline/daily_predictions.csv --events $B/weather_events/weather_events.csv \
  --run-metadata $B/baseline/run_metadata.json --output outputs/seeun_1007/priority
python scripts/review_recovery_rule_stability.py
# 2) 합의 기준 회복 곡선 → 최종 그림
python scripts/compute_recovery_from_baseline.py --daily-predictions $B/baseline/daily_predictions.csv \
  --daily-industry $B/baseline/daily_industry.csv --events $B/weather_events/weather_events.csv \
  --run-metadata $B/baseline/run_metadata.json --threshold 0.95 --consecutive-days 3 --output outputs/seeun_1007/common_recovery
python scripts/plot_final_recovery_curves.py
```

- 로컬 실행에서 #31 우선순위 결과가 문서와 같음을 확인했다: 주 분석 54행의 지원 상태(자료 부족 22, 양의 순부족 없음 22, 감소 기준 미충족 7, 회복 미확인 2, 회복 확인 1), 순위 후보가 18개 설정 중 6개에서 유지, ALL 회복 상태(자료 부족 197, 감소 기준 미충족 45, 미확인 8, 회복 5).
- 출력 (로컬):
  - `outputs/seeun_1007/stability/`: `rule_sensitivity_by_event.csv`, `rule_sensitivity_by_queue.csv`, `rule_sensitivity_axes.csv`(건수만), `recovery_rule_stability_PRIVATE_REVIEW_ONLY.csv`(업종별)
  - `outputs/seeun_1007/curves/`: `final_recovery_curves_HEAT03~05.png`, `final_recovery_curves_PRIVATE_REVIEW_ONLY.csv`(업종별 곡선 자료)
- 테스트: `tests/test_recovery_final_1007.py`(가상자료). 기준·축별 변화와 표시, 18개 설정 누락 거부, 건수 요약에 업종명이 없는지, 곡선의 판정용/참고용 비율 분리, 확인 완료일, 짧은 창 안내, 단일 규칙 검사, 그림 생성.

## 팀 확인

- "크게 달라짐(high)" 경계를 기준 외 8개 규칙 중 4개(절반)로 정했다. 경계를 바꾸려면 `HIGH_SHARE`를 조정한다.
- 순위 후보·회복 미확인 행이 모두 high이므로, 지원 실행안(#16)과 보고서(#14)에서 해당 업종을 "회복 기준에 민감, 추가 확인 필요"로 표시할지 결정이 필요하다.
- 핵심 결론 3개 선정(#11 공동 확인)은 이 표와 #33 민감도 결과를 근거로 회의에서 정한다.
