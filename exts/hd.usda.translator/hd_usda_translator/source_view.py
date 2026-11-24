"""Read-only view of the file and the prim behind each selected badge row."""
import asyncio

import omni.ui as ui
from pxr import Sdf

from .telemetry import parse_layer


def _read_sections(path, keys, expected_source):
    # The receiver may replace the file while this window is open. Parse the
    # same bytes shown under "Whole file" so every excerpt belongs to that copy.
    text = path.read_text(encoding="utf-8-sig")
    layer = Sdf.Layer.CreateAnonymous("source.usda")
    layer.ImportFromString(text)
    snapshot = parse_layer(layer)
    if snapshot.source != expected_source:
        raise ValueError("Endpoint changed. Open the file again.")
    sections = []
    for row, (uri, identifier) in enumerate(keys, start=1):
        sample = snapshot.tags.get((snapshot.source, uri, identifier))
        label = f"{row}. {identifier}  [{uri}]"
        if sample is None:
            sections.append((label, "/Telemetry/Tags", "This tag is absent from this file."))
        else:
            prim = layer.GetPrimAtPath(sample.prim_path)
            sections.append((label, sample.prim_path, prim.GetAsText()))
    sections.append(("Whole file", str(path), text))
    return snapshot.published_at.isoformat(), sections


class SourceWindow:
    def __init__(self, path, keys, source):
        self._window = ui.Window("USDA source", width=780, height=460)
        with self._window.frame, ui.VStack(spacing=6):
            ui.Label(path.name, height=22, elided_text=True, tooltip=str(path))
            self._status = ui.Label("Reading USDA...", height=22, elided_text=True)
            self._selector = ui.Frame(height=26)
            self._location = ui.Label("", height=22, elided_text=True)
            self._text = ui.StringField(multiline=True, read_only=True)
        self._task = asyncio.ensure_future(self._load(path, keys, source))

    async def _load(self, path, keys, source):
        try:
            published, self._sections = await asyncio.to_thread(_read_sections, path, keys, source)
        except Exception as exc:
            self._status.text = "Could not read the receiver USDA."
            self._text.model.set_value(str(exc))
            return
        self._status.text = f"File snapshot published at {published}"
        with self._selector:
            self._combo = ui.ComboBox(0, *(label for label, _, _ in self._sections))
            self._combo.model.add_item_changed_fn(self._select)
        self._select(self._combo.model, None)

    def _select(self, model, _item):
        index = model.get_item_value_model().as_int
        _, location, text = self._sections[index]
        self._location.text = self._location.tooltip = location
        self._text.model.set_value(text)

    def destroy(self):
        self._task.cancel()
        self._window.destroy()
