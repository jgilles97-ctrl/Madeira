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


def save_root(tmp):
    root = pathlib.Path(tmp) / "HunieCam Studio"
    root.mkdir()
    return root


class HunieCamSaveProbeTests(unittest.TestCase):
    def test_snapshot_is_content_fingerprint_without_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = save_root(tmp); (root / "save.dat").write_bytes(b"abc")
            report = mod.snapshot(root)
            self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_SAVE_SNAPSHOT_V2")
            self.assertTrue(report["exists"]); self.assertEqual(report["source_label"], "HunieCam Studio"); self.assertTrue(report["source_path_sha256"]); self.assertTrue(report["expected_title_folder"]); self.assertEqual(report["file_count"], 1); self.assertEqual(report["files"][0]["path"], "save.dat"); self.assertNotIn(str(root.parent), str(report)); self.assertFalse(report["privacy"]["absolute_path_embedded"])

    def test_compare_detects_changed_and_added_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = save_root(tmp); (root / "a.dat").write_bytes(b"one"); before = mod.snapshot(root); (root / "a.dat").write_bytes(b"two"); (root / "b.dat").write_bytes(b"new"); after = mod.snapshot(root); diff = mod.compare(before, after)
            self.assertTrue(diff["valid_comparison"]); self.assertTrue(diff["same_source_directory_proven"]); self.assertTrue(diff["progress_write_detected"]); self.assertIn("a.dat", diff["changed"]); self.assertIn("b.dat", diff["added"]); self.assertFalse(diff["same_tree"])

    def test_compare_identical_snapshots_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = save_root(tmp); (root / "save.dat").write_bytes(b"same"); first = mod.snapshot(root); second = mod.snapshot(root); diff = mod.compare(first, second); self.assertTrue(diff["valid_comparison"]); self.assertFalse(diff["progress_write_detected"]); self.assertTrue(diff["same_tree"])

    def test_verify_proves_write_and_relaunch_tree_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = save_root(tmp); (root / "save.dat").write_bytes(b"before"); before = mod.snapshot(root); (root / "save.dat").write_bytes(b"after-progress"); after = mod.snapshot(root); relaunch = mod.snapshot(root); verify = mod.verify(before, after, relaunch)
            self.assertEqual(verify["schema"], "MADEIRA_HUNIECAM_SAVE_VERIFY_V2"); self.assertTrue(verify["same_source_directory_proven"]); self.assertTrue(verify["expected_save_folder_proven"]); self.assertTrue(verify["progress_write_detected"]); self.assertTrue(verify["save_tree_survived_relaunch"]); self.assertTrue(verify["machine_gate_pass"]); self.assertFalse(verify["errors"])
            guidance = verify["manual_gate_still_required"].lower(); self.assertIn("relaunch", guidance); self.assertIn("visible progress", guidance); self.assertIn("matching files alone", guidance)

    def test_verify_fails_when_progress_was_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = save_root(tmp); (root / "save.dat").write_bytes(b"same"); before = mod.snapshot(root); after = mod.snapshot(root); relaunch = mod.snapshot(root); verify = mod.verify(before, after, relaunch); self.assertFalse(verify["progress_write_detected"]); self.assertTrue(verify["save_tree_survived_relaunch"]); self.assertFalse(verify["machine_gate_pass"])

    def test_verify_fails_when_tree_changes_across_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = save_root(tmp); (root / "save.dat").write_bytes(b"before"); before = mod.snapshot(root); (root / "save.dat").write_bytes(b"progress"); after = mod.snapshot(root); (root / "save.dat").write_bytes(b"lost-or-rewritten"); relaunch = mod.snapshot(root); verify = mod.verify(before, after, relaunch); self.assertTrue(verify["progress_write_detected"]); self.assertFalse(verify["save_tree_survived_relaunch"]); self.assertFalse(verify["machine_gate_pass"])

    def test_wrong_folder_name_cannot_pass_machine_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "some-copy"; root.mkdir(); (root / "save.dat").write_bytes(b"before"); before = mod.snapshot(root); (root / "save.dat").write_bytes(b"after"); after = mod.snapshot(root); relaunch = mod.snapshot(root); verify = mod.verify(before, after, relaunch); self.assertFalse(verify["expected_save_folder_proven"]); self.assertFalse(verify["machine_gate_pass"]); self.assertTrue(verify["errors"])

    def test_different_directories_with_same_label_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = pathlib.Path(tmp) / "a" / "HunieCam Studio"; b = pathlib.Path(tmp) / "b" / "HunieCam Studio"; a.mkdir(parents=True); b.mkdir(parents=True)
            (a / "save.dat").write_bytes(b"before"); before = mod.snapshot(a); (a / "save.dat").write_bytes(b"after"); after = mod.snapshot(a); (b / "save.dat").write_bytes(b"after"); relaunch = mod.snapshot(b); verify = mod.verify(before, after, relaunch)
            self.assertFalse(verify["same_source_directory_proven"]); self.assertFalse(verify["machine_gate_pass"]); self.assertTrue(any("exact save directory" in x for x in verify["errors"]))


if __name__ == "__main__": unittest.main()
