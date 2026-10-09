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


class HunieCamEvidenceManifestTests(unittest.TestCase):
    def test_manifest_hashes_files_without_embedding_raw_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pre = root / "preflight.json"
            pre.write_text(json.dumps({"schema": "P", "exe_found": True, "identity": {"exe_sha256": "abc", "pe": {"architecture": "i386"}}, "runtime_signals": {"runtime_family": "Unity Mono"}, "depot_shape": {}}))
            ses = root / "session.json"
            ses.write_text(json.dumps({"schema": "S", "deepest_stage": 65, "deepest_stage_name": "game managed assembly loaded", "markers": [{"code": "game_assembly"}], "failures": [], "next": {"priority": "device acceptance"}}))
            log = root / "madeira-log.txt"
            secret = "RAW LOG TOKEN SHOULD NOT APPEAR"
            log.write_text(secret)
            report = mod.build({"preflight": pre, "session": ses, "madeira_log": log})
            rendered = json.dumps(report)
            self.assertTrue(report["minimum_review_bundle_complete"])
            self.assertNotIn(secret, rendered)
            self.assertFalse(report["privacy"]["raw_logs_embedded"])
            self.assertTrue(any(f["kind"] == "madeira_log" and f["sha256"] for f in report["files"]))

    def test_guard_failure_is_integrity_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            guard = root / "guard.json"
            guard.write_text(json.dumps({"schema": "G", "status": "FAIL", "experiment": "bad", "changes": []}))
            report = mod.build({"guard": guard})
            self.assertTrue(report["integrity_warnings"])

    def test_acceptance_flag_only_comes_from_acceptance_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            acceptance = root / "acceptance.json"
            acceptance.write_text(json.dumps({"schema": "A", "accepted": False, "overall": "NOT_READY_MISSING_EVIDENCE", "counts": {}}))
            report = mod.build({"acceptance": acceptance})
            self.assertFalse(report["device_acceptance_complete"])
            acceptance.write_text(json.dumps({"schema": "A", "accepted": True, "overall": "ACCEPTED", "counts": {}}))
            report = mod.build({"acceptance": acceptance})
            self.assertTrue(report["device_acceptance_complete"])


if __name__ == "__main__":
    unittest.main()
