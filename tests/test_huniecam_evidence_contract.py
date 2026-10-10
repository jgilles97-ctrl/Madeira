import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("huniecam_evidence_contract",ROOT/"tools"/"huniecam_evidence_contract.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_evidence_contract"]=mod;SPEC.loader.exec_module(mod)

def preflight(exe_hash="abc"):return {"schema":"MADEIRA_HUNIECAM_PROBE_V4","identity":{"exe_sha256":exe_hash}}
def session(exe_hash="abc",stage=75,schema="MADEIRA_HUNIECAM_SESSION_V3"):return {"schema":schema,"deepest_stage":stage,"preflight":{"identity":{"exe_sha256":exe_hash}},"evidence":{"madeira_log_present":True}}
def guard(status="PASS"):return {"schema":"MADEIRA_HUNIECAM_CONFIG_GUARD_V2","status":status}
def performance(clean=True,cap=True):return {"schema":"MADEIRA_HUNIECAM_PERFORMANCE_V2","comparison_clean":clean,"fps_cap":{"expected":60,"effective":cap}}
def pe_imports(exe_hash="abc",valid=True):return {"schema":"MADEIRA_HUNIECAM_PE_IMPORTS_V1","valid":valid,"file_sha256":exe_hash,"imports":[]}
def native_modules(module_set="native-a",valid=True):return {"schema":"MADEIRA_HUNIECAM_NATIVE_MODULES_V1","valid":valid,"module_set_sha256":module_set,"module_count":3}
def run_record(exe_hash="abc",stage=75,build="build-a",profile="profile-a",input_mode="direct_finger"):
    return {"schema":"MADEIRA_HUNIECAM_RUN_RECORD_V1","ready_for_comparison":True,"build":{"fingerprint_sha256":build,"material":{"exe_sha256":exe_hash}},"profile":{"input_mode":input_mode,"launch_mode":"direct","resolution":"1280x720","display":"fit","fps":60},"profile_sha256":profile,"session":{"deepest_stage":stage}}
