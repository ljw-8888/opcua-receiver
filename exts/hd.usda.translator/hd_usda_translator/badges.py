"""Render a measurement as a single badge row."""


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
