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


class HunieCamAcceptanceTests(unittest.TestCase):
    def test_missing_manual_evidence_never_accepts(self):
        report = mod.evaluate(preflight(), session(), None, None, None)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_MISSING_EVIDENCE")
        self.assertGreater(report["counts"]["UNKNOWN"], 0)

    def test_explicit_failed_gate_blocks_acceptance(self):
        manual = {
            "jit_memory_ready": True,
            "real_gameplay": False,
        }
        report = mod.evaluate(preflight(), session(), None, None, manual)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_FAILED_GATE")
        failed = {g["name"] for g in report["gates"] if g["status"] == "FAIL"}
        self.assertIn("real_gameplay", failed)

    def test_full_evidence_accepts(self):
        manual = {
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
        save_after_compare = {"progress_write_detected": True}
        after_snapshot = {"tree_sha256": "same"}
        # save_write_detected is supplied by a compare report, while persistence
        # needs the actual post-progress snapshot. The evaluator intentionally
        # accepts a combined object for save-after so both can be carried.
        save_after = {**save_after_compare, **after_snapshot}
        save_relaunch = {"tree_sha256": "same"}
        report = mod.evaluate(preflight(), session(75), save_after, save_relaunch, manual)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["overall"], "ACCEPTED")
        self.assertEqual(report["counts"], {"PASS": len(report["gates"]), "FAIL": 0, "UNKNOWN": 0})

    def test_changed_relaunch_tree_fails_persistence(self):
        manual = {"jit_memory_ready": True}
        report = mod.evaluate(preflight(), session(), {"progress_write_detected": True, "tree_sha256": "a"}, {"tree_sha256": "b"}, manual)
        gate = next(g for g in report["gates"] if g["name"] == "save_survives_relaunch")
        self.assertEqual(gate["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
