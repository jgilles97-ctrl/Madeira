import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_next_run", ROOT / "tools" / "huniecam_next_run.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_next_run"] = mod
SPEC.loader.exec_module(mod)


def acceptance_session():
    return {"deepest_stage": 75, "next": {"priority": "device acceptance", "action": "test gameplay", "experiment": {"config": "", "arguments": ""}}}


def clean_perf():
    return {"comparison_clean": True, "fps_cap": {"expected": 60, "effective": True}, "warnings": []}


def valid_contract():
    return {"valid": True, "errors": []}


class HunieCamNextRunTests(unittest.TestCase):
    def test_acceptance_requires_contract_and_clean_performance(self):
        r = mod.choose(acceptance_session(), performance=clean_perf(), evidence_contract=valid_contract())
        self.assertEqual(r["schema"], "MADEIRA_HUNIECAM_NEXT_RUN_V2")
        self.assertEqual(r["status"], "RUN_ACCEPTANCE_BASELINE")
        self.assertEqual(r["purpose"], "acceptance")
        self.assertEqual(r["profile"]["config"], "")

    def test_acceptance_without_contract_stops_before_final_test(self):
        r = mod.choose(acceptance_session(), performance=clean_perf())
        self.assertEqual(r["status"], "BUILD_EVIDENCE_CONTRACT_THEN_ACCEPTANCE")
        self.assertFalse(r["run_now"])

    def test_acceptance_with_dirty_performance_repeats_measurement_not_tuning(self):
        perf = {"comparison_clean": False, "fps_cap": {"expected": 60, "effective": False}, "warnings": ["cap missing"]}
        r = mod.choose(acceptance_session(), performance=perf, evidence_contract=valid_contract())
        self.assertEqual(r["status"], "RUN_ACCEPTANCE_MEASUREMENT_BASELINE")
        self.assertTrue(r["run_now"])
        self.assertEqual(r["profile"]["config"], "")
        self.assertEqual(r["profile"]["arguments"], "")

    def test_guard_failure_blocks_even_when_game_code_was_reached(self):
        guard = {"status": "FAIL", "failures": [{"code": "multiple_variables"}]}
        r = mod.choose(acceptance_session(), guard=guard, performance=clean_perf(), evidence_contract=valid_contract())
        self.assertEqual(r["status"], "BLOCK_INVALID_PROFILE")
        self.assertFalse(r["run_now"])

    def test_invalid_contract_blocks_interpretation(self):
        r = mod.choose(acceptance_session(), performance=clean_perf(), evidence_contract={"valid": False, "errors": ["hash mismatch"]})
        self.assertEqual(r["status"], "BLOCK_INVALID_EVIDENCE")
        self.assertFalse(r["run_now"])

    def test_issue_173_blocks_unrelated_tuning(self):
        session = {"deepest_stage": 20, "next": {"priority": "WoW64 breakpoint / self-modifying image runtime bug", "action": "preserve evidence", "experiment": {"config": "", "arguments": ""}}}
        issues = {"best_match": {"issue": 173, "title": "WRITECOPY"}}
        r = mod.choose(session, issues)
        self.assertEqual(r["status"], "BLOCKED_ON_RUNTIME_EVIDENCE")
        self.assertFalse(r["run_now"])

    def test_rwx_experiment_is_run_once(self):
        session = {"deepest_stage": 55, "next": {"priority": "Unity Mono protected-memory writes", "action": "A/B", "experiment": {"name": "rwx", "config": "env.MADEIRA_WOW_RWX_PLAIN = 1", "arguments": "", "reason": "test"}}}
        r = mod.choose(session)
        self.assertEqual(r["status"], "RUN_SINGLE_VARIABLE_EXPERIMENT")
        fp = r["profile"]["sha256"]
        ledger = {"best_stage": 55, "attempts": [{"index": 2, "profile_sha256": fp, "deepest_stage": 55}]}
        r2 = mod.choose(session, ledger=ledger)
        self.assertEqual(r2["status"], "DUPLICATE_DIAGNOSTIC_PROFILE")
        self.assertFalse(r2["run_now"])

    def test_missing_dependency_is_fixed_before_more_tuning(self):
        session = {"deepest_stage": 20, "next": {"priority": "Windows dependency", "action": "install exact prerequisite", "experiment": {"config": "", "arguments": ""}}}
        r = mod.choose(session)
        self.assertEqual(r["status"], "FIX_PREREQUISITE_THEN_RERUN_BASELINE")
        self.assertFalse(r["run_now"])


if __name__ == "__main__":
    unittest.main()
