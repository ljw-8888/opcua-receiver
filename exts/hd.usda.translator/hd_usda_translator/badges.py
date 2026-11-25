"""Match viewport labels to translated measurements and format their values."""
from dataclasses import dataclass


def group_measurements(rows):
    by_field = {}
    for m in rows:
        by_field.setdefault((m.target, m.quantity), []).append(m)
    return by_field


@dataclass(frozen=True)
class BadgeField:
    target: str
    quantity: str
    # Set only when the user chooses a particular source among duplicate fields.
    source_tag: tuple[str, str] | None = None

    @property
    def label(self):
        return f"{self.target} {self.quantity}".strip()

    def resolve(self, by_field):
        matches = by_field.get((self.target, self.quantity), ())
        if self.source_tag:
            for m in matches:
                if (m.namespace_uri, m.identifier) == self.source_tag:
                    return m, ""
            return None, "No tag"
        if len(matches) == 1:
            return matches[0], ""
        return None, "태그 중복" if matches else "No tag"


def _value_text(value, unit, status, number_format):
    if status == "No snapshot":
        return "—"
    if status != "Live":
        return status
    if value is None:
        return "Unavailable"
    if type(value) not in (float, int):
        return f"{value} {unit}".rstrip()
    if number_format == "percent":
        return f"{value:.2f} {unit}"
    if number_format == "raw" and not isinstance(value, float):
        return f"{value} {unit}".rstrip()
    return f"{value:.5g} {unit}".rstrip()


def measurement_line(measurement):
    label = f"{measurement.target} {measurement.quantity}".strip()
    text = _value_text(measurement.value, measurement.unit, measurement.status, measurement.number_format)
    return f"{label}: {text}"
