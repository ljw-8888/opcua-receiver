# 구축된 시험 서버에서 OPC UA 데이터 받기

제공된 Windows·Ubuntu 수신기로 시험 서버에 접속하면 배관의 압력·온도 등 선택한 태그의 현재값을 받을 수 있다. 시험 서버는 HYSYS Excel의 항목과 기준값으로 구성한 모의 데이터를 제공한다. 실증설비 DCS 접속 정보와 현장 태그는 별도 확정 대상이다.

## 접속과 첫 수신

| 항목 | 시험 서버에서 쓸 값 |
|---|---|
| Endpoint URL | `opc.tcp://218.52.73.150:4840/hd/` (외부 접속용. 같은 내부망에서 시간 초과가 발생하면 담당자가 제공한 내부 Endpoint 사용) |
| 보안 정책 / 사용자 인증 | `None` / `Anonymous` (인증서·계정 입력 없이 접속) |
| 탐색 경로 | `Objects → Telemetry` |
| 압력 태그 예시 | Namespace URI `urn:hd:opcua:test:v1` · NodeId `s=Stream/1/Pressure` · 단위 `barG` |
| 온도 태그 예시 | 같은 Namespace URI · NodeId `s=Stream/1/Temperature` · 단위 `degC` |

1. **서버 연결** 탭에 Endpoint 전체를 붙여 넣고 **연결**을 누른다. 우측 상단의 **연결됨 · 수신 대기**는 서버 접속이 끝나고 태그를 고를 수 있다는 뜻이다.
2. 수신할 태그는 두 방법으로 고를 수 있다.
   - **서버에서 조회** — 왼쪽 **서버 항목 → Telemetry**에서 태그 목록을 열고 `Stream/1/Pressure`를 체크한다. Namespace URI와 NodeId는 수신기가 서버에서 가져온다.
   - **주소 직접 입력** — **태그 관리**에서 위 표의 Namespace URI와 NodeId를 입력하고 **등록**을 누른다. 위쪽 표에서 등록한 행을 선택하고 **↓ 수신할 태그 목록에 추가**를 누른다. 두 방식으로 고른 태그는 같은 수신 목록에 모인다.
3. **Excel 저장**에서 쓰기 가능한 폴더와 결과 파일명(예: `receive-test.xlsx`)을 지정한다. 저장 주기를 정하고 **수신·저장 시작**을 누른다.
4. 수신 중 태그 개수, 숫자로 표시되는 압력, 단위, 품질 `Good`, 수신 시각을 확인한다. 첫 수신 뒤 지정한 파일이 생성되고, 이후 그 파일의 결과 시트에 주기적으로 최신값이 갱신된다. 시험값은 시점에 따라 달라진다. Excel 저장만 멈출 수도 있다. [상세 조작 안내](receiver-guide.md)

## 수신 코드만 참고할 때

[한 태그를 구독하는 예제](receive_tag.py)는 제공된 수신기의 [Receiver](telemetry.py)를 사용한다. Python 3.12 가상환경의 `opcua-test` 폴더에서 실행한다. 아래 명령은 구축된 시험 서버의 Stream 1 압력을 받는다.

    python -m pip install asyncua==2.1.0 openpyxl==3.1.5
    python receive_tag.py "opc.tcp://218.52.73.150:4840/hd/"

다른 태그는 `--namespace`와 `--node`로 지정한다. 예제는 연결 → Namespace URI와 NodeId로 변수 확인 → 구독 → 첫 샘플 출력 → 연결 해제 순서로 동작한다. 출력에서 `identifier`는 NodeId, `value`는 수신값, `unit`은 단위, `quality`는 품질, `source_timestamp`와 `received_at`은 각각 측정 시각과 수신 시각이다. 값이 없거나 품질이 불량할 때도 상태를 확인할 수 있다. GUI 실행과 Excel 저장 없이 시험할 수 있다. 현재 공통 모듈이 `openpyxl`을 import하므로 예제 실행 환경에도 포함한다.

기존 시험 서버를 이용하는 사람은 서버를 설치할 필요가 없다. 자체 재현이 필요할 때만 같은 폴더에서 `python sender.py --host 127.0.0.1 --port 14845`로 로컬 서버를 실행하고, 다른 터미널에서 `python receive_tag.py opc.tcp://127.0.0.1:14845/hd/`를 실행한다. 이 주소는 두 프로그램을 같은 PC에서 실행하는 경우에만 사용한다.

## 상대 업체에 전달하는 데이터

| 자료 | 용도 |
|---|---|
| 고정 HYSYS Excel (`Process data from HYSYS_R01.xlsx`, 별도 제공 자료) | 시각화 업체가 보유한 기준 데이터로 표현을 정의하고 시험한다. 시험 서버 접속과 독립적으로 진행할 수 있다. |
| [수신기 출력 Excel 예시](sample-pressure.xlsx) | 시험 서버에서 실제로 구독한 압력 한 건. 수신기가 생성하는 파일의 열과 단위를 확인할 때 사용한다. |
| 수신기 소스와 시험 서버 Endpoint | 다른 클라이언트 또는 Omniverse Extension에 OPC UA 수신 기능이 필요할 때, 접속·탐색·구독 방법을 참고한다. |

시각화 정의와 구현은 해당 업체가 담당한다. 고정 데이터로 시험한 후 **수신기를 별도로 둘지, Extension 안에서 직접 받을지** 협의한다. 수신값을 **Excel·CSV 같은 파일로 전달할지, USD 레이어에 직접 반영할지**도 이때 정한다. 현재 제공하는 Excel 출력은 시험 가능한 한 가지 방식이다.
