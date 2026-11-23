# OPC UA Receiver for Omniverse Kit

## 등록

Python 3.12를 내장한 Windows 또는 Linux x86-64용 GUI Kit 앱에서 사용한다. Linux 검증 환경은 Kit 110.4.1이다. Windows용 의존성도 함께 배포하며 Windows Kit에서의 실행은 아직 검증 전이다.

1. `git clone https://github.com/ljw-8888/opcua-receiver.git`을 실행하거나 GitHub의 **Code → Download ZIP**으로 받은 파일을 원하는 폴더에 푼다. 설치 후에도 이 폴더를 유지한다.
2. Kit의 **Window → Extensions**에서 검색 경로에 `exts` 폴더를 추가한다. 이 폴더 바로 아래에 `hd.opcua.receiver/config/extension.toml`이 있어야 한다.
3. **OPC UA Receiver**를 검색해 활성화한다. 다음 시작에도 열려면 확장 관리자에서 **Autoload**를 켠다. 닫은 창은 **Window → OPC UA Settings**에서 다시 연다.

실행 인자로도 등록할 수 있다. 기존 Kit 실행 명령 뒤에 다음 두 인자를 붙인다.

```text
--ext-folder "/absolute/path/to/opcua-receiver/exts" --enable hd.opcua.receiver
```

처음 활성화하면 확장이 동봉한 Python 패키지를 Kit의 사용자 캐시에 한 번 푼다. 별도 pip 설치나 Composer 재빌드가 필요하지 않다. 시작할 때 함께 로드하면 한글 글꼴을 사용한다. 이미 실행 중인 Kit의 글꼴에 한글이 없으면 첫 세션의 조작부는 영어로 표시된다.

## 사용

- **서버 연결**에서 Endpoint URL을 입력하고 연결한다. 기본 모드는 None / Anonymous다. 인증이 필요한 서버는 먼저 **보안 및 인증**에서 보안 정책, 클라이언트 인증서·키, 신뢰할 서버 인증서, Application URI와 계정을 설정한다.
- 연결하면 Objects 아래의 로컬 계층을 순회한다. **전체 태그**에서 이름·NodeId로 검색하거나 왼쪽에서 그룹을 선택한다. 화살표로 하위 그룹을 접거나 펼친다. 표 위에는 선택한 그룹의 경로가 표시된다. 검색 줄 오른쪽의 **전체 선택**과 **전체 선택 해제**는 현재 검색 결과 전체에 적용된다. 화면의 다른 페이지에 있는 행도 포함한다. 전체 목록의 일괄 선택은 탐색이 끝나면 활성화된다.
- **태그 관리**에서는 Namespace URI와 NodeId를 직접 등록하고 표시명·단위를 지정할 수 있다. 등록한 태그를 수신 목록에 추가하거나, 수신 목록에서 체크를 풀어 제외한다. 등록 정보는 Endpoint별로 사용자 데이터 폴더에 보관한다.
- **수신만 시작**은 Excel 경로 없이 실시간 값·단위·품질·수신 시각을 표시한다. USD를 열기 전에도 확인할 수 있다. **수신·저장 시작**은 지정한 주기로 태그별 최신값을 저장하며, 해당 태그가 있으면 HYSYS 결과 시트도 갱신한다. **Excel 저장값 보기**는 마지막 저장에 성공한 시트를 보여 준다.
- **Excel 저장 중지**는 구독을 유지한다. **수신 중지**는 연결을 유지하고 마지막 수신값을 표시한다. **연결 해제**는 구독과 저장을 종료한다. 설정 창을 닫아도 구독은 유지된다.

![EngineRoom 그룹에서 Pressure를 검색한 수신 화면](receiving.png)

## 기본 GUI 버튼 및 3D 표시와 연결

이 확장을 사용하는 쪽에서 확장 의존성 `hd.opcua.receiver`를 선언한다. 설정 버튼은 아래 함수를 콜백으로 사용할 수 있다.

```python
import omni.ui as ui
from hd_opcua_receiver import show_settings, get_latest_samples

ui.Button("OPC UA Settings", clicked_fn=show_settings)

# Kit 메인 스레드에서 현재 구독값을 읽는다.
for row in get_latest_samples():
    tag = row["source"], row["namespace_uri"], row["identifier"]
    value, unit, quality = row["value"], row["unit"], row["quality"]
```

연결이 끊기거나 수신을 중지하면 조회 결과는 빈 목록이다. USD 경로나 설비 매핑은 해당 Kit 앱에서 결정할 수 있다.

## 패키지 유지보수

저장소 루트에서 `python3 kit-tools/package_extension.py`를 실행하면 등록용 폴더 구조를 담은 ZIP이 `dist`에 생성된다. Linux x86-64 및 Python 3.12 환경에서 `--rebuild-bundles`를 추가하면 고정한 버전의 Linux·Windows 의존성도 다시 만든다. 대체 wheel을 사용하려면 `--wheelhouse <폴더>`를 지정한다. 각 번들의 배포 메타데이터와 라이선스, `licenses/` 및 `data/FONT-LICENSE.txt`를 함께 전달한다.
