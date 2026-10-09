import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_evidence_manifest", ROOT / "tools" / "huniecam_evidence_manifest.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_evidence_manifest"] = mod
SPEC.loader.exec_module(mod)


def put(root, name, data):
    path = root / name
    path.write_text(json.dumps(data))
    return path


class HunieCamEvidenceManifestTests(unittest.TestCase):
    def test_manifest_hashes_files_without_embedding_raw_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pre = put(root, "preflight.json", {"schema": "P", "exe_found": True, "identity": {"exe_sha256": "abc", "pe": {"architecture": "i386"}}, "runtime_signals": {"runtime_family": "Unity Mono"}, "depot_shape": {}})
            ses = put(root, "session.json", {"schema": "S", "deepest_stage": 65, "deepest_stage_name": "game managed assembly loaded", "markers": [{"code": "game_assembly"}], "failures": [], "next": {"priority": "device acceptance"}})
            log = root / "madeira-log.txt"; secret = "RAW LOG TOKEN SHOULD NOT APPEAR"; log.write_text(secret)
            report = mod.build({"preflight": pre, "session": ses, "madeira_log": log})
            rendered = json.dumps(report)
            self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V4")
            self.assertTrue(report["minimum_review_bundle_complete"])
            self.assertNotIn(secret, rendered)
            self.assertFalse(report["privacy"]["raw_logs_embedded"])

    def test_sealed_launch_identity_requires_matching_context_and_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            context = put(root, "context.json", {"schema": "MADEIRA_HUNIECAM_RUN_CONTEXT_V1", "ready": True, "run_id_sha256": "run-1", "build_fingerprint_sha256": "b", "profile_sha256": "p"})
            contract = put(root, "contract.json", {"schema": "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V2", "valid": True, "run_id_sha256": "run-1", "errors": [], "warnings": []})
            self.assertTrue(mod.build({"run_context": context, "contract": contract})["sealed_launch_identity_complete"])
            contract.write_text(json.dumps({"schema": "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V2", "valid": True, "run_id_sha256": "different", "errors": [], "warnings": []}))
            report = mod.build({"run_context": context, "contract": contract})
            self.assertFalse(report["sealed_launch_identity_complete"])
            self.assertTrue(report["integrity_warnings"])

    def test_device_template_must_match_primary_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            context = put(root, "context.json", {"schema": "C", "ready": True, "run_id_sha256": "r", "build_fingerprint_sha256": "b", "profile_sha256": "p"})
            device = put(root, "device.json", {"schema": "D", "run_id_sha256": "r", "build_fingerprint_sha256": "b", "profile_sha256": "p"})
            self.assertTrue(mod.build({"run_context": context, "device_template": device})["device_template_linked_to_primary_run"])
            device.write_text(json.dumps({"schema": "D", "run_id_sha256": "other", "build_fingerprint_sha256": "b", "profile_sha256": "p"}))
            self.assertFalse(mod.build({"run_context": context, "device_template": device})["device_template_linked_to_primary_run"])

    def test_repeatability_requires_three_unique_matching_build_profile_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            context = put(root, "context.json", {"schema": "C", "ready": True, "run_id_sha256": "r1", "build_fingerprint_sha256": "b", "profile_sha256": "p"})
            repeat = put(root, "repeat.json", {"schema": "R", "passed": True, "unique_run_count": 3, "run_count": 3, "build_fingerprint_sha256": "b", "profile_sha256": "p"})
            self.assertTrue(mod.build({"run_context": context, "repeatability": repeat})["cold_launch_repeatability_complete"])
            repeat.write_text(json.dumps({"schema": "R", "passed": True, "unique_run_count": 2, "build_fingerprint_sha256": "b", "profile_sha256": "p"}))
            self.assertFalse(mod.build({"run_context": context, "repeatability": repeat})["cold_launch_repeatability_complete"])

    def test_pe_dependency_audit_must_match_preflight_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pre = put(root, "preflight.json", {"schema": "P", "identity": {"exe_sha256": "abc"}, "runtime_signals": {}})
            imports = put(root, "imports.json", {"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": True, "file_sha256": "abc", "import_count": 4, "categories": {"graphics": ["d3d9.dll"]}})
            self.assertTrue(mod.build({"preflight": pre, "pe_imports": imports})["pe_dependency_audit_complete"])
            imports.write_text(json.dumps({"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": True, "file_sha256": "other", "import_count": 1, "categories": {}}))
            self.assertFalse(mod.build({"preflight": pre, "pe_imports": imports})["pe_dependency_audit_complete"])

    def test_guard_failure_is_integrity_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            guard = put(root, "guard.json", {"schema": "G", "status": "FAIL", "experiment": "bad", "changes": []})
            self.assertTrue(mod.build({"guard": guard})["integrity_warnings"])

    def test_acceptance_flag_only_comes_from_acceptance_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            acceptance = put(root, "acceptance.json", {"schema": "A", "accepted": False, "overall": "NOT_READY_MISSING_EVIDENCE", "counts": {}})
            self.assertFalse(mod.build({"acceptance": acceptance})["device_acceptance_complete"])
            acceptance.write_text(json.dumps({"schema": "A", "accepted": True, "overall": "ACCEPTED", "counts": {}, "run_id_sha256": "run-1"}))
            self.assertTrue(mod.build({"acceptance": acceptance})["device_acceptance_complete"])


if __name__ == "__main__":
    unittest.main()
