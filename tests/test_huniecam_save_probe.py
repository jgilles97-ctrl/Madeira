import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_save_probe", ROOT / "tools" / "huniecam_save_probe.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_save_probe"] = mod
SPEC.loader.exec_module(mod)


class HunieCamSaveProbeTests(unittest.TestCase):
    def test_snapshot_is_content_fingerprint_without_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "HunieCam Studio"
            root.mkdir()
            (root / "save.dat").write_bytes(b"abc")
            report = mod.snapshot(root)
            self.assertTrue(report["exists"])
            self.assertEqual(report["source_label"], "HunieCam Studio")
            self.assertEqual(report["file_count"], 1)
            self.assertEqual(report["files"][0]["path"], "save.dat")
            self.assertNotIn(str(root.parent), str(report))

    def test_compare_detects_changed_and_added_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "save"
            root.mkdir()
            (root / "a.dat").write_bytes(b"one")
            before = mod.snapshot(root)
            (root / "a.dat").write_bytes(b"two")
            (root / "b.dat").write_bytes(b"new")
            after = mod.snapshot(root)
            diff = mod.compare(before, after)
            self.assertTrue(diff["progress_write_detected"])
            self.assertIn("a.dat", diff["changed"])
            self.assertIn("b.dat", diff["added"])
            self.assertFalse(diff["same_tree"])

    def test_compare_identical_snapshots_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "save.dat").write_bytes(b"same")
            first = mod.snapshot(root)
            second = mod.snapshot(root)
            diff = mod.compare(first, second)
            self.assertFalse(diff["progress_write_detected"])
            self.assertTrue(diff["same_tree"])


if __name__ == "__main__":
    unittest.main()
