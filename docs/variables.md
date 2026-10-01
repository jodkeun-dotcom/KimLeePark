# 정제 데이터 변수 설명

조은 담당 공유용. 세은·선하의 실제 정제 파일은 아직 이 저장소에서 검증하지 않았으며, 기상·공휴일 항목은 결합을 위한 제안 형식이다.

기상자료는 세은, 공휴일 목록은 선하가 GitHub에 공유할 예정이다. 업로드 후 실제 경로·열 이름·단위를 확인하고 아래 형식에 맞춰 연결한다. 현재는 팀 자료 결합 전이며, 실행 절차는 [데이터 결합 안내](data_join.md)를 참고한다.

## SKT 원본 → 정제 자료

원본은 `|` 구분 UTF-8, 정제 파일은 쉼표 구분 UTF-8 BOM CSV.GZ다.

| 변수 | 의미 / 처리 |
|---|---|
| STD_YM | 기준년월, 문자열 YYYYMM. 개별 날짜가 아님 |
| BLOCK_CD | 소지역코드 문자열. 앞 5자리는 prefix로 보존하며 지역명 확정은 제공기관 답변 대기 |
| X_COORD / Y_COORD | UTM-K 좌표. 정확한 EPSG는 별도 확인 필요 |
| MAN_FLOW_POP_CNT_10G~50G, 60GU | 남성 연령별 월의 일평균 유동인구 지표 |
| WMAN_FLOW_POP_CNT_10G~50G, 60GU | 여성 연령별 지표. 60GU는 60세 이상 |
| TMST_00~23 | 시간대별 지표. 성연령표와 교차 집계로 해석하지 않음 |
| FLOW_POP_CNT_MON/TUS/WED/THU/FRI/SAT/SUN | 요일별 지표. 화요일은 원본 철자 TUS 유지 |

키는 STD_YM + BLOCK_CD + X_COORD + Y_COORD다. 202512 시간대·요일표의 완전히 동일한 행만 제거한다. 상충하는 키, 결측, 음수, 다른 파일의 중복은 오류로 중단한다.

## SKT 월별 요약

| 변수 | 의미 |
|---|---|
| month / prefix | 기준년월 / 코드 앞 5자리, 문자열 |
| type / variable | age·time·wkdy / 연령 또는 원본 지표 이름 |
| age | 10대·20대·30대·40대·50대·60대 이상, 성별 합산 |
| scope | all_observed: 해당 월 관측 격자 / common_6months: 같은 종류·접두어에서 6개월 공통 격자 |
| grid_value_sum | 격자 지표 합계. 고유 방문자 수 아님 |
| grids | 해당 요약에 포함한 격자 수 |
| observed_grids / common_grids | 월 관측 / 6개월 공통 격자 수 |

월별 없는 격자를 0으로 채우지 않는다. 공통 격자도 지역 전체를 대표한다고 가정하지 않는다. 요일 지표의 합을 실제 월 방문 횟수로 해석하지 않는다.

## 카드 정제 자료

신한 데이터1(탭 구분, 기본 CP949), 춘천 개인카드만 사용한다. 법인은 제외하고 성별·시간대를 합산한다. 데이터2와 합산하지 않는다.

| 변수 | 의미 |
|---|---|
| date | YYYY-MM-DD, 원본 TA_YMD |
| region | 원본 MCT_SGG_CD. 현재 필터는 강원 춘천시 |
| industry | 원본 MCT_RY_CD. 보고된 모든 업종 보존 |
| age | AGE_CCD의 공백 제거 후 60·70·80·90대를 60대 이상으로 합산 |
| amount | TS_AT 합계, 원자료 단위 유지. 임의 단위 환산 없음 |
| transactions | USE_CNT 합계 |
| month | YYYYMM |
| observed_days | 해당 월·지역·연령에서 관측된 날짜 수 |
| calendar_days | 달력상 월 일수 |
| amount_per_calendar_day | 월 amount / calendar_days. 결측이 0이라는 뜻은 아님 |

일별 키: date + region + industry + age. 월별 키: month + region + age.
미관측 날짜·업종·연령을 0으로 생성하지 않는다. ZZ_나머지도 보존하므로 핵심 업종 분석 시 별도 처리 기준을 정한다.

## 팀 결합 입력 형식

| 파일 | 필수 열 / 조건 |
|---|---|
| 기상 | date, region 및 기상 변수. date+region당 한 행. 관측소 선택·단위·결측 처리·출처는 작성자가 명시 |
| 달력 | date, is_holiday(0/1). 분석 기간 전체 날짜 포함. holiday_name, is_substitute 등 추가 가능 |
| SKT 지역표 | prefix, region, status, source. 제공기관 확인 후에만 status=confirmed. source에는 확인 자료 또는 답변 일자 기록 |

미확인 32010을 confirmed로 채운 예시 파일은 제공하지 않는다. 지역표는 최종 비교할 지역에 필요한 코드만 넣는다.
공휴일 목록만 있다면 먼저 전체 날짜 달력으로 확장하고 공식 목록의 완전성을 확인한다. 결합 코드는 누락 날짜를 비공휴일로 간주하지 않는다.

## 결합 출력

- 일별: 카드 열 + 기상 열 + 달력 열 + weekday(월=0~일=6), is_weekend(0/1), weather_match, calendar_match.
- 날짜/지역 기상행 누락, 달력행 누락, 중복 키는 오류다. 존재하는 기상행의 측정값 결측은 그대로 유지한다.
- 월별: month, region, age, scope, grid_value_sum + 카드 월별 열. scope별 카드 금액이 반복되므로 두 scope를 합산하지 않는다.
- 일별 결과에 SKT를 넣지 않으며, 매출/격자합을 개인 구매전환율로 해석하지 않는다.
