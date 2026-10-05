# 2025년 7~12월 공휴일 달력

관련 #27, #12, #13. 선하가 전달한 한국천문연구원 특일정보 `getRestDeInfo` XML 6개를 검사해 분석기간 전체 184일 달력을 만들었다. 여기서 직접 API를 재호출한 것은 아니다.

## 출처와 조회 기록

- 제공기관·서비스: [한국천문연구원 특일정보](https://www.data.go.kr/data/15012690/openapi.do).
- 경로: `https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo`.
- 선하가 설명한 요청 조건: `solYear=2025`, `solMonth=07`부터 `12`까지 월별 조회.
- 실제 조회일: **2026-10-05**, 선하의 답장을 사용자가 전달해 확인했다. 조회 시각은 미확인이다. 파일 수정 시각이나 분석 실행 시각에서 조회일을 추정하지 않았다.
- 받은 응답에는 `pageNo=1`, `numOfRows=100`이 있다. 이는 응답에 표시된 값이며 별도로 확보한 HTTP 요청 로그가 아니다. 인증키는 기록·공유하지 않는다.
- 자세한 응답 파일 해시·크기·개수·검사 결과와 달력 해시는 [출처 메타정보](holiday_calendar_source.json)에 보존한다. 달력 생성 시각은 조회일과 별도 필드다.

## 받은 응답 검사

6개 모두 `resultCode=00`이며 실제 항목 수가 `totalCount`와 같다. 날짜가 있는 응답은 파일에 지정된 2025년 월과 일치하고 날짜·seq 중복이 없다. API 키 표시는 없다.

| 월 | 공휴일 날짜 수 | 날짜와 이름 |
|---|---:|---|
| 7월 | 0 | 정상 빈 응답 |
| 8월 | 1 | 8/15 광복절 |
| 9월 | 0 | 정상 빈 응답 |
| 10월 | 6 | 10/3 개천절, 10/5~7 추석, 10/8 대체공휴일, 10/9 한글날 |
| 11월 | 0 | 정상 빈 응답 |
| 12월 | 1 | 12/25 기독탄신일 |

빈 응답은 연·월을 되돌려 주지 않아 7·9·11월 파일 바이트와 해시가 같다. 이는 정상적으로 가능한 형태다. **어느 월의 빈 응답인지 자체 XML만으로 증명할 수 없으며**, 파일명과 선하의 월별 조회 설명에 근거한다. 이를 중복 데이터로 삭제하지 않는다.

## 생성과 연결

팀 내부에서 받은 여섯 파일을 같은 디렉터리에 둔다. 공개 저장소에는 생성 코드·가상 테스트·문서·출처 메타정보를 공유하고, 원본 응답과 실제 달력은 팀 공유 ZIP에 함께 보관한다.

```bash
python -m scripts.prepare_holiday_calendar --input-dir data/external/holiday_xml --output outputs/holiday_2025_h2_received_20261005 --queried-date 2026-10-05
python -m scripts.run_support_review --card data/processed/card/daily.csv --events data/processed/weather_events/weather_events.csv --windows data/processed/weather_events/weather_event_windows.csv --calendar outputs/holiday_2025_h2_received_20261005/calendar.csv --calendar-metadata outputs/holiday_2025_h2_received_20261005/calendar_metadata.json --output outputs/joeun_1007/full_calendar_review_v1
```

필요한 파일명은 `holiday_2025_07.xml`~`holiday_2025_12.xml`이다. 이후 새 응답으로 갱신하면 **그때의 실제 조회일**을 사용하고 새 출력 폴더에 저장한다. 조회일이 없으면 옵션을 생략해 미확인으로 남긴다.

달력 열:

- `date`: 2025-07-01~12-31, 중복 없이 하루 한 행.
- `is_holiday`: 받은 항목의 `isHoliday=Y`인 날짜만 1. 일반 주말을 자동으로 1로 만들지 않는다.
- `holiday_name`: 해당 날짜의 공휴일명. 여러 이름이면 세미콜론으로 연결.
- `is_substitute`: 이름에 `대체공휴일`이 있는 날짜에 1.
- `is_weekend`: 토·일요일 여부. 공휴일 표시와 별개다.

`raw/`는 받은 XML의 바이트 그대로 복사하고 각 해시를 검증한다. 불완전 페이지·오류 응답·다른 월 날짜·잘못된 공휴일 표시·중복 항목은 거부한다. 기존 출력 폴더는 덮어쓰지 않는다. 통합 실행은 메타정보와 달력의 해시가 다르면 거부하며 동일 달력을 기준선과 모델에 전달한다. 조회 기록을 받았다는 사실이 모델·회복·우선순위 규칙의 공동 승인을 뜻하지 않는다.
