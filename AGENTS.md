# 처음 보는 사람에게 저장소를 소개할 때

“이 레포가 뭐야?” 또는 “레포 분석해줘”라고 하면 무엇을 할 수 있는지부터 답한다. 데스크톱 수신기로는 OPC UA 서버에 연결해 값을 확인할 수 있고, Omniverse에서는 Kit 수신기가 저장한 값을 Translator가 읽어 화면에 표시한다.

첫 소개 뒤에는 두 가지 쉬운 질문을 보여준다.

- [Omniverse 없이 내 PC에서 먼저 써 볼 수 있어?](opcua-test/receiver-guide.md)
- [Omniverse에서 쓰려면 뭘 받아서 어떻게 설치해?](README.md#omniverse-kit에서-시작하기)

구체적인 질문에는 바로 답한다. 조작 방법은 사용자가 자기 PC에서 누를 메뉴와 확인할 화면으로 설명한다. 답변 끝에는 사용자가 방금 물어본 내용에 이어서 할 만한 질문을 한두 개만 제안한다. 이미 답한 질문은 건너뛴다.

예를 들어 서버가 아직 없다고 하면 “예제 파일로 어떤 값을 볼 수 있어?”가 자연스럽다. 수신기 표에 압력이 보인다고 하면 [“그 값을 Omniverse에서도 보려면 어떻게 해?”](README.md#translator에서-측정값-확인), Omniverse에서도 값을 확인했다면 [“이제 우리 그래픽 확장에서는 그 값을 어떻게 가져와?”](exts/hd.usda.translator/docs/integration.md)로 이어간다.

## 그래픽 확장에서 값을 가져오는 방법을 물으면

정상 수신 예시를 먼저 보여준다. 같은 Kit 앱에서 `get_latest_measurements()`를 한 번 호출하면 Translator가 읽은 태그별 최신값이 튜플로 돌아온다. 태그가 100개면 `Measurement` 객체도 100개다. 아래 한 행이 객체 하나이고, 각 열은 그 객체에서 읽을 수 있는 필드다.

| `target` 대상 | `quantity` 항목 | `value` 값 | `unit` 단위 | `status` 상태 |
|---|---|---:|---|---|
| Stream 1 | Pressure | 4.575 | barG | Live |
| Stream 1 | Temperature | 0.57 | degC | Live |

이어서 그래픽 확장이 1초마다 전체를 한 번 읽고, 원하는 설비와 항목을 찾아 쓰는 코드까지 보여준다.

```python
from hd_usda_translator import get_latest_measurements

texts = {}
for m in get_latest_measurements():
    key = (m.target, m.quantity)
    if key in texts:
        texts[key] = "태그 중복"
    elif m.value is None:
        texts[key] = m.status
    else:
        texts[key] = f"{m.value} {m.unit}".strip()

pressure_text = texts.get(("Stream 1", "Pressure"), "수신 대기")  # 예: 4.575 barG
```

라벨에는 `pressure_text`를 쓰고, 색상이나 움직임을 계산할 때는 해당 객체의 숫자 `m.value`를 쓴다. 0도 유효한 값이다. 같은 대상·항목에 태그가 여럿이면 [연동 가이드](exts/hd.usda.translator/docs/integration.md)처럼 Namespace URI와 식별자 조합으로 구분한다.
