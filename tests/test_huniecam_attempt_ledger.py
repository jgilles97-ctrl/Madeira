import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_attempt_ledger", ROOT / "tools" / "huniecam_attempt_ledger.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_attempt_ledger"] = mod
SPEC.loader.exec_module(mod)


def session(stage, failures=()):
    return {
        "deepest_stage": stage,
        "deepest_stage_name": f"stage {stage}",
        "markers": [{"code": "target_started"}] if stage >= 20 else [],
        "failures": [{"code": x} for x in failures],
        "next": {"priority": "test"},
    }


class HunieCamAttemptLedgerTests(unittest.TestCase):
    def test_first_run_is_baseline(self):
        ledger, summary = mod.add_attempt(None, session(30), {"status": "PASS", "experiment": "clean baseline"}, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:00:00+00:00")
        self.assertEqual(summary["attempt"]["movement"], "BASELINE")
        self.assertEqual(ledger["best_stage"], 30)

    def test_deeper_run_is_improvement(self):
        ledger, _ = mod.add_attempt(None, session(30), {"status": "PASS", "experiment": "clean baseline"}, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:00:00+00:00")
        ledger, summary = mod.add_attempt(ledger, session(65), {"status": "PASS", "experiment": "Unity Mono RWX plain-memory A/B"}, launch_mode="direct", resolution="1280x720", fps=60, config="env.MADEIRA_WOW_RWX_PLAIN = 1", arguments="", now="2026-10-09T00:01:00+00:00")
        self.assertEqual(summary["attempt"]["movement"], "IMPROVED")
        self.assertEqual(ledger["best_stage"], 65)
        self.assertEqual(ledger["best_attempt"], 2)

    def test_regression_warns_against_promotion(self):
        ledger, _ = mod.add_attempt(None, session(65), {"status": "PASS", "experiment": "clean baseline"}, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:00:00+00:00")
        ledger, summary = mod.add_attempt(ledger, session(45, ("unity_crash",)), {"status": "PASS", "experiment": "native D3D9 frontend A/B"}, launch_mode="direct", resolution="1280x720", fps=60, config="d3d9 = native", arguments="", now="2026-10-09T00:01:00+00:00")
        self.assertEqual(summary["attempt"]["movement"], "REGRESSED_VS_BEST")
        self.assertTrue(summary["warnings"])

    def test_duplicate_diagnostic_profile_is_flagged(self):
        ledger, _ = mod.add_attempt(None, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:00:00+00:00")
        _, summary = mod.add_attempt(ledger, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:01:00+00:00")
        self.assertTrue(summary["attempt"]["duplicate_profile_before"])
        self.assertTrue(summary["warnings"])

    def test_repeatability_duplicate_is_not_warned_as_waste(self):
        ledger, _ = mod.add_attempt(None, session(75), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", purpose="acceptance", now="2026-10-09T00:00:00+00:00")
        _, summary = mod.add_attempt(ledger, session(75), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", purpose="repeatability", now="2026-10-09T00:01:00+00:00")
        self.assertFalse(any("already tried" in w for w in summary["warnings"]))

    def test_guard_failure_blocks_recording(self):
        with self.assertRaises(ValueError):
            mod.add_attempt(None, session(20), {"status": "FAIL"}, launch_mode="direct", resolution="1280x720", fps=60, config="d3d9=native", arguments="-force-d3d9")


if __name__ == "__main__":
    unittest.main()
