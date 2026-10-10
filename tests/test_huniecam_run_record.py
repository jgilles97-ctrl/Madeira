import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_run_record", ROOT / "tools" / "huniecam_run_record.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_run_record"] = mod
SPEC.loader.exec_module(mod)


def preflight(exe_hash="abc"):
    return {"steam_app_id":426000,"identity":{"exe_sha256":exe_hash,"assembly_csharp_sha256":"assembly","unity_mono_sha256":"mono","pe":{"valid_pe":True,"is_32bit_x86":True}}}

def session(exe_hash="abc",stage=75):
    return {"schema":"MADEIRA_HUNIECAM_SESSION_V3","deepest_stage":stage,"deepest_stage_name":"scene","failures":[],"markers":[{"code":"game_assembly"}],"preflight":{"identity":{"exe_sha256":exe_hash}}}

def profile(input_mode="direct_finger"):
    return {"entry_fragment":{"relativePath":"Games/HunieCam Studio/HunieCamStudio.exe","bits":32,"arguments":"","resolution":"1280x720","display":"fit","fpsMode":1,"launchMode":"direct","inputMode":input_mode,"config":""}}

class HunieCamRunRecordTests(unittest.TestCase):
    def test_good_record_is_comparison_ready_and_seals_input_mode(self):
        record=mod.build(preflight(),session(),profile());self.assertTrue(record["ready_for_comparison"]);self.assertEqual(record["schema"],"MADEIRA_HUNIECAM_RUN_RECORD_V1");self.assertEqual(record["profile"]["fps"],60);self.assertEqual(record["profile"]["bits"],32);self.assertEqual(record["profile"]["input_mode"],"direct_finger");self.assertTrue(record["build"]["fingerprint_sha256"]);self.assertTrue(record["profile_sha256"])
    def test_input_mode_changes_profile_and_comparison_identity(self):
        finger=mod.build(preflight(),session(),profile("direct_finger"));pointer=mod.build(preflight(),session(),profile("touch_pointer"));mouse=mod.build(preflight(),session(),profile("hardware_mouse"));self.assertNotEqual(finger["profile_sha256"],pointer["profile_sha256"]);self.assertNotEqual(finger["comparison_key_sha256"],pointer["comparison_key_sha256"]);self.assertNotEqual(pointer["profile_sha256"],mouse["profile_sha256"])
    def test_unsupported_input_mode_is_rejected(self):
        record=mod.build(preflight(),session(),profile("magic_touch"));self.assertFalse(record["ready_for_comparison"]);self.assertTrue(any("Unsupported HunieCam input mode" in x for x in record["errors"]))
    def test_legacy_missing_input_mode_is_diagnostic_with_warning(self):
        p=profile();del p["entry_fragment"]["inputMode"];record=mod.build(preflight(),session(),p);self.assertTrue(record["ready_for_comparison"]);self.assertIsNone(record["profile"]["input_mode"]);self.assertTrue(any("Pipeline V9" in x for x in record["warnings"]))
    def test_session_hash_mismatch_is_rejected(self):
        record=mod.build(preflight("aaa"),session("bbb"),profile());self.assertFalse(record["ready_for_comparison"]);self.assertTrue(any("different executable hash" in x for x in record["errors"]))
    def test_missing_owned_hash_is_rejected(self):
        p=preflight();del p["identity"]["exe_sha256"];record=mod.build(p,session(),profile());self.assertFalse(record["ready_for_comparison"])
    def test_wrong_bits_are_rejected(self):
        p=profile();p["entry_fragment"]["bits"]=64;record=mod.build(preflight(),session(),p);self.assertFalse(record["ready_for_comparison"]);self.assertTrue(any("not 32-bit" in x for x in record["errors"]))
    def test_dirty_performance_is_warning_not_identity_failure(self):
        perf={"schema":"MADEIRA_HUNIECAM_PERFORMANCE_V2","comparison_clean":False,"fps":{"median":40}};record=mod.build(preflight(),session(),profile(),perf);self.assertTrue(record["ready_for_comparison"]);self.assertTrue(record["warnings"])

if __name__ == "__main__":unittest.main()
