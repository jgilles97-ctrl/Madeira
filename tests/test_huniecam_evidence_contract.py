import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_evidence_contract", ROOT / "tools" / "huniecam_evidence_contract.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_evidence_contract"] = mod
SPEC.loader.exec_module(mod)


def preflight(exe_hash="abc"):
    return {"schema": "MADEIRA_HUNIECAM_PROBE_V4", "identity": {"exe_sha256": exe_hash}}


def session(exe_hash="abc", stage=75, schema="MADEIRA_HUNIECAM_SESSION_V3"):
    return {
        "schema": schema,
        "deepest_stage": stage,
        "preflight": {"identity": {"exe_sha256": exe_hash}},
        "evidence": {"madeira_log_present": True},
    }


def run_record(exe_hash="abc", stage=75, build="build-a", profile="profile-a"):
    return {
        "schema": "MADEIRA_HUNIECAM_RUN_RECORD_V1",
        "ready_for_comparison": True,
        "build": {"fingerprint_sha256": build, "material": {"exe_sha256": exe_hash}},
        "profile_sha256": profile,
        "session": {"deepest_stage": stage},
    }


def run_context(sess=None, rec=None, run_id="run-a"):
    sess = sess or session()
    rec = rec or run_record()
    return {
        "schema": "MADEIRA_HUNIECAM_RUN_CONTEXT_V1",
        "ready": True,
        "run_id_sha256": run_id,
        "build_fingerprint_sha256": rec["build"]["fingerprint_sha256"],
        "profile_sha256": rec["profile_sha256"],
        "session_sha256": mod._sha_json(sess),
        "run_record_sha256": mod._sha_json(rec),
        "logs": {"madeira": {"present": True}},
    }


class HunieCamEvidenceContractTests(unittest.TestCase):
    def test_matching_current_evidence_is_valid(self):
        sess, rec = session(), run_record()
        report = mod.validate(
            preflight(), sess,
            {"schema": "MADEIRA_HUNIECAM_CONFIG_GUARD_V2", "status": "PASS"},
            {"schema": "MADEIRA_HUNIECAM_PERFORMANCE_V2", "comparison_clean": True, "fps_cap": {"expected": 60, "effective": True}},
            rec, run_context=run_context(sess, rec),
            pe_imports={"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": True, "file_sha256": "abc"},
        )
        self.assertTrue(report["valid"])
        self.assertFalse(report["errors"])
        self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V2")
        self.assertEqual(report["run_id_sha256"], "run-a")

    def test_legacy_session_v2_remains_readable(self):
        report = mod.validate(preflight(), session(schema="MADEIRA_HUNIECAM_SESSION_V2"))
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])

    def test_session_from_other_exe_is_rejected(self):
        report = mod.validate(preflight("aaa"), session("bbb"))
        self.assertFalse(report["valid"])
        self.assertTrue(any("Session embedded executable hash" in x for x in report["errors"]))

    def test_guard_rejected_profile_is_invalid(self):
        guard = {"schema": "MADEIRA_HUNIECAM_CONFIG_GUARD_V2", "status": "FAIL"}
        report = mod.validate(preflight(), session(), guard)
        self.assertFalse(report["valid"])

    def test_unsupported_schema_is_rejected(self):
        bad = preflight(); bad["schema"] = "MADEIRA_HUNIECAM_PROBE_V999"
        report = mod.validate(bad)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Unsupported preflight schema" in x for x in report["errors"]))

    def test_run_record_stage_must_match_session(self):
        report = mod.validate(preflight(), session(stage=75), run_record=run_record(stage=55))
        self.assertFalse(report["valid"])
        self.assertTrue(any("deepest stage" in x for x in report["errors"]))

    def test_context_rejects_different_structured_session(self):
        sess_a, sess_b = session(stage=65), session(stage=75)
        rec = run_record(stage=75)
        report = mod.validate(preflight(), sess_b, run_record=rec, run_context=run_context(sess_a, rec))
        self.assertFalse(report["valid"])
        self.assertTrue(any("different launches" in x for x in report["errors"]))

    def test_context_rejects_different_run_record(self):
        sess = session()
        rec_a, rec_b = run_record(profile="profile-a"), run_record(profile="profile-b")
        report = mod.validate(preflight(), sess, run_record=rec_b, run_context=run_context(sess, rec_a))
        self.assertFalse(report["valid"])

    def test_pe_import_audit_must_match_owned_exe(self):
        imports = {"schema": "MADEIRA_HUNIECAM_PE_IMPORTS_V1", "valid": True, "file_sha256": "other"}
        report = mod.validate(preflight("owned"), pe_imports=imports)
        self.assertFalse(report["valid"])
        self.assertTrue(any("different executable" in x for x in report["errors"]))

    def test_bad_fps_cap_is_warning_until_acceptance_claims_success(self):
        perf = {"schema": "MADEIRA_HUNIECAM_PERFORMANCE_V2", "comparison_clean": False, "fps_cap": {"expected": 60, "effective": False}}
        report = mod.validate(preflight(), session(), performance=perf)
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])
        accepted = {"schema": "MADEIRA_HUNIECAM_ACCEPTANCE_V6", "accepted": True}
        report2 = mod.validate(preflight(), session(), performance=perf, acceptance=accepted)
        self.assertFalse(report2["valid"])

    def test_acceptance_without_run_context_is_invalid(self):
        accepted = {"schema": "MADEIRA_HUNIECAM_ACCEPTANCE_V6", "accepted": True}
        report = mod.validate(preflight(), acceptance=accepted)
        self.assertFalse(report["valid"])
        self.assertTrue(any("without a per-launch run context" in x for x in report["errors"]))

    def test_acceptance_run_id_must_match_context(self):
        sess, rec = session(), run_record()
        ctx = run_context(sess, rec, "run-a")
        accepted = {"schema": "MADEIRA_HUNIECAM_ACCEPTANCE_V6", "accepted": True, "run_id_sha256": "run-b"}
        report = mod.validate(preflight(), sess, run_record=rec, acceptance=accepted, run_context=ctx)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Acceptance report run ID" in x for x in report["errors"]))


if __name__ == "__main__":
    unittest.main()
