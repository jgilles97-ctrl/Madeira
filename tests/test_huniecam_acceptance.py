import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_acceptance", ROOT / "tools" / "huniecam_acceptance.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC); sys.modules["huniecam_acceptance"] = mod; SPEC.loader.exec_module(mod)


def preflight(): return {"exe_found": True, "identity": {"exe_sha256": "abc", "pe": {"valid_pe": True}}}
def session(stage=75): return {"deepest_stage": stage}
def saves(): return {"schema": "MADEIRA_HUNIECAM_SAVE_VERIFY_V2", "progress_write_detected": True, "save_tree_survived_relaunch": True, "same_source_directory_proven": True, "expected_save_folder_proven": True, "machine_gate_pass": True, "errors": []}
def performance(clean=True): return {"comparison_clean": clean}
def context(run="run-1", build="build-1", profile="profile-1", ready=True, schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V2"): return {"schema": schema, "ready": ready, "run_id_sha256": run, "build_fingerprint_sha256": build, "profile_sha256": profile, "guard_sha256": "guard", "performance_sha256": "perf"}
def contract(valid=True, run="run-1", schema="MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V3"): return {"schema": schema, "valid": valid, "run_id_sha256": run}
def repeatability(passed=True, build="build-1", profile="profile-1", runs=("run-1", "run-2", "run-3"), schema="MADEIRA_HUNIECAM_REPEATABILITY_V2"): return {"schema": schema, "passed": passed, "build_fingerprint_sha256": build, "profile_sha256": profile, "runs": [{"run_id_sha256": run} for run in runs]}

def full_manual_counts(run="run-1", build="build-1", profile="profile-1"):
    return {"run_id_sha256": run, "build_fingerprint_sha256": build, "profile_sha256": profile, "jit_memory_ready": True, "real_gameplay": True, "rendering_correct": True, "pointer_points_tested": 9, "pointer_points_passed": 9, "audio_correct": True, "save_progress_visible_after_relaunch": True, "performance_acceptable": True, "stable_minutes": 30, "cold_launches": 3, "suspend_resume_cycles": 2, "repeatable_profile": True}

def full_structured_manual():
    manual = full_manual_counts(); manual["pointer_grid"] = [{"point": name, "passed": True} for name in sorted(mod.POINTER_POINTS)]; manual["cold_launch_trials"] = [{"trial": i, "success": True} for i in range(1, 4)]; manual["suspend_resume_trials"] = [{"trial": i, "success": True} for i in range(1, 3)]; return manual

def evaluate(manual=None, save=None, perf=None, cont=None, ctx=None, repeat=None, stage=75):
    return mod.evaluate(preflight(), session(stage), saves() if save is None else save, full_manual_counts() if manual is None else manual, performance() if perf is None else perf, contract() if cont is None else cont, context() if ctx is None else ctx, repeatability() if repeat is None else repeat)


class HunieCamAcceptanceTests(unittest.TestCase):
    def test_full_current_evidence_accepts(self):
        report = evaluate(); self.assertTrue(report["accepted"]); self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_ACCEPTANCE_V7"); self.assertEqual(report["counts"]["FAIL"], 0); self.assertEqual(report["counts"]["UNKNOWN"], 0)
    def test_structured_and_normalized_device_evidence_accept(self):
        self.assertTrue(evaluate(manual=full_structured_manual())["accepted"]); wrapped = {"schema": "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V2", "normalized": full_structured_manual(), "derived": {}}; self.assertTrue(evaluate(manual=wrapped)["accepted"])
    def test_missing_manual_never_accepts(self):
        report = mod.evaluate(preflight(), session(), saves(), None, performance(), contract(), context(), repeatability()); self.assertFalse(report["accepted"]); self.assertGreater(report["counts"]["UNKNOWN"], 0)
    def test_wrong_run_id_blocks(self):
        report = evaluate(manual=full_manual_counts(run="different")); self.assertEqual(next(g for g in report["gates"] if g["name"] == "device_evidence_same_run")["status"], "FAIL")
    def test_context_v1_cannot_finish_cycle6(self):
        report = evaluate(ctx=context(schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V1")); self.assertEqual(next(g for g in report["gates"] if g["name"] == "run_context_v2_ready")["status"], "FAIL"); self.assertFalse(report["accepted"])
    def test_context_must_seal_guard_and_performance(self):
        ctx = context(); ctx["guard_sha256"] = None; report = evaluate(ctx=ctx); self.assertFalse(report["accepted"])
    def test_contract_v2_is_legacy_not_final(self):
        report = evaluate(cont=contract(schema="MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V2")); self.assertEqual(next(g for g in report["gates"] if g["name"] == "evidence_contract_valid")["status"], "FAIL")
    def test_save_v1_is_legacy_not_final(self):
        old = {"schema": "MADEIRA_HUNIECAM_SAVE_VERIFY_V1", "progress_write_detected": True, "save_tree_survived_relaunch": True, "machine_gate_pass": True}; report = evaluate(save=old); self.assertEqual(next(g for g in report["gates"] if g["name"] == "save_verify_v2_exact_folder")["status"], "FAIL"); self.assertFalse(report["accepted"])
    def test_save_v2_wrong_folder_blocks(self):
        bad = saves(); bad["expected_save_folder_proven"] = False; report = evaluate(save=bad); self.assertFalse(report["accepted"])
    def test_repeatability_v1_is_legacy_not_final(self):
        report = evaluate(repeat=repeatability(schema="MADEIRA_HUNIECAM_REPEATABILITY_V1")); self.assertEqual(next(g for g in report["gates"] if g["name"] == "three_sealed_cold_launches")["status"], "FAIL")
    def test_repeatability_must_include_primary_and_match_build_profile(self):
        self.assertFalse(evaluate(repeat=repeatability(runs=("run-2", "run-3", "run-4")))["accepted"]); self.assertFalse(evaluate(repeat=repeatability(build="other"))["accepted"]); self.assertFalse(evaluate(repeat=repeatability(profile="other"))["accepted"])
    def test_missing_repeatability_is_unknown(self):
        report = mod.evaluate(preflight(), session(), saves(), full_manual_counts(), performance(), contract(), context(), None); self.assertEqual(next(g for g in report["gates"] if g["name"] == "three_sealed_cold_launches")["status"], "UNKNOWN")
    def test_pointer_and_stability_thresholds_fail_hard(self):
        manual = full_manual_counts(); manual["pointer_points_passed"] = 8; self.assertFalse(evaluate(manual=manual)["accepted"]); manual = full_manual_counts(); manual["stable_minutes"] = 29; self.assertFalse(evaluate(manual=manual)["accepted"]); manual = full_manual_counts(); manual["cold_launches"] = 2; self.assertFalse(evaluate(manual=manual)["accepted"])
    def test_structured_pointer_false_overrides_counts(self):
        manual = full_structured_manual(); manual["pointer_grid"][0]["passed"] = False; self.assertEqual(next(g for g in evaluate(manual=manual)["gates"] if g["name"] == "pointer_grid")["status"], "FAIL")
    def test_save_loss_blocks(self):
        bad = saves(); bad["save_tree_survived_relaunch"] = False; bad["machine_gate_pass"] = False; self.assertFalse(evaluate(save=bad)["accepted"])
    def test_missing_performance_is_unknown(self):
        report = mod.evaluate(preflight(), session(), saves(), full_manual_counts(), None, contract(), context(), repeatability()); self.assertEqual(next(g for g in report["gates"] if g["name"] == "performance_measurement_clean")["status"], "UNKNOWN")
    def test_explicit_gameplay_failure_blocks(self):
        manual = full_manual_counts(); manual["real_gameplay"] = False; self.assertEqual(evaluate(manual=manual)["overall"], "NOT_READY_FAILED_GATE")


if __name__ == "__main__": unittest.main()
