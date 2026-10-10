import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];TOOLS=ROOT/"tools";sys.path.insert(0,str(TOOLS))
SPEC=importlib.util.spec_from_file_location("huniecam_schema_audit",TOOLS/"huniecam_schema_audit.py");assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC);sys.modules["huniecam_schema_audit"]=mod;SPEC.loader.exec_module(mod)

class HunieCamSchemaAuditTests(unittest.TestCase):
    def test_current_cycle8_schema_matrix_passes(self):
        report=mod.audit();self.assertTrue(report["passed"],report["errors"]);self.assertFalse(report["errors"]);self.assertEqual(report["current"],report["expected_current"]);self.assertEqual(report["schema"],"MADEIRA_HUNIECAM_SCHEMA_AUDIT_V2")
    def test_contract_supports_every_current_contract_artifact(self):
        report=mod.audit()
        for kind in ("preflight","session","guard","performance","run_record","run_context","pe_imports","native_modules","acceptance"):self.assertIn(report["current"][kind],report["contract_supported"][kind],kind)
    def test_repeatability_requires_current_run_context(self):self.assertEqual(mod.repeatability.REQUIRED_CONTEXT_SCHEMA,mod.run_context.SCHEMA)
    def test_acceptance_requires_current_device_evidence(self):self.assertEqual(mod.acceptance.DEVICE_SCHEMA,mod.device_evidence.SCHEMA)
    def test_attempt_ledger_requires_current_runtime_audit(self):self.assertEqual(mod.attempt_ledger.RUNTIME_SCHEMA,mod.runtime_bundle_audit.SCHEMA)
    def test_matrix_pins_cycle8_acceptance_manifest_pipeline_runtime_ledger_and_bundle(self):
        self.assertEqual(mod.EXPECTED_CURRENT["device_evidence"],"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3")
        self.assertEqual(mod.EXPECTED_CURRENT["runtime_bundle"],"MADEIRA_HUNIECAM_RUNTIME_BUNDLE_AUDIT_V1")
        self.assertEqual(mod.EXPECTED_CURRENT["attempt_ledger"],"MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V4")
        self.assertEqual(mod.EXPECTED_CURRENT["acceptance"],"MADEIRA_HUNIECAM_ACCEPTANCE_V10")
        self.assertEqual(mod.EXPECTED_CURRENT["manifest"],"MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V7")
        self.assertEqual(mod.EXPECTED_CURRENT["pipeline"],"MADEIRA_HUNIECAM_PIPELINE_V9")
        self.assertEqual(mod.EXPECTED_CURRENT["acceptance_bundle"],"MADEIRA_HUNIECAM_ACCEPTANCE_BUNDLE_V4")
    def test_touch_mode_vocabularies_are_locked_together(self):
        report=mod.audit();self.assertEqual(report["input_modes"]["touch"],["direct_finger","touch_pointer"]);self.assertEqual(set(mod.device_evidence.TOUCH_INPUT_MODES),set(mod.acceptance.TOUCH_INPUT_MODES));self.assertEqual(set(mod.acceptance.TOUCH_INPUT_MODES),set(mod.evidence_manifest.TOUCH_INPUT_MODES));self.assertEqual(set(mod.acceptance.TOUCH_INPUT_MODES),set(mod.repeatability.FINAL_TOUCH_MODES))
    def test_all_diagnostic_input_modes_are_locked_between_pipeline_profile_device_and_ledger(self):
        expected={"direct_finger","touch_pointer","hardware_mouse","hardware_trackpad"};self.assertEqual(set(mod.pipeline.INPUT_MODES),expected);self.assertEqual(set(mod.run_record.INPUT_MODES),expected);self.assertEqual(set(mod.device_evidence.DIAGNOSTIC_INPUT_MODES),expected);self.assertEqual(set(mod.attempt_ledger.INPUT_MODES),expected)

if __name__=="__main__":unittest.main()
