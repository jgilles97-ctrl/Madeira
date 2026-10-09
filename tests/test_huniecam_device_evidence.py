import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_device_evidence", ROOT / "tools" / "huniecam_device_evidence.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_device_evidence"] = mod
SPEC.loader.exec_module(mod)


class HunieCamDeviceEvidenceTests(unittest.TestCase):
    def test_template_has_named_nine_point_grid_and_required_trials(self):
        data = mod.template()
        self.assertEqual(data["schema"], "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V1")
        self.assertEqual(len(data["pointer_grid"]), 9)
        self.assertEqual({x["point"] for x in data["pointer_grid"]}, set(mod.POINTER_POINTS))
        self.assertEqual(len(data["cold_launch_trials"]), 3)
        self.assertEqual(len(data["suspend_resume_trials"]), 2)
        self.assertTrue(all(x["passed"] is None for x in data["pointer_grid"]))

    def test_all_successes_derive_acceptance_counts(self):
        data = mod.template()
        for item in data["pointer_grid"]:
            item["passed"] = True
        for item in data["cold_launch_trials"]:
            item["success"] = True
        for item in data["suspend_resume_trials"]:
            item["success"] = True
        report = mod.summarize(data)
        norm = report["normalized"]
        self.assertEqual(norm["pointer_points_tested"], 9)
        self.assertEqual(norm["pointer_points_passed"], 9)
        self.assertEqual(norm["cold_launches"], 3)
        self.assertEqual(norm["suspend_resume_cycles"], 2)
        self.assertTrue(report["derived"]["pointer_grid_complete"])
        self.assertTrue(report["derived"]["cold_launch_trials_complete"])
        self.assertTrue(report["derived"]["suspend_resume_trials_complete"])

    def test_failed_pointer_is_not_hidden_by_count(self):
        data = mod.template()
        for item in data["pointer_grid"]:
            item["passed"] = True
        data["pointer_grid"][0]["passed"] = False
        report = mod.summarize(data)
        self.assertEqual(report["normalized"]["pointer_points_tested"], 9)
        self.assertEqual(report["normalized"]["pointer_points_passed"], 8)
        self.assertFalse(report["derived"]["pointer_grid_complete"])
        self.assertEqual(report["derived"]["pointer_failed"], ["top_left"])

    def test_unknown_stays_unknown(self):
        report = mod.summarize(mod.template())
        self.assertEqual(report["normalized"]["pointer_points_tested"], 0)
        self.assertEqual(len(report["derived"]["pointer_unknown"]), 9)
        self.assertFalse(report["derived"]["cold_launch_trials_complete"])


if __name__ == "__main__":
    unittest.main()
