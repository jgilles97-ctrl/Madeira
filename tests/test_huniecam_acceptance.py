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


def full_manual():
    return {
        "jit_memory_ready": True,
        "real_gameplay": True,
        "rendering_correct": True,
        "pointer_aligned": True,
        "audio_correct": True,
        "save_progress_visible_after_relaunch": True,
        "performance_acceptable": True,
        "stable_30_minutes": True,
        "three_cold_launches": True,
        "two_suspend_resume_cycles": True,
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
        failed = {g["name"] for g in report["gates"] if g["status"] == "FAIL"}
        self.assertIn("real_gameplay", failed)

    def test_full_evidence_accepts(self):
        save_verification = {
            "progress_write_detected": True,
            "save_tree_survived_relaunch": True,
            "machine_gate_pass": True,
        }
        report = mod.evaluate(preflight(), session(75), save_verification, full_manual())
        self.assertTrue(report["accepted"])
        self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_ACCEPTANCE_V2")
        self.assertEqual(report["overall"], "ACCEPTED")
        self.assertEqual(report["counts"], {"PASS": len(report["gates"]), "FAIL": 0, "UNKNOWN": 0})

    def test_progress_written_but_relaunch_tree_changed_fails(self):
        verify = {
            "progress_write_detected": True,
            "save_tree_survived_relaunch": False,
            "machine_gate_pass": False,
        }
        report = mod.evaluate(preflight(), session(), verify, {"jit_memory_ready": True})
        gate = next(g for g in report["gates"] if g["name"] == "save_survives_relaunch")
        machine = next(g for g in report["gates"] if g["name"] == "save_machine_verification")
        self.assertEqual(gate["status"], "FAIL")
        self.assertEqual(machine["status"], "FAIL")

    def test_matching_save_tree_without_progress_write_does_not_pass(self):
        verify = {
            "progress_write_detected": False,
            "save_tree_survived_relaunch": True,
            "machine_gate_pass": False,
        }
        report = mod.evaluate(preflight(), session(), verify, {"jit_memory_ready": True})
        write = next(g for g in report["gates"] if g["name"] == "save_write_detected")
        self.assertEqual(write["status"], "FAIL")
        self.assertFalse(report["accepted"])

    def test_missing_save_verification_stays_unknown_not_false_pass(self):
        report = mod.evaluate(preflight(), session(), None, full_manual())
        save_gates = [g for g in report["gates"] if g["name"].startswith("save_") and g["name"] != "save_progress_visible_after_relaunch"]
        self.assertTrue(save_gates)
        self.assertTrue(all(g["status"] == "UNKNOWN" for g in save_gates))
        self.assertEqual(report["overall"], "NOT_READY_MISSING_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
