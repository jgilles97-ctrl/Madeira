import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_dependency_plan", ROOT / "tools" / "huniecam_dependency_plan.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC); sys.modules["huniecam_dependency_plan"] = mod; SPEC.loader.exec_module(mod)

def audit(imports=(), valid=True): return {"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": valid, "imports": list(imports)}
def modules(requesters=None, valid=True): return {"schema": "MADEIRA_HUNIECAM_NATIVE_MODULES_V1", "valid": valid, "dependency_requesters": requesters or {}}
def session(text=None): return {"failures": [] if text is None else [{"code": "missing_dll", "samples": [{"text": text}]}]}

class HunieCamDependencyPlanTests(unittest.TestCase):
    def test_no_missing_dll_evidence_means_no_dependency_change(self):
        report=mod.choose(audit(("KERNEL32.dll",)),session(),modules()); self.assertEqual(report["schema"],"MADEIRA_HUNIECAM_DEPENDENCY_PLAN_V2"); self.assertEqual(report["status"],"NO_MISSING_DLL_EVIDENCE"); self.assertIn("Do not install",report["action"])
    def test_direct_import_missing_is_exact_lane(self):
        report=mod.choose(audit(("MSVCR100.dll",)),session("Library MSVCR100.dll not found"),modules()); self.assertEqual(report["status"],"EXACT_DIRECT_IMPORT_MISSING")
    def test_bundled_native_requester_is_identified(self):
        report=mod.choose(audit(("KERNEL32.dll",)),session("Library XINPUT1_3.dll missing"),modules({"xinput1_3.dll":["HunieCamStudio_Data/Plugins/foo.dll"]})); self.assertEqual(report["status"],"EXACT_BUNDLED_NATIVE_REQUESTER_FOUND"); self.assertEqual(report["bundled_native_requesters"]["XINPUT1_3.dll"],["HunieCamStudio_Data/Plugins/foo.dll"])
    def test_unresolved_dynamic_missing_stays_unproven(self):
        report=mod.choose(audit(("KERNEL32.dll",)),session("Library XINPUT1_3.dll missing"),modules()); self.assertEqual(report["status"],"RUNTIME_REPORTED_DYNAMIC_OR_UNRESOLVED_MISSING"); self.assertEqual([x.lower() for x in report["unresolved_dynamic_candidates"]],["xinput1_3.dll"])
    def test_unparseable_missing_dll_stays_unproven(self):
        self.assertEqual(mod.choose(audit(),session("dependency not found"),modules())["status"],"MISSING_DLL_NAME_UNPARSED")
    def test_invalid_audits_are_visible(self):
        self.assertTrue(mod.choose(audit(valid=False),session(),modules())["errors"]); self.assertTrue(mod.choose(audit(),session(),modules(valid=False))["errors"])
    def test_matching_is_case_insensitive(self):
        self.assertEqual(mod.choose(audit(("steam_api.dll",)),session("Library STEAM_API.DLL missing"),modules())["status"],"EXACT_DIRECT_IMPORT_MISSING")

if __name__ == "__main__": unittest.main()
