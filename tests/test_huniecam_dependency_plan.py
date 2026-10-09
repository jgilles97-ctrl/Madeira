import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_dependency_plan", ROOT / "tools" / "huniecam_dependency_plan.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_dependency_plan"] = mod
SPEC.loader.exec_module(mod)


def audit(imports=(), valid=True):
    return {"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": valid, "imports": list(imports)}


def session(text=None):
    failures = []
    if text is not None:
        failures.append({"code": "missing_dll", "samples": [{"text": text}]})
    return {"failures": failures}


class HunieCamDependencyPlanTests(unittest.TestCase):
    def test_no_missing_dll_evidence_means_no_dependency_change(self):
        report = mod.choose(audit(("KERNEL32.dll", "d3d9.dll")), session())
        self.assertEqual(report["status"], "NO_MISSING_DLL_EVIDENCE")
        self.assertIn("Do not install", report["action"])

    def test_direct_import_missing_is_exact_prerequisite_lane(self):
        report = mod.choose(audit(("MSVCR100.dll",)), session("err:module:import_dll Library MSVCR100.dll not found"))
        self.assertEqual(report["status"], "EXACT_DIRECT_IMPORT_MISSING")
        self.assertEqual([x.lower() for x in report["direct_exe_import_matches"]], ["msvcr100.dll"])

    def test_indirect_missing_dll_does_not_pretend_exe_imported_it(self):
        report = mod.choose(audit(("KERNEL32.dll",)), session("library XINPUT1_3.dll missing"))
        self.assertEqual(report["status"], "RUNTIME_REPORTED_INDIRECT_OR_DYNAMIC_MISSING")
        self.assertEqual([x.lower() for x in report["indirect_or_dynamic_candidates"]], ["xinput1_3.dll"])
        self.assertIn("request", report["action"].lower())

    def test_unparseable_missing_dll_stays_unproven(self):
        report = mod.choose(audit(), session("err:module:import_dll dependency not found"))
        self.assertEqual(report["status"], "MISSING_DLL_NAME_UNPARSED")

    def test_invalid_pe_audit_is_visible(self):
        report = mod.choose(audit(valid=False), session())
        self.assertTrue(report["errors"])
        self.assertFalse(report["pe_audit_valid"])

    def test_matching_is_case_insensitive(self):
        report = mod.choose(audit(("steam_api.dll",)), session("Library STEAM_API.DLL missing"))
        self.assertEqual(report["status"], "EXACT_DIRECT_IMPORT_MISSING")


if __name__ == "__main__": unittest.main()
