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
            self.assertEqual(diff["old_tree_sha256"], before["tree_sha256"])
            self.assertEqual(diff["new_tree_sha256"], after["tree_sha256"])

    def test_compare_identical_snapshots_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "save.dat").write_bytes(b"same")
            first = mod.snapshot(root)
            second = mod.snapshot(root)
            diff = mod.compare(first, second)
            self.assertFalse(diff["progress_write_detected"])
            self.assertTrue(diff["same_tree"])

    def test_verify_proves_write_and_relaunch_tree_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "save"
            root.mkdir()
            (root / "save.dat").write_bytes(b"before")
            before = mod.snapshot(root)
            (root / "save.dat").write_bytes(b"after-progress")
            after = mod.snapshot(root)
            # A full relaunch leaves the saved bytes unchanged.
            relaunch = mod.snapshot(root)
            verify = mod.verify(before, after, relaunch)
            self.assertTrue(verify["progress_write_detected"])
            self.assertTrue(verify["save_tree_survived_relaunch"])
            self.assertTrue(verify["machine_gate_pass"])
            self.assertEqual(verify["after_tree_sha256"], verify["relaunch_tree_sha256"])
            # Machine persistence is not enough: the game must visibly restore
            # the same progress after relaunch. Assert that semantic requirement
            # rather than depending on one exact sentence/word choice.
            guidance = verify["manual_gate_still_required"].lower()
            self.assertIn("relaunch", guidance)
            self.assertIn("visible progress", guidance)
            self.assertIn("matching files alone", guidance)

    def test_verify_fails_when_progress_was_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "save.dat").write_bytes(b"same")
            before = mod.snapshot(root)
            after = mod.snapshot(root)
            relaunch = mod.snapshot(root)
            verify = mod.verify(before, after, relaunch)
            self.assertFalse(verify["progress_write_detected"])
            self.assertTrue(verify["save_tree_survived_relaunch"])
            self.assertFalse(verify["machine_gate_pass"])

    def test_verify_fails_when_tree_changes_across_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "save.dat").write_bytes(b"before")
            before = mod.snapshot(root)
            (root / "save.dat").write_bytes(b"progress")
            after = mod.snapshot(root)
            (root / "save.dat").write_bytes(b"lost-or-rewritten")
            relaunch = mod.snapshot(root)
            verify = mod.verify(before, after, relaunch)
            self.assertTrue(verify["progress_write_detected"])
            self.assertFalse(verify["save_tree_survived_relaunch"])
            self.assertFalse(verify["machine_gate_pass"])


if __name__ == "__main__":
    unittest.main()
