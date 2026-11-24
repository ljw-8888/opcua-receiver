"""Check the telemetry file contract using the OpenUSD libraries shipped with Kit."""
import base64
import tempfile
import traceback
from pathlib import Path

import omni.kit.app
from asyncua.common.utils import Buffer
from asyncua.ua.ua_binary import variant_from_binary
from pxr import Sdf, Usd

from hd_opcua_receiver.latest_usda import UsdaOutput


def check(directory):
    path = directory / "telemetry.usda"
    source = "opc.tcp://example:4840"
    output = UsdaOutput(path)
    sample = dict(source=source, namespace_uri="urn:test", identifier="s=a/b", metric="한글",
                  unit="m/s", data_type="Double", value_type="Double", value=0.0, dimensions=None,
                  received_at="2026-01-01T00:00:00Z", source_timestamp="", quality="Good", connection="Connected")
    rows = [sample,
            dict(sample, identifier="s=a-b", value=None, received_at="", quality="Missing"),
            dict(sample, namespace_uri="urn:other", value_type="UInt64", value=2**64 - 1),
            dict(sample, identifier="s=array", value=[1., 2.]),
            dict(sample, identifier="s=matrix", value=[[1., 2.]], dimensions=[1, 2]),
            dict(sample, identifier="s=invalid", quality="BadNotConnected", value=None)]
    output.save(source, "Connected", True, rows)
    stage = Usd.Stage.Open(str(path))
    root = stage.GetDefaultPrim()
    tags = {(p.GetAttribute("opcua:namespaceUri").Get(), p.GetAttribute("opcua:identifier").Get()): p
            for p in root.GetChild("Tags").GetChildren()}
    assert len(tags) == len(rows)

    def prop(node, name, uri="urn:test"):
        return tags[uri, node].GetAttribute("opcua:" + name)

    assert prop("s=a/b", "value").IsCustom() and prop("s=a/b", "value").Get() == 0
    assert prop("s=a-b", "sampleState").Get() == "Waiting" and not prop("s=a-b", "value")
    assert prop("s=invalid", "sampleState").Get() == "Unavailable" and not prop("s=invalid", "value")
    counter = prop("s=a/b", "value", "urn:other")
    assert counter.GetTypeName() == Sdf.ValueTypeNames.UInt64 and counter.Get() == 2**64 - 1
    assert list(prop("s=array", "value").Get()) == [1., 2.]
    matrix = variant_from_binary(Buffer(base64.b64decode(prop("s=matrix", "value").Get())))
    assert matrix.Value == [[1., 2.]] and matrix.Dimensions == [1, 2]
    assert prop("s=matrix", "encoding").Get() == "UaBinaryVariantBase64"

    # Old selection disappears on reload. Last sample time is independent of the publication time.
    output.save(source, "Disconnected", False, [sample])
    stage.GetRootLayer().Reload(force=True)
    assert len(root.GetChild("Tags").GetChildren()) == 1
    assert prop("s=a/b", "receivedAt").Get() == sample["received_at"]
    assert prop("s=a/b", "sampleState").Get() == "Stale"

    def check_protected(target):
        original = target.read_bytes()
        try:
            UsdaOutput(target).save("opc.tcp://another:4840", "Connected", True, [])
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unexpected overwrite: {target}")
        assert target.read_bytes() == original

    check_protected(path)
    asset = directory / "asset.usda"
    asset.write_text('#usda 1.0\ndef Xform "Vessel" {}\n', encoding="utf-8")
    check_protected(asset)


code = 1
try:
    with tempfile.TemporaryDirectory() as tmp:
        check(Path(tmp))
    print("USDA FORMAT PASS", flush=True)
    code = 0
except Exception:
    traceback.print_exc()
finally:
    omni.kit.app.get_app().post_uncancellable_quit(code)
