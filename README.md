# OPC UA 수신기

OPC UA 서버에서 태그를 골라 실시간 값과 단위, 품질, 수신 시각을 확인하고 Excel(`.xlsx`) 또는 USD(`.usda`)로 저장한다.

| 환경 | 설치 방법 |
|---|---|
| [1. Windows x64](#windows-데스크톱-실행) | 실행 파일을 내려받아 실행 |
| [2. Ubuntu x86-64](#ubuntu-데스크톱-실행) | 배포 파일의 압축을 풀고 실행 |
| [3. Omniverse Kit](#omniverse-kit에서-시작하기) | Kit 앱에 확장 폴더를 등록 |

## Windows 데스크톱 실행

`OPCUA-Receiver.exe`를 내려받아 더블클릭한다. [Windows 실행 파일 다운로드](https://github.com/ljw-8888/opcua-receiver/releases/latest/download/OPCUA-Receiver.exe)

## Ubuntu 데스크톱 실행

배포 파일을 내려받은 폴더에서 다음 명령을 실행한다. [Ubuntu 배포 파일 다운로드](https://github.com/ljw-8888/opcua-receiver/releases/latest/download/OPCUA-Receiver-Ubuntu-x86_64.tar.gz)

```bash
mkdir -p opcua-receiver-app
tar -xzf OPCUA-Receiver-Ubuntu-x86_64.tar.gz -C opcua-receiver-app
cd opcua-receiver-app
./OPCUA-Receiver
```

앱 메뉴에 등록하려면 같은 폴더에서 `bash install-launcher.sh`를 실행한다.

### [Windows·Ubuntu 수신기 GUI 가이드](opcua-test/receiver-guide.md)

## Omniverse Kit에서 시작하기

Python 3.12가 내장된 x86-64용 USD Composer 또는 GUI Kit 앱에서 사용한다.

1. [Kit 확장 ZIP](https://github.com/ljw-8888/opcua-receiver/releases/download/v0.3.0/hd.opcua.receiver-0.3.0.zip)의 압축을 풀거나 이 저장소를 복제한다.
2. Kit의 **Window → Extensions**에서 검색 경로에 `exts` 폴더를 추가하고 **OPC UA Receiver**를 켠다.
3. 설정 창은 **Window → OPC UA Settings**에서 다시 열 수 있다. Kit 시작 시 자동으로 열려면 **Autoload**를 켠다.

서버 연결과 파일 저장은 씬을 열기 전에도 가능하다. [Kit 확장 사용 가이드](exts/hd.opcua.receiver/docs/README.md)

## 태그 수신과 저장

1. **서버 연결** 탭에서 Endpoint URL을 입력하고 **연결**을 누른다. 시험 서버 주소는 `opc.tcp://218.52.73.150:4840/hd/`다.
2. **서버 항목 → Objects → Telemetry**에서 받을 태그를 체크한다. 다른 서버에서는 해당 설비 그룹을 고른다. 주소를 아는 태그는 **태그 관리**에서 직접 등록할 수 있다.
3. **저장 형식**과 **결과 파일**을 고르고 **수신·저장 시작**을 누른다. **파일 저장 중지**를 누르면 구독을 유지한 채 파일이나 형식을 바꿀 수 있다.

| 저장 형식 | 기본 주기 | 저장 내용 |
|---|---|---|
| Excel (`.xlsx`) | 5초 | 태그별 최신값을 결과 시트에 기록한다. **Excel 저장값 보기**에서 마지막 저장 내용을 확인할 수 있다. |
| USD (`.usda`) | 1초 | 선택한 태그마다 Prim 하나에 값·단위·품질·시각을 기록한다. 연결이 끊기면 마지막 샘플은 `Stale`로 표시된다. |

세 수신기 모두 같은 USDA 형식을 쓴다. 다른 Kit 앱에서는 이 데이터 파일을 열어 최신값을 읽을 수 있다. [USDA 속성과 읽기 예제](exts/hd.opcua.receiver/docs/README.md#usda-데이터-형식)

<a id="asyncua-rebuild"></a>
<a id="테스트와-빌드"></a>

## 데스크톱 소스 실행 및 빌드

저장소 전체를 복제한 뒤 `opcua-test` 폴더에서 실행한다. 공통 수신 코드와 USDA 저장 코드는 `exts` 폴더에 있다.

<details>
<summary>Windows · PowerShell</summary>

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements-receiver.txt
& $python receiver_gui.py
```

실행 파일을 만들 때는 다음 명령을 사용한다.

```powershell
& $python -m pip install PyInstaller==6.22.3
& $python -m PyInstaller --clean --noconfirm --distpath ../dist --workpath ../build receiver.spec
```

</details>

<details>
<summary>Ubuntu · 터미널</summary>

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-receiver.txt
bash run-receiver.sh
```

실행 파일과 배포용 압축 파일을 만들려면 다음 명령을 사용한다.

```bash
.venv/bin/python -m pip install PyInstaller==6.22.3
.venv/bin/python -m PyInstaller --clean --noconfirm --distpath ../dist --workpath ../build receiver.spec
tar -czf ../dist/OPCUA-Receiver-Ubuntu-x86_64.tar.gz -C ../dist OPCUA-Receiver -C ../opcua-test install-launcher.sh icons/opcua-receiver.svg
```

</details>

`asyncua`를 수정해 빌드하려면 릴리스에 첨부한 `asyncua-2.1.0.tar.gz`의 압축을 풀고, 같은 가상환경에서 `python -m pip install --force-reinstall --no-deps <수정한-소스-폴더>`를 실행한 뒤 다시 빌드한다. GitHub Actions의 **Desktop receiver build**에서도 Windows·Ubuntu 배포본을 만들 수 있다.

## 라이선스

수신기에 포함한 `asyncua 2.1.0`의 라이선스는 LGPL v3 이상이다. [사용 고지](licenses/asyncua-NOTICE.txt) · [LGPL v3](licenses/LGPL-3.0.txt) · [GPL v3](licenses/GPL-3.0.txt) · [글꼴 라이선스](exts/hd.opcua.receiver/data/FONT-LICENSE.txt)
