# USDA에서 측정값 읽기

수신 파일 한 개에는 서버의 마지막 발행 상태와 태그별 샘플이 들어 있다. 예를 들어 [예제 파일](examples/telemetry.usda)에서 Stream 1 압력의 속성은 다음과 같다.

```usda
custom string opcua:identifier = "s=Stream/1/Pressure"
custom string opcua:namespaceUri = "urn:hd:opcua:test:v1"
custom string opcua:unit = "barG"
custom double opcua:value = 4.575
```

## 저장된 샘플 확인

Kit에서 확장을 켜고 **Window → Script Editor**에서 실행하면 함께 제공한 예제 파일을 읽을 수 있다.

```python
from pathlib import Path
import omni.kit.app
from hd_usda_translator.telemetry import read_snapshot

manager = omni.kit.app.get_app().get_extension_manager()
ext_id = manager.get_enabled_extension_id("hd.usda.translator")
path = Path(manager.get_extension_path(ext_id)) / "docs/examples/telemetry.usda"
snapshot = read_snapshot(path)

key = (snapshot.source, "urn:hd:opcua:test:v1", "s=Stream/1/Pressure")
sample = snapshot.tags[key]
print(sample.value, sample.unit, sample.quality, sample.state)
```

결과는 `4.575 barG Good Stale`다. `Good`은 마지막 수신 당시의 품질이고 `Stale`은 그 값이 더 이상 현재값이 아니라는 뜻이다.

`read_snapshot()`은 `Sdf.Layer.OpenAsAnonymous()`로 USDA를 열고 레이어의 `opcuaFormat`을 확인한다. `/Telemetry`에서 Endpoint와 연결·발행 상태를 읽은 뒤, `/Telemetry/Tags`의 자식 Prim을 `(Endpoint, Namespace URI, 식별자)`로 찾아볼 수 있게 한다. 각 샘플에는 값·단위 외에 표시명, 자료형, 측정 시각과 수신 시각도 들어 있다. 파일을 읽는 코드는 [telemetry.py](../hd_usda_translator/telemetry.py)에 있다.

## 다른 Kit 확장에서 사용

소비하는 확장의 `extension.toml`에 아래 의존성을 추가하고 두 확장을 같은 Kit의 검색 경로에 둔다.

```toml
[dependencies]
"hd.usda.translator" = {}
```

아래 예는 앞에서 읽은 `snapshot`에서 Stream 1 압력을 찾는다. `Measurement`의 네 필드는 대상(`target`), 측정 항목(`quantity`), 값(`value`), 단위(`unit`)다.

```python
from hd_usda_translator.measurements import iter_measurements

for m in iter_measurements(snapshot, timeout=10):
    if (m.target, m.quantity) == ("Stream 1", "Pressure"):
        if m.value is None:
            print(m.target, m.quantity, m.status)
        else:
            print(m.target, m.quantity, m.value, m.unit)
```

예제 파일에서는 `Stream 1 Pressure Stopped`가 출력된다. 수신 중이면 `value`로 실제 숫자를 받는다. 0은 정상값이며, 수신이 끊기거나 품질이 나쁘면 `value`가 `None`이고 `status`에 사유가 들어 있다. `quality`와 `received_at`도 조회할 수 있다.

계속 갱신되는 파일은 경로마다 `SnapshotFile(path)`을 한 번 만들고 같은 객체의 `read()`를 호출한다. 파일이 교체되면 새 스냅샷을 읽는다. 같은 경로에서 Endpoint가 바뀌면 파일을 다시 열어야 한다. 이 예제의 [_watch()](../hd_usda_translator/extension.py)는 1초마다 파일을 확인한다.

## 태그 선택과 표시

- [태그 선택 창](../hd_usda_translator/tag_selection.py)은 `snapshot.tags`에서 목록을 만들고 줄마다 선택한 Namespace URI와 식별자를 기억한다. 처음 표시할 다섯 태그는 [tags.json](../data/tags.json)에 있다.
- [측정값 파서](../hd_usda_translator/measurements.py)는 선택한 태그를 대상과 측정 항목으로 해석한다. 액체·기체 분율은 단위와 범위를 확인하고 %로 반환한다.
- [배지](../hd_usda_translator/badges.py)는 받은 측정값으로 문구를 만든다. [원문 보기](../hd_usda_translator/source_view.py)는 버튼을 누를 때 파일을 한 번 읽어, 같은 발행본 안에서 태그의 속성과 전체 원문을 보여 준다.
