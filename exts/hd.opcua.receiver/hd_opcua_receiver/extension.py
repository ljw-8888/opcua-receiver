"""Kit-native settings, address-space browser, live monitor and workbook preview."""
import asyncio
import sys
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

import carb.tokens
import omni.ext
import omni.ui as ui
from omni.kit.menu.utils import MenuItemDescription, add_menu_items, remove_menu_items

from . import language
from .language import tr
from .receiver import SECURITY_MODES
from .session import ROOT_NODE, SAVED_FIELDS, Session

_active = None
TITLE = "OPC UA Settings"
PAGE_SIZE = 50
ICONS = Path(__file__).resolve().parents[1] / "data"
TABLE_WEIGHTS = (3, 4, 2, 1, 1, 3)
TREE_ROW = 32
TREE_INDENT = 22
STYLE = {
    "Label": {"font_size": 22, "color": 0xfff5f5f5},
    "Button": {"background_color": 0xff494642, "border_radius": 4},
    "Button:hovered": {"background_color": 0xff625c55},
    "Button:disabled": {"background_color": 0xff363432},
    "Button.Label": {"font_size": 20, "color": 0xffffffff},
    "Button.Label:disabled": {"color": 0xffb3afab},
    "ScrollingFrame": {"background_color": 0xff302c29},
    "Field": {"font_size": 22, "color": 0xfffafafa, "background_color": 0xff21201e,
                    "border_width": 1, "border_color": 0xff736d65, "border_radius": 3},
    "Button::active": {"background_color": 0xff64562d, "border_color": 0xffb6bd69, "border_width": 1},
    "Button::bulk": {"background_color": 0xff65533b, "border_color": 0xffa89479, "border_width": 1},
    "Button::bulk:disabled": {"background_color": 0xff393735, "border_color": 0xff62605d},
    "Button::branch": {"background_color": 0xff534d45, "border_radius": 4},
    "Button::branch:hovered": {"background_color": 0xff786851},
    "Rectangle::treeLine": {"background_color": 0xff948878},
    "Button::group": {"background_color": 0x00000000},
    "Button::group:hovered": {"background_color": 0xff514c45},
    "Button.Label::group": {"alignment": ui.Alignment.LEFT_CENTER},
    "Button.Label::currentGroup": {"alignment": ui.Alignment.LEFT_CENTER},
    "Button::currentGroup": {"background_color": 0xff67572b},
}



def show_settings():
    """Open or focus the existing window from a host application's settings button."""
    if _active:
        _active.show()


def get_latest_samples():
    """Kit main-thread API. Tag identity is (source, namespace_uri, identifier)."""
    return _active.session.snapshot() if _active else []


class OpcUaExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global _active
        language.english = False
        directory = Path(carb.tokens.get_tokens_interface().resolve("${data}")) / "hd.opcua.receiver"
        self.session = Session(directory / "receiver-settings.json")
        self._job = None
        self._busy = False
        self._picker = self._preview = None
        self._preview_data = None
        self._excel = None
        self._sheet = ""
        self._preview_page = 0
        self._tab = 0
        self._group = "all"
        self._group_path = ()
        self._expanded = {ROOT_NODE}
        self._page = 0
        self._marked = set()
        self._visible_keys = []
        self._cells = {}
        self._controls = []
        self._revision = None
        self._font_checked = False
        self._notice = tr("서버 주소를 입력하고 연결하세요.")
        self._models = {k: ui.SimpleStringModel(str(self.session.settings.get(k, default))) for k, default in {
            "endpoint": "", "namespace": "", "node": "", "alias": "", "unit": "", "search": "",
            "file": "", "seconds": "5", "username": "", "password": "", "key_password": "",
            "certificate": "", "private_key": "", "server_certificate": "", "application_uri": "",
        }.items()}
        self._mode = self.session.settings.get("mode", "None")
        self._auth = self.session.settings.get("auth", "Anonymous")
        self._models["search"].add_value_changed_fn(self._search_changed)
        self._window = ui.Window(TITLE, width=1130, height=695, visible=True, raster_policy=ui.RasterPolicy.NEVER)
        self._menu = [MenuItemDescription(name=TITLE, onclick_fn=show_settings)]
        add_menu_items(self._menu, "Window")
        ui.Workspace.set_show_window_fn(TITLE, self._workspace_show)
        _active = self
        with self._window.frame, ui.ZStack():
            ui.Rectangle(style={"background_color": 0xff2d2926})
            with ui.VStack(spacing=6, style=STYLE):
                with ui.HStack(height=34, spacing=8):
                    # Measure Kit's current atlas. Adding an extension to an already
                    # running host may leave it with Latin glyphs until its next start.
                    with ui.ZStack(width=1, height=1):
                        with ui.HStack(width=0):
                            self._glyph = ui.Label("압압압", style={"color": 0})
                        with ui.HStack(width=0):
                            self._fallback = ui.Label("???", style={"color": 0})
                    self._title = ui.Label(tr("OPC UA 데이터 수신"), style={"font_size": 24})
                    self._status = ui.Label("", alignment=ui.Alignment.RIGHT_CENTER)
                with ui.HStack(height=30, spacing=4):
                    self._tabs = [ui.Button(name, width=130, clicked_fn=partial(self._switch, i))
                                  for i, name in enumerate((tr("서버 연결"), tr("보안 및 인증"), tr("태그 관리")))]
                    ui.Spacer()
                self._content = ui.Frame()
                self._content.set_build_fn(self._build_tab)
                self._note = ui.Label(self._notice, height=30, word_wrap=True)
        self._refresh = asyncio.ensure_future(self._loop())

    def _workspace_show(self, visible):
        if visible:
            self.show()
        else:
            self._window.visible = False

    def show(self):
        self._window.visible = True
        self._window.focus()

    @property
    def editable(self):
        return self.session.receiver.state == "Connected" and not self.session.receiver.selected

    def _value(self, key):
        return self._models[key].as_string

    def _options(self):
        values = {k: v.as_string for k, v in self._models.items()}
        return dict(values, mode=self._mode, auth=self._auth)

    def _call(self, fn, *args):
        if self._busy:
            return
        self._busy = True

        async def run():
            try:
                result = fn(*args)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                self._notice = str(exc) or type(exc).__name__
            finally:
                self._busy = False
                self._revision = None
        self._job = asyncio.ensure_future(run())

    def _button(self, title, fn, enabled=lambda: True, **kwargs):
        button = ui.Button(title, clicked_fn=partial(self._call, fn), **kwargs)
        self._controls.append((button, enabled))
        button.enabled = enabled() and not self._busy
        return button

    def _field(self, key, secret=False, enabled=lambda: True, **kwargs):
        widget = ui.StringField(model=self._models[key], password_mode=secret, **kwargs)
        self._controls.append((widget, enabled))
        widget.enabled = enabled()
        return widget

    def _switch(self, tab):
        self._tab = tab
        self._page = 0
        self._content.rebuild()

    def _build_tab(self):
        self._controls.clear()
        self._cells.clear()
        self._browser = self._table = self._records = None
        self._save_label = self._last_label = None
        for i, button in enumerate(self._tabs):
            button.name = "active" if i == self._tab else ""
        with ui.VStack(spacing=6):
            if self._tab == 0:
                self._build_server()
            elif self._tab == 1:
                self._build_security()
            else:
                self._build_tags()
        self._revision = None

    def _build_server(self):
        receiver = self.session.receiver
        with ui.HStack(height=32, spacing=5):
            ui.Label(tr("서버 주소 (Endpoint URL)"), width=202)
            self._field("endpoint", enabled=lambda: receiver.state == "Disconnected",
                        tooltip=tr("opc.tcp://서버주소:포트/경로"))
            self._button(tr("연결"), self._connect, lambda: receiver.state == "Disconnected", width=75)
            self._button(tr("연결 해제"), self._disconnect, lambda: receiver.state != "Disconnected", width=90)
        with ui.HStack(height=34, spacing=8):
            ui.Label(tr("수신 태그 검색"), width=115)
            self._field("search", width=275, tooltip=tr("현재 목록에서 표시명 또는 NodeId 검색"))
            ui.Spacer()
            self._button(tr("전체 선택"), lambda: self.session.choose(self._filtered(), True),
                         self._can_select, width=112, name="bulk")
            self._button(tr("전체 선택 해제"), lambda: self.session.choose(self._filtered(), False),
                         self._can_select, width=147, name="bulk")
        with ui.HStack(spacing=6):
            self._browser = ui.ScrollingFrame(width=237)
            self._browser.set_build_fn(self._build_browser)
            self._make_table()
        ui.Label(tr("Excel 저장"), height=26)
        with ui.HStack(height=26, spacing=4):
            ui.Label(tr("결과 파일"), width=100)
            self._field("file", enabled=lambda: not self.session.writer)
            self._button(tr("파일 선택"), lambda: self._pick("file"), lambda: not self.session.writer, width=86)
            self._button(tr("Excel 저장값 보기"), self._show_preview, width=138)
        with ui.HStack(height=28, spacing=4):
            ui.Label(tr("저장 주기 (초)"), width=100)
            self._field("seconds", enabled=lambda: not self.session.writer, width=68)
            ui.Spacer()
            self._button(tr("수신만 시작"), lambda: self._start(False),
                         lambda: self.editable and bool(self.session.chosen), width=110)
            self._button(tr("수신·저장 시작"), lambda: self._start(True),
                         lambda: receiver.state == "Connected" and bool(self.session.chosen) and not self.session.writer,
                         width=132)
            self._button(tr("Excel 저장 중지"), self.session.stop_save, lambda: bool(self.session.writer), width=130)
            self._button(tr("수신 중지"), self.session.pause, lambda: bool(receiver.selected), width=96)
        with ui.HStack(height=24):
            self._save_label = ui.Label(tr(self.session.save_status))
            self._last_label = ui.Label("", alignment=ui.Alignment.RIGHT_CENTER)

    def _can_select(self):
        return self.editable and bool(self._visible_keys) and (
            self._group != "all" or not self.session.scanning)

    def _connect(self):
        opts = self._options()
        security = {k: opts[k] for k in ("mode", "certificate", "private_key", "key_password",
                                           "server_certificate", "application_uri")}
        if self._auth != "Anonymous":
            if not opts["username"].strip():
                raise ValueError(tr("사용자명을 입력하세요."))
            security.update(username=opts["username"], password=opts["password"])
        self.session.connect(opts["endpoint"], security)
        self._group = "all"
        self._group_path = ()
        self._expanded = {ROOT_NODE}
        self._marked.clear()
        self._models["search"].set_value("")
        self._notice = tr("연결 후 서버의 Objects 아래 태그를 자동 조회합니다.")

    async def _disconnect(self):
        await self.session.disconnect()
        self._notice = tr("서버 연결을 해제했습니다.")

    async def _start(self, save):
        opts = self._options()
        await self.session.start(filename=opts["file"] if save else None, seconds=opts["seconds"],
                                 settings={k: opts[k] for k in SAVED_FIELDS})
        self._select_group("chosen")
        self._notice = tr("태그 {n}개 수신 중").format(n=len(self.session.chosen))

    def _build_browser(self):
        s = self.session
        with ui.VStack(spacing=0, height=0):
            for key, label in (("all", f"{tr('전체 태그')} ({len(s.catalog)})"),
                               ("chosen", f"{tr('수신할 태그 목록')} ({len(s.chosen)})")):
                ui.Button(label, height=27, name="active" if key == self._group else "",
                          clicked_fn=partial(self._select_group, key))
            ui.Label(tr("서버 항목"), height=25)
            if s.receiver.client:
                self._draw_group(ROOT_NODE, "Objects", (), (), ())

    def _draw_group(self, node, name, ancestors, path, last_siblings):
        if node in ancestors:
            return
        path = (*path, name)
        lineage = " / ".join(path)
        children = self.session.groups.get(node, ())
        expanded = node in self._expanded
        selected = self._group == node and self._group_path == path
        with ui.HStack(height=TREE_ROW, spacing=0):
            # Keep vertical guides through the descendants of each unfinished branch.
            for level, last in enumerate(last_siblings):
                current = level == len(last_siblings) - 1
                with ui.ZStack(width=TREE_INDENT):
                    if current or not last:
                        with ui.Placer(offset_x=13):
                            ui.Rectangle(name="treeLine", width=1, height=TREE_ROW // 2 if current and last else TREE_ROW)
                    if current:
                        with ui.Placer(offset_x=13, offset_y=TREE_ROW // 2):
                            ui.Rectangle(name="treeLine", width=TREE_INDENT - 13, height=1)
            if children:
                icon = "branch-down.svg" if expanded else "branch-right.svg"
                action = tr("접기") if expanded else tr("펼치기")
                ui.Button("", name="branch", width=28, height=TREE_ROW, image_url=str(ICONS / icon),
                          image_width=16, image_height=16, tooltip=f"{lineage} · {action}",
                          clicked_fn=partial(self._expand, node))
            else:
                ui.Spacer(width=28)
            ui.Button(name, name="currentGroup" if selected else "group", tooltip=lineage,
                      clicked_fn=partial(self._select_group, node, path))
        if expanded:
            for i, (child, label) in enumerate(children):
                self._draw_group(child, label, (*ancestors, node), path, (*last_siblings, i == len(children) - 1))

    def _expand(self, node):
        self._expanded.symmetric_difference_update([node])
        self._browser.rebuild()

    def _select_group(self, node, path=()):
        self._group = node
        self._group_path = path
        self._expanded.add(node)
        self._page = 0
        self._models["search"].set_value("")
        self._revision = None

    def _search_changed(self, model):
        self._page = 0
        self._revision = None

    def _filtered(self):
        s = self.session
        if self._group == "chosen" or self._tab == 2:
            keys = s.chosen
        elif self._group == "all":
            keys = s.catalog
        else:
            keys = s.members.get(self._group, set())
        query = self._value("search").casefold().strip() if self._tab == 0 else ""
        return sorted(k for k in keys if not query or any(
            query in s.overrides.get(k, s.tags[k])[field].casefold() for field in ("metric", "node_id")))

    def _make_table(self):
        with ui.VStack(spacing=3):
            self._scope = ui.Label("", height=26, elided_text=True)
            with ui.HStack(height=28, spacing=4):
                ui.Spacer(width=24)
                titles = (tr("항목"), "NodeId", tr("마지막 수신값"), tr("단위"), tr("품질"), tr("수신 시각 (UTC)"))
                for text, weight in zip(titles, TABLE_WEIGHTS):
                    ui.Label(text, width=ui.Fraction(weight))
            self._table = ui.ScrollingFrame()
            self._table.set_build_fn(self._build_rows)
            with ui.HStack(height=22, spacing=3):
                self._count = ui.Label("")
                ui.Button(tr("이전"), width=60, clicked_fn=partial(self._turn, -1))
                ui.Button(tr("다음"), width=60, clicked_fn=partial(self._turn, 1))

    def _turn(self, delta):
        self._page += delta
        self._table.rebuild()

    def _build_rows(self):
        s = self.session
        keys = self._filtered()
        self._visible_keys = keys
        if self._tab == 2 or self._group == "chosen":
            scope = tr("수신할 태그 목록")
        elif self._group == "all":
            scope = tr("전체 태그")
        else:
            scope = " / ".join(self._group_path)
        self._scope.text = scope
        self._scope.tooltip = scope
        pages = max(1, (len(keys) + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page = min(max(0, self._page), pages - 1)
        self._count.text = tr("{n}개").format(n=len(keys)) + f" · {self._page + 1}/{pages}"
        self._cells.clear()
        with ui.VStack(height=0, spacing=2):
            for key in keys[self._page * PAGE_SIZE:(self._page + 1) * PAGE_SIZE]:
                tag = s.overrides.get(key, s.tags[key])
                with ui.HStack(height=28, spacing=4):
                    model = ui.SimpleBoolModel(key in s.chosen)
                    ui.CheckBox(model=model, width=24, enabled=self.editable and not self._busy)
                    model.add_value_changed_fn(partial(self._check, key))
                    ui.Label(tag["metric"], width=ui.Fraction(TABLE_WEIGHTS[0]), elided_text=True, tooltip=tag["metric"])
                    ui.Label(tag["node_id"], width=ui.Fraction(TABLE_WEIGHTS[1]), elided_text=True,
                             tooltip=f'{tag["namespace_uri"]}\n{tag["node_id"]}')
                    value = ui.Label("", width=ui.Fraction(TABLE_WEIGHTS[2]), elided_text=True)
                    ui.Label(tag["unit"], width=ui.Fraction(TABLE_WEIGHTS[3]))
                    quality = ui.Label("", width=ui.Fraction(TABLE_WEIGHTS[4]), elided_text=True)
                    stamp = ui.Label("", width=ui.Fraction(TABLE_WEIGHTS[5]), elided_text=True)
                    self._cells[key] = (value, quality, stamp)
        self._update_values()

    def _check(self, key, model):
        if self.editable and not self._busy:
            self.session.choose([key], model.as_bool)

    def _update_values(self):
        s = self.session
        samples = s.receiver.samples if s.receiver.selected and s.receiver.state == "Connected" else s.paused
        for key, widgets in self._cells.items():
            sample = samples.get(key, {})
            raw = sample.get("value")
            value = f"{raw:.7g}" if isinstance(raw, float) else ("" if raw is None else str(raw))
            stamp = sample.get("received_at", "").replace("T", " ").removesuffix("+00:00")
            for widget, text in zip(widgets, (value, sample.get("quality", ""), stamp)):
                if widget.text != text:
                    widget.text = text
                    widget.tooltip = text

    def _build_security(self):
        def field(key, title, enabled, secret=False, pick=False):
            with ui.HStack(height=30, spacing=5):
                ui.Label(title, width=135)
                self._field(key, secret, enabled)
                if pick:
                    self._button(tr("찾아보기"), lambda: self._pick(key), enabled, width=82)

        def choice(title, values, selected, attr):
            with ui.HStack(height=30, spacing=5):
                ui.Label(title, width=135)
                box = ui.ComboBox(values.index(selected), *values)
                def changed(model, item):
                    setattr(self, attr, values[model.get_item_value_model().as_int])
                box.model.add_item_changed_fn(changed)
                self._controls.append((box, lambda: self.session.receiver.state == "Disconnected"))

        disconnected = lambda: self.session.receiver.state == "Disconnected"
        secure = lambda: disconnected() and self._mode != "None"
        account = lambda: disconnected() and self._auth != "Anonymous"
        with ui.HStack(spacing=18):
            with ui.VStack(spacing=6):
                choice(tr("보안 정책 / 모드"), SECURITY_MODES, self._mode, "_mode")
                field("certificate", tr("클라이언트 인증서"), secure, pick=True)
                field("private_key", tr("개인 키 파일"), secure, pick=True)
                field("server_certificate", tr("신뢰할 서버 인증서"), secure, pick=True)
                field("application_uri", tr("클라이언트 URI"), secure)
                field("key_password", tr("개인 키 암호"), secure, secret=True)
            with ui.VStack(spacing=6):
                choice(tr("사용자 인증"), ["Anonymous", "Username / Password"], self._auth, "_auth")
                field("username", tr("사용자명"), account)
                field("password", tr("비밀번호"), account, secret=True)
        ui.Label(tr("None / Anonymous 서버는 주소만으로 연결할 수 있습니다. 계정 인증은 보안 정책을 선택하세요."),
                 height=32, word_wrap=True)
        ui.Spacer()

    def _build_tags(self):
        ui.Label(tr("등록한 태그"), height=24)
        for names in [(("namespace", "Namespace URI"), ("node", "NodeId")),
                      (("alias", tr("표시명")), ("unit", tr("단위")))]:
            with ui.HStack(height=27, spacing=4):
                for key, title in names:
                    ui.Label(title, width=105)
                    self._field(key, enabled=lambda: self.editable)
        with ui.HStack(height=27, spacing=4):
            self._button(tr("등록"), self._register, lambda: self.editable, width=90)
            self._button(tr("등록 삭제"), self._delete, lambda: self.editable and bool(self._marked), width=105)
            ui.Spacer()
        self._records = ui.ScrollingFrame(height=135)
        self._records.set_build_fn(self._build_records)
        self._button(tr("선택한 등록 태그를 수신 목록에 추가"), self._include,
                     lambda: self.editable and bool(self._marked), height=28)
        ui.Label(tr("수신할 태그 목록 · 체크 해제로 제외"), height=24)
        self._make_table()

    def _build_records(self):
        with ui.VStack(height=0, spacing=3):
            for key, tag in self.session.registered.items():
                with ui.HStack(height=23, spacing=4):
                    model = ui.SimpleBoolModel(key in self._marked)
                    ui.CheckBox(model=model, width=24, enabled=self.editable)
                    model.add_value_changed_fn(partial(self._mark, key))
                    for field in ("metric", "node_id", "namespace_uri", "unit"):
                        ui.Label(tag[field], elided_text=True, tooltip=tag[field])

    def _mark(self, key, model):
        if model.as_bool:
            self._marked.add(key)
        else:
            self._marked.discard(key)

    async def _register(self):
        key = await self.session.register(*(self._value(k) for k in ("node", "namespace", "alias", "unit")))
        self._marked = {key}
        self._notice = tr("태그를 등록했습니다. 수신 목록에 추가하면 구독 대상으로 선택됩니다.")

    async def _include(self):
        await self.session.include_registered(set(self._marked))
        self._notice = tr("수신할 태그 {n}개").format(n=len(self.session.chosen))

    def _delete(self):
        self.session.persist(remove=self._marked)
        self._marked.clear()

    def _pick(self, key):
        from omni.kit.window.filepicker import FilePickerDialog
        if self._picker:
            self._picker.destroy()
        def apply(filename, dirname):
            url = urlsplit(dirname)
            if url.scheme == "file":
                dirname = url2pathname(url.path)
            elif url.scheme and len(url.scheme) != 1:
                self._notice = tr("로컬 파일 경로를 선택하세요.")
                return
            if filename:
                path = Path(dirname) / filename
                if key == "file" and not path.suffix:
                    path = path.with_suffix(".xlsx")
                self._models[key].set_value(str(path))
            self._picker.hide()
        self._picker = FilePickerDialog("Excel file" if key == "file" else "Certificate / Key",
                                        allow_multi_selection=False, apply_button_label="Select",
                                        click_apply_handler=apply,
                                        click_cancel_handler=lambda *args: self._picker.hide())
        self._picker.show()

    def _show_preview(self):
        if self._preview is None:
            self._preview = ui.Window("OPC UA Excel Preview", width=900, height=510, raster_policy=ui.RasterPolicy.NEVER)
            self._preview.frame.set_build_fn(self._build_preview)
        self._preview.visible = True
        self._preview.focus()
        self._preview.frame.rebuild()

    def _build_preview(self):
        self._preview_data = self.session.preview
        with ui.VStack(spacing=5, style=STYLE):
            if not self._preview_data:
                ui.Label(tr("첫 저장을 기다리고 있습니다."), height=28)
                return
            name, stamp, tables = self._preview_data
            ui.Label(f"{name} · {tr('최근 저장 (UTC)')} {stamp}", height=28)
            if self._sheet not in tables:
                self._sheet = next(iter(tables))
            with ui.HStack(height=26, spacing=5):
                if sys.platform == "win32":
                    ui.Button(tr("Microsoft Excel 창으로 보기"), clicked_fn=partial(self._call, self._open_excel), width=185)
                for sheet in tables:
                    ui.Button(sheet, width=145, clicked_fn=partial(self._choose_sheet, sheet))
            rows = tables[self._sheet]
            pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
            self._preview_page = min(max(self._preview_page, 0), pages - 1)
            with ui.ScrollingFrame():
                with ui.VStack(height=0, width=145 * max(map(len, rows), default=1)):
                    for row in rows[self._preview_page*PAGE_SIZE:(self._preview_page+1)*PAGE_SIZE]:
                        with ui.HStack(height=22):
                            for v in row:
                                text = "" if v is None else str(v)
                                ui.Label(text, width=145, elided_text=True, tooltip=text)
            with ui.HStack(height=24):
                ui.Label(f"{self._preview_page + 1}/{pages}")
                for label, delta in ((tr("이전"), -1), (tr("다음"), 1)):
                    ui.Button(label, width=65, clicked_fn=partial(self._preview_turn, delta))

    def _open_excel(self):
        if self._excel is None:
            from .desktop_excel import DesktopPreview
            self._excel = DesktopPreview()
        self._excel.enabled = True

    def _update_excel(self):
        view = self._excel
        if not view or not view.enabled or not self.session.preview:
            return
        if view.task:
            if not view.task.done():
                return
            error = view.task.exception()
            view.task = None
            if error:
                view.enabled = False
                self._notice = f"Microsoft Excel: {error}"
                return
        if view.displayed is not self.session.preview:
            view.task = asyncio.create_task(view.update(self.session.preview))

    def _choose_sheet(self, sheet):
        self._sheet, self._preview_page = sheet, 0
        self._preview.frame.rebuild()

    def _preview_turn(self, delta):
        self._preview_page += delta
        self._preview.frame.rebuild()

    async def _loop(self):
        while True:
            await asyncio.sleep(.25)
            s = self.session
            s.update_client()
            self._update_excel()
            if self._preview and self._preview.visible and self._preview_data is not s.preview:
                self._preview.frame.rebuild()
            if not self._window.visible or not hasattr(self, "_table"):
                continue
            if not self._font_checked and self._glyph.computed_content_width > 0 and self._fallback.computed_content_width > 0:
                self._font_checked = True
                language.english = abs(self._glyph.computed_content_width - self._fallback.computed_content_width) < .1
                if language.english:
                    self._title.text = tr("OPC UA 데이터 수신")
                    for button, name in zip(self._tabs, ("서버 연결", "보안 및 인증", "태그 관리")):
                        button.text = tr(name)
                    self._content.rebuild()
            receiver = s.receiver
            state = {"Connected": tr("연결됨"), "Connecting": tr("연결 중"), "Reconnecting": tr("재연결 중"),
                     "Disconnected": tr("연결 대기")}[receiver.state]
            detail = tr("수신 대기")
            if receiver.selected:
                detail = tr("구독 {n}/{m}개").format(n=receiver.subscription_count, m=len(receiver.selected))
            elif s.paused:
                detail = tr("수신 중지 · 마지막 수신값 표시")
            self._status.text = f"{state} · {detail}"
            if receiver.error and receiver.state != "Connected":
                self._note.text = receiver.error + " · " + tr("주소나 인증 설정을 바꾸려면 연결을 해제하세요.")
            elif s.scan_error:
                self._note.text = tr("태그 조회 오류") + " · " + s.scan_error
            elif s.scanning:
                self._note.text = tr("서버 태그 조회 중 · {n}개 발견").format(n=len(s.catalog))
            else:
                self._note.text = tr(self._notice) + (" · " + tr("조회할 수 없는 항목 {n}개").format(n=s.skipped) if s.skipped else "")
            for widget, enabled in self._controls:
                widget.enabled = not self._busy and enabled()
            revision = (s.revision, receiver.state, bool(receiver.selected), self._busy)
            if self._revision != revision:
                self._revision = revision
                for frame in (self._browser, self._records, self._table):
                    if frame:
                        frame.rebuild()
            self._update_values()
            if self._save_label:
                self._save_label.text = tr(s.save_status)
                self._last_label.text = tr("최근 저장 (UTC)") + "  " + (s.last_save or "-")

    def on_shutdown(self):
        global _active
        _active = None
        ui.Workspace.set_show_window_fn(TITLE, None)
        remove_menu_items(self._menu, "Window")
        self._refresh.cancel()
        if self._job:
            self._job.cancel()
        async def cleanup():
            if self._job:
                await asyncio.gather(self._job, return_exceptions=True)
            await self.session.disconnect()
            if self._excel:
                await self._excel.close()
        asyncio.ensure_future(cleanup())
        for window in (self._picker, self._preview, self._window):
            if window:
                window.destroy()
