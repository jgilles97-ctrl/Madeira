import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_repeatability", ROOT / "tools" / "huniecam_repeatability.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_repeatability"] = mod
SPEC.loader.exec_module(mod)


def ctx(run, build="build-a", profile="profile-a", stage=75, failures=(), ready=True, schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V2", sealed=True):
    return {"schema": schema, "ready": ready, "run_id_sha256": run, "build_fingerprint_sha256": build, "profile_sha256": profile, "guard_sha256": "g" if sealed else None, "performance_sha256": "p" if sealed else None, "session_summary": {"deepest_stage": stage, "failure_codes": list(failures)}}


class HunieCamRepeatabilityTests(unittest.TestCase):
    def test_three_distinct_matching_clean_runs_pass(self):
        report = mod.analyze([ctx("r1"), ctx("r2"), ctx("r3")])
        self.assertTrue(report["passed"]); self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_REPEATABILITY_V2"); self.assertEqual(report["unique_run_count"], 3); self.assertEqual(report["build_fingerprint_sha256"], "build-a")

    def test_duplicate_run_id_fails(self):
        report = mod.analyze([ctx("r1"), ctx("r1"), ctx("r3")]); self.assertFalse(report["passed"]); self.assertTrue(any("Duplicate run IDs" in x for x in report["errors"]))

    def test_different_build_fails(self):
        report = mod.analyze([ctx("r1"), ctx("r2", build="build-b"), ctx("r3")]); self.assertFalse(report["passed"]); self.assertTrue(any("owned-build" in x for x in report["errors"]))

    def test_different_profile_fails(self):
        self.assertFalse(mod.analyze([ctx("r1"), ctx("r2", profile="profile-b"), ctx("r3")])["passed"])

    def test_stage_below_scene_fails(self):
        report = mod.analyze([ctx("r1"), ctx("r2", stage=65), ctx("r3")]); self.assertFalse(report["passed"]); self.assertTrue(any("below required stage" in x for x in report["errors"]))

    def test_triaged_failure_fails(self):
        self.assertFalse(mod.analyze([ctx("r1"), ctx("r2", failures=("unity_crash",)), ctx("r3")])["passed"])

    def test_fewer_than_three_fails(self):
        report = mod.analyze([ctx("r1"), ctx("r2")]); self.assertFalse(report["passed"]); self.assertEqual(report["unique_run_count"], 2)

    def test_unready_context_fails(self):
        self.assertFalse(mod.analyze([ctx("r1"), ctx("r2", ready=False), ctx("r3")])["passed"])

    def test_legacy_context_v1_does_not_count_for_cycle6(self):
        report = mod.analyze([ctx("r1"), ctx("r2", schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V1"), ctx("r3")]); self.assertFalse(report["passed"]); self.assertTrue(any("RUN_CONTEXT_V2" in x for x in report["errors"]))

    def test_missing_guard_or_performance_seal_fails(self):
        report = mod.analyze([ctx("r1"), ctx("r2", sealed=False), ctx("r3")]); self.assertFalse(report["passed"]); self.assertTrue(any("guard and performance" in x for x in report["errors"]))


if __name__ == "__main__": unittest.main()
