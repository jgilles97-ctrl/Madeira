import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_acceptance", ROOT / "tools" / "huniecam_acceptance.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_acceptance"] = mod
SPEC.loader.exec_module(mod)


def preflight():
    return {"exe_found": True, "identity": {"exe_sha256": "abc", "pe": {"valid_pe": True}}}


def session(stage=75):
    return {"deepest_stage": stage}


def saves():
    return {"progress_write_detected": True, "save_tree_survived_relaunch": True, "machine_gate_pass": True}


def full_manual_counts():
    return {
        "jit_memory_ready": True,
        "real_gameplay": True,
        "rendering_correct": True,
        "pointer_points_tested": 9,
        "pointer_points_passed": 9,
        "audio_correct": True,
        "save_progress_visible_after_relaunch": True,
        "performance_acceptable": True,
        "stable_minutes": 30,
        "cold_launches": 3,
        "suspend_resume_cycles": 2,
        "repeatable_profile": True,
    }


class HunieCamAcceptanceTests(unittest.TestCase):
    def test_missing_manual_evidence_never_accepts(self):
        report = mod.evaluate(preflight(), session(), None, None)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_MISSING_EVIDENCE")
        self.assertGreater(report["counts"]["UNKNOWN"], 0)

    def test_explicit_failed_gate_blocks_acceptance(self):
        manual = {"jit_memory_ready": True, "real_gameplay": False}
        report = mod.evaluate(preflight(), session(), None, manual)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_FAILED_GATE")

    def test_full_counted_evidence_accepts(self):
        report = mod.evaluate(preflight(), session(75), saves(), full_manual_counts())
        self.assertTrue(report["accepted"])
        self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_ACCEPTANCE_V3")
        self.assertEqual(report["overall"], "ACCEPTED")
        self.assertEqual(report["counts"]["FAIL"], 0)
        self.assertEqual(report["counts"]["UNKNOWN"], 0)

    def test_29_minutes_fails_even_if_everything_else_passes(self):
        manual = full_manual_counts(); manual["stable_minutes"] = 29
        report = mod.evaluate(preflight(), session(), saves(), manual)
        gate = next(g for g in report["gates"] if g["name"] == "stable_30_minutes")
        self.assertEqual(gate["status"], "FAIL")

    def test_two_cold_launches_fail(self):
        manual = full_manual_counts(); manual["cold_launches"] = 2
        report = mod.evaluate(preflight(), session(), saves(), manual)
        gate = next(g for g in report["gates"] if g["name"] == "three_cold_launches")
        self.assertEqual(gate["status"], "FAIL")

    def test_pointer_grid_requires_all_nine(self):
        manual = full_manual_counts(); manual["pointer_points_passed"] = 8
        report = mod.evaluate(preflight(), session(), saves(), manual)
        gate = next(g for g in report["gates"] if g["name"] == "pointer_grid")
        self.assertEqual(gate["status"], "FAIL")

    def test_legacy_booleans_still_work(self):
        manual = full_manual_counts()
        for k in ["stable_minutes", "cold_launches", "suspend_resume_cycles", "pointer_points_tested", "pointer_points_passed"]:
            manual.pop(k)
        manual.update({"stable_30_minutes": True, "three_cold_launches": True, "two_suspend_resume_cycles": True, "pointer_aligned": True})
        report = mod.evaluate(preflight(), session(), saves(), manual)
        self.assertTrue(report["accepted"])

    def test_save_failure_blocks_acceptance(self):
        verify = {"progress_write_detected": True, "save_tree_survived_relaunch": False, "machine_gate_pass": False}
        report = mod.evaluate(preflight(), session(), verify, full_manual_counts())
        self.assertFalse(report["accepted"])
        failed = {g["name"] for g in report["gates"] if g["status"] == "FAIL"}
        self.assertIn("save_survives_relaunch", failed)
        self.assertIn("save_machine_verification", failed)


if __name__ == "__main__":
    unittest.main()
