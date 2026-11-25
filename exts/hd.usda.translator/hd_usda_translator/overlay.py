"""Viewport example that displays selected rows from the public measurement API."""
from . import get_latest_measurements
from .badges import measurement_line


class ScreenBadge:
    def __init__(self, fields):
        import omni.ui as ui

        self.lines = []
        with ui.ZStack(height=34 + 22 * len(fields), opaque_for_mouse_events=False):
            ui.Rectangle(style={"background_color": 0xf52d2520, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=12)
                with ui.VStack(spacing=2):
                    ui.Spacer(height=3)
                    for _ in fields:
                        self.lines.append(ui.Label("", height=20, elided_text=True))
                    self.status = ui.Label("", height=22, alignment=ui.Alignment.RIGHT_CENTER,
                                           style={"color": 0xffb9c2c3})
                ui.Spacer(width=12)

    def refresh(self, selected, publication_status, idle_status):
        batch = get_latest_measurements()
        by_tag = {(m.namespace_uri, m.identifier): m for m in batch}
        namespaces = {}
        for uri, identifier in selected.values():
            namespaces.setdefault(identifier, set()).add(uri)

        self.status.text = f"USDA: {publication_status}" if publication_status else idle_status
        for row, line in enumerate(self.lines):
            uri, identifier = selected[row]
            measurement = by_tag.get((uri, identifier))
            if measurement is None:
                missing = "No tag" if publication_status else "—"
                text = f"{identifier}: {missing}"
            else:
                text = measurement_line(measurement)
            if len(namespaces[identifier]) > 1:
                text += f" [{uri}]"
            if line.text != text:
                line.text = text
            line.tooltip = f"{text}\n{identifier}\n{uri}"
