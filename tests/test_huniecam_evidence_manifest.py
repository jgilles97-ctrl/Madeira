import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("huniecam_evidence_manifest",ROOT/"tools"/"huniecam_evidence_manifest.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_evidence_manifest"]=mod;SPEC.loader.exec_module(mod)

def put(root,name,data):
    path=root/name;path.write_text(json.dumps(data));return path
def current_context(run="run-1",build="b",profile="p",native="n",input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_RUN_CONTEXT_V2","ready":True,"run_id_sha256":run,"build_fingerprint_sha256":build,"profile_sha256":profile,"input_mode":input_mode,"native_module_set_sha256":native,"session_summary":{"deepest_stage":75,"failure_codes":[]}}
def current_contract(run="run-1",valid=True,input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4","valid":valid,"run_id_sha256":run,"sealed_input_mode":input_mode,"run_context_v2_complete":valid,"errors":[],"warnings":[]}
def current_device(run="run-1",build="b",profile="p",drag_ok=True,input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3","run_id_sha256":run,"build_fingerprint_sha256":build,"profile_sha256":profile,"drag_release_trials":[{"trial":i,"input_mode":input_mode,"press_registered":True,"movement_registered":True,"release_registered":drag_ok,"game_response_registered":drag_ok} for i in range(1,4)]}
def current_repeat(input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_REPEATABILITY_V3","passed":True,"unique_run_count":3,"run_count":3,"build_fingerprint_sha256":"b","profile_sha256":"p","input_mode":input_mode,"touch_mode_final_candidate":input_mode in {"direct_finger","touch_pointer"},"native_module_set_sha256":"n"}

class HunieCamEvidenceManifestTests(unittest.TestCase):
    def test_manifest_hashes_files_without_embedding_raw_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);pre=put(root,"preflight.json",{"schema":"P","exe_found":True,"identity":{"exe_sha256":"abc","pe":{"architecture":"i386"}},"runtime_signals":{"runtime_family":"Unity Mono"},"depot_shape":{}});ses=put(root,"session.json",{"schema":"S","deepest_stage":65,"deepest_stage_name":"game managed assembly loaded","markers":[{"code":"game_assembly"}],"failures":[],"next":{"priority":"device acceptance"}});log=root/"madeira-log.txt";secret="RAW LOG TOKEN SHOULD NOT APPEAR";log.write_text(secret);report=mod.build({"preflight":pre,"session":ses,"madeira_log":log});rendered=json.dumps(report);self.assertEqual(report["schema"],"MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V7");self.assertTrue(report["minimum_review_bundle_complete"]);self.assertNotIn(secret,rendered);self.assertFalse(report["privacy"]["raw_logs_embedded"])
    def test_sealed_launch_identity_requires_current_matching_context_contract_and_input_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context());contract=put(root,"contract.json",current_contract());report=mod.build({"run_context":context,"contract":contract});self.assertTrue(report["sealed_launch_identity_complete"]);self.assertEqual(report["sealed_input_mode"],"direct_finger");contract.write_text(json.dumps(current_contract(run="different")));report=mod.build({"run_context":context,"contract":contract});self.assertFalse(report["sealed_launch_identity_complete"]);contract.write_text(json.dumps(current_contract(input_mode="touch_pointer")));report=mod.build({"run_context":context,"contract":contract});self.assertFalse(report["sealed_launch_identity_complete"])
    def test_legacy_context_without_input_mode_cannot_claim_current_sealed_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",{"schema":"MADEIRA_HUNIECAM_RUN_CONTEXT_V2","ready":True,"run_id_sha256":"run-1","build_fingerprint_sha256":"b","profile_sha256":"p"});contract=put(root,"contract.json",{"schema":"MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4","valid":True,"run_id_sha256":"run-1","run_context_v2_complete":True});self.assertFalse(mod.build({"run_context":context,"contract":contract})["sealed_launch_identity_complete"])
    def test_device_v3_must_match_primary_context_and_prove_drag_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context());device=put(root,"device.json",current_device());report=mod.build({"run_context":context,"device_template":device});self.assertTrue(report["device_template_linked_to_primary_run"]);self.assertTrue(report["drag_release_evidence_complete"])
            device.write_text(json.dumps(current_device(drag_ok=False)));report=mod.build({"run_context":context,"device_template":device});self.assertTrue(report["device_template_linked_to_primary_run"]);self.assertFalse(report["drag_release_evidence_complete"])
            device.write_text(json.dumps(current_device(run="other")));report=mod.build({"run_context":context,"device_template":device});self.assertFalse(report["device_template_linked_to_primary_run"]);self.assertFalse(report["drag_release_evidence_complete"])
    def test_interaction_provenance_requires_device_context_and_repeatability_same_touch_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context());device=put(root,"device.json",current_device());repeat=put(root,"repeat.json",current_repeat());report=mod.build({"run_context":context,"device_template":device,"repeatability":repeat});self.assertTrue(report["interaction_mode_provenance_complete"]);self.assertEqual(report["accepted_touch_mode"],"direct_finger");repeat.write_text(json.dumps(current_repeat("touch_pointer")));report=mod.build({"run_context":context,"device_template":device,"repeatability":repeat});self.assertFalse(report["interaction_mode_provenance_complete"]);self.assertIsNone(report["accepted_touch_mode"]);self.assertTrue(any("touch mode proven" in x for x in report["integrity_warnings"]))
    def test_touch_pointer_can_be_one_current_interaction_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context(input_mode="touch_pointer"));device=put(root,"device.json",current_device(input_mode="touch_pointer"));repeat=put(root,"repeat.json",current_repeat("touch_pointer"));report=mod.build({"run_context":context,"device_template":device,"repeatability":repeat});self.assertTrue(report["interaction_mode_provenance_complete"]);self.assertEqual(report["accepted_touch_mode"],"touch_pointer")
    def test_hardware_mouse_never_becomes_completed_touch_interaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context(input_mode="hardware_mouse"));device=put(root,"device.json",current_device(input_mode="hardware_mouse"));repeat=put(root,"repeat.json",current_repeat("hardware_mouse"));report=mod.build({"run_context":context,"device_template":device,"repeatability":repeat});self.assertFalse(report["drag_release_evidence_complete"]);self.assertFalse(report["interaction_mode_provenance_complete"]);self.assertIsNone(report["accepted_touch_mode"])
    def test_legacy_device_v2_cannot_claim_current_link_or_drag_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context());device=put(root,"device.json",{"schema":"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V2","run_id_sha256":"run-1","build_fingerprint_sha256":"b","profile_sha256":"p"});report=mod.build({"run_context":context,"device_template":device});self.assertFalse(report["device_template_linked_to_primary_run"]);self.assertFalse(report["drag_release_evidence_complete"])
    def test_repeatability_requires_current_v3_three_unique_matching_build_profile_native_input_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context(run="r1"));repeat=put(root,"repeat.json",current_repeat());self.assertTrue(mod.build({"run_context":context,"repeatability":repeat})["cold_launch_repeatability_complete"]);bad=current_repeat();bad["unique_run_count"]=2;repeat.write_text(json.dumps(bad));self.assertFalse(mod.build({"run_context":context,"repeatability":repeat})["cold_launch_repeatability_complete"]);bad=current_repeat("touch_pointer");repeat.write_text(json.dumps(bad));self.assertFalse(mod.build({"run_context":context,"repeatability":repeat})["cold_launch_repeatability_complete"])
    def test_pe_dependency_audit_must_match_preflight_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);pre=put(root,"preflight.json",{"schema":"P","identity":{"exe_sha256":"abc"},"runtime_signals":{}});imports=put(root,"imports.json",{"schema":"MADEIRA_HUNIECAM_PE_IMPORTS_V1","valid":True,"file_sha256":"abc","import_count":4,"categories":{"graphics":["d3d9.dll"]}});self.assertTrue(mod.build({"preflight":pre,"pe_imports":imports})["pe_dependency_audit_complete"]);imports.write_text(json.dumps({"schema":"MADEIRA_HUNIECAM_PE_IMPORTS_V1","valid":True,"file_sha256":"other","import_count":1,"categories":{}}));self.assertFalse(mod.build({"preflight":pre,"pe_imports":imports})["pe_dependency_audit_complete"])
    def test_guard_failure_is_integrity_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);guard=put(root,"guard.json",{"schema":"G","status":"FAIL","experiment":"bad","changes":[]});self.assertTrue(mod.build({"guard":guard})["integrity_warnings"])
    def test_acceptance_requires_v10_report_linked_to_primary_context_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);context=put(root,"context.json",current_context());acceptance=put(root,"acceptance.json",{"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V10","accepted":True,"overall":"ACCEPTED","counts":{},"run_id_sha256":"run-1","accepted_touch_mode":"direct_finger","sealed_input_mode":"direct_finger"});self.assertTrue(mod.build({"run_context":context,"acceptance":acceptance})["device_acceptance_complete"]);acceptance.write_text(json.dumps({"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V9","accepted":True,"overall":"ACCEPTED","run_id_sha256":"run-1"}));self.assertFalse(mod.build({"run_context":context,"acceptance":acceptance})["device_acceptance_complete"]);acceptance.write_text(json.dumps({"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V10","accepted":True,"overall":"ACCEPTED","run_id_sha256":"run-1","accepted_touch_mode":"touch_pointer"}));self.assertFalse(mod.build({"run_context":context,"acceptance":acceptance})["device_acceptance_complete"])

if __name__=="__main__":unittest.main()
