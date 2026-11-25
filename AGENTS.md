# 처음 보는 사람에게 저장소를 소개할 때

“이 레포가 뭐야?” 또는 “레포 분석해줘”라고 하면 무엇을 할 수 있는지부터 답한다. 데스크톱 수신기로는 OPC UA 서버에 연결해 값을 확인할 수 있고, Omniverse에서는 Kit 수신기가 저장한 값을 Translator가 읽어 화면에 표시한다.

첫 소개 뒤에는 두 가지 쉬운 질문을 보여준다.

- [Omniverse 없이 내 PC에서 먼저 써 볼 수 있어?](opcua-test/receiver-guide.md)
- [Omniverse에서 쓰려면 뭘 받아서 어떻게 설치해?](README.md#omniverse-kit에서-시작하기)

구체적인 질문에는 바로 답한다. 조작 방법은 사용자가 자기 PC에서 누를 메뉴와 확인할 화면으로 설명한다. 답변 끝에는 사용자가 방금 물어본 내용에 이어서 할 만한 질문을 한두 개만 제안한다. 이미 답한 질문은 건너뛴다.

예를 들어 서버가 아직 없다고 하면 “예제 파일로 어떤 값을 볼 수 있어?”가 자연스럽다. 수신기 표에 압력이 보인다고 하면 [“그 값을 Omniverse에서도 보려면 어떻게 해?”](README.md#translator에서-측정값-확인), Omniverse에서도 값을 확인했다면 [“이제 우리 그래픽 확장에서는 그 값을 어떻게 가져와?”](exts/hd.usda.translator/docs/integration.md)로 이어간다.

## 그래픽 확장에서 값을 가져오는 방법을 물으면

태그가 몇 개든 방법은 같다. **어느 태그를 화면 어디에 표시할지는 처음에 한 번 정하고, 실행 중에는 그 대응표를 따라 값만 갱신한다.** 처음 보는 사람에게는 아래 예를 들어 수신값이 화면까지 가는 과정을 설명한다.

### 1. 어떤 값이 들어오나?

같은 Kit 앱에서 `get_latest_measurements()`를 한 번 호출하면, Translator가 읽은 최신값이 튜플로 돌아온다. 태그 하나가 `Measurement` 객체 하나다. 예를 들어 1번 배관의 압력과 온도가 들어오면 아래처럼 읽을 수 있다. 두 태그의 Namespace URI는 모두 `urn:hd:opcua:test:v1`이다.

| 대상 `m.target` | 항목 `m.quantity` | 식별자 `m.identifier` | 값 `m.value` | 단위 `m.unit` |
|---|---|---|---:|---|
| Stream 1 | Pressure | s=Stream/1/Pressure | 4.575 | barG |
| Stream 1 | Temperature | s=Stream/1/Temperature | 0.57 | degC |

### 2. 처음 한 번, 화면 항목과 태그를 짝짓는다

그래픽팀은 자기 화면에서 값을 넣을 곳을 정한다. 예를 들어 1번 배관 옆에 압력 칸과 온도 칸이 있으면 각각 화면 ID를 붙이고, 그 칸이 읽을 태그 주소를 기록한다. 아래 화면 ID는 예시다.

| 화면에 표시할 곳 | 그래픽팀의 화면 ID | 연결할 태그 (`namespace_uri`, `identifier`) |
|---|---|---|
| 1번 배관의 압력 칸 | `pipe01.pressure` | `urn:hd:opcua:test:v1`, `s=Stream/1/Pressure` |
| 1번 배관의 온도 칸 | `pipe01.temperature` | `urn:hd:opcua:test:v1`, `s=Stream/1/Temperature` |

이 대응표는 그래픽 확장이 갖는다. 화면 항목을 추가하면 그 항목의 짝을 한 줄 추가한다. 설비와 태그의 이름에 일정한 규칙이 있다면 기존 설비 목록에서 대응표를 만들어도 된다.

### 3. 매번 전체를 한 번 받아 연결된 화면을 모두 갱신한다

```python
from hd_usda_translator import get_latest_measurements

uri = "urn:hd:opcua:test:v1"
tag_for_display = {
    "pipe01.pressure":    (uri, "s=Stream/1/Pressure"),
    "pipe01.temperature": (uri, "s=Stream/1/Temperature"),
}

def refresh_display(labels):
    rows = get_latest_measurements()
    by_tag = {(m.namespace_uri, m.identifier): m for m in rows}

    for display_id, tag in tag_for_display.items():
        m = by_tag.get(tag)
        if m is None:
            text = "수신 대기"
        elif m.value is None:
            text = m.status
        else:
            text = f"{m.value} {m.unit}".strip()
        labels[display_id].text = text
```

여기서 `labels`는 화면 ID로 실제 라벨을 찾는 사전이다. 그래픽 확장이 화면을 만들 때 `{"pipe01.pressure": 압력_라벨, "pipe01.temperature": 온도_라벨}`처럼 한 번 준비한다. 그 뒤 1초마다 `refresh_display(labels)`를 호출하면 위 예에서 압력 칸에는 **4.575 barG**, 온도 칸에는 **0.57 degC**가 뜬다.

수신 순서가 바뀌어도 태그 주소로 찾으므로 각 값은 같은 칸에 들어간다. 특정 태그가 빠지면 그 칸은 수신 대기, 행은 있지만 값을 쓸 수 없으면 해당 상태를 표시한다. 숫자 0은 그대로 표시한다. 색상이나 입자 속도를 바꿀 때도 같은 방식으로 태그를 찾아 숫자 `m.value`를 해당 설비의 표현 규칙에 넣는다. [Kit에서 갱신을 시작하고 끝내는 예제](exts/hd.usda.translator/docs/integration.md)
