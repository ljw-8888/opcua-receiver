"""Run with Python and usd-core: python kit-tools/test_measurement_api.py"""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from pxr import Vt

EXT = Path(__file__).resolve().parents[1] / "exts" / "hd.usda.translator"
sys.path.insert(0, str(EXT))
from hd_usda_translator import get_latest_measurements
from hd_usda_translator.measurements import _publish
from hd_usda_translator.overlay import ScreenBadge
from hd_usda_translator.telemetry import read_snapshot


class MeasurementApiTests(unittest.TestCase):
    def setUp(self):
        _publish(None)
        self.addCleanup(_publish, None)
        self.snapshot = read_snapshot(EXT / "docs/examples/telemetry.usda")

    def test_stopped_file_retains_all_rows_and_clear_drops_them(self):
        self.assertEqual(get_latest_measurements(), ())
        _publish(self.snapshot, "Stopped")
        rows = get_latest_measurements()
        self.assertEqual(len(rows), len(self.snapshot.tags))
        self.assertTrue(all(m.status == "Stopped" and m.value is None for m in rows))
        _publish(None)
        self.assertEqual(get_latest_measurements(), ())

    def test_all_tags_are_published_together_and_age_without_a_file_change(self):
        sample = next(iter(self.snapshot.tags.values()))
        tags = {
            (self.snapshot.source, "urn:example", f"s=Stream/{n}/Pressure"):
                replace(sample, value=n, state="Current", quality="Good")
            for n in range(100)
        }
        snapshot = replace(self.snapshot, tags=tags)
        _publish(snapshot, "Live")
        live = get_latest_measurements()
        self.assertEqual([row.value for row in live], list(range(100)))
        _publish(snapshot, "Live")
        self.assertIs(get_latest_measurements(), live)
        _publish(snapshot, "No update")
        self.assertTrue(all(m.value is None and m.status == "No update" for m in get_latest_measurements()))
        self.assertEqual(live[0].value, 0)

    def test_array_values_do_not_share_mutable_storage_with_the_reader(self):
        sample = next(iter(self.snapshot.tags.values()))
        values = Vt.IntArray([3, 4])
        key = (self.snapshot.source, "urn:example", "s=array")
        snapshot = replace(self.snapshot, tags={key: replace(sample, value=values, state="Current", quality="Good")})
        _publish(snapshot, "Live")
        values[0] = 9
        self.assertEqual(get_latest_measurements()[0].value, (3, 4))

    def test_overlay_uses_the_selected_namespace_and_clears_missing_rows(self):
        sample = next(iter(self.snapshot.tags.values()))
        node = "s=Stream/1/Pressure"
        tags = {
            (self.snapshot.source, uri, node): replace(sample, value=n, state="Current")
            for uri, n in [("urn:plant", 0), ("urn:sim", 7), ("urn:other", 4)]
        }
        _publish(replace(self.snapshot, tags=tags), "Live")
        badge = ScreenBadge.__new__(ScreenBadge)
        badge.lines = [SimpleNamespace(text=""), SimpleNamespace(text="")]
        badge.status = SimpleNamespace(text="")
        selected = {0: ("urn:sim", node), 1: ("urn:plant", node)}
        badge.refresh(selected, "Live", "")
        self.assertEqual(badge.lines[0].text, "Stream 1 Pressure: 7 barG [urn:sim]")
        self.assertEqual(badge.lines[1].text, "Stream 1 Pressure: 0 barG [urn:plant]")
        self.assertEqual(len(get_latest_measurements()), 3)
        _publish(self.snapshot, "Stopped")
        badge.refresh(selected, "Stopped", "")
        self.assertIn("No tag", badge.lines[0].text)
        _publish(None)
        badge.refresh(selected, None, "File unavailable")
        self.assertEqual(badge.status.text, "File unavailable")
        self.assertIn("—", badge.lines[1].text)


if __name__ == "__main__":
    unittest.main()
