"""Standalone OPC UA receiver. Run on the receiver VM's desktop."""

import asyncio
import contextlib
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock, Timeout
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWhatsThis, QWidget,
)

from latest_excel import hysys_definitions, save_latest
from saved_preview import SavedPreview
from telemetry import (LEGACY_PREFIX, NAMESPACE, Receiver, SECURITY_MODES, address_key, interval,
                       validate_endpoint)
from latest_usda import UsdaOutput


ROOT = Path(__file__).resolve().parent
DATA_DIR = (Path(os.environ["LOCALAPPDATA"]) / "OPC UA Receiver"
            if getattr(sys, "frozen", False) and sys.platform == "win32" else ROOT)
if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
    DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "opcua-receiver"
CONFIG = DATA_DIR / "receiver-settings.json"
SAVED_FIELDS = ("mode", "auth", "username", "certificate", "private_key",
                "server_certificate", "application_uri", "seconds", "usda_seconds", "format")
EXCEL = "Excel (.xlsx)"
USDA = "USD (.usda)"


def migrate_settings(target, previous):
    if target.exists() or not previous.is_file():
        return
    with FileLock(str(target) + ".lock"):
        if not target.exists():
            pending = target.with_suffix(".tmp")
            shutil.copyfile(previous, pending)
            pending.replace(target)


