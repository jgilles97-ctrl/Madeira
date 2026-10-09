import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_run_context", ROOT / "tools" / "huniecam_run_context.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_run_context"] = mod
SPEC.loader.exec_module(mod)


def record(build="build-a", profile="profile-a", ready=True):
    return {
        "schema": "MADEIRA_HUNIECAM_RUN_RECORD_V1",
        "ready_for_comparison": ready,
        "build": {"fingerprint_sha256": build},
        "profile_sha256": profile,
    }


class HunieCamRunContextTests(unittest.TestCase):
    def test_same_evidence_is_deterministic(self):
        a = mod.build(record(), "[WineProc] Target exe: HunieCamStudio.exe\n", "Unity\n")
        b = mod.build(record(), "[WineProc] Target exe: HunieCamStudio.exe\n", "Unity\n")
        self.assertTrue(a["ready"])
        self.assertEqual(a["run_id_sha256"], b["run_id_sha256"])

    def test_changed_madeira_log_changes_run_id(self):
        a = mod.build(record(), "launch A\n", "unity\n")
        b = mod.build(record(), "launch B\n", "unity\n")
        self.assertNotEqual(a["run_id_sha256"], b["run_id_sha256"])

    def test_changed_unity_log_changes_run_id(self):
        a = mod.build(record(), "launch\n", "unity A\n")
        b = mod.build(record(), "launch\n", "unity B\n")
        self.assertNotEqual(a["run_id_sha256"], b["run_id_sha256"])

    def test_changed_build_or_profile_changes_run_id(self):
        a = mod.build(record("build-a", "profile-a"), "launch\n", "unity\n")
        b = mod.build(record("build-b", "profile-a"), "launch\n", "unity\n")
        c = mod.build(record("build-a", "profile-b"), "launch\n", "unity\n")
        self.assertNotEqual(a["run_id_sha256"], b["run_id_sha256"])
        self.assertNotEqual(a["run_id_sha256"], c["run_id_sha256"])

    def test_missing_madeira_log_is_not_ready(self):
        report = mod.build(record(), "", "unity\n")
        self.assertFalse(report["ready"])
        self.assertIsNone(report["run_id_sha256"])

    def test_unready_run_record_is_rejected(self):
        report = mod.build(record(ready=False), "launch\n", "unity\n")
        self.assertFalse(report["ready"])

    def test_raw_text_is_not_embedded(self):
        report = mod.build(record(), "secret-looking-log-body\n", "unity body\n")
        rendered = str(report)
        self.assertNotIn("secret-looking-log-body", rendered)
        self.assertFalse(report["privacy"]["raw_log_text_embedded"])


if __name__ == "__main__":
    unittest.main()
