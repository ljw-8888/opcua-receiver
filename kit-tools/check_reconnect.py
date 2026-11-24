"""Exercise server restart, Kit table widgets, the snapshot API and both output formats.

Run in Kit with --enable omni.kit.uiapp --enable hd.opcua.receiver --exec <this file>.
The script starts its own loopback server and exits Kit with the test result.
"""
import asyncio
import socket
import tempfile
import traceback
from contextlib import closing
from pathlib import Path

import omni.kit.app
import omni.ui as ui
from asyncua import Server, ua
from openpyxl import load_workbook
from pxr import Sdf, Usd

from hd_opcua_receiver import extension as ext
from hd_opcua_receiver.receiver import address_key


URI = "urn:receiver:reconnect-test"
PERIOD = 0.6


async def wait_for(predicate, timeout=30):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.03)


async def make_server(endpoint, *, restarted):
    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    if restarted:
        await server.register_namespace("urn:receiver:index-padding")
    ns = await server.register_namespace(URI)
    folder = await server.nodes.objects.add_object(ns, "Telemetry")
    values = (200, 775, 11) if restarted else (2.0, 7.75, 1.0)
    for name, value in zip(("Pressure", "Flow", "Manual"), values):
        node = await folder.add_variable(ua.NodeId(name, ns), name, value)
        await node.add_property(ns, "Unit", "kPa" if restarted else "bar")
    return server, ns


def saved_rows(path):
    if path.suffix == ".usda":
        # Open an independent layer from disk, bypassing the layer registry.
        stage = Usd.Stage.Open(Sdf.Layer.OpenAsAnonymous(str(path)))
        root = stage.GetDefaultPrim()
        assert str(root.GetPath()) == "/Telemetry"
        result = {}
        for prim in root.GetChild("Tags").GetChildren():
            def get(name):
                attribute = prim.GetAttribute("opcua:" + name)
                return attribute.Get() if attribute else None
            assert get("namespaceUri") == URI
            result[get("identifier")] = {
                "값": get("value"), "단위": get("unit"), "수신 시각": get("receivedAt"),
                "연결 상태": root.GetAttribute("opcua:connection").Get(), "state": get("sampleState"),
                "publishing": root.GetAttribute("opcua:publishing").Get(),
                "path": str(prim.GetPath()), "type": get("valueType"),
            }
        return result
    with closing(load_workbook(path, read_only=True)) as book:
        rows = iter(book["최신값"].values)
        header = next(rows)
        records = (dict(zip(header, values)) for values in rows)
        return {row["NodeId"]: row for row in records}


def table_values(panel):
    """Read the value and unit columns directly from the settings window."""
    table = getattr(panel, "_table", None)
    containers = [table] if table else []
    result = {}
    while containers:
        widget = containers.pop()
        children = ui.Inspector.get_children(widget)
        if isinstance(widget, ui.HStack):
            labels = [child.text for child in children if isinstance(child, ui.Label)]
            if len(labels) == 6:
                result[labels[1]] = (labels[2], labels[3])
        else:
            containers.extend(child for child in children if isinstance(child, ui.Container))
    return result


