import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("huniecam_device_evidence",ROOT/"tools"/"huniecam_device_evidence.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_device_evidence"]=mod;SPEC.loader.exec_module(mod)

def context(ready=True,input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_RUN_CONTEXT_V2","ready":ready,"run_id_sha256":"run-1","build_fingerprint_sha256":"build-1","profile_sha256":"profile-1","input_mode":input_mode}
def pass_drag(item,mode=None):
    if mode is not None:item["input_mode"]=mode
    item.update({"press_registered":True,"movement_registered":True,"release_registered":True,"game_response_registered":True})

class HunieCamDeviceEvidenceTests(unittest.TestCase):
    def test_unlinked_template_has_unknown_input_mode(self):
        data=mod.template();self.assertEqual(data["schema"],"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3");self.assertEqual(len(data["pointer_grid"]),9);self.assertEqual(len(data["drag_release_trials"]),3);self.assertTrue(all(x["input_mode"] is None for x in data["drag_release_trials"]));self.assertIsNone(data["sealed_input_mode"]);self.assertIsNone(data["run_id_sha256"])
    def test_template_seeds_run_link_and_prefills_sealed_input_mode(self):
        data=mod.template(context());self.assertEqual(data["run_id_sha256"],"run-1");self.assertEqual(data["build_fingerprint_sha256"],"build-1");self.assertEqual(data["profile_sha256"],"profile-1");self.assertEqual(data["sealed_input_mode"],"direct_finger");self.assertTrue(all(x["input_mode"]=="direct_finger" for x in data["drag_release_trials"]));report=mod.summarize(data);self.assertTrue(report["derived"]["run_link_ready"]);self.assertTrue(report["derived"]["input_mode_link_ready"])
    def test_touch_pointer_template_is_prefilled_as_touch_pointer(self):
        data=mod.template(context(input_mode="touch_pointer"));self.assertEqual(data["sealed_input_mode"],"touch_pointer");self.assertTrue(all(x["input_mode"]=="touch_pointer" for x in data["drag_release_trials"]))
    def test_unready_context_does_not_seed_false_link_or_mode(self):
        data=mod.template(context(False));self.assertIsNone(data["run_id_sha256"]);self.assertIsNone(data["sealed_input_mode"]);self.assertTrue(all(x["input_mode"] is None for x in data["drag_release_trials"]));self.assertFalse(mod.summarize(data)["derived"]["run_link_ready"])
    def test_all_successes_derive_acceptance_counts_including_drag_release(self):
        data=mod.template(context());
        for item in data["pointer_grid"]:item["passed"]=True
        for item in data["drag_release_trials"]:pass_drag(item)
        for item in data["cold_launch_trials"]:item["success"]=True
        for item in data["suspend_resume_trials"]:item["success"]=True
        report=mod.summarize(data);norm=report["normalized"];self.assertEqual(norm["pointer_points_tested"],9);self.assertEqual(norm["pointer_points_passed"],9);self.assertEqual(norm["drag_release_trials_tested"],3);self.assertEqual(norm["drag_release_trials_passed"],3);self.assertEqual(norm["cold_launches"],3);self.assertEqual(norm["suspend_resume_cycles"],2);self.assertTrue(report["derived"]["pointer_grid_complete"]);self.assertTrue(report["derived"]["drag_release_trials_complete"]);self.assertTrue(report["derived"]["input_mode_link_ready"]);self.assertEqual(report["derived"]["drag_release_touch_mode"],"direct_finger")
    def test_editing_linked_form_to_different_mode_warns_and_breaks_mode_link(self):
        data=mod.template(context());
        for item in data["drag_release_trials"]:pass_drag(item,"touch_pointer")
        report=mod.summarize(data);self.assertTrue(report["derived"]["drag_release_trials_complete"]);self.assertFalse(report["derived"]["input_mode_link_ready"]);self.assertTrue(any("separate Pipeline V9" in x for x in report["warnings"]))
    def test_release_failure_is_not_hidden_by_successful_press_and_move(self):
        data=mod.template(context());
        for item in data["drag_release_trials"]:pass_drag(item)
        data["drag_release_trials"][1]["release_registered"]=False;report=mod.summarize(data);self.assertEqual(report["normalized"]["drag_release_trials_tested"],3);self.assertEqual(report["normalized"]["drag_release_trials_passed"],2);self.assertFalse(report["derived"]["drag_release_trials_complete"])
    def test_game_response_is_required_after_release(self):
        data=mod.template(context());
        for item in data["drag_release_trials"]:pass_drag(item)
        data["drag_release_trials"][0]["game_response_registered"]=None;report=mod.summarize(data);self.assertEqual(report["normalized"]["drag_release_trials_tested"],2);self.assertFalse(report["derived"]["drag_release_trials_complete"])
    def test_failed_pointer_is_not_hidden_by_count(self):
        data=mod.template(context());
        for item in data["pointer_grid"]:item["passed"]=True
        data["pointer_grid"][0]["passed"]=False;report=mod.summarize(data);self.assertEqual(report["normalized"]["pointer_points_passed"],8);self.assertFalse(report["derived"]["pointer_grid_complete"])
    def test_unknown_stays_unknown(self):
        report=mod.summarize(mod.template(context()));self.assertEqual(report["normalized"]["pointer_points_tested"],0);self.assertEqual(report["normalized"]["drag_release_trials_tested"],0);self.assertFalse(report["derived"]["drag_release_trials_complete"])
    def test_legacy_v2_normalizes_but_cannot_prove_drag_release(self):
        data=mod.template(context());data["schema"]="MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V2";data.pop("drag_release_trials");report=mod.summarize(data);self.assertEqual(report["normalized"]["schema"],"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3");self.assertFalse(report["derived"]["drag_release_trials_complete"]);self.assertTrue(any("Legacy" in x for x in report["warnings"]))

if __name__=="__main__":unittest.main()
