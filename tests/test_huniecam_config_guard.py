import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_config_guard", ROOT / "tools" / "huniecam_config_guard.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_config_guard"] = mod
SPEC.loader.exec_module(mod)


class HunieCamConfigGuardTests(unittest.TestCase):
    def test_clean_baseline_passes(self):
        r = mod.inspect("", "")
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["change_count"], 0)
        self.assertEqual(r["experiment"], "clean baseline")

    def test_single_known_rwx_experiment_passes(self):
        r = mod.inspect("env.MADEIRA_WOW_RWX_PLAIN = 1\n", "")
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["change_count"], 1)
        self.assertIn("RWX", r["experiment"])

    def test_single_force_d3d9_argument_passes(self):
        r = mod.inspect("", "-force-d3d9")
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["change_count"], 1)

    def test_two_changes_fail_one_variable_rule(self):
        r = mod.inspect("d3d9 = native\n", "-force-d3d9")
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any(f["code"] == "multiple_variables" for f in r["failures"]))

    def test_hybrid_mono_suspend_is_rejected(self):
        r = mod.inspect("mono-suspend = hybrid\n", "")
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any(f["code"] == "known_bad_config" for f in r["failures"]))

    def test_forced_wx_is_rejected(self):
        r = mod.inspect("env.MADEIRA_WX = 1\n", "")
        self.assertEqual(r["status"], "FAIL")

    def test_pool_change_is_warned_not_silently_accepted(self):
        r = mod.inspect("pool = 512\n", "")
        self.assertEqual(r["status"], "WARN")
        self.assertTrue(any(w["code"] == "discouraged_config" for w in r["warnings"]))

    def test_force_d3d11_is_rejected(self):
        r = mod.inspect("", "-force-d3d11")
        self.assertEqual(r["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