async def exercise(directory, suffix):
    panel = ext._active
    session = panel.session
    session.config = directory / "registrations.json"
    path = directory / ("values." + suffix)
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        endpoint = f"opc.tcp://127.0.0.1:{sock.getsockname()[1]}/reconnect/"
    first, ns1 = await make_server(endpoint, restarted=False)
    second, ns2 = await make_server(endpoint, restarted=True)
    assert ns1 != ns2
    pressure = address_key(URI, "s=Pressure")
    failures = []
    bad_pairs = set()
    loss_at = offline_save_at = None

    def check(ok, message):
        if not ok:
            failures.append(message)

    def api():
        return {r["identifier"]: r for r in ext.get_latest_samples()}

    # Server.stop() itself awaits shutdown. Observe the loss while that call is
    # still in flight, and open each newly replaced workbook independently.
    async def monitor():
        nonlocal loss_at, offline_save_at
        last_file = None
        while True:
            now = asyncio.get_running_loop().time()
            if session.receiver.state == "Reconnecting" and loss_at is None:
                loss_at = now
            row = api().get("s=Pressure", {})
            if row.get("value") == 200 and row.get("unit") != "kPa":
                bad_pairs.add(("API", row["unit"]))
            value, unit = table_values(panel).get("s=Pressure", ("", ""))
            if value == "200" and unit != "kPa":
                bad_pairs.add(("Kit", unit))
            if path.exists():
                stat = path.stat()
                file_id = (stat.st_ino, stat.st_mtime_ns)
                if file_id != last_file:
                    disk = saved_rows(path)
                    if disk["s=Pressure"]["값"] == 200 and disk["s=Pressure"]["단위"] != "kPa":
                        bad_pairs.add((suffix, disk["s=Pressure"]["단위"]))
                    if loss_at is not None and offline_save_at is None and disk["s=Flow"]["연결 상태"] != "Connected":
                        offline_save_at = now
                    last_file = file_id
            await omni.kit.app.get_app().next_update_async()

    monitor_task = asyncio.create_task(monitor())
    try:
        async with first:
            session.connect(endpoint, {})
            await wait_for(lambda: pressure in session.catalog)
            session.choose([pressure], True)
            for name, unit in (("Flow", ""), ("Manual", "operator-unit")):
                key = await session.register("s=" + name, URI, name, unit)
                await session.include_registered([key])
            panel._select_group("chosen")
            if suffix == "usda":
                combo = next(w for w, _ in panel._controls if isinstance(w, ui.ComboBox))
                combo.model.get_item_value_model().set_value(1)
                assert panel._format == "usda"
                panel._models["usda_file"].set_value(str(path))
                panel._models["usda_seconds"].set_value(str(PERIOD))
                await panel._start(True)
            else:
                await session.start(filename=str(path), seconds=str(PERIOD))
            await wait_for(lambda: path.exists() and
                           saved_rows(path)["s=Flow"]["값"] == 7.75 and
                           table_values(panel).get("s=Pressure") == ("2", "bar"))
            before = saved_rows(path)
            assert before["s=Pressure"]["단위"] == "bar"
            assert before["s=Manual"]["단위"] == "operator-unit"
            print("INITIAL:", [(k, r["값"], r["단위"], r["연결 상태"], r["수신 시각"]) for k, r in before.items()], flush=True)
        await wait_for(lambda: session.receiver.state == "Reconnecting")
        assert ext.get_latest_samples() == []
        try:
            await wait_for(lambda: offline_save_at is not None, PERIOD + 0.25)
        except TimeoutError:
            pass
        offline = saved_rows(path)["s=Flow"]
        elapsed = offline_save_at - loss_at if offline_save_at is not None else None
        print("OFFLINE:", offline["값"], offline["단위"], offline["연결 상태"], offline["수신 시각"],
              "elapsed", elapsed, "interval", PERIOD, "API=[]", flush=True)
        check(elapsed is not None and elapsed <= PERIOD + 0.1, "missed the next file save")
        check(offline["연결 상태"] in ("Reconnecting", "Disconnected"), "stale connection in workbook")
        check(offline["값"] == 7.75 and offline["수신 시각"] == before["s=Flow"]["수신 시각"], "lost last sample")
        async with second:
            await wait_for(lambda: api().get("s=Pressure", {}).get("value") == 200)
            await wait_for(lambda: saved_rows(path)["s=Flow"]["값"] == 775 and
                           table_values(panel).get("s=Pressure", ("", ""))[0] == "200")
            after = saved_rows(path)
            rows = api()
            for name, expected, unit in (("Pressure", 200, "kPa"), ("Flow", 775, "kPa"), ("Manual", 11, "operator-unit")):
                node = "s=" + name
                row, disk = rows[node], after[node]
                displayed = table_values(panel)[node]
                print("RECONNECTED:", name, "API", row["value"], row["unit"], row["data_type"],
                      "GUI", displayed, suffix, disk["값"], disk["단위"], disk["연결 상태"], disk["수신 시각"], flush=True)
                check((row["value"], row["unit"], row["data_type"]) == (expected, unit, "Int64"), name + " API")
                check(displayed == (str(expected), unit), name + " Kit table")
                check((disk["값"], disk["단위"], disk["연결 상태"]) == (expected, unit, "Connected"), name + " workbook")
                check(disk["수신 시각"] == row["received_at"] and disk["수신 시각"] != before[node]["수신 시각"], name + " timestamp")
            check(not bad_pairs, f"transient mismatches {bad_pairs}")
            print("NAMESPACE:", ns1, "->", ns2, "MISMATCHES:", bad_pairs, flush=True)
            if suffix == "usda":
                assert len(after) == 3
                assert before["s=Pressure"]["type"] == "Double" and after["s=Pressure"]["type"] == "Int64"
                assert before["s=Pressure"]["path"] == after["s=Pressure"]["path"]
                assert offline["state"] == "Stale" and after["s=Flow"]["state"] == "Current"
                await session.stop_save()
                stopped = saved_rows(path)["s=Pressure"]
                assert not stopped["publishing"] and stopped["state"] == "Stale" and api()["s=Pressure"]["value"] == 200
                await panel._start(True)
                await wait_for(lambda: saved_rows(path)["s=Pressure"]["publishing"])
            await session.disconnect()
            if suffix == "usda":
                stopped = saved_rows(path)["s=Pressure"]
                assert not stopped["publishing"] and stopped["연결 상태"] == "Disconnected"
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        finally:
            await session.disconnect()
    assert not failures, failures


async def main():
    code = 1
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ("xlsx", "usda"):
                await exercise(Path(tmp), suffix)
        print("RECONNECT PASS", flush=True)
        code = 0
    except Exception:
        traceback.print_exc()
    finally:
        omni.kit.app.get_app().post_uncancellable_quit(code)


asyncio.ensure_future(main())
