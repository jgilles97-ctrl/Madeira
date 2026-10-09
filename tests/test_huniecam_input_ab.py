import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];TOOLS=ROOT/"tools";sys.path.insert(0,str(TOOLS))
SPEC=importlib.util.spec_from_file_location("huniecam_input_ab",TOOLS/"huniecam_input_ab.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_input_ab"]=mod;SPEC.loader.exec_module(mod)

def record(mode="direct_finger",build="build-a",extra=None):
    profile={"launch_mode":"direct","resolution":"1280x720","display":"fit","fps":60,"bits":32,"input_mode":mode,"config":"","arguments":"","relative_executable":"HunieCamStudio.exe"}
    if extra:profile.update(extra)
    return {"schema":"MADEIRA_HUNIECAM_RUN_RECORD_V1","ready_for_comparison":True,"build":{"fingerprint_sha256":build},"profile":profile,"profile_sha256":f"profile-{mode}"}
def context(run,mode="direct_finger",build="build-a",native="native-a",profile=None):
    return {"schema":"MADEIRA_HUNIECAM_RUN_CONTEXT_V2","ready":True,"run_id_sha256":run,"build_fingerprint_sha256":build,"profile_sha256":profile or f"profile-{mode}","input_mode":mode,"native_module_set_sha256":native}
def device(run,mode="direct_finger",ok=True,pointer=True,build="build-a",profile=None):
    points=["top_left","top_center","top_right","middle_left","center","middle_right","bottom_left","bottom_center","bottom_right"]
    return {"schema":"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3","run_id_sha256":run,"build_fingerprint_sha256":build,"profile_sha256":profile or f"profile-{mode}","pointer_grid":[{"point":p,"passed":pointer} for p in points],"drag_release_trials":[{"trial":i,"input_mode":mode,"press_registered":True,"movement_registered":True,"release_registered":ok,"game_response_registered":ok} for i in range(1,4)]}

class HunieCamInputABTests(unittest.TestCase):
    def compare(self,before_ok=False,after_ok=True,before_mode="direct_finger",after_mode="touch_pointer"):
        return mod.compare(record(before_mode),context("run-before",before_mode),device("run-before",before_mode,before_ok),record(after_mode),context("run-after",after_mode),device("run-after",after_mode,after_ok))
    def test_touch_pointer_can_be_proven_as_single_variable_improvement(self):
        report=self.compare();self.assertTrue(report["valid_experiment"],report["errors"]);self.assertEqual(report["status"],"TOUCH_MODE_IMPROVED");self.assertTrue(report["keep_after_mode"]);self.assertEqual(report["recommended_final_touch_mode"],"touch_pointer");self.assertEqual([x["key"] for x in report["profile_changes"]],["input_mode"])
    def test_direct_finger_can_be_proven_as_single_variable_improvement(self):
        report=self.compare(before_ok=False,after_ok=True,before_mode="touch_pointer",after_mode="direct_finger");self.assertEqual(report["status"],"TOUCH_MODE_IMPROVED");self.assertEqual(report["recommended_final_touch_mode"],"direct_finger")
    def test_hardware_success_is_diagnostic_not_final_mode(self):
        report=self.compare(before_ok=False,after_ok=True,after_mode="hardware_mouse");self.assertTrue(report["valid_experiment"]);self.assertEqual(report["status"],"HARDWARE_DIAGNOSTIC_IMPROVED");self.assertFalse(report["keep_after_mode"]);self.assertIsNone(report["recommended_final_touch_mode"])
    def test_both_touch_modes_work_keeps_existing_working_touch_mode(self):
        report=self.compare(before_ok=True,after_ok=True);self.assertEqual(report["status"],"BOTH_MODES_WORK");self.assertEqual(report["recommended_final_touch_mode"],"direct_finger")
    def test_regression_rolls_back(self):
        report=self.compare(before_ok=True,after_ok=False);self.assertEqual(report["status"],"REGRESSION");self.assertFalse(report["keep_after_mode"]);self.assertEqual(report["recommended_final_touch_mode"],"direct_finger")
    def test_two_failed_touch_modes_do_not_promote_either(self):
        report=self.compare(before_ok=False,after_ok=False);self.assertEqual(report["status"],"NO_TOUCH_IMPROVEMENT");self.assertIsNone(report["recommended_final_touch_mode"])
    def test_more_than_input_mode_change_invalidates_experiment(self):
        before=record("direct_finger");after=record("touch_pointer",extra={"resolution":"1600x900"});report=mod.compare(before,context("b","direct_finger"),device("b","direct_finger",False),after,context("a","touch_pointer",profile="profile-touch_pointer"),device("a","touch_pointer",True,profile="profile-touch_pointer"));self.assertFalse(report["valid_experiment"]);self.assertEqual(report["status"],"INVALID_EXPERIMENT");self.assertTrue(any("change only input_mode" in x for x in report["errors"]))
    def test_different_build_or_native_set_invalidates_experiment(self):
        before=record("direct_finger");after=record("touch_pointer",build="build-b");report=mod.compare(before,context("b","direct_finger"),device("b","direct_finger",False),after,context("a","touch_pointer",build="build-b"),device("a","touch_pointer",True,build="build-b"));self.assertFalse(report["valid_experiment"]);before=record("direct_finger");after=record("touch_pointer");report=mod.compare(before,context("b","direct_finger",native="one"),device("b","direct_finger",False),after,context("a","touch_pointer",native="two"),device("a","touch_pointer",True));self.assertFalse(report["valid_experiment"])
    def test_reusing_same_run_id_invalidates_experiment(self):
        report=mod.compare(record("direct_finger"),context("same","direct_finger"),device("same","direct_finger",False),record("touch_pointer"),context("same","touch_pointer"),device("same","touch_pointer",True));self.assertFalse(report["valid_experiment"])
    def test_device_evidence_must_match_its_own_context(self):
        report=mod.compare(record("direct_finger"),context("b","direct_finger"),device("wrong","direct_finger",False),record("touch_pointer"),context("a","touch_pointer"),device("a","touch_pointer",True));self.assertFalse(report["valid_experiment"]);self.assertTrue(any("Device evidence run_id" in x for x in report["errors"]))
    def test_pointer_baseline_must_pass_both_runs(self):
        report=mod.compare(record("direct_finger"),context("b","direct_finger"),device("b","direct_finger",False,pointer=False),record("touch_pointer"),context("a","touch_pointer"),device("a","touch_pointer",True));self.assertTrue(report["valid_experiment"]);self.assertEqual(report["status"],"POINTER_BASELINE_NOT_PROVEN");self.assertFalse(report["keep_after_mode"])

if __name__=="__main__":unittest.main()
