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


def context(run="run-1", build="build-1", profile="profile-1", ready=True):
    return {"ready": ready, "run_id_sha256": run, "build_fingerprint_sha256": build, "profile_sha256": profile}


def contract(valid=True, run="run-1"):
    return {"valid": valid, "run_id_sha256": run}


def repeatability(passed=True, build="build-1", profile="profile-1", runs=("run-1", "run-2", "run-3")):
    return {
        "schema": "MADEIRA_HUNIECAM_REPEATABILITY_V1",
        "passed": passed,
        "build_fingerprint_sha256": build,
        "profile_sha256": profile,
        "runs": [{"run_id_sha256": run} for run in runs],
    }


def full_manual_counts(run="run-1", build="build-1", profile="profile-1"):
    return {
        "run_id_sha256": run,
        "build_fingerprint_sha256": build,
        "profile_sha256": profile,
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
    manual["pointer_grid"] = [{"point": name, "passed": True} for name in sorted(mod.POINTER_POINTS)]
    manual["cold_launch_trials"] = [{"trial": i, "success": True} for i in range(1, 4)]
    manual["suspend_resume_trials"] = [{"trial": i, "success": True} for i in range(1, 3)]
    return manual


def evaluate(manual=None, save=None, perf=None, cont=None, ctx=None, repeat=None, stage=75):
    return mod.evaluate(
        preflight(), session(stage), saves() if save is None else save,
        full_manual_counts() if manual is None else manual,
        performance() if perf is None else perf,
        contract() if cont is None else cont,
        context() if ctx is None else ctx,
        repeatability() if repeat is None else repeat,
    )


class HunieCamAcceptanceTests(unittest.TestCase):
    def test_missing_manual_evidence_never_accepts(self):
        report = mod.evaluate(preflight(), session(), None, None, performance(), contract(), context(), repeatability())
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_MISSING_EVIDENCE")
        self.assertGreater(report["counts"]["UNKNOWN"], 0)

    def test_explicit_failed_gate_blocks_acceptance(self):
        manual = full_manual_counts(); manual["real_gameplay"] = False
        report = evaluate(manual=manual)
        self.assertFalse(report["accepted"])
        self.assertEqual(report["overall"], "NOT_READY_FAILED_GATE")

    def test_full_counted_evidence_accepts(self):
        report = evaluate()
        self.assertTrue(report["accepted"])
        self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_ACCEPTANCE_V6")
        self.assertEqual(report["run_id_sha256"], "run-1")
        self.assertEqual(report["overall"], "ACCEPTED")
        self.assertEqual(report["counts"]["FAIL"], 0)
        self.assertEqual(report["counts"]["UNKNOWN"], 0)

    def test_full_structured_evidence_accepts(self):
        self.assertTrue(evaluate(manual=full_structured_manual())["accepted"])

    def test_normalized_device_wrapper_is_consumed(self):
        wrapped = {"schema": "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V2", "normalized": full_structured_manual(), "derived": {}}
        self.assertTrue(evaluate(manual=wrapped)["accepted"])

    def test_wrong_run_id_blocks_acceptance(self):
        manual = full_manual_counts(run="different")
        report = evaluate(manual=manual)
        gate = next(g for g in report["gates"] if g["name"] == "device_evidence_same_run")
        self.assertEqual(gate["status"], "FAIL")
        self.assertFalse(report["accepted"])

    def test_missing_run_link_is_unknown_not_pass(self):
        manual = full_manual_counts(); manual.pop("run_id_sha256")
        report = evaluate(manual=manual)
        gate = next(g for g in report["gates"] if g["name"] == "device_evidence_same_run")
        self.assertEqual(gate["status"], "UNKNOWN")
        self.assertFalse(report["accepted"])

    def test_unready_run_context_blocks_acceptance(self):
        report = evaluate(ctx=context(ready=False))
        gate = next(g for g in report["gates"] if g["name"] == "run_context_ready")
        self.assertEqual(gate["status"], "FAIL")

    def test_missing_repeatability_is_unknown(self):
        report = mod.evaluate(preflight(), session(), saves(), full_manual_counts(), performance(), contract(), context(), None)
        gate = next(g for g in report["gates"] if g["name"] == "three_sealed_cold_launches")
        self.assertEqual(gate["status"], "UNKNOWN")
        self.assertFalse(report["accepted"])

    def test_failed_repeatability_blocks_acceptance(self):
        report = evaluate(repeat=repeatability(False))
        gate = next(g for g in report["gates"] if g["name"] == "three_sealed_cold_launches")
        self.assertEqual(gate["status"], "FAIL")

    def test_repeatability_build_and_profile_must_match_primary(self):
        self.assertFalse(evaluate(repeat=repeatability(build="other"))["accepted"])
        self.assertFalse(evaluate(repeat=repeatability(profile="other"))["accepted"])

    def test_repeatability_must_include_primary_run(self):
        report = evaluate(repeat=repeatability(runs=("run-2", "run-3", "run-4")))
        gate = next(g for g in report["gates"] if g["name"] == "three_sealed_cold_launches")
        self.assertEqual(gate["status"], "FAIL")

    def test_structured_pointer_false_overrides_good_aggregate_counts(self):
        manual = full_structured_manual(); manual["pointer_grid"][0]["passed"] = False
        report = evaluate(manual=manual)
        gate = next(g for g in report["gates"] if g["name"] == "pointer_grid")
        self.assertEqual(gate["status"], "FAIL")

    def test_29_minutes_fails_even_if_everything_else_passes(self):
        manual = full_manual_counts(); manual["stable_minutes"] = 29
        report = evaluate(manual=manual)
        gate = next(g for g in report["gates"] if g["name"] == "stable_30_minutes")
        self.assertEqual(gate["status"], "FAIL")

    def test_two_cold_launches_observed_fail(self):
        manual = full_manual_counts(); manual["cold_launches"] = 2
        report = evaluate(manual=manual)
        gate = next(g for g in report["gates"] if g["name"] == "three_cold_launches_observed")
        self.assertEqual(gate["status"], "FAIL")

    def test_pointer_grid_requires_all_nine(self):
        manual = full_manual_counts(); manual["pointer_points_passed"] = 8
        report = evaluate(manual=manual)
        gate = next(g for g in report["gates"] if g["name"] == "pointer_grid")
        self.assertEqual(gate["status"], "FAIL")

    def test_legacy_boolean_shape_still_works_when_provenance_is_current(self):
        manual = full_manual_counts()
        for k in ["stable_minutes", "cold_launches", "suspend_resume_cycles", "pointer_points_tested", "pointer_points_passed"]:
            manual.pop(k)
        manual.update({"stable_30_minutes": True, "three_cold_launches": True, "two_suspend_resume_cycles": True, "pointer_aligned": True})
        self.assertTrue(evaluate(manual=manual)["accepted"])

    def test_save_failure_blocks_acceptance(self):
        verify = {"progress_write_detected": True, "save_tree_survived_relaunch": False, "machine_gate_pass": False}
        report = evaluate(save=verify)
        failed = {g["name"] for g in report["gates"] if g["status"] == "FAIL"}
        self.assertIn("save_survives_relaunch", failed)
        self.assertIn("save_machine_verification", failed)

    def test_missing_performance_is_unknown_and_cannot_accept(self):
        report = mod.evaluate(preflight(), session(), saves(), full_manual_counts(), None, contract(), context(), repeatability())
        gate = next(g for g in report["gates"] if g["name"] == "performance_measurement_clean")
        self.assertEqual(gate["status"], "UNKNOWN")
        self.assertFalse(report["accepted"])

    def test_bad_contract_blocks_acceptance(self):
        report = evaluate(cont=contract(False))
        gate = next(g for g in report["gates"] if g["name"] == "evidence_contract_valid")
        self.assertEqual(gate["status"], "FAIL")
        self.assertFalse(report["accepted"])


if __name__ == "__main__":
    unittest.main()
