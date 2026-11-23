"""Readable controls when a running host has already built a Latin-only font atlas."""

ENGLISH = {
    "펼치기": "Expand", "접기": "Collapse",
    "OPC UA 데이터 수신": "OPC UA Receiver", "서버 연결": "Server", "보안 및 인증": "Security & identity",
    "태그 관리": "Tag management", "서버 주소 (Endpoint URL)": "Server endpoint", "연결": "Connect",
    "연결 해제": "Disconnect", "수신 태그 검색": "Search tags", "전체 선택": "Select all",
    "전체 선택 해제": "Deselect all", "결과 파일": "Workbook", "파일 선택": "Choose file",
    "Excel 저장값 보기": "Preview workbook", "저장 주기 (초)": "Interval (s)", "수신만 시작": "Receive only",
    "수신·저장 시작": "Receive & save", "Excel 저장 중지": "Stop Excel saving", "수신 중지": "Pause receiving",
    "서버 항목": "Server groups", "등록": "Register", "등록 삭제": "Delete registration",
    "Excel 저장": "Excel output", "등록한 태그": "Registered tags",
    "선택한 등록 태그를 수신 목록에 추가": "Add selected registrations to receive list",
    "수신할 태그 목록 · 체크 해제로 제외": "Receive list · uncheck to remove", "이전": "Previous", "다음": "Next",
    "보안 정책 / 모드": "Security policy", "클라이언트 인증서": "Client certificate",
    "개인 키 파일": "Private key file", "신뢰할 서버 인증서": "Trusted server certificate",
    "클라이언트 URI": "Application URI", "개인 키 암호": "Key password", "사용자 인증": "Identity",
    "사용자명": "User name", "비밀번호": "Password", "표시명": "Display name", "단위": "Unit",
    "항목": "Tag", "마지막 수신값": "Latest value", "품질": "Quality", "수신 시각 (UTC)": "Received (UTC)",
    "찾아보기": "Browse", "Microsoft Excel 창으로 보기": "View in Microsoft Excel",
    "전체 태그": "All tags", "수신할 태그 목록": "Receive list", "최근 저장 (UTC)": "Last save (UTC)",
    "연결됨": "Connected", "연결 중": "Connecting", "재연결 중": "Reconnecting", "연결 대기": "Disconnected",
    "수신 대기": "Ready", "수신 중지 · 마지막 수신값 표시": "Paused · last values shown",
    "Excel 저장 대기": "Excel idle", "첫 수신 대기 중": "Waiting for the first sample",
    "수신 대기 중": "Waiting for data", "첫 저장을 기다리고 있습니다.": "Waiting for the first saved workbook.",
    "서버 주소를 입력하고 연결하세요.": "Enter a server endpoint and click Connect.",
    "연결 후 서버의 Objects 아래 태그를 자동 조회합니다.": "Browsing tags under Objects after connection.",
    "서버 연결을 해제했습니다.": "Disconnected from the server.",
    "태그를 등록했습니다. 수신 목록에 추가하면 구독 대상으로 선택됩니다.": "Tag registered. Add it to the receive list to select it.",
    "None / Anonymous 서버는 주소만으로 연결할 수 있습니다. 계정 인증은 보안 정책을 선택하세요.": "For None / Anonymous servers, enter only the endpoint. For account authentication, select a secure policy.",
    "opc.tcp://서버주소:포트/경로": "opc.tcp://host:port/path",
    "현재 목록에서 표시명 또는 NodeId 검색": "Search this list by name or NodeId",
    "사용자명을 입력하세요.": "Enter a user name.", "로컬 파일 경로를 선택하세요.": "Choose a local file.",
    "서버 연결이 변경되었습니다.": "Server connection changed.",
    "수신을 중지한 뒤 태그를 변경하세요.": "Pause receiving before editing tags.",
    "서버에 연결하고 수신할 태그를 선택하세요.": "Connect and select at least one tag.",
    "이미 저장 중입니다.": "Already saving.", "저장 주기": "Save interval",
    "기존 폴더 안에 결과 파일(.xlsx)을 지정하세요.": "Choose an .xlsx file in an existing folder.",
    "태그 {n}개 수신 중": "Receiving {n} tags", "수신할 태그 {n}개": "{n} selected tags",
    "{n}개": "{n} tags", "구독 {n}/{m}개": "Subscribed {n}/{m}",
    "주소나 인증 설정을 바꾸려면 연결을 해제하세요.": "Disconnect to edit the endpoint or security settings.",
    "태그 조회 오류": "Browse error", "서버 태그 조회 중 · {n}개 발견": "Browsing server · {n} tags found",
    "조회할 수 없는 항목 {n}개": "{n} inaccessible nodes", "{name} 저장 완료 · {n:g}초 간격": "{name} saved · every {n:g}s",
    "저장 실패 · 다음 주기에 재시도합니다.": "Save failed. Retrying next interval.",
}

english = False


def tr(text):
    return ENGLISH.get(text, text) if english else text
