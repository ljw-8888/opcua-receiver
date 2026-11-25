"""Interpret receiver tags as measurements for consumers of the example USDA."""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .telemetry import publication_status


_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "tags.json"
TAG_DEFAULTS = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
_STREAM_FIELDS = {field["tag"]: field for field in TAG_DEFAULTS["fields"]}


@dataclass(frozen=True)
class Measurement:
    """A process reading. An unavailable value is None and status gives the reason."""
    target: str
    quantity: str
    value: object
    unit: str
    status: str = "Live"
    quality: str = ""
    received_at: str = ""
    number_format: str = "number"
    namespace_uri: str = ""
    identifier: str = ""


def _interpret_tag(key, sample, stream_fields):
    _, identifier = key
    name = identifier.removeprefix("s=")
    parts = name.split("/") if identifier.startswith("s=") else []
    if len(parts) == 3 and parts[0] in ("Stream", "Equipment") and all(parts):
        group, target, quantity = parts
        field = stream_fields.get(quantity) if group == "Stream" else None
        if field:
            return f"{group} {target}", field.get("label", quantity), field.get("format", "number")
        return f"{group} {target}", quantity, "raw"
    if len(parts) <= 1 and sample and sample.display_name not in ("", name, identifier):
        name = f"{sample.display_name} ({identifier})"
    return "", name, "raw"


def current_reading(sample, status, number_format):
    """Return the numeric or raw value, unit and availability from the same sample."""
    if sample is None:
        return None, "", "No tag"
    value, unit = sample.value, sample.unit
    if status != "Live":
        return None, unit, status
    if sample.state != "Current":
        return None, unit, sample.state or "Unavailable"
    if not sample.quality.startswith("Good"):
        return None, unit, sample.quality or "Unknown quality"
    if sample.encoding or value is None:
        return None, unit, "Unavailable"
    if number_format == "raw" and not isinstance(value, float):
        # USD arrays must not be mutable through a shared measurement.
        if type(value).__module__ == "pxr.Vt":
            value = tuple(value)
        return value, unit, "Live"
    if type(value) not in (int, float) or not math.isfinite(value):
        return None, unit, "Unavailable"
    if number_format == "percent":
        scale = unit.strip().casefold()
        if scale == "fraction":
            value *= 100
        elif scale not in ("%", "percent"):
            return None, unit, "Check unit"
        if not 0 <= value <= 100:
            return None, "%", "Out of range"
        unit = "%"
    return value, unit, "Live"


def parse_measurement(snapshot, key, status, stream_fields=_STREAM_FIELDS):
    """Resolve a selected (namespace URI, identifier) within one publication."""
    sample = snapshot.tags.get((snapshot.source, *key)) if snapshot is not None else None
    target, quantity, number_format = _interpret_tag(key, sample, stream_fields)
    if snapshot is None:
        return Measurement(target, quantity, None, "", "No snapshot",
                           namespace_uri=key[0], identifier=key[1])
    value, unit, state = current_reading(sample, status, number_format)
    return Measurement(
        target, quantity, value, unit, status=state, number_format=number_format,
        quality=sample.quality if sample else "",
        received_at=sample.received_at if sample else "",
        namespace_uri=key[0], identifier=key[1],
    )


def _readings(snapshot, status):
    for _, uri, identifier in snapshot.tags:
        yield parse_measurement(snapshot, (uri, identifier), status)


def iter_measurements(snapshot, timeout=10):
    """Yield one measurement per stored tag, including its current availability."""
    yield from _readings(snapshot, publication_status(snapshot, timeout))


_last_snapshot = None
_last_status = ""
_latest: tuple[Measurement, ...] = ()


def get_latest_measurements() -> tuple[Measurement, ...]:
    """Return all measurements from the last completed watch cycle, without file I/O."""
    return _latest


def _publish(snapshot, status=""):
    global _last_snapshot, _last_status, _latest
    if snapshot is _last_snapshot and status == _last_status:
        return
    _latest = tuple(_readings(snapshot, status)) if snapshot is not None else ()
    _last_snapshot, _last_status = snapshot, status
