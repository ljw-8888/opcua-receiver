# OPC UA 수신기

OPC UA 서버에서 태그를 골라 실시간 값과 단위, 품질, 수신 시각을 확인한다. Excel 저장을 켜면 지정한 주기마다 태그별 최신값을 `.xlsx` 파일에 기록한다.

| 사용 환경 | 시작 방법 |
|---|---|
| [1. Windows x64 데스크톱](#windows-데스크톱-실행) | 실행 파일(`.exe`)을 내려받아 실행한다. |
| [2. Ubuntu x86-64 데스크톱](#ubuntu-데스크톱-실행) | 배포 파일(`.tar.gz`)의 압축을 풀고 실행한다. |
| [3. Omniverse USD Composer 또는 다른 GUI Kit 앱](#omniverse-kit에서-시작하기) | 저장소의 `exts` 폴더를 등록하고 **OPC UA Receiver** 확장을 켠다. |

## Windows 데스크톱 실행

`OPCUA-Receiver.exe`를 내려받아 더블클릭한다. [Windows 실행 파일 다운로드](https://github.com/ljw-8888/opcua-receiver/releases/latest/download/OPCUA-Receiver.exe)

## Ubuntu 데스크톱 실행

배포 파일을 내려받은 폴더에서 터미널을 열고 다음 명령을 실행한다. [Ubuntu 배포 파일 다운로드](https://github.com/ljw-8888/opcua-receiver/releases/latest/download/OPCUA-Receiver-Ubuntu-x86_64.tar.gz)

```bash
mkdir -p opcua-receiver-app
tar -xzf OPCUA-Receiver-Ubuntu-x86_64.tar.gz -C opcua-receiver-app
cd opcua-receiver-app
./OPCUA-Receiver
```

앱 메뉴에 등록하려면 같은 폴더에서 `bash install-launcher.sh`를 실행한다.

## [Windows·Ubuntu 수신기 GUI 가이드](opcua-test/receiver-guide.md)

## Omniverse Kit에서 시작하기

USD Composer 등 Python 3.12가 내장된 x86-64용 Kit 앱에서 사용한다. [Kit 확장 사용 가이드](exts/hd.opcua.receiver/docs/README.md)

1. `git clone https://github.com/ljw-8888/opcua-receiver.git`으로 저장소를 받거나 GitHub의 **Code → Download ZIP**으로 내려받아 압축을 푼다.
2. Kit의 **Window → Extensions**를 열고 확장 검색 경로에 저장소의 `exts` 폴더를 추가한다.
3. **OPC UA Receiver**를 찾아 켠다. 설정 창이 열리면 서버 주소를 입력하고 **연결**을 누른다. 다음 실행부터 자동으로 열려면 **Autoload**를 켠다.
4. 왼쪽에서 그룹을 펼치고 오른쪽에서 받을 태그를 고른다. **수신만 시작**을 누르면 USD를 열기 전에도 값이 보인다.
5. Excel로 저장하려면 결과 파일(`.xlsx`)과 저장 주기를 지정하고 **수신·저장 시작**을 누른다.

설정 창은 **Window → OPC UA Settings**에서 다시 연다. 다른 Kit 앱에서 설정 버튼을 추가하거나 3D 화면에 수신값을 표시할 때는 확장 API를 사용한다. [설정 버튼 및 수신값 연동 예제](exts/hd.opcua.receiver/docs/README.md#기본-gui-버튼-및-3d-표시와-연결)

## 시험 서버 접속

시험 서버는 HYSYS Excel의 기준값으로 만든 모의 데이터를 보낸다.

**서버 연결** 탭의 **서버 주소 (Endpoint URL)**에 아래 주소를 넣고 **연결**을 누른다.

```text
opc.tcp://218.52.73.150:4840/hd/
```

시험 서버는 기본 설정인 `None / Anonymous`로 접속한다. **연결됨 · 수신 대기**가 뜨면 태그를 고른다. 계정이나 인증서를 쓰는 서버는 접속 전에 **보안 및 인증** 탭에서 설정한다.

내부망에서 위 공인 주소로 접속하다 시간 초과가 뜨면 **연결 해제**를 누르고 서버 담당자가 알려 준 내부 Endpoint로 다시 연결한다.

### 목록에서 태그 선택

1. 왼쪽 **서버 항목**에서 **Objects → Telemetry**를 연다.
2. **수신 태그 검색**에 `Stream/1/Pressure`를 입력하고 오른쪽 표에서 압력 태그를 체크한다. 검색 범위는 현재 열어 둔 목록이다.
3. **수신할 태그 목록 (1)**에서 선택한 태그를 확인한다.

### 태그 주소 직접 입력

서버에 연결하고 **태그 관리** 탭을 연다. 시험 서버의 Stream 1 온도를 등록하려면 아래처럼 입력한다.

| 입력칸 | Stream 1 온도 예시 |
|---|---|
| Namespace URI | `urn:hd:opcua:test:v1` |
| NodeId | `s=Stream/1/Temperature` |
| 표시명 (선택) | 비워 두면 `Stream/1/Temperature`로 표시된다. `Stream 1 온도`처럼 원하는 이름을 써도 된다. |
| 단위 (선택) | 비워 두면 서버에서 읽은 `degC`가 표시된다. 서버에 단위 정보가 없으면 빈칸으로 남는다. |

**등록**을 누른 뒤 위쪽 **등록한 태그**에서 온도 행을 고른다. **↓ 수신할 태그 목록에 추가**를 누르면 아래쪽 수신 목록에 온도가 나타난다.

### 수신 시작과 Excel 저장

1. **서버 연결 → 수신할 태그 목록**에서 받을 태그를 확인한다.
2. **파일 선택**에서 저장할 폴더와 `.xlsx` 파일명을 정한다. 기존 파일을 고르면 그 파일의 결과 시트를 갱신한다.
3. 저장 주기를 초 단위로 입력하고 **수신·저장 시작**을 누른다. 주기가 `5`이면 5초마다 최신값을 저장한다.

마지막으로 저장한 값은 **Excel 저장값 보기**에서 확인한다.

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

</details>

서버 연결, 태그 조회와 구독은 `telemetry.py`의 `Receiver` 클래스에서 처리한다. [수신 코드](opcua-test/telemetry.py)

<a id="asyncua-rebuild"></a>
<a id="테스트와-빌드"></a>

## 데스크톱 수신기 빌드

Python 3.12(x64)를 사용한다. 저장소를 복제하거나 `opcua-receiver-0.1.2-source.zip`의 압축을 푼 뒤 `opcua-test` 폴더로 이동한다. [v0.1.2 릴리스](https://github.com/ljw-8888/opcua-receiver/releases/tag/v0.1.2)

두 배포본에는 시험 태그와 HYSYS 기준값을 담은 `data.json`이 포함된다. 아이콘 원본을 바꿨다면 빌드 전에 가상환경에서 `python icons/build_icon.py`를 실행한다.

기본 빌드는 PyPI의 `asyncua 2.1.0`을 사용한다. 수정한 `asyncua`로 빌드하려면 릴리스에서 `asyncua-2.1.0.tar.gz`를 받아 `opcua-receiver`와 같은 상위 폴더에 푼다. `opcua-test`에서 본 소스 경로는 `../../asyncua-2.1.0`이다.

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

같은 창에서 의존성을 확인하고 빌드한다. 결과 파일은 `dist\OPCUA-Receiver.exe`다.

```powershell
& $python -m pip check
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

같은 터미널에서 의존성을 확인하고 빌드한다. 결과 파일은 `dist/OPCUA-Receiver`다.

```bash
.venv/bin/python -m pip check
.venv/bin/python -m PyInstaller --clean --noconfirm --distpath ../dist --workpath ../build receiver.spec
```

실행할 때 `libEGL.so.1` 오류가 뜨면 `sudo apt install libegl1`로 Qt에 필요한 라이브러리를 설치한다. 앱 메뉴 등록 스크립트와 아이콘까지 함께 배포하려면 `opcua-test`에서 압축한다.

```bash
tar -czf ../dist/OPCUA-Receiver-Ubuntu-x86_64.tar.gz -C ../dist OPCUA-Receiver -C ../opcua-test install-launcher.sh icons/opcua-receiver.svg
```

## 라이선스

Windows와 Ubuntu 배포본에 포함된 `asyncua 2.1.0`에는 GNU LGPL v3 이상이 적용된다. [사용 고지](licenses/asyncua-NOTICE.txt) · [LGPL v3 전문](licenses/LGPL-3.0.txt) · [GPL v3 전문](licenses/GPL-3.0.txt)

Kit 확장에도 `asyncua` 고지와 라이선스, 동봉한 글꼴의 라이선스가 포함된다. 확장을 다른 팀에 전달할 때는 `exts/hd.opcua.receiver` 폴더 전체를 배포한다. [확장 패키징 방법](exts/hd.opcua.receiver/docs/README.md#패키지-유지보수) · [글꼴 라이선스](exts/hd.opcua.receiver/data/FONT-LICENSE.txt)
