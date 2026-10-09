import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_run_compare", ROOT / "tools" / "huniecam_run_compare.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_run_compare"] = mod
SPEC.loader.exec_module(mod)


class HunieCamRunCompareTests(unittest.TestCase):
    def test_one_change_that_moves_deeper_is_kept(self):
        before = {"deepest_stage": 55, "failures": [{"code": "store_undecoded"}]}
        after = {"deepest_stage": 75, "failures": []}
        p0 = {"config": "", "arguments": "", "resolution": "1280x720"}
        p1 = {"config": "env.MADEIRA_WOW_RWX_PLAIN = 1", "arguments": "", "resolution": "1280x720"}
        report = mod.compare(before, after, p0, p1)
        self.assertEqual(report["verdict"], "DEEPER")
        self.assertEqual(report["changed_variable_count"], 1)
        self.assertTrue(report["keep_single_change"])

    def test_two_changes_are_ambiguous_even_if_stage_moves(self):
        before = {"deepest_stage": 40, "failures": []}
        after = {"deepest_stage": 75, "failures": []}
        p0 = {"config": "", "arguments": "", "resolution": "1280x720"}
        p1 = {"config": "d3d9 = native", "arguments": "-force-d3d9", "resolution": "1280x720"}
        report = mod.compare(before, after, p0, p1)
        self.assertEqual(report["verdict"], "AMBIGUOUS_MULTI_CHANGE")
        self.assertFalse(report["comparison_useful"])
        self.assertFalse(report["keep_single_change"])

    def test_same_stage_with_new_failure_is_regression(self):
        before = {"deepest_stage": 50, "failures": []}
        after = {"deepest_stage": 50, "failures": [{"code": "unity_crash"}]}
        report = mod.compare(before, after)
        self.assertEqual(report["verdict"], "REGRESSION_NEW_FAILURE")

    def test_same_stage_with_cleared_failure_is_improvement(self):
        before = {"deepest_stage": 50, "failures": [{"code": "steam_init_failed"}]}
        after = {"deepest_stage": 50, "failures": []}
        p0 = {"launch": "direct"}
        p1 = {"launch": "dock"}
        report = mod.compare(before, after, p0, p1)
        self.assertEqual(report["verdict"], "IMPROVED_FAILURE_SET")
        self.assertTrue(report["keep_single_change"])

    def test_notes_do_not_count_as_experiment_variables(self):
        session = {"deepest_stage": 65, "failures": []}
        p0 = {"config": "", "notes": "baseline", "timestamp": "a"}
        p1 = {"config": "", "notes": "retry", "timestamp": "b"}
        report = mod.compare(session, session, p0, p1)
        self.assertEqual(report["changed_variable_count"], 0)


if __name__ == "__main__":
    unittest.main()
