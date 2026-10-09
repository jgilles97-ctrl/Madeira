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


class HunieCamNextRunTests(unittest.TestCase):
    def test_acceptance_stage_stops_tuning(self):
        session = {"deepest_stage": 75, "next": {"priority": "device acceptance", "action": "test gameplay", "experiment": {"config": "", "arguments": ""}}}
        r = mod.choose(session)
        self.assertEqual(r["status"], "RUN_ACCEPTANCE_BASELINE")
        self.assertEqual(r["purpose"], "acceptance")
        self.assertEqual(r["profile"]["config"], "")

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
