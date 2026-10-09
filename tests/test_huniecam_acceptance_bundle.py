import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];TOOLS=ROOT/"tools";sys.path.insert(0,str(TOOLS))
SPEC=importlib.util.spec_from_file_location("huniecam_acceptance_bundle",TOOLS/"huniecam_acceptance_bundle.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_acceptance_bundle"]=mod;SPEC.loader.exec_module(mod)
def write(path,data):path.write_text(json.dumps(data));return path
def primary_data(input_mode="direct_finger"):
    pre={"schema":"MADEIRA_HUNIECAM_PROBE_V4","exe_found":True,"identity":{"exe_sha256":"abc","pe":{"valid_pe":True}}};ses={"schema":"MADEIRA_HUNIECAM_SESSION_V3","deepest_stage":75,"deepest_stage_name":"scene","preflight":{"identity":{"exe_sha256":"abc"}},"evidence":{"madeira_log_present":True},"failures":[],"markers":[]};guard={"schema":"MADEIRA_HUNIECAM_CONFIG_GUARD_V2","status":"PASS","experiment":"clean baseline"};perf={"schema":"MADEIRA_HUNIECAM_PERFORMANCE_V2","comparison_clean":True,"fps_cap":{"expected":60,"effective":True}};profile={"launch_mode":"direct","resolution":"1280x720","display":"fit","fps":60,"bits":32,"input_mode":input_mode,"config":"","arguments":"","relative_executable":"HunieCamStudio.exe"};rec={"schema":"MADEIRA_HUNIECAM_RUN_RECORD_V1","ready_for_comparison":True,"build":{"fingerprint_sha256":"build-a","material":{"exe_sha256":"abc"}},"profile":profile,"profile_sha256":"profile-a","session":{"deepest_stage":75}};pe={"schema":"MADEIRA_HUNIECAM_PE_IMPORTS_V1","valid":True,"file_sha256":"abc","imports":[]};native={"schema":"MADEIRA_HUNIECAM_NATIVE_MODULES_V1","valid":True,"module_set_sha256":"native-a","module_count":4};ctx={"schema":"MADEIRA_HUNIECAM_RUN_CONTEXT_V2","ready":True,"run_id_sha256":"run-1","build_fingerprint_sha256":"build-a","profile_sha256":"profile-a","input_mode":input_mode,"session_sha256":mod.contract_tool._sha_json(ses),"run_record_sha256":mod.contract_tool._sha_json(rec),"guard_sha256":mod.contract_tool._sha_json(guard),"performance_sha256":mod.contract_tool._sha_json(perf),"pe_imports_sha256":mod.contract_tool._sha_json(pe),"native_modules_sha256":mod.contract_tool._sha_json(native),"native_module_set_sha256":"native-a","session_summary":{"deepest_stage":75,"failure_codes":[]},"logs":{"madeira":{"present":True}}};return {"preflight":pre,"session":ses,"guard":guard,"performance":perf,"run_record":rec,"run_context":ctx,"pe_imports":pe,"native_modules":native}
