"""Choose the tag for each badge row from the loaded receiver file."""
from functools import partial

import omni.ui as ui

from .badges import BadgeField


class BadgeTags:
    def __init__(self, rules):
        self.defaults = {}
        self.selected = {}
        self._buttons = {}
        self._snapshot = self._slot = None
        self._by_field = {}
        self._options = []
        self._query = ui.SimpleStringModel("")

        self._overview = ui.VStack(height=0, spacing=4)
        with self._overview:
            with ui.HStack(height=24):
                ui.Label("Badge tags")
                ui.Button("Reset defaults", width=110, clicked_fn=self._reset)
            for slot, field in enumerate(rules["fields"]):
                choice = BadgeField(rules["defaultTarget"], field["label"])
                self.defaults[slot] = self.selected[slot] = choice
                self._buttons[slot] = ui.Button(
                    choice.label, height=24, enabled=False,
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

    def update_snapshot(self, snapshot, by_field=None):
        self._by_field = by_field or {}
        if snapshot is self._snapshot:
            return
        if (snapshot is None) != (self._snapshot is None):
            for slot, button in self._buttons.items():
                button.enabled = snapshot is not None
                button.tooltip = self.selected[slot].label if snapshot else "Choose a receiver USDA to select its tags."
        self._snapshot = snapshot
        if snapshot is None:
            self._close()
        elif self._slot is not None:
            self._refresh_options()

    def _open(self, slot):
        if self._snapshot is None:
            return
        self._slot = slot
        self._heading.text = self.selected[slot].label
        self._query.set_value("")
        self._overview.visible = False
        self._editor.visible = True
        self._refresh_options()

    def _refresh_options(self):
        options = []
        for (target, quantity), group in self._by_field.items():
            for m in group:
                sample = self._snapshot.tags[self._snapshot.source, m.namespace_uri, m.identifier]
                options.append((target, quantity, m.namespace_uri, m.identifier, sample.display_name, len(group) > 1))
        options.sort()
        if self._options != options:
            self._options = options
            self._results.rebuild()

    def _build_results(self):
        query = self._query.as_string.strip().casefold()
        with ui.VStack(height=0, spacing=2):
            found = False
            for target, quantity, uri, identifier, name, duplicate in self._options:
                label = f"{target} {quantity}".strip()
                if query and not any(query in text.casefold() for text in (label, name, identifier, uri)):
                    continue
                found = True
                detail = f"{uri} · {identifier}" if duplicate else identifier
                with ui.HStack(height=24, spacing=6):
                    ui.Button(label, tooltip=f"{name}\n{identifier}\n{uri}",
                              clicked_fn=partial(self._choose, target, quantity, uri, identifier))
                    ui.Label(detail, width=ui.Percent(40), elided_text=True, tooltip=f"{uri}\n{identifier}")
            if not found:
                ui.Label("No matching tags in this file.", height=24)

    def _choose(self, target, quantity, uri, identifier):
        matches = self._by_field.get((target, quantity), ())
        if self._slot is None or not any((m.namespace_uri, m.identifier) == (uri, identifier) for m in matches):
            return
        source_tag = (uri, identifier) if len(matches) > 1 else None
        self._set(self._slot, BadgeField(target, quantity, source_tag))
        self._close()

    def _set(self, slot, field):
        self.selected[slot] = field
        self._buttons[slot].text = field.label
        if self._snapshot is not None:
            self._buttons[slot].tooltip = "\n".join(field.source_tag) if field.source_tag else field.label

    def source_rows(self):
        rows = []
        for field in self.selected.values():
            m, reason = field.resolve(self._by_field)
            address = (m.namespace_uri, m.identifier) if m is not None else None
            rows.append((field.label, address, reason))
        return rows

    def _reset(self):
        for slot, key in self.defaults.items():
            self._set(slot, key)

    def _close(self):
        self._slot = None
        self._editor.visible = False
        self._overview.visible = True
