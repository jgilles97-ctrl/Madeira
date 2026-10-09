import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_run_context", ROOT / "tools" / "huniecam_run_context.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC); sys.modules["huniecam_run_context"] = mod; SPEC.loader.exec_module(mod)


def record(build="build-a", profile="profile-a", ready=True): return {"schema": "MADEIRA_HUNIECAM_RUN_RECORD_V1", "ready_for_comparison": ready, "build": {"fingerprint_sha256": build}, "profile_sha256": profile}
def session(stage=75): return {"schema": "MADEIRA_HUNIECAM_SESSION_V3", "deepest_stage": stage, "failures": [], "markers": []}
def guard(status="PASS"): return {"schema": "MADEIRA_HUNIECAM_CONFIG_GUARD_V2", "status": status}
def performance(clean=True): return {"schema": "MADEIRA_HUNIECAM_PERFORMANCE_V2", "comparison_clean": clean, "fps_cap": {"expected": 60, "effective": clean}}
def pe(imports=()): return {"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": True, "file_sha256": "exe", "imports": list(imports)}
def native(module_set="native-a"): return {"schema": "MADEIRA_HUNIECAM_NATIVE_MODULES_V1", "valid": True, "module_set_sha256": module_set, "module_count": 3}
def build_context(rec=None, sess=None, madeira="launch\n", unity="unity\n", grd=None, perf=None, pe_report=None, native_report=None): return mod.build(rec or record(), sess or session(), madeira, unity, grd or guard(), perf or performance(), pe_report or pe(), native_report or native())


class HunieCamRunContextTests(unittest.TestCase):
    def test_same_fully_sealed_evidence_is_deterministic(self):
        a = build_context(); b = build_context(); self.assertTrue(a["ready"]); self.assertEqual(a["schema"], "MADEIRA_HUNIECAM_RUN_CONTEXT_V2"); self.assertEqual(a["run_id_sha256"], b["run_id_sha256"]); self.assertTrue(a["guard_sha256"]); self.assertTrue(a["performance_sha256"]); self.assertTrue(a["pe_imports_sha256"]); self.assertTrue(a["native_modules_sha256"]); self.assertEqual(a["native_module_set_sha256"], "native-a")
    def test_changed_logs_session_build_or_profile_change_run_id(self):
        base = build_context(); self.assertNotEqual(base["run_id_sha256"], build_context(madeira="other launch\n")["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(unity="other unity\n")["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(sess=session(65))["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(rec=record(build="build-b"))["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(rec=record(profile="profile-b"))["run_id_sha256"])
    def test_changed_guard_performance_or_dependency_evidence_changes_run_id(self):
        base = build_context(); self.assertNotEqual(base["run_id_sha256"], build_context(grd=guard("WARN"))["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(perf=performance(False))["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(pe_report=pe(("NEW.dll",)))["run_id_sha256"]); self.assertNotEqual(base["run_id_sha256"], build_context(native_report=native("native-b"))["run_id_sha256"])
    def test_native_module_set_is_explicitly_exposed(self):
        report = build_context(native_report=native("set-123")); self.assertEqual(report["native_module_set_sha256"], "set-123"); self.assertEqual(report["material"]["native_module_set_sha256"], "set-123")
    def test_missing_madeira_log_is_not_ready(self):
        report = build_context(madeira=""); self.assertFalse(report["ready"]); self.assertIsNone(report["run_id_sha256"])
    def test_unready_run_record_is_rejected(self): self.assertFalse(build_context(rec=record(ready=False))["ready"])
    def test_missing_session_is_rejected(self):
        report = mod.build(record(), None, "launch\n", "unity\n", guard(), performance(), pe(), native()); self.assertFalse(report["ready"])
    def test_bad_evidence_schema_is_rejected(self):
        bad = guard(); bad["schema"] = "OLD"; self.assertFalse(mod.build(record(), session(), "launch\n", "unity\n", bad, performance(), pe(), native())["ready"])
    def test_raw_text_or_binary_contents_are_not_embedded(self):
        report = build_context(madeira="secret-looking-log-body\n"); rendered = str(report); self.assertNotIn("secret-looking-log-body", rendered); self.assertFalse(report["privacy"]["raw_log_text_embedded"]); self.assertFalse(report["privacy"]["binary_contents_embedded"])


if __name__ == "__main__": unittest.main()
