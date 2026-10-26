# elastic_net 개별 분석 및 리뷰

Ridge PR의 공통 실행 코드를 사용하여 `elastic_net`만 학습·검증한다. 다른 신규 모형은 이 진입점에서 학습하지 않는다. 요일 평균·중앙값, 기본 Ridge, 기존 HistGradientBoosting을 공통 표본 비교 기준으로 포함한다.

## 실행

```bash
python -m scripts.evaluate_elastic_net --input-dir data/private/model_inputs --ridge-dir outputs/ridge_comparison/ridge --output outputs/elastic_net_comparison
python -m unittest discover -s tests -p 'test_elastic_net_entrypoint.py' -v
```

입력 파일, 학습 행, 변수, 평가 키, 음수 예측 처리와 지표는 `regression_comparison_20261026.md`와 동일하다. 후보는 공통 코드의 해당 모형 설정을 사용하며, 9월 WAPE로 결정한 후 10~12월에는 재조정하지 않는다. 사후 비교이므로 미열람 테스트 성능으로 주장하지 않는다.

## 리뷰 확인

- 선하: 같은 표본·날짜·단위에서 지표가 계산되는지와 모형 설정을 확인한다.
- 세은: 예측 정확도와 폭염 피해·회복 분석의 해석이 구분되는지 확인한다.
- 팀 내부 ZIP에서 해당 모형 결과 행과 선택 설정을 확인한다. 공개 저장소에는 개별 예측값·금액·실제 결과 CSV를 게시하지 않는다.
- 회복·지원의 주 기준선을 바꾸는 PR이 아니며, 기준선 변경은 별도 재계산과 공동 검토가 필요하다.

## 의존 관계

공통 코드가 들어 있는 Ridge PR을 먼저 머지해야 한다. 이 브랜치는 동일한 공통 코드 커밋에서 분기했으며, Ridge PR이 main에 병합되기 전에는 그 공통 변경이 diff에도 나타난다. Ridge PR 병합 후 이 PR의 독립 변경분은 개별 실행 진입점·테스트·문서다.

## 공통 검증 보완 반영

#41의 강화된 입력·저장 예측 대조를 포함한다. 모형 성능은 전체 수치와 월별·업종별·연령별 결과를 함께 확인하고, 요일 평균 대비 WAPE 차이의 날짜 블록 재표집 범위도 함께 검토한다. 이 범위는 선택·재학습 불확실성을 포함하는 통계적 유의성 검정이 아니다. 새로운 평가기간 튜닝은 하지 않았다.
