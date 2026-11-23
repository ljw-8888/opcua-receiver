"""Run inside a GUI-capable Kit app with --enable hd.opcua.receiver --exec <this file>."""
import asyncio
import socket
import tempfile
import traceback
from pathlib import Path


async def until(predicate, seconds=90):
    async with asyncio.timeout(seconds):
        while not predicate():
            await asyncio.sleep(.1)


async def smoke():
    import omni.kit.app
    code = 1
    try:
        import hd_opcua_receiver.extension as ext
        from asyncua import Server, ua
        from openpyxl import Workbook, load_workbook

        panel = ext._active
        assert panel._window.visible
        s = panel.session
        with tempfile.TemporaryDirectory() as tmp:
            s.config = Path(tmp) / "receiver-settings.json"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                endpoint = f"opc.tcp://127.0.0.1:{sock.getsockname()[1]}/test/"
            server = Server()
            await server.init()
            server.set_endpoint(endpoint)
            server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            uri = "urn:hd:opcua:test:v1"
            ns = await server.register_namespace(uri)
            plant = await server.nodes.objects.add_object(ns, "Plant")
            room = await plant.add_object(ns, "EngineRoom")
            sensor = await room.add_variable(ua.NodeId("Stream/1/Pressure", ns), "Pressure", 4.5)
            await sensor.add_property(ns, "Unit", "barG")
            await plant.add_variable(ua.NodeId("Stream/1/Temperature", ns), "Temperature", 21.0)
            for i in range(70):
                await room.add_variable(ns, f"BulkTag{i:02}", float(i))
            async with server:
                # Endpoint is the only input to discovery.
                panel._models["endpoint"].set_value(endpoint)
                panel._connect()
                await until(lambda: bool(s.catalog) and not s.scanning)
                assert not s.scan_error, s.scan_error
                panel._models["search"].set_value("stream/1/")
                found = panel._filtered()
                assert len(found) == 2
                assert len(s.members[room.nodeid.to_string()]) == 71
                panel._select_group("all")
                panel._models["search"].set_value("BulkTag")
                all_pages = panel._filtered()
                assert len(all_pages) > ext.PAGE_SIZE
                s.choose(all_pages, True)
                assert s.chosen == set(all_pages)
                await panel._start(False)
                await until(lambda: s.receiver.subscription_count == 70 and len(s.receiver.samples) == 70)
                await s.pause()
                s.choose(all_pages, False)
                panel._switch(1)
                await asyncio.sleep(.3)
                panel._switch(2)
                await asyncio.sleep(.3)
                panel._switch(0)
                await asyncio.sleep(.3)
                s.choose(found, True)
                panel._select_group("chosen")
                assert len(panel._filtered()) == 2
                panel._models["search"].set_value("Temperature")
                s.choose(panel._filtered(), False)
                assert len(s.chosen) == 1
                panel._models["search"].set_value("")
                for key, value in dict(node="s=Stream/1/Temperature", namespace=uri, alias="온도", unit="degC").items():
                    panel._models[key].set_value(value)
                await panel._register()
                await panel._include()
                assert len(s.chosen) == 2 and len(s.registered) == 1
                await panel._start(False)
                await until(lambda: len(ext.get_latest_samples()) == 2 and
                            all(row["quality"] == "Good" for row in ext.get_latest_samples()))
                assert {r["unit"] for r in ext.get_latest_samples()} == {"degC", "barG"}
                panel._window.visible = False
                ext.show_settings()
                assert panel._window.visible and len(s.receiver.selected) == 2
                output = Path(tmp) / "receiver.xlsx"
                book = Workbook()
                book.active.title = "최신값"
                book.active["A1"] = "기존 사용자 데이터"
                book.save(output)
                book.close()
                panel._models["file"].set_value(str(output))
                panel._models["seconds"].set_value("0.3")
                await panel._start(True)
                await until(lambda: s.preview is not None)
                assert set(s.preview[2]) == {"최신값1", "HYSYS"}
                panel._show_preview()
                panel._choose_sheet("HYSYS")
                await sensor.write_value(7.25)
                await until(lambda: any(row[2] == 7.25 for row in s.preview[2]["최신값1"][1:]))
                await s.stop_save()
                assert s.receiver.selected
                book = load_workbook(output)
                assert book["최신값"]["A1"].value == "기존 사용자 데이터"
                assert "HYSYS" in book.sheetnames
                book.close()
                await s.pause()
                assert not ext.get_latest_samples() and s.paused
                await panel._disconnect()
                assert not ext.get_latest_samples()
                from hd_opcua_receiver.session import Session
                restored = Session(s.config)
                restored.receiver.url = endpoint
                restored._read_settings()
                assert len(restored.registered) == 1 and restored.settings["seconds"] == "0.3"
        print("HD_OPCUA_SMOKE_PASS", flush=True)
        code = 0
    except Exception:
        traceback.print_exc()
        print("HD_OPCUA_SMOKE_FAIL", flush=True)
    finally:
        omni.kit.app.get_app().post_uncancellable_quit(code)


asyncio.ensure_future(smoke())
