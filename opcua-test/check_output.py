"""Exercise the desktop format selector and reopen files across an OPC UA restart."""
import asyncio
import os
import socket
import tempfile
from contextlib import closing
from pathlib import Path

from asyncua import Server, ua
from openpyxl import load_workbook
from pxr import Sdf
from PySide6.QtWidgets import QApplication

import receiver_gui as gui

URI = "urn:test:desktop"


async def until(check):
    async with asyncio.timeout(30):
        while not check():
            QApplication.processEvents()
            await asyncio.sleep(.04)


async def server(endpoint, unit, value):
    instance = Server()
    await instance.init()
    instance.set_endpoint(endpoint)
    if unit == "kPa":
        await instance.register_namespace("urn:test:extra")
    ns = await instance.register_namespace(URI)
    node = await instance.nodes.objects.add_variable(ua.NodeId("Pressure", ns), "Pressure", value)
    await node.add_property(ns, "Unit", unit)
    return instance


def sample(path):
    if not path.is_file():
        return {}
    layer = Sdf.Layer.OpenAsAnonymous(str(path))
    root = layer.GetPrimAtPath("/Telemetry")
    tag, = root.nameChildren["Tags"].nameChildren
    assert tag.attributes["opcua:namespaceUri"].default == URI
    assert tag.attributes["opcua:identifier"].default == "s=Pressure"
    return {str(attr.name): attr.default for prim in (root, tag) for attr in prim.attributes.values()}


async def exercise(directory):
    gui.CONFIG = directory / "settings.json"
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        endpoint = f"opc.tcp://127.0.0.1:{sock.getsockname()[1]}/"
    first = await server(endpoint, "bar", 2.0)
    second = await server(endpoint, "kPa", 200)
    panel = gui.Panel()
    path = directory / "pressure.usda"
    book = directory / "pressure.xlsx"
    try:
        async with first:
            panel.set_field("endpoint", endpoint)
            panel.connect()
            await until(lambda: panel.receiver.state == "Connected")
            panel.chosen.add(await panel.receiver.add_node("s=Pressure", URI))
            panel.set_field("format", gui.USDA)
            assert panel.get(panel.period_key) == "1" and panel.preview_button.isHidden()
            panel.set_field(panel.file_key, str(path))
            panel.set_field(panel.period_key, "0.25")
            panel.start()
            await until(lambda: sample(path).get("opcua:value") == 2.0)
            before = sample(path)
            assert before["opcua:unit"] == "bar" and before["opcua:sampleState"] == "Current"
        await until(lambda: sample(path).get("opcua:connection") == "Reconnecting")
        old = sample(path)
        assert old["opcua:sampleState"] == "Stale" and old["opcua:value"] == 2.0
        assert old["opcua:receivedAt"] == before["opcua:receivedAt"]
        async with second:
            await until(lambda: sample(path).get("opcua:value") == 200)
            new = sample(path)
            assert (new["opcua:unit"], new["opcua:dataType"], new["opcua:sampleState"]) == ("kPa", "Int64", "Current")
            assert new["opcua:receivedAt"] != before["opcua:receivedAt"]
            await panel.stop()
            assert not sample(path)["opcua:publishing"] and panel.receiver.selected
            panel.set_field("format", gui.EXCEL)
            assert panel.get(panel.period_key) == "5" and not panel.preview_button.isHidden()
            panel.set_field(panel.file_key, str(book))
            panel.start()
            await until(book.is_file)
            await panel.pause_receiving()
            with closing(load_workbook(book, read_only=True)) as xl:
                header, values = xl["최신값"].values
                row = dict(zip(header, values))
                assert (row["값"], row["단위"], row["연결 상태"]) == (200, "kPa", "Connected")
            panel.set_field("format", gui.USDA)
            assert panel.get(panel.file_key) == str(path)
            panel.start()
            await until(lambda: sample(path).get("opcua:sampleState") == "Current")
            await panel.disconnect()
            assert sample(path)["opcua:connection"] == "Disconnected" and not sample(path)["opcua:publishing"]
    finally:
        await panel.disconnect()
        await panel.preview.shutdown()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(exercise(Path(tmp)))
    print("Desktop USDA and Excel output passed")
