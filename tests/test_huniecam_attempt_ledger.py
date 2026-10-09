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


def run_record(stage, build="build-a"):
    return {
        "schema": "MADEIRA_HUNIECAM_RUN_RECORD_V1",
        "ready_for_comparison": True,
        "build": {"fingerprint_sha256": build},
        "session": {"deepest_stage": stage},
    }


class HunieCamAttemptLedgerTests(unittest.TestCase):
    def test_first_run_is_baseline_and_locks_build(self):
        ledger, summary = mod.add_attempt(None, session(30), {"status": "PASS", "experiment": "clean baseline"}, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:00:00+00:00", run_record=run_record(30))
        self.assertEqual(ledger["schema"], "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V2")
        self.assertEqual(summary["attempt"]["movement"], "BASELINE")
        self.assertEqual(ledger["best_stage"], 30)
        self.assertEqual(ledger["owned_build_fingerprint"], "build-a")

    def test_deeper_run_is_improvement_same_build(self):
        ledger, _ = mod.add_attempt(None, session(30), {"status": "PASS", "experiment": "clean baseline"}, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", now="2026-10-09T00:00:00+00:00", run_record=run_record(30))
        ledger, summary = mod.add_attempt(ledger, session(65), {"status": "PASS", "experiment": "Unity Mono RWX plain-memory A/B"}, launch_mode="direct", resolution="1280x720", fps=60, config="env.MADEIRA_WOW_RWX_PLAIN = 1", arguments="", now="2026-10-09T00:01:00+00:00", run_record=run_record(65))
        self.assertEqual(summary["attempt"]["movement"], "IMPROVED")
        self.assertEqual(ledger["best_stage"], 65)
        self.assertEqual(ledger["best_attempt"], 2)

    def test_different_build_is_rejected(self):
        ledger, _ = mod.add_attempt(None, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(30, "aaa"))
        with self.assertRaisesRegex(ValueError, "different owned HunieCam build"):
            mod.add_attempt(ledger, session(75), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(75, "bbb"))

    def test_locked_ledger_requires_run_record(self):
        ledger, _ = mod.add_attempt(None, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(30))
        with self.assertRaisesRegex(ValueError, "run record is required"):
            mod.add_attempt(ledger, session(40), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="")

    def test_run_record_stage_must_match_session(self):
        with self.assertRaisesRegex(ValueError, "deepest stage"):
            mod.add_attempt(None, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(65))

    def test_regression_warns_against_promotion(self):
        ledger, _ = mod.add_attempt(None, session(65), {"status": "PASS", "experiment": "clean baseline"}, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(65))
        ledger, summary = mod.add_attempt(ledger, session(45, ("unity_crash",)), {"status": "PASS", "experiment": "native D3D9 frontend A/B"}, launch_mode="direct", resolution="1280x720", fps=60, config="d3d9 = native", arguments="", run_record=run_record(45))
        self.assertEqual(summary["attempt"]["movement"], "REGRESSED_VS_BEST")
        self.assertTrue(summary["warnings"])

    def test_duplicate_diagnostic_profile_is_flagged(self):
        ledger, _ = mod.add_attempt(None, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(30))
        _, summary = mod.add_attempt(ledger, session(30), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", run_record=run_record(30))
        self.assertTrue(summary["attempt"]["duplicate_profile_before"])
        self.assertTrue(summary["warnings"])

    def test_repeatability_duplicate_is_not_warned_as_waste(self):
        ledger, _ = mod.add_attempt(None, session(75), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", purpose="acceptance", run_record=run_record(75))
        _, summary = mod.add_attempt(ledger, session(75), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="", purpose="repeatability", run_record=run_record(75))
        self.assertFalse(any("already tried" in w for w in summary["warnings"]))

    def test_legacy_unsealed_attempt_still_loads_but_warns(self):
        legacy = {"schema": "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V1", "title": "HunieCam Studio", "steam_app_id": 426000, "attempts": [], "best_stage": 0, "best_attempt": None}
        ledger, summary = mod.add_attempt(legacy, session(20), None, launch_mode="direct", resolution="1280x720", fps=60, config="", arguments="")
        self.assertEqual(ledger["schema"], "MADEIRA_HUNIECAM_ATTEMPT_LEDGER_V2")
        self.assertTrue(any("unsealed" in w for w in summary["warnings"]))

    def test_guard_failure_blocks_recording(self):
        with self.assertRaises(ValueError):
            mod.add_attempt(None, session(20), {"status": "FAIL"}, launch_mode="direct", resolution="1280x720", fps=60, config="d3d9=native", arguments="-force-d3d9")


if __name__ == "__main__":
    unittest.main()
