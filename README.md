# OPC UA 수신기

OPC UA 서버에 연결하면 수신 가능한 태그를 찾아 트리와 표로 보여 준다. 필요한 태그를 선택해 값·단위·품질·수신 시각을 확인하고, 지정한 주기마다 태그별 최신값을 Excel(`.xlsx`)에 저장할 수 있다.

| 사용 환경 | 시작 방법 |
|---|---|
| Windows x64 데스크톱 | [Windows 실행 파일](https://github.com/ljw-8888/opcua-receiver/releases/latest/download/OPCUA-Receiver.exe)을 내려받아 실행한다. |
| Ubuntu x86-64 데스크톱 | [Ubuntu 배포 파일](https://github.com/ljw-8888/opcua-receiver/releases/latest/download/OPCUA-Receiver-Ubuntu-x86_64.tar.gz)을 내려받아 아래 명령으로 압축을 푼다. |
| Omniverse USD Composer 또는 다른 GUI Kit 앱 | 이 저장소의 `exts`를 등록하고 **OPC UA Receiver**를 켠다. [확장 설치 및 사용 가이드](exts/hd.opcua.receiver/docs/README.md) |

## Omniverse Kit에서 시작하기

Python 3.12를 내장한 Windows·Linux x86-64 GUI Kit 앱용 확장이다. Ubuntu에서는 Kit 110.4.1에서 실행을 검증했다. Windows용 의존성도 포함하며 Windows Kit에서의 실행은 아직 검증 전이다.

1. `git clone https://github.com/ljw-8888/opcua-receiver.git`을 실행하거나 GitHub의 **Code → Download ZIP**으로 받아 압축을 푼다.
2. Kit의 **Window → Extensions**에서 확장 검색 경로에 내려받은 저장소의 `exts` 폴더를 추가한다. 검색 경로 바로 아래에 `hd.opcua.receiver` 폴더가 보여야 한다.
3. **OPC UA Receiver**를 검색해 활성화한다. 자동으로 열린 설정 창에서 서버 주소를 입력하고 **연결**을 누른다. 다음 실행에도 창을 띄우려면 **Autoload**를 켠다. 닫은 창은 **Window → OPC UA Settings**에서 다시 연다.
4. 왼쪽에서 서버 그룹을 펼치고 오른쪽에서 받을 태그를 체크한다. 이름이나 NodeId로 검색한 뒤 **전체 선택**을 누르면 현재 그룹의 검색 결과를 모든 페이지에 걸쳐 선택한다. **수신만 시작**을 누르면 빈 스테이지에서도 실시간 값이 표시된다.
5. Excel에도 저장하려면 결과 파일(`.xlsx`)과 저장 주기를 지정하고 **수신·저장 시작**을 누른다. **Excel 저장 중지**를 누르면 화면 수신은 계속된다.

다른 Kit 앱에 설정 버튼을 붙일 때는 `show_settings()`로 창을 열고, `get_latest_samples()`로 3D 표시에 사용할 최신값을 읽을 수 있다. [버튼 및 수신값 연동 예제](exts/hd.opcua.receiver/docs/README.md#기본-gui-버튼-및-3d-표시와-연결)

## Ubuntu 데스크톱 실행

배포 파일을 내려받은 폴더에서 터미널을 연다. Windows와 Ubuntu 데스크톱 배포본에는 Python이 포함돼 있다.

```bash
mkdir -p opcua-receiver-app
tar -xzf OPCUA-Receiver-Ubuntu-x86_64.tar.gz -C opcua-receiver-app
cd opcua-receiver-app
./OPCUA-Receiver
```

앱 메뉴에 등록하려면 같은 폴더에서 `bash install-launcher.sh`를 실행한다.

## 시험 서버 접속

**서버 연결** 탭의 **서버 주소 (Endpoint URL)**에 아래 주소를 넣고 **연결**을 누른다.

```text
opc.tcp://218.52.73.150:4840/hd/
```

시험 서버는 기본 설정인 `None / Anonymous`를 사용하므로 주소만 입력하면 된다. 오른쪽 위에 **연결됨 · 수신 대기**가 뜨면 태그를 고를 수 있다. 계정이나 인증서가 필요한 서버는 연결 전에 **보안 및 인증** 탭에서 설정한다.

내부망에서 위 공인 주소로 접속하다 시간 초과가 뜨면 **연결 해제**를 누르고 서버 담당자가 알려 준 내부 Endpoint로 다시 연결한다.

### 목록에서 태그 선택

1. 왼쪽 **서버 항목**에서 **Objects → Telemetry**를 누른다. 오른쪽에 시험 서버의 태그가 보인다.
2. **수신 태그 검색**에 `Stream/1/Pressure`를 입력하고 압력 태그 왼쪽의 체크박스를 누른다. 검색은 현재 열어 둔 목록 안에서만 된다.
3. **수신할 태그 목록 (1)**을 누르면 선택한 압력 태그가 보인다. 압력만 받으려면 [수신 시작과 Excel 저장](#수신-시작과-excel-저장)으로 넘어간다.

### 태그 주소 직접 입력

서버에 연결하고 **태그 관리** 탭을 연다. 시험 서버의 Stream 1 온도를 등록하려면 아래처럼 입력한다.

| 입력칸 | Stream 1 온도 예시 |
|---|---|
| Namespace URI | `urn:hd:opcua:test:v1` |
| NodeId | `s=Stream/1/Temperature` |
| 표시명 (선택) | 비워 두면 `Stream/1/Temperature`로 표시된다. `Stream 1 온도`처럼 원하는 이름을 써도 된다. |
| 단위 (선택) | 비워 두면 서버에서 읽은 `degC`가 표시된다. 서버에 단위 정보가 없으면 빈칸으로 남는다. |

**등록**을 누르면 위쪽 **등록한 태그**에 온도가 나타난다. 그 행을 선택하고 **↓ 수신할 태그 목록에 추가**를 누른다. 아래쪽 목록에 온도가 보이면 이번 수신 대상에 들어간 것이다.

### 수신 시작과 Excel 저장

1. **서버 연결 → 수신할 태그 목록**에서 받을 태그를 확인한다.
2. **파일 선택**을 누르고 저장할 폴더와 파일 이름을 지정한다. 예를 들어 `stream-check.xlsx`를 입력하면 첫 수신 때 파일이 생긴다. 기존 파일을 고르면 그 파일의 결과 시트를 갱신한다.
3. **Excel 저장 주기 (초)**에 `5`를 입력하고 **수신·저장 시작**을 누른다. 압력 태그 한 개를 골랐다면 오른쪽 위에 **수신 중 1개**가 뜨고, 압력 행에 수신값과 품질이 표시된다.

**Excel 저장값 보기**를 누르면 방금 저장한 값을 볼 수 있다. 압력이 일정할 때는 **마지막 저장 성공 (UTC)** 시각으로 파일 갱신 여부를 확인한다.

[GUI 가이드](opcua-test/receiver-guide.md) · [Excel 예시](opcua-test/sample-pressure.xlsx)

## 데스크톱 수신기를 소스로 실행

Git과 Python 3.12가 필요하다.

<details>
<summary>Windows (PowerShell)</summary>

```powershell
git clone https://github.com/ljw-8888/opcua-receiver.git
cd opcua-receiver\opcua-test
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-receiver.txt
.\.venv\Scripts\python.exe receiver_gui.py
```

압력 태그 하나를 터미널에서 받으려면 같은 폴더에서 실행한다.

```powershell
.\.venv\Scripts\python.exe receive_tag.py "opc.tcp://218.52.73.150:4840/hd/"
```

</details>

<details>
<summary>Ubuntu (Bash)</summary>

Python 3.12의 `venv` 모듈이 필요하다.

```bash
git clone https://github.com/ljw-8888/opcua-receiver.git
cd opcua-receiver/opcua-test
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-receiver.txt
bash run-receiver.sh
```

압력 태그 하나를 터미널에서 받으려면 같은 폴더에서 실행한다.

```bash
.venv/bin/python receive_tag.py "opc.tcp://218.52.73.150:4840/hd/"
```

</details>

## 수신 코드

서버 연결, 태그 조회와 구독은 `telemetry.py`의 `Receiver` 클래스에 있다. `receive_tag.py`는 이 클래스로 압력 태그 하나를 받는 예제다. [OPC UA 수신 인계서](opcua-test/opcua-handoff.md) · [수신 코드](opcua-test/telemetry.py) · [예제](opcua-test/receive_tag.py)

Claude나 Codex에서 확인하려면 복제한 `opcua-receiver` 폴더를 열고 아래처럼 요청한다.

> README.md와 opcua-test/opcua-handoff.md를 읽고, 내 운영체제에서 receive_tag.py로 시험 서버의 Stream/1/Pressure를 한 번 받는 명령을 알려줘.

<a id="asyncua-rebuild"></a>
<a id="테스트와-빌드"></a>

## 데스크톱 수신기 빌드

Python 3.12(x64)가 필요하다. Git으로 복제한 저장소나 [v0.1.2 릴리스](https://github.com/ljw-8888/opcua-receiver/releases/tag/v0.1.2)의 `opcua-receiver-0.1.2-source.zip`을 푼 폴더에서 `opcua-test`로 들어간다.

두 배포본에는 시험 태그와 HYSYS 기준값을 담은 `data.json`이 포함된다. 아이콘 원본을 바꿨다면 빌드 전에 가상환경에서 `python icons/build_icon.py`를 실행한다.

기본 빌드는 PyPI의 `asyncua 2.1.0`을 사용한다. 로컬 소스를 사용하려면 릴리스의 `asyncua-2.1.0.tar.gz`를 **수신기 프로젝트 폴더와 같은 상위 폴더**에 풀어 둔다. 아래 명령에서 `../../asyncua-2.1.0`은 그 소스 폴더를 가리킨다.

### Windows · PowerShell

`opcua-test`에서 빌드 환경을 준비한다.

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements-receiver.txt PyInstaller==6.22.3
```

로컬 `asyncua`를 사용할 때만 다음 명령을 실행한다. 라이브러리 코드를 편집한 뒤에도 이 명령으로 가상환경에 반영한다.

```powershell
& $python -m pip install --force-reinstall --no-deps ..\..\asyncua-2.1.0
```

같은 창에서 테스트와 빌드를 실행한다. 결과 파일은 `dist\OPCUA-Receiver.exe`다.

```powershell
& $python -m pip check
& $python -m unittest test_core test_receiver_gui
& $python -m PyInstaller --clean --noconfirm --distpath ../dist --workpath ../build receiver.spec
```

### Ubuntu · 터미널

Python 3.12의 `venv` 모듈이 필요하다. `opcua-test`에서 빌드 환경을 준비한다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-receiver.txt PyInstaller==6.22.3
```

로컬 `asyncua`를 사용할 때만 다음 명령을 실행한다. 라이브러리 코드를 편집한 뒤에도 같은 명령을 쓴다.

```bash
.venv/bin/python -m pip install --force-reinstall --no-deps ../../asyncua-2.1.0
```

같은 터미널에서 테스트와 빌드를 실행한다. 결과 파일은 `dist/OPCUA-Receiver`다.

```bash
.venv/bin/python -m pip check
.venv/bin/python -m unittest test_core test_receiver_gui
.venv/bin/python -m PyInstaller --clean --noconfirm --distpath ../dist --workpath ../build receiver.spec
```

실행할 때 `libEGL.so.1` 오류가 뜨면 `sudo apt install libegl1`로 Qt에 필요한 라이브러리를 설치한다. 앱 메뉴 등록 스크립트와 아이콘까지 함께 배포하려면 `opcua-test`에서 압축한다.

```bash
tar -czf ../dist/OPCUA-Receiver-Ubuntu-x86_64.tar.gz -C ../dist OPCUA-Receiver -C ../opcua-test install-launcher.sh icons/opcua-receiver.svg
```

## 라이선스

Windows와 Ubuntu 배포본에 포함된 `asyncua 2.1.0`에는 GNU LGPL v3 이상이 적용된다. [사용 고지](licenses/asyncua-NOTICE.txt) · [LGPL v3 전문](licenses/LGPL-3.0.txt) · [GPL v3 전문](licenses/GPL-3.0.txt)

Kit 확장에도 `asyncua` 고지와 라이선스, 동봉한 글꼴의 라이선스가 포함된다. 확장을 다른 팀에 전달할 때는 `exts/hd.opcua.receiver` 폴더 전체를 배포한다. [확장 패키징 방법](exts/hd.opcua.receiver/docs/README.md#패키지-유지보수) · [글꼴 라이선스](exts/hd.opcua.receiver/data/FONT-LICENSE.txt)
