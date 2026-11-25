"""Viewport example that displays selected rows from the public measurement API."""
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

    def refresh(self, selected, by_field, publication_status, idle_status):
        self.status.text = f"USDA: {publication_status}" if publication_status else idle_status
        for row, line in enumerate(self.lines):
            field = selected[row]
            measurement, missing = field.resolve(by_field)
            if measurement is not None:
                text = measurement_line(measurement)
                if field.source_tag:
                    text += f" [{measurement.namespace_uri}]"
                line.tooltip = f"{text}\n{measurement.identifier}\n{measurement.namespace_uri}"
            else:
                text = f"{field.label}: {missing if publication_status else '—'}"
                line.tooltip = text
            if line.text != text:
                line.text = text
