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
    return {"schema": "MADEIRA_HUNIECAM_PROBE_V3", "identity": {"exe_sha256": exe_hash}}


def session(exe_hash="abc", stage=75):
    return {
        "schema": "MADEIRA_HUNIECAM_SESSION_V2",
        "deepest_stage": stage,
        "preflight": {"identity": {"exe_sha256": exe_hash}},
        "evidence": {"madeira_log_present": True},
    }


def run_record(exe_hash="abc", stage=75):
    return {
        "schema": "MADEIRA_HUNIECAM_RUN_RECORD_V1",
        "ready_for_comparison": True,
        "build": {"material": {"exe_sha256": exe_hash}},
        "session": {"deepest_stage": stage},
    }


class HunieCamEvidenceContractTests(unittest.TestCase):
    def test_matching_evidence_is_valid(self):
        report = mod.validate(
            preflight(), session(),
            {"schema": "MADEIRA_HUNIECAM_CONFIG_GUARD_V1", "status": "PASS"},
            {"schema": "MADEIRA_HUNIECAM_PERFORMANCE_V2", "comparison_clean": True, "fps_cap": {"expected": 60, "effective": True}},
            run_record(),
        )
        self.assertTrue(report["valid"])
        self.assertFalse(report["errors"])

    def test_session_from_other_exe_is_rejected(self):
        report = mod.validate(preflight("aaa"), session("bbb"))
        self.assertFalse(report["valid"])
        self.assertTrue(any("Session embedded executable hash" in x for x in report["errors"]))

    def test_guard_rejected_profile_is_invalid(self):
        guard = {"schema": "MADEIRA_HUNIECAM_CONFIG_GUARD_V1", "status": "FAIL"}
        report = mod.validate(preflight(), session(), guard)
        self.assertFalse(report["valid"])

    def test_unsupported_schema_is_rejected(self):
        bad = preflight()
        bad["schema"] = "MADEIRA_HUNIECAM_PROBE_V999"
        report = mod.validate(bad)
        self.assertFalse(report["valid"])
        self.assertTrue(any("Unsupported preflight schema" in x for x in report["errors"]))

    def test_run_record_stage_must_match_session(self):
        report = mod.validate(preflight(), session(stage=75), run_record=run_record(stage=55))
        self.assertFalse(report["valid"])
        self.assertTrue(any("deepest stage" in x for x in report["errors"]))

    def test_bad_fps_cap_is_warning_until_acceptance_claims_success(self):
        perf = {"schema": "MADEIRA_HUNIECAM_PERFORMANCE_V2", "comparison_clean": False, "fps_cap": {"expected": 60, "effective": False}}
        report = mod.validate(preflight(), session(), performance=perf)
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])
        accepted = {"schema": "MADEIRA_HUNIECAM_ACCEPTANCE_V3", "accepted": True}
        report2 = mod.validate(preflight(), session(), performance=perf, acceptance=accepted)
        self.assertFalse(report2["valid"])


if __name__ == "__main__":
    unittest.main()
