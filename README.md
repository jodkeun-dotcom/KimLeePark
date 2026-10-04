# kimleepark

## 기상자료

춘천 ASOS(관측소 101) 일자료를 정제하고 폭염·호우·폭설 사건을 라벨링한다. 자세한 기준과 결과는 [기상자료 변수 설명](docs/weather.md)을 참고한다.

기상청 원본(`data/raw/wether/OBS_ASOS_DD_20261001161226.csv`)과 정제본(`data/processed/weather.csv`)은 저장소에 포함되어 있어 아래 명령을 바로 실행할 수 있다. 포털에서 직접 받는 방법은 [원본 데이터 받는 방법](docs/weather.md#원본-데이터-받는-방법)에 있다. 카드·SKT 등 대회 제공 자료는 저장소에 포함하지 않는다.

```text
scripts/prepare_weather.py       # 춘천 ASOS 일별 기상 (CP949 → 영문 열, UTF-8)
scripts/label_weather_events.py  # 체감온도·폭염/호우/폭설 라벨, 사건·분석기간 표, 타임라인
notebook/data_read.ipynb         # 기상자료 pandas 읽기 확인
tests/test_weather_events.py     # 사건 묶기·적설 결측·분석기간·사건 겹침 처리 검증
scripts/compute_recovery.py      # 폭염 이후 업종·연령별 회복 곡선·회복일 (잠정, docs/recovery.md)
tests/test_recovery.py           # 회복일·미회복·기준선 학습 범위 검증 (합성자료)
```

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/prepare_weather.py --input data/raw/wether/OBS_ASOS_DD_20261001161226.csv --output data/processed/weather.csv
python scripts/label_weather_events.py
```

회복 곡선은 대회 제공 카드자료가 로컬에 있어야 실행된다. 실행 순서와 기준은 [회복 곡선·회복 지표](docs/recovery.md)를 참고한다.