def device(run="run-1",drag_ok=True,mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3","run_id_sha256":run,"build_fingerprint_sha256":"build-a","profile_sha256":"profile-a","jit_memory_ready":True,"real_gameplay":True,"rendering_correct":True,"pointer_grid":[{"point":p,"passed":True,"note":""} for p in mod.acceptance_tool.POINTER_POINTS],"drag_release_trials":[{"trial":i,"input_mode":mode,"press_registered":True,"movement_registered":True,"release_registered":drag_ok,"game_response_registered":drag_ok,"note":""} for i in range(1,4)],"audio_correct":True,"save_progress_visible_after_relaunch":True,"performance_acceptable":True,"stable_minutes":30,"cold_launch_trials":[{"trial":i,"success":True,"note":""} for i in range(1,4)],"suspend_resume_trials":[{"trial":i,"success":True,"note":""} for i in range(1,3)],"repeatable_profile":True}
def save():return {"schema":"MADEIRA_HUNIECAM_SAVE_VERIFY_V2","progress_write_detected":True,"save_tree_survived_relaunch":True,"same_source_directory_proven":True,"expected_save_folder_proven":True,"machine_gate_pass":True,"errors":[]}

class HunieCamAcceptanceBundleTests(unittest.TestCase):
    def setup_bundle(self,root,input_mode="direct_finger",device_mode=None):
        primary=root/"primary";primary.mkdir();data=primary_data(input_mode)
        for kind,filename in mod.REQUIRED_PRIMARY.items():write(primary/filename,data[kind])
        device_path=write(root/"device.json",device(mode=device_mode or input_mode));save_path=write(root/"save.json",save());contexts=[]
        for index in range(1,4):
            ctx=copy.deepcopy(data["run_context"]);ctx["run_id_sha256"]=f"run-{index}";contexts.append(write(root/f"context-{index}.json",ctx))
        return primary,device_path,save_path,contexts
    def test_full_current_bundle_accepts_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,dev,save_path,contexts=self.setup_bundle(root);out=root/"final";report=mod.run_bundle(primary,dev,save_path,contexts,out);self.assertTrue(report["accepted"],report);self.assertEqual(report["schema"],"MADEIRA_HUNIECAM_ACCEPTANCE_BUNDLE_V3");self.assertEqual(report["accepted_touch_mode"],"direct_finger");self.assertEqual(report["sealed_input_mode"],"direct_finger");self.assertEqual(report["repeatability_input_mode"],"direct_finger");self.assertTrue(report["interaction_modes_match"]);self.assertTrue(report["interaction_mode_provenance_complete"]);self.assertTrue(report["repeatability_passed"]);self.assertEqual(report["repeatability_unique_runs"],3);self.assertTrue(report["final_contract_valid"]);self.assertTrue(report["drag_release_evidence_complete"]);self.assertTrue(report["input_source_release_path_proven"]);self.assertEqual(report["input_fallback_status"],"DIRECT_FINGER_DRAG_PROVEN")
            self.assertTrue((out/"huniecam-input-path-audit.json").is_file());self.assertTrue((out/"huniecam-input-fallback.json").is_file())
            acceptance=json.loads((out/"huniecam-acceptance.json").read_text());self.assertEqual(acceptance["schema"],"MADEIRA_HUNIECAM_ACCEPTANCE_V10");self.assertEqual(acceptance["accepted_touch_mode"],"direct_finger");self.assertTrue(acceptance["accepted"])
            manifest=json.loads((out/"huniecam-final-manifest.json").read_text());self.assertEqual(manifest["schema"],"MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V7");self.assertEqual(manifest["accepted_touch_mode"],"direct_finger");self.assertTrue(manifest["interaction_mode_provenance_complete"]);self.assertTrue(manifest["drag_release_evidence_complete"]);self.assertTrue(manifest["cold_launch_repeatability_complete"]);self.assertTrue(manifest["save_machine_verification_complete"]);self.assertTrue(manifest["device_acceptance_complete"])
    def test_touch_pointer_bundle_accepts_when_every_sealed_layer_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,dev,save_path,contexts=self.setup_bundle(root,input_mode="touch_pointer");report=mod.run_bundle(primary,dev,save_path,contexts,root/"final");self.assertTrue(report["accepted"],report);self.assertEqual(report["accepted_touch_mode"],"touch_pointer");self.assertEqual(report["repeatability_input_mode"],"touch_pointer")
    def test_device_mode_mismatch_cannot_accept_even_when_drag_mechanics_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,dev,save_path,contexts=self.setup_bundle(root,input_mode="direct_finger",device_mode="touch_pointer");report=mod.run_bundle(primary,dev,save_path,contexts,root/"final");self.assertFalse(report["accepted"]);self.assertFalse(report["interaction_modes_match"]);self.assertFalse(report["interaction_mode_provenance_complete"]);self.assertEqual(report["next_unproven_gate"]["name"],"input_mode_provenance")
    def test_failed_drag_release_cannot_accept_and_gets_one_variable_touch_pointer_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,_,save_path,contexts=self.setup_bundle(root);dev=write(root/"drag-fail.json",device(drag_ok=False));report=mod.run_bundle(primary,dev,save_path,contexts,root/"final");self.assertFalse(report["accepted"]);self.assertEqual(report["next_unproven_gate"]["name"],"drag_release_gameplay");self.assertEqual(report["input_fallback_status"],"TRY_TOUCH_POINTER_ONE_VARIABLE");self.assertIn("Change only",report["input_next_action"])
    def test_mouse_only_drag_success_cannot_accept_touch_first_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,_,save_path,contexts=self.setup_bundle(root);dev=write(root/"mouse.json",device(mode="hardware_mouse"));report=mod.run_bundle(primary,dev,save_path,contexts,root/"final");self.assertFalse(report["accepted"]);self.assertFalse(report["drag_release_evidence_complete"]);self.assertIsNone(report["accepted_touch_mode"])
    def test_wrong_device_run_id_cannot_accept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,_,save_path,contexts=self.setup_bundle(root);dev=write(root/"wrong-device.json",device("wrong"));report=mod.run_bundle(primary,dev,save_path,contexts,root/"final");self.assertFalse(report["accepted"]);self.assertEqual(report["next_unproven_gate"]["name"],"device_evidence_same_run")
    def test_duplicate_context_cannot_fake_three_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,dev,save_path,contexts=self.setup_bundle(root);report=mod.run_bundle(primary,dev,save_path,[contexts[0],contexts[0],contexts[2]],root/"final");self.assertFalse(report["accepted"]);self.assertFalse(report["repeatability_passed"])
    def test_mixed_repeatability_input_modes_cannot_fake_one_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,dev,save_path,contexts=self.setup_bundle(root);mixed=copy.deepcopy(json.loads(contexts[1].read_text()));mixed["input_mode"]="touch_pointer";mixed_path=write(root/"context-mixed.json",mixed);report=mod.run_bundle(primary,dev,save_path,[contexts[0],mixed_path,contexts[2]],root/"final");self.assertFalse(report["accepted"]);self.assertFalse(report["repeatability_passed"])
    def test_missing_primary_artifact_fails_without_synthesizing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);primary,dev,save_path,contexts=self.setup_bundle(root);(primary/"huniecam-native-modules.json").unlink();out=root/"final";report=mod.run_bundle(primary,dev,save_path,contexts,out);self.assertFalse(report["accepted"]);self.assertTrue(report["errors"]);self.assertTrue((out/"huniecam-final-summary.json").is_file())

if __name__=="__main__":unittest.main()
