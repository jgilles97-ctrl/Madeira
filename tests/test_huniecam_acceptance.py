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


def performance(clean=True):
    return {"comparison_clean": clean}


def contract(valid=True):
    return {"valid": valid}


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


def full_structured_manual():
    manual = full_manual_counts()
    manual["pointer_grid"] = [
        {"point": name, "passed": True}
        for name in sorted(mod.POINTER_POINTS)
    ]
    manual["cold_launch_trials"] = [{"trial": i, "success": True} for i in range(1, 4)]
    manual["suspend_resume_trials"] = [{"trial": i, "success": True} for i in range(1, 3)]
    return manual


class HunieCamAcceptanceTests(unittest.TestCase):
    def test_missing_manual_evidence_never_accepts(self):
        report = mod.evaluate(preflight(), session(), None, None, performance(), contract())
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_MISSING_EVIDENCE")
        self.assertGreater(report["counts"]["UNKNOWN"], 0)

    def test_explicit_failed_gate_blocks_acceptance(self):
        manual = {"jit_memory_ready": True, "real_gameplay": False}
        report = mod.evaluate(preflight(), session(), None, manual, performance(), contract())
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_FAILED_GATE")

    def test_full_counted_evidence_accepts(self):
        report = mod.evaluate(preflight(), session(75), saves(), full_manual_counts(), performance(), contract())
        self.assertTrue(report["accepted"])
        self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_ACCEPTANCE_V4")
        self.assertEqual(report["overall"], "ACCEPTED")
        self.assertEqual(report["counts"]["FAIL"], 0)
        self.assertEqual(report["counts"]["UNKNOWN"], 0)

    def test_full_structured_evidence_accepts(self):
        report = mod.evaluate(preflight(), session(), saves(), full_structured_manual(), performance(), contract())
        self.assertTrue(report["accepted"])

    def test_structured_pointer_false_overrides_good_aggregate_counts(self):
        manual = full_structured_manual()
        manual["pointer_grid"][0]["passed"] = False
        report = mod.evaluate(preflight(), session(), saves(), manual, performance(), contract())
        gate = next(g for g in report["gates"] if g["name"] == "pointer_grid")
        self.assertEqual(gate["status"], "FAIL")

    def test_29_minutes_fails_even_if_everything_else_passes(self):
        manual = full_manual_counts(); manual["stable_minutes"] = 29
        report = mod.evaluate(preflight(), session(), saves(), manual, performance(), contract())
        gate = next(g for g in report["gates"] if g["name"] == "stable_30_minutes")
        self.assertEqual(gate["status"], "FAIL")

    def test_two_cold_launches_fail(self):
        manual = full_manual_counts(); manual["cold_launches"] = 2
        report = mod.evaluate(preflight(), session(), saves(), manual, performance(), contract())
        gate = next(g for g in report["gates"] if g["name"] == "three_cold_launches")
        self.assertEqual(gate["status"], "FAIL")

    def test_pointer_grid_requires_all_nine(self):
        manual = full_manual_counts(); manual["pointer_points_passed"] = 8
        report = mod.evaluate(preflight(), session(), saves(), manual, performance(), contract())
        gate = next(g for g in report["gates"] if g["name"] == "pointer_grid")
        self.assertEqual(gate["status"], "FAIL")

    def test_legacy_booleans_still_work(self):
        manual = full_manual_counts()
        for k in ["stable_minutes", "cold_launches", "suspend_resume_cycles", "pointer_points_tested", "pointer_points_passed"]:
            manual.pop(k)
        manual.update({"stable_30_minutes": True, "three_cold_launches": True, "two_suspend_resume_cycles": True, "pointer_aligned": True})
        report = mod.evaluate(preflight(), session(), saves(), manual, performance(), contract())
        self.assertTrue(report["accepted"])

    def test_save_failure_blocks_acceptance(self):
        verify = {"progress_write_detected": True, "save_tree_survived_relaunch": False, "machine_gate_pass": False}
        report = mod.evaluate(preflight(), session(), verify, full_manual_counts(), performance(), contract())
        self.assertFalse(report["accepted"])
        failed = {g["name"] for g in report["gates"] if g["status"] == "FAIL"}
        self.assertIn("save_survives_relaunch", failed)
        self.assertIn("save_machine_verification", failed)

    def test_missing_performance_is_unknown_and_cannot_accept(self):
        report = mod.evaluate(preflight(), session(), saves(), full_manual_counts(), None, contract())
        gate = next(g for g in report["gates"] if g["name"] == "performance_measurement_clean")
        self.assertEqual(gate["status"], "UNKNOWN")
        self.assertFalse(report["accepted"])

    def test_bad_contract_blocks_acceptance(self):
        report = mod.evaluate(preflight(), session(), saves(), full_manual_counts(), performance(), contract(False))
        gate = next(g for g in report["gates"] if g["name"] == "evidence_contract_valid")
        self.assertEqual(gate["status"], "FAIL")
        self.assertFalse(report["accepted"])


if __name__ == "__main__":
    unittest.main()
