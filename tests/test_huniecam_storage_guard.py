import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_storage_guard", ROOT / "tools" / "huniecam_storage_guard.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_storage_guard"] = mod
SPEC.loader.exec_module(mod)


class HunieCamStorageGuardTests(unittest.TestCase):
    def test_large_dump_is_reported_and_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            dump = root / "fex-jit-dump.bin"
            with dump.open("wb") as f:
                f.truncate(70 * 1024 * 1024)
            report = mod.scan(root)
            self.assertEqual(report["large_jit_dump_count"], 1)
            self.assertTrue(dump.exists())
            self.assertTrue(report["read_only"])

    def test_known_logs_are_inventoried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "madeira-log.txt").write_text("log")
            data = root / "HunieCamStudio_Data"
            data.mkdir()
            (data / "output_log.txt").write_text("unity")
            report = mod.scan(root)
            self.assertEqual(report["artifact_count"], 2)
            paths = {a["relative_path"] for a in report["artifacts"]}
            self.assertIn("madeira-log.txt", paths)
            self.assertIn("HunieCamStudio_Data/output_log.txt", paths)

    def test_unrelated_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "game.dat").write_bytes(b"x" * 100)
            report = mod.scan(root)
            self.assertEqual(report["artifact_count"], 0)


if __name__ == "__main__":
    unittest.main()
