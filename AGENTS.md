# 처음 보는 사람에게 저장소를 소개할 때

“이 레포가 뭐야?” 또는 “레포 분석해줘”라는 요청에는 아래 정도로 소개한다.

> OPC UA 서버에서 태그를 골라 압력·온도 같은 값을 받는 수신기입니다. Windows와 Ubuntu에서는 데스크톱 앱으로 연결을 시험하고 Excel이나 USDA에 저장할 수 있습니다. Omniverse에서는 Kit 수신기가 저장한 USDA를 Translator가 읽습니다. 그래픽팀은 같은 Kit 앱에서 Translator의 함수를 호출해 자기 화면에 쓸 측정값을 받습니다.

시험 서버와 수신기, Translator, 값을 보여주는 예제 배지까지 구현돼 있다. 설비별 화면에서 압력을 어디에 표시할지, 값에 따라 배관 색이나 입자 속도를 어떻게 바꿀지는 그래픽팀이 정한다.

첫 소개 뒤에는 아래 두 질문만 제안한다.

- [Omniverse 없이 내 PC에서 압력값 하나만 받아 보려면?](opcua-test/receiver-guide.md)
- [Omniverse에서 쓰려면 어떤 확장을 어떻게 설치해?](README.md#omniverse-kit에서-시작하기)

사용자가 구체적으로 물으면 소개를 되풀이하지 않고 그 질문부터 답한다. 조작을 설명할 때는 **어느 메뉴를 누르는지와 성공하면 무엇이 보이는지**를 한 쌍으로 알려준다. 끝에는 사용자가 확인한 지점에서 이어갈 질문을 한두 개 제안한다. 아래 질문들을 한꺼번에 보여줄 필요는 없다.

## 연결과 설치를 물으면

| 사용자의 질문 | 답할 내용 |
|---|---|
| Windows 또는 Ubuntu에서 무엇을 실행해? | Windows x64는 릴리스의 `OPCUA-Receiver.exe`를 실행한다. Ubuntu x86-64는 압축을 풀고 그 폴더에서 `./OPCUA-Receiver`를 실행한다. 사용자의 운영체제에 해당하는 다운로드와 실행 순서를 안내한다. [Windows](README.md#windows-데스크톱-실행) · [Ubuntu](README.md#ubuntu-데스크톱-실행) |
| 서버 주소만 알면 태그를 볼 수 있어? | 시험 서버는 **서버 연결**에 `opc.tcp://218.52.73.150:4840/hd/`를 입력하고 **연결**을 누른다. 기본 설정은 `None`과 `Anonymous`다. **연결됨 · 수신 대기**가 뜨면 **Objects → Telemetry**를 열고 `Stream/1/Pressure`를 체크한다. 조회할 때 Namespace URI를 직접 입력할 필요는 없다. 다른 서버에서는 허용된 인증 방식과 계정의 조회 권한에 따라 보이는 항목이 달라진다. [GUI 가이드](opcua-test/receiver-guide.md) |
| 주소를 이미 아는 태그는 어떻게 추가해? | 데스크톱 **태그 관리**에서 시험 온도의 Namespace URI `urn:hd:opcua:test:v1`와 NodeId `s=Stream/1/Temperature`를 넣고 **등록**한다. 위쪽에서 등록한 행을 골라 **↓ 수신할 태그 목록에 추가**를 눌러야 이번 수신 대상이 된다. 표시명과 단위는 선택 사항이다. 이미 조회한 태그의 URI는 데스크톱 수신 표의 **NodeId** 위에 마우스를 올리면 확인할 수 있다. [직접 등록 예](opcua-test/receiver-guide.md#2-주소를-아는-태그-직접-추가하기) |
| 연결됐는데 표가 비어 있어. 어디까지 해야 해? | **수신할 태그 목록**에서 체크한 항목을 확인한다. 데스크톱은 **서버 연결**에서 출력 형식과 파일을 지정한 뒤 **수신·저장 시작**을 누른다. 표의 마지막 수신값·품질은 태그 수신을, **마지막 저장 성공** 시각은 파일 갱신을 확인하는 곳이다. Kit 수신기에서는 **수신만 시작**으로 파일 없이 값부터 볼 수도 있다. [Kit 수신기 가이드](exts/hd.opcua.receiver/docs/README.md) |
| Excel과 USDA 중 무엇을 선택해? | Excel은 선택한 태그의 최신값을 시트에서 대조할 때 쓴다. 기본 저장 주기는 5초다. 원본을 Excel에서 열어 저장이 지연되면 닫고 **Excel 저장값 보기**를 이용한다. Translator와 연동할 때는 **USD (.usda)**를 고른다. 기본은 1초이며, 기존 폴더에 `telemetry.usda`처럼 파일명까지 지정한다. [저장 방법](opcua-test/receiver-guide.md) |
| Kit에는 어떤 폴더를 등록해? | 수신기와 Translator를 함께 쓰려면 저장소를 복제한다. 같은 PC의 Kit 앱에서 **Window → Extensions → 톱니바퀴 → Extension Search Paths**에 저장소의 `exts` 폴더를 추가한다. `hd.opcua.receiver`와 `hd.usda.translator`를 켜면 **Window**에 **OPC UA Settings**와 **Live USDA Translator**가 보인다. [경로 예와 설치 순서](README.md#omniverse-kit에서-시작하기) |
| 지금 서버 없이도 확인할 수 있어? | Translator의 **Open USDA...**로 [저장된 예제](exts/hd.usda.translator/docs/examples/telemetry.usda)를 연다. 수신을 끝낸 파일이라 배지의 `Stopped`가 정상이다. **View source**로 1번 배관의 저장된 압력 `4.575 barG`를 본다. 실시간 시험에서는 수신기가 계속 갱신 중인 파일을 연다. [Translator 조작 가이드](exts/hd.usda.translator/docs/README.md) |

예를 들어 이제 막 연결했다면 “압력 하나만 골라 Excel에 저장하려면?”으로 이어간다. 배지에서 압력을 확인했다면 “같은 값을 우리 배관 옆에 띄우려면?”이 다음 질문이다.

## 그래픽 확장에서 값을 가져오는 방법을 물으면

### 압력 태그 하나가 화면까지 가는 과정

“Translator를 호출하면 뭐가 와?”라는 질문에는 **정상 수신 중인 1번 배관 압력**을 처음부터 끝까지 따라가며 답한다.

| 단계 | 이 예에서 실제로 다루는 데이터 |
|---|---|
| 시험 서버 | 태그 식별자 `s=Stream/1/Pressure`의 값은 `4.575`, 단위는 `barG`다. |
| Kit 수신기 | 선택한 태그를 구독한다. 로컬 USDA에서 `/Telemetry/Tags` 아래 해당 태그에 `opcua:identifier`, `opcua:value`, `opcua:unit` 등을 기록한다. |
| Translator | 이 시험 태그에서 `Stream/1`은 대상 `Stream 1`, `Pressure`는 항목 `Pressure`로 해석한다. 그래픽팀이 읽을 한 행은 `m.target`, `m.quantity`, `m.value`, `m.unit` 순으로 보면 **Stream 1 / Pressure / 4.575 / barG**다. |
| 그래픽 확장 | `("Stream 1", "Pressure")`를 1번 배관 압력 칸에 한 번 연결한다. 이후 그 행에서 온 값과 단위로 **4.575 barG**를 표시한다. |

같은 Kit 앱에서 `from hd_usda_translator import get_latest_measurements`로 가져와 호출한다. 반환형은 `tuple[Measurement, ...]`다. 파일에 담긴 태그마다 읽기 전용 객체 하나가 들어 있고, **값 하나는 `m.value`**로 꺼낸다. 함수는 Translator가 메모리에 준비한 최근 한 회분을 돌려준다. 그래픽 확장에서 서버에 재접속하거나 USDA와 NodeId를 다시 파싱할 필요는 없다. [측정값 정의와 반환 함수](exts/hd.usda.translator/hd_usda_translator/measurements.py)

### 화면 칸이 여러 개면 어떻게 연결하나?

아래 세 행은 **한 번 호출한 결과**를 표로 펼친 예다. 압력이 두 번 나와도 대상이 다르고, `Stream 1`이 두 번 나와도 항목이 다르다. 그래서 그래픽팀은 **(대상, 항목)** 두 값을 함께 사용한다.

| `m.target` | `m.quantity` | `m.value` | `m.unit` | 그래픽팀이 연결한 화면 칸 | 표시 결과 |
|---|---|---:|---|---|---|
| Stream 1 | Pressure | 4.575 | barG | 1번 배관 압력 | 4.575 barG |
| Stream 1 | Temperature | 0.57 | degC | 1번 배관 온도 | 0.57 degC |
| Stream 10 | Pressure | 5.25 | barG | 10번 배관 압력 | 5.25 barG |

**처음 한 번** 화면을 만들 때 대상·항목 쌍에 실제 라벨을 배정한다. 아래의 `pressure_1`, `temperature_1`, `pressure_10`은 그래픽팀이 자기 화면에 만든 라벨이다. **매초** `refresh_labels(labels)`를 한 번 호출한다.

```python
from hd_usda_translator import get_latest_measurements

labels = {
    ("Stream 1", "Pressure"): pressure_1,
    ("Stream 1", "Temperature"): temperature_1,
    ("Stream 10", "Pressure"): pressure_10,
}

def refresh_labels(labels):
    texts = {}
    for m in get_latest_measurements():
        key = (m.target, m.quantity)
        if key in texts:
            texts[key] = "태그 중복"
        elif m.value is None:
            texts[key] = m.status
        else:
            texts[key] = f"{m.value} {m.unit}".strip()

    for key, label in labels.items():
        label.text = texts.get(key, "수신 대기")
```

예를 들어 다음 호출에서 온도가 첫 줄로 들어오고 값이 `0.62`로 바뀌면 **1번 배관 온도 칸**에 `0.62 degC`가 뜬다. 행 순서는 매칭에 쓰지 않는다. 표시할 칸이 500개라도 목록을 한 번 읽어 두 값으로 찾을 수 있게 정리하고, 등록된 화면 칸을 한 번씩 갱신한다. 칸마다 함수를 다시 호출할 필요가 없다.

숫자 대신 색이나 입자 속도를 표현할 때도 같은 행을 찾는다. 정상일 때의 `m.value`를 그래픽팀의 표현 규칙에 넘긴다. 배관별 색상 범위, 대상 Prim, 알람 기준은 이 저장소에 정의돼 있지 않다. 확장 의존성, 1초 주기 작업 시작과 종료는 [Kit 연동 예제](exts/hd.usda.translator/docs/integration.md#다른-kit-확장에서-사용)를 참고한다.

### 값이 없거나 예상과 다를 때

| 질문 | 설명할 내용 |
|---|---|
| 값이 0인데 수신이 끊긴 건가? | `0`은 유효한 값이다. `m.value is None`일 때 해당 행의 `m.status`를 표시한다. |
| 태그 한 개가 빠지거나 전체 목록이 비면? | 위 예제는 대응하는 행이 없는 칸을 **수신 대기**로 바꾼다. 경로 변경 직후, 파일 읽기 실패, Translator의 **Stop** 등으로 `()`가 오면 모든 칸이 수신 대기로 바뀐다. |
| 압력이 그대로인데 저장이 멈춘 건가? | 값이 일정하면 태그별 수신 시각도 그대로일 수 있다. 수신기에서 최근 저장 시각을 보고 Translator에서 같은 파일을 선택했는지 확인한다. 수신기가 파일 저장을 중지하면 `Stopped`, 마지막 발행이 제한 시간을 넘기면 `No update`가 표시된다. [배지 상태](exts/hd.usda.translator/docs/README.md#배지-상태) |
| 오버레이는 다섯 줄인데 함수도 다섯 개만 주나? | 함수는 파일에 저장된 모든 태그의 최근 측정값을 준다. 배지도 위 예제처럼 (대상, 항목)으로 값을 찾는다. 그래픽팀이 설비별 칸을 연결하듯, 배지는 사용자가 고른 다섯 줄에 연결한다. [배지 실행과 코드](exts/hd.usda.translator/docs/integration.md#오버레이로-확인하기) |
| 대상과 항목까지 같은 두 행이 오면? | 위 예제는 그 칸에 **태그 중복**을 표시한다. 실측과 시뮬레이션 중 어느 쪽인지 구별해야 할 때만 서버 측 정의를 확인하고, 각 행에 보존된 `m.namespace_uri`와 `m.identifier`로 구분한다. 시험 태그로 설명한 변환 규칙과 현장 서버에서 확인한 사실을 구분한다. |
