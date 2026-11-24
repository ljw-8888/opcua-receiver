"""Publish one standalone OpenUSD layer containing the selected OPC UA samples."""

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from asyncua import ua
from asyncua.ua.ua_binary import variant_to_binary
from pxr import Sdf

FORMAT = "hd.opcua.receiver/telemetry/1"
T = Sdf.ValueTypeNames
VALUE_TYPES = {
    "Boolean": T.Bool, "SByte": T.Int, "Byte": T.UChar, "Int16": T.Int, "UInt16": T.UInt,
    "Int32": T.Int, "UInt32": T.UInt, "Int64": T.Int64, "UInt64": T.UInt64,
    "Float": T.Float, "Double": T.Double, "String": T.String,
}


def tag_name(row):
    identity = [row[k] for k in ("source", "namespace_uri", "identifier")]
    key = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
    label = re.sub(r"[^A-Za-z0-9]+", "_", row["identifier"].partition("=")[2]).strip("_")[:48]
    return "T_" + label + "_" + hashlib.sha256(key).hexdigest()


def attr(prim, name, dtype, value):
    spec = Sdf.AttributeSpec(prim, "opcua:" + name, dtype, declaresCustom=True)
    spec.default = value


def write_value(prim, row):
    value, kind = row["value"], row["value_type"] or row["data_type"]
    dtype = VALUE_TYPES.get(kind)
    is_array = isinstance(value, (list, tuple))
    dimensions = row["dimensions"]
    nested = is_array and any(isinstance(v, (list, tuple)) for v in value)
    if dtype and len(dimensions or ()) <= 1 and not nested:
        attr(prim, "value", dtype.arrayType if is_array else dtype, value)
    elif kind == "DateTime" and not is_array:
        attr(prim, "value", T.String, value.isoformat())
    else:
        # Preserve structured values and multidimensional arrays without converting them to repr().
        variant = ua.Variant(value, ua.VariantType[kind], Dimensions=dimensions)
        attr(prim, "value", T.String, base64.b64encode(variant_to_binary(variant)).decode("ascii"))
        attr(prim, "encoding", T.Token, "UaBinaryVariantBase64")


def make_layer(source, connection, publishing, rows):
    layer = Sdf.Layer.CreateAnonymous("telemetry.usda")
    layer.customLayerData = {"opcuaFormat": FORMAT}
    layer.defaultPrim = "Telemetry"
    root = Sdf.PrimSpec(layer, "Telemetry", Sdf.SpecifierDef, "Scope")
    attr(root, "source", T.String, source)
    attr(root, "connection", T.Token, connection)
    attr(root, "publishing", T.Bool, publishing)
    attr(root, "publishedAt", T.String, datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
    tags = Sdf.PrimSpec(root, "Tags", Sdf.SpecifierDef, "Scope")
    for row in rows:
        prim = Sdf.PrimSpec(tags, tag_name(row), Sdf.SpecifierDef, "Scope")
        for name, field in (("namespaceUri", "namespace_uri"), ("identifier", "identifier"),
                            ("displayName", "metric"), ("dataType", "data_type"),
                            ("valueType", "value_type"), ("unit", "unit"),
                            ("quality", "quality"), ("sourceTimestamp", "source_timestamp"),
                            ("receivedAt", "received_at")):
            attr(prim, name, T.String, row[field])
        if not row["received_at"]:
            state = "Waiting" if row["quality"] == "Missing" else "Unavailable"
        elif not publishing or connection != "Connected" or row["connection"] != "Connected":
            state = "Stale"
        elif row["value"] is None:
            state = "Unavailable"
        else:
            state = "Current"
        if row["value"] is not None:
            write_value(prim, row)
        attr(prim, "sampleState", T.Token, state)
    return layer


def file_version(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size


class UsdaOutput:
    def __init__(self, path, translate=str):
        self.path = path
        self.translate = translate
        self.last_version = None

    def save(self, source, connection, publishing, rows):
        original = file_version(self.path)
        if original is not None and original != self.last_version:
            existing = Sdf.Layer.OpenAsAnonymous(str(self.path))
            if not existing or existing.customLayerData.get("opcuaFormat") != FORMAT:
                raise ValueError(self.translate("새 .usda 파일이나 수신기가 만든 데이터 파일을 선택하세요."))
            root = existing.GetPrimAtPath("/Telemetry")
            origin = root.attributes.get("opcua:source") if root else None
            if not origin or origin.default != source:
                raise ValueError(self.translate("이 데이터 파일은 다른 OPC UA 서버에서 저장했습니다."))

        layer = make_layer(source, connection, publishing, rows)
        with TemporaryDirectory(dir=self.path.parent) as directory:
            pending = Path(directory) / "snapshot.usda"
            if not layer.Export(str(pending)):
                raise OSError(f"Cannot export {self.path}")
            if file_version(self.path) != original:
                raise OSError(f"File changed during publication: {self.path}")
            version = file_version(pending)
            os.replace(pending, self.path)
            self.last_version = version
