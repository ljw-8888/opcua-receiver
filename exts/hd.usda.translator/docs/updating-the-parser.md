# 현장 태그에 맞게 파서 수정하기

시험 서버의 태그 이름은 HYSYS 엑셀을 기준으로 정했다. 현장 서버를 연결하면 수신기가 저장한 첫 USDA에서 실제 식별자와 값의 구조를 확인한다.

1. `read_snapshot(path)`로 파일을 열고 `snapshot.tags.items()`에서 Endpoint, Namespace URI, 식별자와 샘플의 표시명·단위·자료형을 확인한다. 파일에는 수신기에서 저장 대상으로 고른 태그만 들어 있다.
2. 화면에 필요한 항목 하나를 정해 실제 신호를 찾는다. HD 서버에는 HYSYS 계산값과 현장 실측값이 함께 있다. 같은 지점의 압력이 둘이라면 어떤 정보로 두 출처를 구분할 수 있는지 확인한다. 같은 서버의 `opcua:source`에는 동일한 Endpoint가 기록된다. 파일만으로 출처나 측정 지점을 알 수 없으면 해당 신호를 예로 들어 HD 측에 확인한다.
3. [measurements.py](../hd_usda_translator/measurements.py)의 `_interpret_tag()`에서 실제 태그를 대상과 측정 항목으로 해석한다. 하나의 태그에 여러 값이 들어 있다면 `parse_measurement()`에서 확인된 필드의 값과 단위를 함께 꺼낸다. 첫 화면에 표시할 태그는 [tags.json](../data/tags.json)과 [BadgeTags](../hd_usda_translator/tag_selection.py)에서 설정한다.
4. 실제 USDA에서 대표 항목을 읽고 원문과 파서 출력을 대조한다. 확인할 항목은 측정 지점, 출처, 값, 단위다. 품질이 나쁘거나 수신이 끊겼을 때에는 `value=None`과 해당 `status`가 반환되는지도 확인한다.

시각화 확장이 `("Stream 1", "Pressure")`로 배관을 찾는다면, 태그 주소가 바뀌어도 변환 결과의 `target`과 `quantity`는 그대로 유지한다. 같은 이름의 행을 구분할 때는 `namespace_uri`와 `identifier`를 함께 쓴다. [오버레이와 시각화 확장의 측정값 조회 예제](integration.md)

**작업 요청 예**

> 첨부한 현장 USDA에서 지정한 측정 항목을 읽도록 파서를 수정해 주세요. 출처나 측정 지점이 불분명한 태그는 따로 알려 주세요. 수정 후 대표 항목의 원본 값·단위와 파서 결과를 비교해 주세요.
