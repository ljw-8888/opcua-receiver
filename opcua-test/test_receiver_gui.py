import asyncio
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from asyncua import Server, ua
from openpyxl import Workbook, load_workbook
import receiver_gui as gui


async def until(check):
    async with asyncio.timeout(20):
        while not check():
            await asyncio.sleep(0.05)


class ReceiverTests(unittest.IsolatedAsyncioTestCase):
    def test_cleanup_preserves_direct_registrations_across_servers(self):
        app = gui.QApplication.instance() or gui.QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            registrations = {"a": {"pressure": {"metric": "압력", "unit": "barG"}, "old": {"legacy": True}},
                             "b": {"level": {"metric": "Level"}}}
            config.write_text(json.dumps({"registrations": registrations, "settings": {"seconds": "10"}}))
            with patch.object(gui, "CONFIG", config):
                panel = gui.Panel()
                self.assertEqual(panel.get("seconds"), "10")
                expected = {"a": {"pressure": registrations["a"]["pressure"]}, "b": registrations["b"]}
                self.assertEqual(panel.registrations, expected)
                self.assertEqual(json.loads(config.read_text(encoding="utf-8"))["registrations"], expected)
                panel.close()

    async def test_failed_connection_shows_how_to_change_address(self):
        app = gui.QApplication.instance() or gui.QApplication([])
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            with patch.object(gui, "CONFIG", Path(tmp) / "settings.json"):
                panel = gui.Panel()
                panel.show()
                run = asyncio.create_task(panel.run())
                try:
                    panel.set_field("endpoint", f"opc.tcp://127.0.0.1:{sock.getsockname()[1]}/field/")
                    panel.connect()
                    await until(panel.connection_error.isVisible)
                    self.assertIn("연결을 거부", panel.connection_error.text())
                    self.assertIn("연결 해제", panel.connection_error.text())
                    await panel.disconnect()
                    self.assertTrue(panel.connection_error.isHidden())
                    self.assertFalse(panel.fields["endpoint"].isReadOnly())
                finally:
                    panel.close()
                    await run

    async def test_discover_select_and_update_existing_file(self):
        app = gui.QApplication.instance() or gui.QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.json"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                url = f"opc.tcp://127.0.0.1:{sock.getsockname()[1]}/field/"
            old_tags = [dict(identifier=f"old-{i}", namespace_uri="urn:old", node_id=f"i={i}",
                             metric=f"old-{i}", asset="OPC UA", unit="") for i in range(113)]
            draft = {"namespace": "urn:hd:opcua:test:v1", "node": "s=Stream/1/Pressure",
                     "alias": "Stream 1 압력", "unit": "barG"}
            config.write_text(json.dumps({"settings": {"endpoint": "old", "file": "old.xlsx", **draft},
                                          "endpoint": url, "tags": old_tags}))
            with patch.object(gui, "CONFIG", config):
                panel = gui.Panel()
                panel.show()
                self.assertNotIn("tags", json.loads(config.read_text(encoding="utf-8")))
                self.assertFalse(panel.registrations)
                self.assertEqual(panel.chosen_view.text(), "수신할 태그 목록 (0)")
                self.assertLess(panel.fields["endpoint"].geometry().right(), panel.controls["connect"].geometry().left())
                self.assertLessEqual(abs(panel.fields["endpoint"].geometry().center().y() -
                                         panel.controls["connect"].geometry().center().y()), 2)
                self.assertTrue(all(panel.get(key) == "" for key in draft))
                self.assertEqual((panel.get("endpoint"), panel.get("file")), ("", ""))
                self.assertIn("opc.tcp://", panel.fields["endpoint"].placeholderText())
                self.assertIn(".xlsx", panel.fields["file"].placeholderText())
                self.assertEqual(panel.groups.topLevelItemCount(), 0)
                panel.tabs.setCurrentIndex(1)
                self.assertFalse(panel.receive_area.isVisible())
                self.assertTrue(panel.note.isHidden())
                self.assertIn("Anonymous", panel.security_help.text())
                self.assertFalse(panel.cert_buttons[0].isEnabled())
                panel.set_field("mode", "Basic256Sha256 / Sign")
                self.assertTrue(all(b.isEnabled() for b in panel.cert_buttons))
                self.assertIn("개인 키", panel.security_help.text())
                panel.set_field("mode", "None")
                panel.tabs.setCurrentIndex(2)
                self.assertFalse(panel.receive_area.isVisible())
                self.assertTrue(panel.registered_tree.isVisible())
                panel.tabs.setCurrentIndex(0)
                self.assertTrue(panel.receive_area.isVisible())
                self.assertFalse(panel.controls["disconnect"].isEnabled())
                self.assertFalse(panel.controls["start"].isEnabled())
                server = Server()
                await server.init()
                server.set_endpoint(url)
                server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
                ns = await server.register_namespace("urn:unrelated:plant")
                group = await server.nodes.objects.add_object(ns, "PumpRoom")
                sensor = await group.add_variable(ua.NodeId(351, ns), "Inlet", 4.5)
                await group.add_variable(ua.NodeId(352, ns), "Outlet", 6.0)
                async with server:
                    run = asyncio.create_task(panel.run())
                    try:
                        panel.set_field("endpoint", url)
                        panel.connect()
                        await until(lambda: panel.groups.topLevelItemCount() and
                                    panel.groups.topLevelItem(0).childCount())
                        root = panel.groups.topLevelItem(0)
                        self.assertTrue(panel.group_hint.isVisible())
                        room = next(root.child(i) for i in range(root.childCount())
                                    if root.child(i).text(0) == "PumpRoom")
                        panel.groups.setCurrentItem(room)
                        await until(lambda: len(panel.visible_keys) == 2)
                        self.assertFalse(panel.group_hint.isVisible())
                        self.assertEqual(panel.chosen, set())
                        panel.search.setText("inlet")
                        panel.select_visible()
                        self.assertEqual(len(panel.chosen), 1)
                        panel.search.clear()
                        panel.select_visible()
                        self.assertEqual(len(panel.chosen), 2)
                        panel.search.setText("inlet")
                        panel.deselect_visible()
                        self.assertEqual(len(panel.chosen), 1)
                        self.assertTrue(panel.displayed_keys().isdisjoint(panel.chosen))
                        self.assertIs(panel.groups.currentItem(), room)
                        self.assertEqual(panel.chosen_view.text(), "수신할 태그 목록 (1)")
                        panel.tabs.setCurrentIndex(2)
                        self.assertIs(panel.tree.parentWidget(), panel.selected_box)
                        self.assertEqual(panel.selected_box.title(), "수신할 태그 목록 (1)")
                        remaining, = panel.chosen
                        self.assertFalse(panel.items[remaining].isHidden())
                        panel.tabs.setCurrentIndex(0)
                        self.assertIs(panel.groups.currentItem(), room)
                        self.assertEqual(panel.search.text(), "inlet")
                        self.assertTrue(panel.items[remaining].isHidden())
                        panel.chosen_view.click()
                        self.assertFalse(panel.search.text())
                        self.assertEqual(panel.displayed_keys(), panel.chosen)
                        panel.search.setText("inlet")
                        panel.deselect_visible()
                        self.assertEqual(len(panel.chosen), 1)
                        panel.search.clear()
                        with self.assertRaisesRegex(ValueError, "Excel"):
                            panel.start()
                        panel.deselect_visible()
                        panel.tabs.setCurrentIndex(2)
                        panel.set_field("node", "i=351")
                        panel.set_field("namespace", "urn:unrelated:plant")
                        panel.set_field("alias", "직접 등록 압력")
                        panel.set_field("unit", "시험 단위")
                        await panel.add()
                        self.assertFalse(panel.chosen)
                        self.assertTrue(panel.controls["use_registered"].isEnabled())
                        self.assertEqual(panel.registered_tree.topLevelItemCount(), 1)
                        await panel.use_registered()
                        self.assertEqual(len(panel.chosen), 1)
                        self.assertIn("1개 추가", panel.note.text())
                        self.assertIn("결과 파일", panel.note.text())
                        await panel.use_registered()
                        self.assertIn("목록에 이미", panel.note.text())
                        self.assertEqual(len(panel.chosen), 1)
                        panel.set_field("node", "i=352")
                        await panel.add()
                        self.assertEqual(len(panel.chosen), 1)
                        await panel.use_registered()
                        self.assertEqual(len(panel.chosen), 2)
                        for tag_key in panel.chosen:
                            panel.items[tag_key].setSelected(True)
                        self.assertTrue(panel.controls["remove_from_list"].isEnabled())
                        panel.remove_from_list()
                        self.assertFalse(panel.visible_keys)
                        self.assertEqual(panel.registered_tree.topLevelItemCount(), 2)
                        self.assertEqual(panel.chosen_view.text(), "수신할 태그 목록 (0)")
                        panel.set_field("node", "i=351")
                        await panel.add()
                        await panel.use_registered()
                        key, = panel.chosen
                        panel.items[key].setCheckState(0, gui.Qt.CheckState.Unchecked)
                        self.assertFalse(panel.chosen)
                        self.assertTrue(panel.items[key].isHidden())
                        await panel.use_registered()
                        panel.set_field("seconds", "1")
                        path = Path(tmp) / "custom.xlsx"
                        panel.set_field("file", str(path))
                        panel.start()
                        await until(path.exists)
                        await until(lambda: panel.items[key].text(2) == "4.5")
                        self.assertEqual(panel.items[key].text(4), "Good")
                        self.assertFalse(panel.controls["remove_from_list"].isEnabled())
                        panel.tabs.setCurrentIndex(0)
                        self.assertTrue(panel.chosen_view.isChecked())
                        self.assertEqual(panel.items[key].text(2), "4.5")
                        self.assertTrue(panel.fields["file"].isReadOnly())
                        self.assertTrue(panel.fields["seconds"].isReadOnly())
                        self.assertFalse(panel.controls["deselect_visible"].isEnabled())
                        self.assertFalse(panel.items[key].flags() & gui.Qt.ItemFlag.ItemIsUserCheckable)
                        await panel.stop()
                        self.assertFalse(panel.fields["file"].isReadOnly())
                        self.assertFalse(panel.controls["deselect_visible"].isEnabled())
                        self.assertTrue(panel.receiver.selected)
                        panel.start()
                        def read_value():
                            book = load_workbook(path)
                            try:
                                return book["최신값"]["C2"].value
                            finally:
                                book.close()
                        self.assertEqual(read_value(), 4.5)
                        panel.preview.show()
                        await until(lambda: panel.preview.sheets.count() == 1)
                        self.assertEqual(panel.preview.sheets.widget(0).item(1, 2).text(), "4.5")
                        if os.name == "nt":
                            await until(lambda: "저장 완료" in panel.save_status.text())
                            with path.open("rb"):
                                last_save = panel.last_save.text()
                                await sensor.write_value(5.25)
                                await until(lambda: "재시도" in panel.save_status.text())
                                self.assertEqual(panel.last_save.text(), last_save)
                                self.assertEqual(read_value(), 4.5)
                            await until(lambda: read_value() == 5.25)
                        await sensor.write_value(5.75)
                        await until(lambda: read_value() == 5.75)
                        await until(lambda: panel.preview.sheets.widget(0).item(1, 2).text() == "5.75")
                        await panel.pause_receiving()
                        await until(lambda: panel.receiver.subscription_count == 0)
                        self.assertEqual(panel.receiver.state, "Connected")
                        await sensor.write_value(9.5)
                        self.assertEqual(next(iter(panel.paused_samples.values()))["value"], 5.75)
                        self.assertEqual(read_value(), 5.75)
                        existing = Path(tmp) / "existing.xlsx"
                        book = Workbook()
                        book.active.title = "최신값"
                        book.active["C2"] = "=1+2"
                        book.save(existing)
                        book.close()
                        panel.set_field("file", str(existing))
                        panel.start()
                        def existing_updated():
                            book = load_workbook(existing)
                            try:
                                self.assertEqual(book["최신값"]["C2"].value, "=1+2")
                                return (book.sheetnames == ["최신값", "최신값1"]
                                        and book["최신값1"]["C2"].value == 9.5)
                            finally:
                                book.close()
                        await until(existing_updated)
                        await panel.pause_receiving()
                        panel.deselect_visible()
                        panel.groups.setCurrentItem(room)
                        await until(lambda: len(panel.visible_keys) == 2)
                        panel.select_visible()
                        self.assertEqual(panel.items[key].text(0), "Inlet")
                        self.assertEqual(panel.items[key].text(3), "")
                        panel.start()
                        def server_values_saved():
                            book = load_workbook(existing, read_only=True)
                            try:
                                return {row[1] for row in list(book["최신값1"].values)[1:]} == {"Inlet", "Outlet"}
                            finally:
                                book.close()
                        await until(server_values_saved)
                        await panel.pause_receiving()
                        record = next(panel.registered_tree.topLevelItem(i)
                                      for i in range(panel.registered_tree.topLevelItemCount())
                                      if panel.registered_tree.topLevelItem(i).data(0, gui.Qt.ItemDataRole.UserRole) == key)
                        record.setSelected(True)
                        await panel.use_registered()
                        self.assertEqual(panel.items[key].text(0), "직접 등록 압력")
                        panel.start()
                        await until(lambda: panel.receiver.subscription_count == 2)
                        self.assertFalse(panel.controls["delete_registered"].isEnabled())
                        await panel.pause_receiving()
                        await panel.delete_registered()
                        self.assertIn(key, panel.chosen)
                        self.assertEqual(panel.items[key].text(0), "직접 등록 압력")
                        self.assertNotIn(key, json.loads(config.read_text(encoding="utf-8"))["registrations"][url])
                        await panel.pause_receiving()
                        panel.tabs.setCurrentIndex(2)
                        panel.tree.clearSelection()
                        panel.items[key].setSelected(True)
                        panel.remove_from_list()
                        self.assertNotIn(key, panel.chosen)
                        panel.tabs.setCurrentIndex(0)
                        panel.groups.setCurrentItem(room)
                        await until(lambda:len(panel.visible_keys) == 2)
                        panel.select_visible()
                        self.assertIn(key, panel.chosen)
                        self.assertEqual(panel.items[key].text(0), "Inlet")
                        again = gui.Panel()
                        self.assertTrue(all(again.get(key) == "" for key in draft))
                        self.assertTrue(draft.keys().isdisjoint(json.loads(config.read_text(encoding="utf-8"))["settings"]))
                        self.assertNotIn(key, again.registrations[url])
                        self.assertEqual(sum(not t.get("legacy") for t in again.registrations[url].values()), 1)
                        again.close()
                    finally:
                        panel.close()
                        await run
