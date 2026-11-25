import asyncio
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

import carb
import omni.ext
import omni.ui as ui
from omni.kit.menu.utils import MenuItemDescription, add_menu_items, remove_menu_items
from omni.kit.viewport.utility import get_active_viewport_window
from omni.kit.window.filepicker import FilePickerDialog

from .measurements import TAG_DEFAULTS, _publish
from .overlay import ScreenBadge
from .source_view import SourceWindow
from .tag_selection import BadgeTags
from .telemetry import SnapshotFile, publication_status

TITLE = "Live USDA Translator"


class TranslatorExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._task = self._picker = self._viewport = self._frame = None
        self._file = self._source_window = self._badge = None
        self._window = ui.Window(TITLE, width=620, height=320)
        self._path = ui.SimpleStringModel("")
        self._timeout = ui.SimpleIntModel(10)
        with self._window.frame, ui.VStack(spacing=6):
            with ui.HStack(height=28, spacing=6):
                ui.Label("Telemetry USDA", width=115)
                ui.StringField(model=self._path)
                ui.Button("Open USDA...", width=100, clicked_fn=self._browse)
                self._source_button = ui.Button("View source", width=95, enabled=False,
                                                clicked_fn=self._show_source)
            with ui.HStack(height=26, spacing=6):
                ui.Label("No update after (s)", width=135)
                ui.IntField(model=self._timeout, width=55)
                ui.Spacer()
                ui.Button("Show badge", width=110, clicked_fn=self._start)
                ui.Button("Stop", width=60, clicked_fn=self._stop)
            self._tags = BadgeTags(TAG_DEFAULTS)
            self._status = ui.Label("Select a receiver USDA file.", word_wrap=True)
        self._path.add_value_changed_fn(lambda _: self._monitor(None))
        self._menu = [MenuItemDescription(name=TITLE, onclick_fn=self._show)]
        add_menu_items(self._menu, "Window")
        self._monitor(None)

    def _show(self):
        self._window.visible = True
        self._window.focus()

    def _browse(self):
        if not self._picker:
            self._picker = FilePickerDialog("Select receiver USDA", allow_multi_selection=False,
                                            item_filter_fn=lambda item: item.is_folder or item.name.lower().endswith(".usda"),
                                            apply_button_label="Open", click_apply_handler=self._picked,
                                            click_cancel_handler=lambda *_: self._picker.hide())
        self._picker.show()

    def _picked(self, filename, directory):
        self._picker.hide()
        if not filename:
            return
        url = urlsplit(directory)
        if url.scheme == "file":
            directory = url2pathname(("//" + url.netloc if url.netloc else "") + url.path)
        elif len(url.scheme) > 1:
            self._status.text = "Select a local file or a mounted share."
            return
        self._path.set_value(str(Path(directory) / filename))
        self._start()

    def _start(self):
        path = Path(self._path.as_string.strip()).expanduser()
        if path.suffix.lower() != ".usda" or self._timeout.as_int <= 0:
            self._monitor(None, "Select a .usda file and set a positive timeout.")
            return
        self._monitor(SnapshotFile(path.resolve()))

    def _monitor(self, file, notice="Select a receiver USDA file."):
        if self._task:
            self._task.cancel()
        _publish(None)
        self._close_source()
        self._file = file
        self._source_button.enabled = False
        self._tags.update_snapshot(None)
        self._task = asyncio.ensure_future(self._watch(file, self._timeout.as_int, notice))
        if file:
            self._display(None, None, "Reading " + file.path.name, "Reading USDA")

    async def _watch(self, file, timeout, notice):
        while True:
            snapshot, status, detail, idle_status = None, None, notice, "Waiting for USDA"
            if file:
                try:
                    snapshot = await asyncio.to_thread(file.read)
                    status = publication_status(snapshot, timeout)
                    _publish(snapshot, status)
                except Exception as exc:
                    snapshot, status = None, None
                    _publish(None)
                    detail, idle_status = str(exc), "File unavailable"
            try:
                self._display(snapshot, status, detail, idle_status)
            except Exception as exc:
                self._tags.update_snapshot(None)
                self._detach()
                message = str(exc).strip() or type(exc).__name__
                if self._status.text != message:
                    carb.log_warn(f"[hd.usda.translator] {message}")
                self._status.text = message
            await asyncio.sleep(1)

    def _close_source(self):
        if self._source_window:
            self._source_window.destroy()
            self._source_window = None

    def _show_source(self):
        if self._source_button.enabled:
            self._close_source()
            self._source_window = SourceWindow(self._file.path, tuple(self._tags.selected.values()),
                                               self._file.snapshot.source)

    def _mount(self, window):
        if self._viewport == window:
            return
        self._detach()
        self._viewport = window
        self._frame = window.get_frame("hd.usda.translator")
        with self._frame, ui.VStack(opaque_for_mouse_events=False):
            ui.Spacer()
            with ui.HStack(height=0):
                ui.Spacer()
                with ui.VStack(width=340, height=0):
                    self._badge = ScreenBadge(TAG_DEFAULTS["fields"])
                ui.Spacer()
            ui.Spacer()

    def _display(self, snapshot, status, notice, idle_status):
        self._tags.update_snapshot(snapshot)
        self._source_button.enabled = snapshot is not None
        window = get_active_viewport_window()
        if not window:
            self._detach()
            self._status.text = "Open a viewport to see the badge."
            return
        self._mount(window)
        self._badge.refresh(self._tags.selected, status, idle_status)
        self._status.text = f"{status}  ·  {snapshot.source}" if snapshot else notice

    def _detach(self):
        if self._frame:
            self._frame.clear()
        self._badge = self._viewport = self._frame = None

    def _stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
        _publish(None)
        self._detach()
        self._close_source()
        self._source_button.enabled = False
        self._file = None
        self._tags.update_snapshot(None)
        self._status.text = "Stopped"

    def on_shutdown(self):
        self._stop()
        if self._picker:
            self._picker.destroy()
        remove_menu_items(self._menu, "Window")
        self._window.destroy()