def configure_display(app):
    app.setApplicationName("OPCUA-Receiver")
    app.setApplicationDisplayName("OPC UA 수신기")
    app.setDesktopFileName("opcua-receiver")
    app.setWindowIcon(QIcon(str(ROOT / "icons" / "opcua-receiver.ico")))
    family = "Noto Sans CJK KR"
    for weight in ("Regular", "Bold"):
        path = ROOT / "fonts" / f"NotoSansCJK-{weight}.ttc"
        index = QFontDatabase.addApplicationFont(str(path))
        if family not in QFontDatabase.applicationFontFamilies(index):
            raise RuntimeError(f"수신기 한글 글꼴을 열 수 없습니다: {path}")
    app.setFont(QFont(family, 12))
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { color: #192e26; }
        QWidget#panel { background: #f4f7f5; }
        QLabel#title { font-size: 25px; font-weight: bold; }
        QLabel#connectionError { color: #8b3827; }
        QLabel#groupHint { color: #56665d; }
        QTabWidget::pane, QGroupBox { background: white; border: 1px solid #b7c9bf; border-radius: 4px; }
        QGroupBox { margin-top: 13px; padding: 11px 5px 3px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
        QTabBar::tab { background: #e5ebe7; padding: 6px 16px; }
        QTabBar::tab:selected { background: #fff; color: #184c39; }
        QLineEdit, QComboBox, QTreeWidget { background: white; border: 1px solid #a6bab0; border-radius: 3px; }
        QLineEdit, QComboBox { padding: 3px 6px; }
        QLineEdit { placeholder-text-color: #76817c; }
        QTreeWidget { alternate-background-color: #f2f6f3; selection-background-color: #cee8d8; selection-color: #142b20; }
        QTreeWidget::item { padding: 3px; }
        QHeaderView::section { background: #e6efe9; padding: 5px; border: 0; border-right: 1px solid #cad8ce; }
        QPushButton { background: white; border: 1px solid #92ab9b; padding: 5px 12px; border-radius: 4px; }
        QPushButton:focus, QLineEdit:focus { border: 2px solid #397d60; }
        QPushButton:hover { background: #e5f2e9; }
        QPushButton[primary="true"] { background: #226044; color: white; border: 1px solid #226044; }
        QPushButton[primary="true"]:hover { background: #174c35; }
        QPushButton#chosenView { text-align: left; font-weight: bold; background: #e5f2e9; color: #184c39; }
        QPushButton#chosenView:checked { background: #226044; color: white; }
        QPushButton:disabled, QPushButton[primary="true"]:disabled { background: #edf0ee; color: #738078; border-color: #d2dad5; }
    """)


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self._wake_writer = asyncio.Event()
        self.receiver = Receiver(on_session_lost=self._wake_writer.set)
        self.definitions = hysys_definitions()
        self.recording = None
        self.paused_samples = None
        self.preview = SavedPreview(self)
        self.pending = set()
        self.closed = False
        self.fields = {}
        self.controls = {}
        self.items = {}
        self.chosen = set()
        self.visible_keys = set()
        self.browser_client = None
        self.browse_task = None
        self.registrations = {}
        self.manual_selection = {}
        self.active_manual = {}
        self.setObjectName("panel")
        self.setWindowTitle("OPC UA 수신기")
        self.resize(1140, 790)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        header = QHBoxLayout()
        layout.addLayout(header)
        title = QLabel("OPC UA 데이터 수신")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.state = QLabel("연결 대기")
        header.addWidget(self.state)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        connect, secure, tags = (QGridLayout() for _ in range(3))
        for grid, name in ((connect, "서버 연결"), (secure, "보안 및 인증"), (tags, "태그 관리")):
            page = QWidget()
            page.setLayout(grid)
            grid.setColumnStretch(1, 1)
            self.tabs.addTab(page, name)
        self.field(connect, 0, 0, "endpoint", "서버 주소 (Endpoint URL)")
        self.fields["endpoint"].setPlaceholderText("opc.tcp://xxx.xxx.xxx.xxx:xxxx/??/")
        connect.addWidget(self.button("연결", self.connect, True), 0, 2)
        connect.addWidget(self.button("연결 해제", self.disconnect), 0, 3)
        self.connection_error = QLabel()
        self.connection_error.setObjectName("connectionError")
        self.connection_error.setTextFormat(Qt.TextFormat.PlainText)
        self.connection_error.setWordWrap(True)
        self.connection_error.hide()
        connect.addWidget(self.connection_error, 1, 1, 1, 3)
        self.field(secure, 0, 0, "mode", "보안 정책 / 모드", "None", choices=SECURITY_MODES)
        self.cert_buttons = []
        for row, (key, label) in enumerate((
            ("certificate", "클라이언트 인증서"), ("private_key", "개인 키 파일"),
            ("server_certificate", "신뢰할 서버 인증서"),
        ), 1):
            self.field(secure, row, 0, key, label)
            button = self.button("찾아보기", lambda k=key, title=label: self.pick_certificate(k, title))
            secure.addWidget(button, row, 2)
            self.cert_buttons.append(button)
        self.field(secure, 4, 0, "application_uri", "클라이언트 URI")
        self.field(secure, 5, 0, "key_password", "개인 키 암호", secret=True)
        secure.setColumnMinimumWidth(3, 30)
        secure.setHorizontalSpacing(12)
        secure.setVerticalSpacing(12)
        secure.setColumnStretch(5, 1)
        self.field(secure, 0, 4, "auth", "사용자 인증", "Anonymous", choices=["Anonymous", "Username / Password"])
        self.field(secure, 1, 4, "username", "사용자명")
        self.field(secure, 2, 4, "password", "비밀번호", secret=True)
        self.security_help = QLabel()
        self.security_help.setWordWrap(True)
        secure.addWidget(self.security_help, 6, 0, 1, 6)
        secure.setRowStretch(7, 1)
        tag_page = tags
        registered_box = QGroupBox("등록한 태그")
        tag_page.addWidget(registered_box, 0, 0, 1, 2)
        tags = QGridLayout(registered_box)
        tags.setColumnStretch(1, 1)
        tags.setVerticalSpacing(8)
        tags.setHorizontalSpacing(16)
        self.field(tags, 0, 0, "namespace", "Namespace URI", span=3)
        self.field(tags, 1, 0, "node", "NodeId", span=3)
        self.field(tags, 2, 0, "alias", "표시명")
        self.field(tags, 2, 2, "unit", "단위")
        tags.addWidget(self.button("등록", self.add), 2, 4)
        self.registered_tree = QTreeWidget()
        self.registered_tree.setHeaderLabels(["표시명", "NodeId", "Namespace URI", "단위"])
        self.registered_tree.setRootIsDecorated(False)
        self.registered_tree.setMinimumHeight(110)
        self.registered_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.registered_tree.setAlternatingRowColors(True)
        tags.setRowStretch(3, 1)
        for col, width in enumerate((195, 270, 240)):
            self.registered_tree.setColumnWidth(col, width)
        tags.addWidget(self.registered_tree, 3, 0, 1, 4)
        tags.addWidget(self.button("등록 삭제", self.delete_registered), 3, 4, Qt.AlignmentFlag.AlignTop)
        self.selected_box = QGroupBox("수신할 태그 목록 (0)")
        self.selected_layout = QGridLayout(self.selected_box)
        self.selected_layout.setColumnStretch(0, 1)
        self.selected_layout.addWidget(self.button("제외", self.remove_from_list), 0, 1, Qt.AlignmentFlag.AlignTop)
        transfer = self.button("↓  수신할 태그 목록에 추가", self.use_registered)
        transfer.setAccessibleName("수신할 태그 목록에 추가")
        tag_page.addWidget(transfer, 1, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)
        tag_page.addWidget(self.selected_box, 2, 0, 1, 2)
        tag_page.setRowStretch(0, 3)
        tag_page.setRowStretch(2, 2)
        self.receive_area = QWidget()
        receive = QVBoxLayout(self.receive_area)
        receive.setContentsMargins(0, 0, 0, 0)
        connect.addWidget(self.receive_area, 2, 0, 1, 4)
        connect.setRowStretch(2, 1)
        line = QHBoxLayout()
        receive.addLayout(line)
        line.addWidget(QLabel("수신 태그 검색"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("현재 목록에서 이름 또는 NodeId로 검색")
        self.search.setAccessibleName("수신 태그 검색")
        self.search.setToolTip("왼쪽에서 고른 그룹이나 수신할 태그 목록 안에서 검색합니다.")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(310)
        line.addWidget(self.search)
        line.addStretch()
        self.tree = QTreeWidget()
        self.group_hint = QLabel("왼쪽에서 설비나 그룹을 선택하세요.", self.tree.viewport())
        self.group_hint.setObjectName("groupHint")
        self.group_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.group_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        QVBoxLayout(self.tree.viewport()).addWidget(self.group_hint)
        self.group_hint.hide()
        line.addWidget(self.button("전체 선택", self.select_visible))
        line.addWidget(self.button("전체 선택 해제", self.deselect_visible))
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["항목", "NodeId", "마지막 수신값", "단위", "품질", "수신 시각 (UTC)"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemChanged.connect(self.check_tag)
        for i, width in enumerate((150, 280, 140, 80, 100)):
            self.tree.setColumnWidth(i, width)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.browser_layout = QHBoxLayout()
        self.groups = QTreeWidget()
        self.groups.setHeaderLabel("서버 항목")
        self.groups.setMinimumWidth(160)
        self.groups.currentItemChanged.connect(self.request_page)
        sidebar = QVBoxLayout()
        self.chosen_view = QPushButton("수신할 태그 목록 (0)")
        self.chosen_view.setObjectName("chosenView")
        self.chosen_view.setCheckable(True)
        self.chosen_view.clicked.connect(self.show_chosen)
        sidebar.addWidget(self.chosen_view)
        sidebar.addWidget(self.groups, 1)
        self.browser_layout.addLayout(sidebar, 1)
        self.browser_layout.addWidget(self.tree, 4)
        receive.addLayout(self.browser_layout, 1)
        group = QGroupBox("파일 저장")
        receive.addWidget(group)
        output = QGridLayout(group)
        output.setColumnStretch(1, 1)
        self.field(output, 0, 0, "format", "저장 형식", EXCEL, choices=[EXCEL, USDA])
        self.fields["format"].setMaximumWidth(200)
        self.field(output, 1, 0, "file", "결과 파일", span=3)
        self.fields["file"].setPlaceholderText("저장 경로와 파일명.xlsx")
        self.fields["usda_file"] = QLineEdit()
        self.fields["usda_file"].setPlaceholderText("저장 경로와 파일명.usda")
        output.addWidget(self.fields["usda_file"], 1, 1, 1, 3)
        file_actions = QHBoxLayout()
        output.addLayout(file_actions, 1, 4)
        file_actions.addWidget(self.button("파일 선택", self.pick_file))
        file_help = QToolButton()
        file_help.setText("?")
        file_help.setAccessibleName("결과 파일 도움말")
        file_help.setToolTip("결과 파일 도움말")
        file_help.setWhatsThis("Excel은 기존 통합문서의 결과 시트를 갱신합니다. USD는 새 파일 또는 이 서버의 수신 데이터 파일을 선택하세요.")
        file_help.clicked.connect(lambda: QWhatsThis.showText(
            file_help.mapToGlobal(file_help.rect().bottomLeft()), file_help.whatsThis(), file_help))
        file_actions.addWidget(file_help)
        self.field(output, 2, 0, "seconds", "저장 주기 (초)", "5")
        self.fields["seconds"].setMaximumWidth(100)
        self.fields["usda_seconds"] = QLineEdit("1")
        self.fields["usda_seconds"].setMaximumWidth(100)
        output.addWidget(self.fields["usda_seconds"], 2, 1)
        output.addWidget(self.button("수신·저장 시작", self.start, True), 2, 3)
        output.addWidget(self.button("파일 저장 중지", self.stop), 2, 4)
        output.addWidget(self.button("수신 중지", self.pause_receiving), 2, 5)
        self.preview_button = self.button("Excel 저장값 보기", self.preview.show)
        output.addWidget(self.preview_button, 1, 5)
        self.save_status = QLabel("저장 대기")
        self.save_status.setWordWrap(True)
        output.addWidget(self.save_status, 3, 0, 1, 4)
        self.last_save = QLabel("마지막 저장 성공 (UTC)  —")
        output.addWidget(self.last_save, 3, 4)
        self.note = QLabel("서버에 연결한 뒤 수신할 태그를 선택하세요.")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        if CONFIG.exists():
            try:
                saved = self.persist()
                for key in SAVED_FIELDS:
                    if key in saved:
                        self.set_field(key, saved[key])
            except (OSError, ValueError, KeyError) as exc:
                self.note.setText(f"설정 읽기 오류: {exc}")
        self.fields["format"].currentTextChanged.connect(self.update_format)
        self.update_format()
        self.fields["mode"].currentTextChanged.connect(self.update_security)
        self.fields["auth"].currentTextChanged.connect(self.update_security)
        self.update_security()
        self.tabs.currentChanged.connect(self.switch_tab)
        self.search.textChanged.connect(self.sync_tree)
        self.registered_tree.itemSelectionChanged.connect(self.update_controls)
        self.tree.itemSelectionChanged.connect(self.update_controls)
        self.update_controls()

    def switch_tab(self, index):
        self.note.setVisible(index != 1)
        if index == 1:
            return
        self.tree.clearSelection()
        if index == 2:
            self.selected_layout.addWidget(self.tree, 0, 0)
        else:
            self.browser_layout.addWidget(self.tree, 4)
        self.tree.show()
        self.sync_tree()

    def update_format(self):
        excel = self.get("format") == EXCEL
        self.file_key, self.period_key = ("file", "seconds") if excel else ("usda_file", "usda_seconds")
        self.preview_button.setVisible(excel)
        for key in ("file", "seconds", "usda_file", "usda_seconds"):
            self.fields[key].setVisible(key in (self.file_key, self.period_key))

    def update_security(self):
        secure = self.get("mode") != "None"
        for key in ("certificate", "private_key", "server_certificate", "application_uri", "key_password"):
            self.fields[key].setEnabled(secure)
        for button in self.cert_buttons:
            button.setEnabled(secure)
        for key in ("username", "password"):
            self.fields[key].setEnabled(self.get("auth") != "Anonymous")
        if secure:
            hint = ("클라이언트 인증서와 개인 키, 신뢰할 서버 인증서를 선택하세요. 클라이언트 URI는 인증서의 URI와 같아야 합니다. "
                    "암호화된 개인 키에는 키 암호도 입력하세요.")
            if self.get("auth") != "Anonymous":
                hint += " 서버에서 발급한 사용자명과 비밀번호를 입력하세요."
        elif self.get("auth") != "Anonymous":
            hint = "계정으로 접속하려면 먼저 서버가 지원하는 보안 정책을 선택하세요."
        else:
            hint = "서버가 None / Anonymous를 허용하면 인증서와 계정 입력 없이 접속할 수 있습니다."
        self.security_help.setText(hint + "\n설정을 적용하려면 ‘서버 연결’ 탭에서 연결하세요. 이미 연결 중이면 연결을 해제한 뒤 다시 연결하세요.")

    def pick_certificate(self, key, title):
        types = "개인 키 (*.pem *.der *.key)" if key == "private_key" else "인증서 (*.pem *.der *.crt *.cer)"
        path, _ = QFileDialog.getOpenFileName(self, title, self.get(key), types + ";;모든 파일 (*)")
        if path:
            self.set_field(key, path)

    def field(self, grid, row, col, key, label, default="", choices=None, secret=False, span=1):
        grid.addWidget(QLabel(label), row, col)
        if choices:
            entry = QComboBox()
            entry.addItems(choices)
        else:
            entry = QLineEdit()
            if secret:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.fields[key] = entry
        self.set_field(key, default)
        grid.addWidget(entry, row, col + 1, 1, span)

    def set_field(self, key, value):
        entry = self.fields[key]
        if isinstance(entry, QComboBox):
            entry.setCurrentText(value)
        else:
            entry.setText(value)

    def button(self, label, fn, primary=False):
        button = QPushButton(label)
        if fn.__name__ != "<lambda>":
            self.controls[fn.__name__] = button
        button.setProperty("primary", primary)
        button.clicked.connect(lambda: self.invoke(fn))
        return button

    def show_count(self):
        self.chosen_view.setText(f"수신할 태그 목록 ({len(self.chosen)})")
        self.selected_box.setTitle(f"수신할 태그 목록 ({len(self.chosen)})")
        self.update_controls()

    def update_controls(self):
        connected = self.receiver.state == "Connected"
        session = bool(self.receiver.task and not self.receiver.task.done())
        receiving = session and bool(self.receiver.selected)
        saving = self.recording is not None
        editable = connected and not receiving
        marked = bool(self.registered_tree.selectedItems())
        displayed = self.displayed_keys()
        self.chosen_view.setEnabled(connected)
        for name, enabled in (
            ("connect", not session), ("disconnect", session),
            ("start", connected and bool(self.chosen) and not saving),
            ("pause_receiving", receiving or saving), ("stop", saving),
            ("pick_file", not saving), ("select_visible", editable and bool(displayed - self.chosen)),
            ("deselect_visible", editable and bool(displayed & self.chosen)),
            ("add", editable),
            ("use_registered", editable and marked), ("delete_registered", editable and marked),
            ("remove_from_list", editable and self.tabs.currentIndex() == 2 and bool(self.tree.selectedItems())),
        ):
            self.controls[name].setEnabled(enabled)
        self.fields["format"].setEnabled(not saving)
        self.fields[self.file_key].setReadOnly(saving)
        self.fields[self.period_key].setReadOnly(saving)
        self.fields["endpoint"].setReadOnly(session)
        self.tabs.widget(1).setEnabled(not session)

    def persist(self, *, settings=None, added=None, removed=()):
        with FileLock(str(CONFIG) + ".lock", timeout=1):
            data = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
            registrations = {url: {key: tag for key, tag in records.items() if not tag.get("legacy")}
                             for url, records in data.get("registrations", {}).items()}
            if added is not None or removed:
                records = registrations.setdefault(self.receiver.url, {})
                if added is not None:
                    records[added["identifier"]] = added
                for key in removed:
                    records.pop(key, None)
            updated = dict(data, registrations=registrations)
            updated.pop("tags", None)
            updated.pop("endpoint", None)
            if settings is not None:
                updated["settings"] = settings
            if updated != data:
                tmp = CONFIG.with_suffix(".tmp")
                tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(CONFIG)
            self.registrations = registrations
            return updated.get("settings", {})

    def refresh_registrations(self, focus_key=None):
        self.registered_tree.clear()
        for key, tag in self.registrations.get(self.receiver.url, {}).items():
            item = QTreeWidgetItem(self.registered_tree, [tag["metric"], tag["node_id"], tag["namespace_uri"], tag["unit"]])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            if key == focus_key:
                self.registered_tree.setCurrentItem(item)

    def check_tag(self, item, column):
        if column == 0:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if item.checkState(0) == Qt.CheckState.Checked:
                self.chosen.add(key)
            else:
                self.chosen.discard(key)
                self.manual_selection.pop(key, None)
                if self.chosen_view.isChecked():
                    self.visible_keys.discard(key)
                if self.chosen_view.isChecked() or self.tabs.currentIndex() == 2:
                    item.setHidden(True)
            self.show_count()

    def displayed_keys(self):
        return {key for key in self.visible_keys if key in self.items and not self.items[key].isHidden()}

    def select_visible(self):
        self.chosen.update(self.displayed_keys())
        self.sync_tree()

    def deselect_visible(self):
        self.deselect_keys(self.displayed_keys())

    def remove_from_list(self):
        if self.receiver.selected:
            raise ValueError("수신을 중지한 뒤 목록을 변경하세요.")
        keys = {item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()}
        self.deselect_keys(keys)
        self.note.setText(f"수신할 태그 목록에서 {len(keys)}개 제외했습니다.")

    def deselect_keys(self, keys):
        self.chosen.difference_update(keys)
        for key in keys:
            self.manual_selection.pop(key, None)
        if self.chosen_view.isChecked():
            self.visible_keys.difference_update(keys)
        self.sync_tree()

    def show_chosen(self):
        self.groups.setCurrentItem(None)
        self.chosen_view.setChecked(True)
        self.visible_keys = self.chosen.copy()
        self.search.clear()
        self.sync_tree()
        self.note.setText("수신할 태그 목록을 확인하고 수신·저장 시작을 누르세요.")

    def invoke(self, fn):
        async def run():
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self.note.setText(str(exc))
        task = asyncio.create_task(run())
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
        return task

    def get(self, name):
        entry = self.fields[name]
        return entry.currentText() if isinstance(entry, QComboBox) else entry.text()

    def connect(self):
        if not self.get("endpoint").strip():
            raise ValueError("서버의 Endpoint URL을 입력하세요.")
        try:
            url = validate_endpoint(self.get("endpoint"))
        except ValueError as exc:
            self.fields["endpoint"].setFocus()
            raise ValueError("서버 주소를 opc.tcp://서버주소:포트/경로 형식으로 입력하세요.") from exc
        auth = self.get("auth")
        options = {k:self.get(k) for k in ("mode","certificate","private_key","key_password","server_certificate","application_uri")}
        if auth != "Anonymous":
            if not self.get("username").strip():
                raise ValueError("사용자명을 입력하세요.")
            options.update(username=self.get("username"), password=self.get("password"))
        self.receiver.connect(url, options)
        self.paused_samples = None
        self.receiver.tags.clear()
        self.receiver.select([])
        self.tree.clear()
        self.items.clear()
        self.manual_selection.clear()
        self.active_manual.clear()
        self.refresh_registrations()
        self.chosen.clear()
        self.visible_keys.clear()
        self.search.clear()
        self.sync_tree()
        self.note.setText("서버 연결 후 항목 목록을 자동으로 불러옵니다.")

    def sync_tree(self):
        with QSignalBlocker(self.tree):
            self.update_rows()
        group = self.groups.currentItem()
        self.group_hint.setVisible(self.tabs.currentIndex() == 0 and self.receiver.state == "Connected"
                                   and not self.visible_keys and group is not None and group.childCount() > 0)
        self.show_count()

    def update_rows(self):
        managing = self.tabs.currentIndex() == 2
        visible = self.chosen if managing else self.visible_keys
        query = "" if managing else self.search.text().strip().casefold()
        checkable = not self.receiver.selected and self.receiver.state == "Connected"
        for tag in self.receiver.tags:
            key = tag["identifier"]
            if key not in visible:
                if key in self.items:
                    self.items[key].setHidden(True)
                continue
            samples = self.receiver.samples if self.paused_samples is None else self.paused_samples
            sample = samples.get(key,{})
            value = sample.get("value")
            shown = f"{value:.7g}" if isinstance(value, float) else ("" if value is None else str(value))
            label = self.manual_selection.get(key, tag)
            unit = label.get("unit_override") or sample.get("unit", tag["unit"])
            values = (label["metric"], tag["node_id"], shown, unit,
                      sample.get("quality", ""), sample.get("received_at", "").replace("T", " ").removesuffix("+00:00"))
            item = self.items.get(key)
            if item is None:
                item = self.items[key] = QTreeWidgetItem(self.tree)
                item.setData(0, Qt.ItemDataRole.UserRole, key)
            item.setHidden(bool(query and not any(query in text.casefold() for text in (label["metric"], tag["node_id"]))))
            flag = Qt.ItemFlag.ItemIsUserCheckable
            if bool(item.flags() & flag) != checkable:
                item.setFlags(item.flags() | flag if checkable else item.flags() & ~flag)
            item.setToolTip(1, tag["namespace_uri"])
            item.setCheckState(0, Qt.CheckState.Checked if key in self.chosen else Qt.CheckState.Unchecked)
            for col, text in enumerate(values):
                if item.text(col) != text:
                    item.setText(col, text)

    def reset_browser(self):
        if self.browse_task:
            self.browse_task.cancel()
        self.browser_client = self.receiver.client
        self.chosen_view.setChecked(False)
        self.groups.clear()
        self.visible_keys.clear()
        if self.browser_client:
            root = QTreeWidgetItem(self.groups, ["Objects"])
            root.setData(0, Qt.ItemDataRole.UserRole, "i=85")
            self.groups.setCurrentItem(root)

    def request_page(self, item, previous=None):
        if self.browse_task:
            self.browse_task.cancel()
        self.visible_keys.clear()
        if item is None:
            return
        self.chosen_view.setChecked(False)
        node = item.data(0, Qt.ItemDataRole.UserRole)
        self.note.setText(f"{item.text(0)} 항목 조회 중…")
        self.browse_task = self.invoke(lambda: self.load_group(item, node))
        self.sync_tree()

    async def load_group(self, item, node):
        keys = await self.receiver.browse(node)
        if self.browser_client is not self.receiver.client or item is not self.groups.currentItem():
            return
        item.takeChildren()
        for group in self.receiver.folders:
            child = QTreeWidgetItem(item, [group["name"]])
            child.setData(0, Qt.ItemDataRole.UserRole, group["node_id"])
        item.setExpanded(True)
        self.visible_keys = set(keys)
        for tag in self.receiver.tags:
            if tag["namespace_uri"] == NAMESPACE and tag["node_id"] in self.definitions:
                tag["asset"] = self.definitions[tag["node_id"]]["asset"]
        self.sync_tree()
        self.note.setText(f"{item.text(0)} · 하위 항목 {item.childCount()}개 · 태그 {len(keys)}개")

    async def add(self):
        if self.receiver.client is None:
            raise ValueError("태그를 직접 추가하려면 먼저 서버에 연결하세요.")
        client = self.receiver.client
        alias, unit = self.get("alias").strip(), self.get("unit").strip()
        key = await self.receiver.add_node(self.get("node"), self.get("namespace"))
        if client is not self.receiver.client or self.receiver.selected:
            return
        tag = next(t for t in self.receiver.tags if t["identifier"] == key)
        self.persist(added=dict(tag, metric=alias or tag["metric"], unit=unit or tag["unit"], unit_override=unit))
        self.refresh_registrations(focus_key=key)
        self.note.setText(f"{alias or tag['metric']} 태그를 등록했습니다.")

    async def use_registered(self):
        items = self.registered_tree.selectedItems()
        if not items or self.receiver.client is None:
            raise ValueError("서버에 연결한 뒤 사용할 등록 항목을 선택하세요.")
        client = self.receiver.client
        keys = []
        records = self.registrations[self.receiver.url]
        requested = [records[item.data(0, Qt.ItemDataRole.UserRole)] for item in items]
        for tag in requested:
            keys.append(await self.receiver.add_node(tag["node_id"], tag["namespace_uri"]))
            if (self.receiver.client is not client or self.receiver.selected
                    or tag["identifier"] not in self.registrations.get(self.receiver.url, {})):
                return
            if "unit_override" not in tag:
                current = next(t for t in self.receiver.tags if t["identifier"] == tag["identifier"])
                self.persist(added=dict(tag, unit_override=tag["unit"] if tag["unit"] != current["unit"] else ""))
        keys = set(keys).intersection(self.registrations[self.receiver.url])
        if not keys:
            return
        added = len(keys - self.chosen)
        self.chosen.update(keys)
        self.manual_selection.update({key: self.registrations[self.receiver.url][key] for key in keys})
        if self.chosen_view.isChecked():
            self.visible_keys = self.chosen.copy()
        self.sync_tree()
        if added:
            next_step = ("‘서버 연결’ 탭에서 수신·저장을 시작하세요." if self.get(self.file_key).strip() else
                         "‘서버 연결’ 탭에서 결과 파일을 지정하고 수신·저장을 시작하세요.")
            self.note.setText(f"수신할 태그 목록에 {added}개 추가했습니다. {next_step}")
        else:
            self.note.setText("수신할 태그 목록에 이미 있습니다.")

    async def delete_registered(self):
        if self.receiver.selected:
            raise ValueError("수신을 중지한 뒤 등록 항목을 삭제하세요.")
        keys = {item.data(0, Qt.ItemDataRole.UserRole) for item in self.registered_tree.selectedItems()}
        if not keys:
            raise ValueError("등록 목록에서 삭제할 항목을 선택하세요.")
        self.persist(removed=keys)
        self.refresh_registrations()
        self.sync_tree()
        self.note.setText(f"직접 등록 {len(keys)}개 삭제")

    def pick_file(self):
        excel = self.get("format") == EXCEL
        path, _ = QFileDialog.getSaveFileName(self, "새 파일 이름 입력 또는 기존 파일 선택",
                                              self.get(self.file_key), "Excel (*.xlsx)" if excel else "USD (*.usda)",
                                              options=QFileDialog.Option.DontConfirmOverwrite)
        if path:
            self.set_field(self.file_key, path if Path(path).suffix else path + (".xlsx" if excel else ".usda"))

    def start(self):
        if self.recording or self.receiver.state != "Connected":
            raise ValueError("서버 연결을 확인하고, 이미 저장 중이면 먼저 저장을 중지하세요.")
        if self.receiver.url != self.get("endpoint").strip():
            raise ValueError("주소를 변경했습니다. 연결 해제 후 다시 연결하세요.")
        keys = self.chosen.copy()
        if not keys:
            raise ValueError("수신할 태그를 한 개 이상 선택하세요.")
        seconds = interval(self.get(self.period_key), "저장 주기")
        path = Path(self.get(self.file_key).strip()).expanduser().resolve()
        suffix = ".xlsx" if self.get("format") == EXCEL else ".usda"
        if path.suffix.lower() != suffix or not path.parent.is_dir():
            raise ValueError(f"기존 폴더 안에 {suffix} 파일명을 지정하세요.")
        settings = {key: self.get(key) for key in SAVED_FIELDS}
        self.persist(settings=settings)
        self.active_manual = self.manual_selection.copy()
        if self.paused_samples is not None:
            self.receiver.samples.clear()
        self.paused_samples = None
        if keys != self.receiver.selected:
            self.receiver.select(keys)
        self._stopping = False
        self._final_connection = None
        self.save_status.setText("첫 수신 대기 중")
        self.last_save.setText("마지막 저장 성공 (UTC)  —")
        self.recording = asyncio.create_task(self.write_loop(path, seconds))
        self.note.setText(f"태그 {len(keys)}개 수신·저장을 시작했습니다.")
        self.sync_tree()

    async def write_loop(self, path, seconds):
        usda = UsdaOutput(path) if path.suffix.lower() == ".usda" else None
        try:
            with FileLock(str(path) + ".lock", timeout=0):
                while True:
                    self._wake_writer.clear()
                    stopping = self._stopping
                    if stopping and not usda:
                        break
                    try:
                        rows = self.receiver.snapshot(for_excel=True)
                        for row in rows:
                            record = self.active_manual.get(address_key(row["namespace_uri"], row["identifier"]))
                            if record:
                                row.update(metric=record["metric"], unit=record.get("unit_override") or row["unit"])
                        if usda:
                            state = self._final_connection or self.receiver.state
                            await asyncio.to_thread(usda.save, self.receiver.url, state, not stopping, rows)
                            saved = True
                        else:
                            tables = await asyncio.to_thread(save_latest, path, rows, self.definitions, preview=True)
                            saved = bool(tables)
                        if saved:
                            self.save_status.setText(f"{path.name} 저장 완료 · {seconds:g}초 간격 · 태그 {len(rows)}개")
                            stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                            self.last_save.setText("마지막 저장 성공 (UTC)  " + stamp)
                            if not usda:
                                self.preview.saved(path, stamp, tables)
                        else:
                            self.save_status.setText("첫 수신 대기 중")
                    except OSError as exc:
                        if stopping:
                            raise
                        self.save_status.setText(f"저장 실패, 다음 주기에 재시도: {exc}")
                    if stopping:
                        break
                    if self._stopping:
                        continue
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._wake_writer.wait(), seconds)
            self.save_status.setText("파일 저장 중지")
        except Timeout:
            self.save_status.setText("다른 수신기가 이 파일에 저장 중입니다. 다른 결과 파일을 선택하세요.")
        except Exception as exc:
            self.save_status.setText(f"파일 저장 중지: {exc}")
        finally:
            self.recording = None
            self.update_controls()

    async def stop(self):
        if self.recording:
            self._stopping = True
            self._wake_writer.set()
            await asyncio.shield(self.recording)

    async def disconnect(self):
        self._final_connection = "Disconnected"
        await self.stop()
        await self.receiver.disconnect()
        self.receiver.select([])
        self.connection_error.hide()
        self.note.setText("서버에 연결한 뒤 수신할 태그를 선택하세요.")
        self.update_controls()

    async def pause_receiving(self):
        await self.stop()
        self.active_manual.clear()
        if self.receiver.selected:
            self.paused_samples = self.receiver.samples.copy()
            self.receiver.select([])
        self.note.setText("수신과 저장을 중지했습니다. 태그를 변경하거나 다시 시작할 수 있습니다.")
        self.sync_tree()

    def closeEvent(self, event):
        self.closed = True
        event.accept()

    async def run(self):
        refresh = 0
        try:
            while not self.closed:
                QApplication.processEvents()
                if asyncio.get_running_loop().time() >= refresh:
                    if self.browser_client is not self.receiver.client:
                        self.reset_browser()
                    status = {"Connected": "연결됨", "Connecting": "연결 중", "Reconnecting": "재연결 중",
                              "Disconnected": "연결 안 됨"}.get(self.receiver.state, self.receiver.state)
                    detail = (f"수신 중 {self.receiver.subscription_count}개" if self.receiver.subscription_count
                              else "구독 대기" if self.receiver.selected else "수신 대기")
                    if self.paused_samples is not None:
                        detail = "수신 중지 · 마지막 수신값 표시"
                    self.state.setText(f"{status}   ·   {detail}")
                    self.state.setToolTip(self.receiver.error)
                    retrying = self.receiver.state in ("Connecting", "Reconnecting") and bool(self.receiver.error)
                    if retrying:
                        kind = self.receiver.error.partition(":")[0]
                        reason = {
                            "ConnectionRefusedError": "서버에서 연결을 거부했습니다.",
                            "TimeoutError": "연결 시간이 초과됐습니다.",
                            "gaierror": "서버 이름을 찾을 수 없습니다.",
                            "BadIdentityTokenRejected": "서버에서 사용자 인증을 거부했습니다.",
                            "BadCertificateUntrusted": "인증서를 신뢰할 수 없습니다.",
                        }.get(kind, self.receiver.error)
                        self.connection_error.setText(f"{reason} 다시 연결하는 중입니다. 주소를 수정하려면 ‘연결 해제’를 누르세요.")
                    self.connection_error.setVisible(retrying)
                    self.sync_tree()
                    refresh = asyncio.get_running_loop().time()+0.6
                await asyncio.sleep(.04)
        finally:
            for task in list(self.pending):
                task.cancel()
            await asyncio.gather(*list(self.pending),return_exceptions=True)
            await self.disconnect()
            await self.preview.shutdown()
            self.hide()


if __name__ == "__main__":
    if sys.platform == "win32":
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("OPCUA.Receiver")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False) and (sys.platform == "win32" or sys.platform.startswith("linux")):
        prefix = LEGACY_PREFIX.upper() + " " if sys.platform == "win32" else LEGACY_PREFIX + "-"
        previous = DATA_DIR.with_name(prefix + DATA_DIR.name) / CONFIG.name
        try:
            migrate_settings(CONFIG, previous)
        except OSError as exc:
            logging.warning("이전 설정을 복사할 수 없습니다: %s", exc)
    logging.basicConfig(level=logging.WARNING)
    app = QApplication([])
    configure_display(app)
    panel = Panel()
    panel.show()
    asyncio.run(panel.run())
