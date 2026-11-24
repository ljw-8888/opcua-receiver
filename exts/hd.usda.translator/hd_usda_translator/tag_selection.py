"""Choose the tag for each badge row from the loaded receiver file."""
from functools import partial

import omni.ui as ui


class BadgeTags:
    def __init__(self, rules):
        self.defaults = {}
        self.selected = {}
        self._buttons = {}
        self._snapshot = self._slot = None
        self._options = []
        self._query = ui.SimpleStringModel("")

        self._overview = ui.VStack(height=0, spacing=4)
        with self._overview:
            with ui.HStack(height=24):
                ui.Label("Badge tags")
                ui.Button("Reset defaults", width=110, clicked_fn=self._reset)
            for slot, field in enumerate(rules["fields"]):
                key = (rules["namespaceUri"], rules["tagPrefix"] + field["tag"])
                self.defaults[slot] = self.selected[slot] = key
                self._buttons[slot] = ui.Button(
                    key[1], height=24, enabled=False,
                    tooltip="Choose a receiver USDA to select its tags.",
                    clicked_fn=partial(self._open, slot),
                )
        self._editor = ui.VStack(height=0, visible=False, spacing=4)
        with self._editor:
            with ui.HStack(height=24):
                self._heading = ui.Label("")
                ui.Button("Back", width=65, clicked_fn=self._close)
            with ui.HStack(height=24, spacing=6):
                ui.Label("Find tag", width=60)
                ui.StringField(model=self._query)
            self._results = ui.ScrollingFrame(height=154, horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF)
            self._results.set_build_fn(self._build_results)
        self._query.add_value_changed_fn(lambda _: self._results.rebuild())

    def update_snapshot(self, snapshot):
        if snapshot is self._snapshot:
            return
        if (snapshot is None) != (self._snapshot is None):
            for slot, button in self._buttons.items():
                button.enabled = snapshot is not None
                button.tooltip = self.selected[slot][0] if snapshot else "Choose a receiver USDA to select its tags."
        self._snapshot = snapshot
        if snapshot is None:
            self._close()
        elif self._slot is not None:
            self._refresh_options()

    def _open(self, slot):
        if self._snapshot is None:
            return
        self._slot = slot
        self._heading.text = self.selected[slot][1]
        self._query.set_value("")
        self._overview.visible = False
        self._editor.visible = True
        self._refresh_options()

    def _refresh_options(self):
        options = sorted((key, tag.display_name) for key, tag in self._snapshot.tags.items())
        if self._options != options:
            self._options = options
            self._results.rebuild()

    def _build_results(self):
        query = self._query.as_string.strip().casefold()
        with ui.VStack(height=0, spacing=2):
            found = False
            for key, name in self._options:
                _, uri, identifier = key
                if query and not any(query in text.casefold() for text in (name, identifier, uri)):
                    continue
                found = True
                with ui.HStack(height=24, spacing=6):
                    ui.Button(identifier, tooltip=f"{name}\n{identifier}", clicked_fn=partial(self._choose, key))
                    ui.Label(uri, width=ui.Percent(35), elided_text=True, tooltip=uri)
            if not found:
                ui.Label("No matching tags in this file.", height=24)

    def _choose(self, key):
        if self._slot is None or self._snapshot is None or key not in self._snapshot.tags:
            return
        self._set(self._slot, key[1:])
        self._close()

    def _set(self, slot, key):
        self.selected[slot] = key
        self._buttons[slot].text = key[1]
        if self._snapshot is not None:
            self._buttons[slot].tooltip = key[0]

    def _reset(self):
        for slot, key in self.defaults.items():
            self._set(slot, key)

    def _close(self):
        self._slot = None
        self._editor.visible = False
        self._overview.visible = True
