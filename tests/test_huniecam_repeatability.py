import importlib.util
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("huniecam_repeatability",ROOT/"tools"/"huniecam_repeatability.py"); assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC); sys.modules["huniecam_repeatability"]=mod; SPEC.loader.exec_module(mod)

def ctx(run,build="build-a",profile="profile-a",native="native-a",input_mode="direct_finger",stage=75,failures=(),ready=True,schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V2",sealed=True):
    return {"schema":schema,"ready":ready,"run_id_sha256":run,"build_fingerprint_sha256":build,"profile_sha256":profile,"input_mode":input_mode,"native_module_set_sha256":native,"guard_sha256":"g" if sealed else None,"performance_sha256":"p" if sealed else None,"pe_imports_sha256":"pe" if sealed else None,"native_modules_sha256":"nm" if sealed else None,"session_summary":{"deepest_stage":stage,"failure_codes":list(failures)}}

class HunieCamRepeatabilityTests(unittest.TestCase):
    def test_three_distinct_matching_clean_runs_pass(self):
        r=mod.analyze([ctx("r1"),ctx("r2"),ctx("r3")]); self.assertTrue(r["passed"]); self.assertEqual(r["schema"],"MADEIRA_HUNIECAM_REPEATABILITY_V3"); self.assertEqual(r["unique_run_count"],3); self.assertEqual(r["native_module_set_sha256"],"native-a"); self.assertEqual(r["input_mode"],"direct_finger"); self.assertTrue(r["touch_mode_final_candidate"])
    def test_touch_pointer_three_run_profile_can_pass(self):
        r=mod.analyze([ctx("r1",input_mode="touch_pointer"),ctx("r2",input_mode="touch_pointer"),ctx("r3",input_mode="touch_pointer")]);self.assertTrue(r["passed"]);self.assertEqual(r["input_mode"],"touch_pointer");self.assertTrue(r["touch_mode_final_candidate"])
    def test_different_input_mode_fails_even_if_other_fingerprints_are_same(self):
        r=mod.analyze([ctx("r1"),ctx("r2",input_mode="touch_pointer"),ctx("r3")]);self.assertFalse(r["passed"]);self.assertTrue(any("input mode" in x for x in r["errors"]))
    def test_missing_input_mode_fails_current_repeatability(self):
        r=mod.analyze([ctx("r1"),ctx("r2",input_mode=None),ctx("r3")]);self.assertFalse(r["passed"]);self.assertTrue(any("Pipeline V9" in x for x in r["errors"]))
    def test_hardware_mode_is_repeatable_diagnostic_but_not_final_touch_candidate(self):
        r=mod.analyze([ctx("r1",input_mode="hardware_mouse"),ctx("r2",input_mode="hardware_mouse"),ctx("r3",input_mode="hardware_mouse")]);self.assertTrue(r["passed"]);self.assertFalse(r["touch_mode_final_candidate"]);self.assertTrue(r["warnings"])
    def test_duplicate_run_id_fails(self): self.assertFalse(mod.analyze([ctx("r1"),ctx("r1"),ctx("r3")])["passed"])
    def test_different_build_or_profile_fails(self): self.assertFalse(mod.analyze([ctx("r1"),ctx("r2",build="b"),ctx("r3")])["passed"]); self.assertFalse(mod.analyze([ctx("r1"),ctx("r2",profile="p"),ctx("r3")])["passed"])
    def test_different_native_module_set_fails(self):
        r=mod.analyze([ctx("r1"),ctx("r2",native="native-b"),ctx("r3")]); self.assertFalse(r["passed"]); self.assertTrue(any("native-module set" in x for x in r["errors"]))
    def test_stage_below_scene_and_triaged_failure_fail(self): self.assertFalse(mod.analyze([ctx("r1"),ctx("r2",stage=65),ctx("r3")])["passed"]); self.assertFalse(mod.analyze([ctx("r1"),ctx("r2",failures=("unity_crash",)),ctx("r3")])["passed"])
    def test_fewer_than_three_and_unready_fail(self): self.assertFalse(mod.analyze([ctx("r1"),ctx("r2")])["passed"]); self.assertFalse(mod.analyze([ctx("r1"),ctx("r2",ready=False),ctx("r3")])["passed"])
    def test_legacy_context_v1_does_not_count(self): self.assertFalse(mod.analyze([ctx("r1"),ctx("r2",schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V1"),ctx("r3")])["passed"])
    def test_missing_sealed_fields_fail(self):
        r=mod.analyze([ctx("r1"),ctx("r2",sealed=False),ctx("r3")]); self.assertFalse(r["passed"]); self.assertTrue(any("native-module evidence" in x for x in r["errors"]))

if __name__=="__main__": unittest.main()