def run_context(sess=None,rec=None,grd=None,perf=None,pe=None,native=None,run_id="run-a",schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V2"):
    sess=sess or session();rec=rec or run_record();grd=grd or guard();perf=perf or performance();pe=pe or pe_imports();native=native or native_modules();out={"schema":schema,"ready":True,"run_id_sha256":run_id,"build_fingerprint_sha256":rec["build"]["fingerprint_sha256"],"profile_sha256":rec["profile_sha256"],"input_mode":(rec.get("profile") or {}).get("input_mode"),"session_sha256":mod._sha_json(sess),"run_record_sha256":mod._sha_json(rec),"logs":{"madeira":{"present":True}}}
    if schema=="MADEIRA_HUNIECAM_RUN_CONTEXT_V2":out.update({"guard_sha256":mod._sha_json(grd),"performance_sha256":mod._sha_json(perf),"pe_imports_sha256":mod._sha_json(pe),"native_modules_sha256":mod._sha_json(native),"native_module_set_sha256":native["module_set_sha256"]})
    return out

class HunieCamEvidenceContractTests(unittest.TestCase):
    def test_matching_current_evidence_is_valid_complete_and_names_input_mode(self):
        sess,rec,grd,perf,pe,native=session(),run_record(),guard(),performance(),pe_imports(),native_modules();ctx=run_context(sess,rec,grd,perf,pe,native);report=mod.validate(preflight(),sess,grd,perf,rec,run_context=ctx,pe_imports=pe,native_modules=native);self.assertTrue(report["valid"],report["errors"]);self.assertEqual(report["schema"],"MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V4");self.assertTrue(report["run_context_v2_complete"]);self.assertEqual(report["sealed_input_mode"],"direct_finger");self.assertEqual(report["run_id_sha256"],"run-a")
    def test_touch_pointer_is_valid_when_run_record_and_context_match(self):
        sess,rec,grd,perf,pe,native=session(),run_record(profile="profile-pointer",input_mode="touch_pointer"),guard(),performance(),pe_imports(),native_modules();ctx=run_context(sess,rec,grd,perf,pe,native);report=mod.validate(preflight(),sess,grd,perf,rec,run_context=ctx,pe_imports=pe,native_modules=native);self.assertTrue(report["valid"],report["errors"]);self.assertEqual(report["sealed_input_mode"],"touch_pointer")
    def test_context_input_mode_must_match_hashed_run_record_profile(self):
        sess,rec,grd,perf,pe,native=session(),run_record(),guard(),performance(),pe_imports(),native_modules();ctx=run_context(sess,rec,grd,perf,pe,native);ctx["input_mode"]="touch_pointer";report=mod.validate(preflight(),sess,grd,perf,rec,run_context=ctx,pe_imports=pe,native_modules=native);self.assertFalse(report["valid"]);self.assertTrue(any("input mode" in x for x in report["errors"]))
    def test_context_missing_input_mode_is_readable_but_not_current_complete(self):
        sess,rec,grd,perf,pe,native=session(),run_record(input_mode=None),guard(),performance(),pe_imports(),native_modules();ctx=run_context(sess,rec,grd,perf,pe,native);report=mod.validate(preflight(),sess,grd,perf,rec,run_context=ctx,pe_imports=pe,native_modules=native);self.assertTrue(report["valid"],report["errors"]);self.assertFalse(report["run_context_v2_complete"]);self.assertTrue(any("Pipeline V9" in x for x in report["warnings"]))
    def test_legacy_session_v2_remains_readable(self):
        report=mod.validate(preflight(),session(schema="MADEIRA_HUNIECAM_SESSION_V2"));self.assertTrue(report["valid"]);self.assertTrue(report["warnings"])
    def test_legacy_context_v1_is_readable_but_not_complete(self):
        sess,rec=session(),run_record();report=mod.validate(preflight(),sess,run_record=rec,run_context=run_context(sess,rec,schema="MADEIRA_HUNIECAM_RUN_CONTEXT_V1"));self.assertTrue(report["valid"]);self.assertFalse(report["run_context_v2_complete"]);self.assertTrue(report["warnings"])
    def test_session_from_other_exe_is_rejected(self):
        report=mod.validate(preflight("aaa"),session("bbb"));self.assertFalse(report["valid"]);self.assertTrue(any("Session embedded executable hash" in x for x in report["errors"]))
    def test_guard_rejected_profile_is_invalid(self):self.assertFalse(mod.validate(preflight(),session(),guard("FAIL"))["valid"])
    def test_unsupported_schema_is_rejected(self):
        bad=preflight();bad["schema"]="MADEIRA_HUNIECAM_PROBE_V999";report=mod.validate(bad);self.assertFalse(report["valid"]);self.assertTrue(any("Unsupported preflight schema" in x for x in report["errors"]))
    def test_run_record_stage_must_match_session(self):
        report=mod.validate(preflight(),session(stage=75),run_record=run_record(stage=55));self.assertFalse(report["valid"]);self.assertTrue(any("deepest stage" in x for x in report["errors"]))
    def test_context_rejects_different_structured_session(self):
        sess_a,sess_b=session(stage=65),session(stage=75);rec=run_record(stage=75);report=mod.validate(preflight(),sess_b,run_record=rec,run_context=run_context(sess_a,rec));self.assertFalse(report["valid"])
    def test_context_rejects_different_run_record(self):
        sess=session();rec_a,rec_b=run_record(profile="profile-a"),run_record(profile="profile-b");report=mod.validate(preflight(),sess,run_record=rec_b,run_context=run_context(sess,rec_a));self.assertFalse(report["valid"])
    def test_context_rejects_mixed_guard_performance_pe_or_native_reports(self):
        sess,rec,grd,perf,pe,native=session(),run_record(),guard(),performance(),pe_imports(),native_modules();ctx=run_context(sess,rec,grd,perf,pe,native);self.assertFalse(mod.validate(preflight(),sess,guard("WARN"),perf,rec,run_context=ctx,pe_imports=pe,native_modules=native)["valid"]);self.assertFalse(mod.validate(preflight(),sess,grd,performance(clean=False),rec,run_context=ctx,pe_imports=pe,native_modules=native)["valid"]);changed_pe=pe_imports();changed_pe["imports"]=["NEW.dll"];self.assertFalse(mod.validate(preflight(),sess,grd,perf,rec,run_context=ctx,pe_imports=changed_pe,native_modules=native)["valid"]);self.assertFalse(mod.validate(preflight(),sess,grd,perf,rec,run_context=ctx,pe_imports=pe,native_modules=native_modules("native-b"))["valid"])
    def test_pe_import_audit_must_match_owned_exe(self):
        report=mod.validate(preflight("owned"),pe_imports=pe_imports("other"));self.assertFalse(report["valid"]);self.assertTrue(any("different executable" in x for x in report["errors"]))
    def test_invalid_native_module_audit_is_rejected(self):self.assertFalse(mod.validate(preflight(),native_modules=native_modules(valid=False))["valid"])
    def test_bad_fps_cap_is_warning_until_acceptance_claims_success(self):
        perf=performance(clean=False,cap=False);report=mod.validate(preflight(),session(),performance=perf);self.assertTrue(report["valid"]);self.assertTrue(report["warnings"]);accepted={"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V10","accepted":True};self.assertFalse(mod.validate(preflight(),session(),performance=perf,acceptance=accepted)["valid"])
    def test_acceptance_without_fully_sealed_context_is_invalid(self):
        accepted={"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V10","accepted":True,"accepted_touch_mode":"direct_finger"};report=mod.validate(preflight(),acceptance=accepted);self.assertFalse(report["valid"])
    def test_acceptance_run_id_and_touch_mode_must_match_context(self):
        sess,rec,grd,perf,pe,native=session(),run_record(),guard(),performance(),pe_imports(),native_modules();ctx=run_context(sess,rec,grd,perf,pe,native,"run-a");bad_id={"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V10","accepted":True,"run_id_sha256":"run-b","accepted_touch_mode":"direct_finger"};report=mod.validate(preflight(),sess,grd,perf,rec,bad_id,ctx,pe,native);self.assertFalse(report["valid"]);self.assertTrue(any("run ID" in x for x in report["errors"]));bad_mode={"schema":"MADEIRA_HUNIECAM_ACCEPTANCE_V10","accepted":True,"run_id_sha256":"run-a","accepted_touch_mode":"touch_pointer"};report=mod.validate(preflight(),sess,grd,perf,rec,bad_mode,ctx,pe,native);self.assertFalse(report["valid"]);self.assertTrue(any("touch mode" in x for x in report["errors"]))

if __name__=="__main__":unittest.main()
