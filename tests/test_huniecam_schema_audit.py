import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("huniecam_schema_audit", TOOLS / "huniecam_schema_audit.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC); sys.modules["huniecam_schema_audit"] = mod; SPEC.loader.exec_module(mod)


class HunieCamSchemaAuditTests(unittest.TestCase):
    def test_current_cycle6_schema_matrix_passes(self):
        report = mod.audit()
        self.assertTrue(report["passed"], report["errors"])
        self.assertFalse(report["errors"])
        self.assertEqual(report["current"], report["expected_current"])

    def test_contract_supports_every_current_contract_artifact(self):
        report = mod.audit()
        for kind in ("preflight", "session", "guard", "performance", "run_record", "run_context", "pe_imports", "native_modules", "acceptance"):
            self.assertIn(report["current"][kind], report["contract_supported"][kind], kind)

    def test_repeatability_requires_current_run_context(self):
        self.assertEqual(mod.repeatability.REQUIRED_CONTEXT_SCHEMA, mod.run_context.SCHEMA)

    def test_matrix_pins_final_acceptance_and_pipeline(self):
        self.assertEqual(mod.EXPECTED_CURRENT["acceptance"], "MADEIRA_HUNIECAM_ACCEPTANCE_V8")
        self.assertEqual(mod.EXPECTED_CURRENT["pipeline"], "MADEIRA_HUNIECAM_PIPELINE_V7")


if __name__ == "__main__": unittest.main()
