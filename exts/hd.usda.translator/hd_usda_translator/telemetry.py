"""Read the standalone OPC UA receiver layer. Requires only OpenUSD."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pxr import Sdf

FORMAT = "hd.opcua.receiver/telemetry/1"


def _attr(prim, name):
    attr = prim.attributes.get("opcua:" + name)
    return attr.default if attr else None


@dataclass(frozen=True)
class Sample:
    value: object
    unit: str
    quality: str
    state: str
    received_at: str
    encoding: str
    display_name: str
    data_type: str
    value_type: str
    source_timestamp: str
    prim_path: str = ""


@dataclass(frozen=True)
class Snapshot:
    source: str
    connection: str
    publishing: bool
    published_at: datetime
    tags: dict


def read_snapshot(path):
    """Read one complete publication independently of any open scene or layer cache."""
    layer = Sdf.Layer.OpenAsAnonymous(str(path))
    return parse_layer(layer)


def parse_layer(layer):
    """Index the tags from one receiver layer by endpoint, namespace URI and identifier."""
    if not layer or layer.customLayerData.get("opcuaFormat") != FORMAT:
        raise ValueError("Select a telemetry USDA written by the OPC UA receiver.")
    root = layer.GetPrimAtPath("/Telemetry")
    group = layer.GetPrimAtPath("/Telemetry/Tags")
    if not root or not group:
        raise ValueError("Missing /Telemetry or /Telemetry/Tags.")
    source = _attr(root, "source")
    published = datetime.fromisoformat(_attr(root, "publishedAt") or "")
    connection = _attr(root, "connection")
    publishing = _attr(root, "publishing")
    if not source or published.tzinfo is None or not connection or not isinstance(publishing, bool):
        raise ValueError("Incomplete telemetry header.")
    tags = {}
    for tag in group.nameChildren:
        uri, identifier = _attr(tag, "namespaceUri"), _attr(tag, "identifier")
        key = (source, uri, identifier)
        if not uri or not identifier or key in tags:
            raise ValueError("Missing or duplicate tag identity.")
        tags[key] = Sample(_attr(tag, "value"), _attr(tag, "unit") or "",
                           _attr(tag, "quality") or "", _attr(tag, "sampleState") or "",
                           _attr(tag, "receivedAt") or "", _attr(tag, "encoding") or "",
                           _attr(tag, "displayName") or "", _attr(tag, "dataType") or "",
                           _attr(tag, "valueType") or "", _attr(tag, "sourceTimestamp") or "",
                           str(tag.path))
    return Snapshot(source, connection, publishing, published, tags)


def publication_status(snapshot, timeout):
    """Report whether this file still has a connected publisher within timeout seconds."""
    if not snapshot.publishing:
        return "Stopped"
    if snapshot.connection != "Connected":
        return snapshot.connection
    age = (datetime.now(timezone.utc) - snapshot.published_at).total_seconds()
    if age < -timeout:
        return "Clock skew"
    return "No update" if age > timeout else "Live"


class SnapshotFile:
    """Keep the last complete read while this file version remains on disk."""
    def __init__(self, path):
        self.path = Path(path)
        self.version = None
        self.snapshot = None

    def read(self):
        st = self.path.stat()
        version = st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size
        if version != self.version:
            snapshot = read_snapshot(self.path)
            if self.snapshot and self.snapshot.source != snapshot.source:
                raise ValueError("Endpoint changed. Select the file again to accept the new source.")
            self.snapshot = snapshot
            self.version = version
        return self.snapshot
