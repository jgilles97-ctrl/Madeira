from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PARSE = load_module("sims4_launcher_canary_parse", "tools/sims4_launcher_canary_parse.py")

PASS_ALL = """\
CANARY x64-process              PASS C:\\canary.exe
CANARY child-process            PASS exit=42 expected=42
CANARY service-control-manager  PASS open
CANARY ea-background-service    PASS query=ok state=4 state_name=RUNNING pid=100 exit=0 service_exit=0
CANARY sensapi                  PASS alive=1 flags=0x1
CANARY network-list-manager     PASS hr=0x00000000 internet=1 connectivity=0x240
CANARY tcp-1.1.1.1-443          PASS connect=ok wsa=0
CANARY winhttp-https            PASS http=200 error=0
CANARY SUMMARY failures=0
"""


class LauncherCanaryParseTests(unittest.TestCase):
    def test_all_pass_advances_only_to_ea_app(self):
        report = PARSE.parse(PASS_ALL)
        self.assertEqual(report["next_gate"], "LAUNCH_EA_APP_IN_WINE_DESKTOP")
        self.assertEqual(report["failed_checks"], [])
        self.assertEqual(report["missing_checks"], [])
        self.assertTrue(report["summary_consistent"])
        self.assertEqual(report["physical_device_success"], "UNPROVEN")

    def test_stopped_ea_service_routes_to_ini_capture_without_treating_query_as_failure(self):
        text = PASS_ALL.replace(
            "state=4 state_name=RUNNING pid=100",
            "state=1 state_name=STOPPED pid=0",
        ).replace(
            "CANARY sensapi",
            "CANARY ea-service-stale-check OBSERVE query=ok state=1 state_name=STOPPED pid=0\nCANARY sensapi",
        )
        report = PARSE.parse(text)
        self.assertEqual(report["failed_checks"], [])
        self.assertTrue(report["ea_service_stopped_observed"])
        self.assertEqual(report["next_gate"], "CAPTURE_AND_INSPECT_EA_BACKGROUNDSERVICE_INI")

    def test_earliest_failed_prerequisite_wins(self):
        text = PASS_ALL.replace("CANARY child-process            PASS", "CANARY child-process            FAIL")
        text = text.replace("CANARY winhttp-https            PASS", "CANARY winhttp-https            FAIL")
        text = text.replace("failures=0", "failures=2")
        report = PARSE.parse(text)
        self.assertEqual(report["failed_checks"], ["child-process", "winhttp-https"])
        self.assertEqual(report["next_gate"], "FIX_PSEUDO_PROCESS_HANDOFF")
        self.assertTrue(report["summary_consistent"])

    def test_missing_output_is_not_silently_passed(self):
        report = PARSE.parse("CANARY x64-process PASS ok\nCANARY SUMMARY failures=0\n")
        self.assertIn("winhttp-https", report["missing_checks"])
        self.assertEqual(report["next_gate"], "REPEAT_LAUNCHER_CANARY_WITH_COMPLETE_OUTPUT")

    def test_summary_mismatch_is_detected(self):
        report = PARSE.parse(PASS_ALL.replace("failures=0", "failures=1"))
        self.assertFalse(report["summary_consistent"])
        self.assertEqual(report["next_gate"], "RECONCILE_CANARY_SUMMARY_WITH_CHECK_LINES")

    def test_678_canary_decision_passes(self):
        variants = (
            (PASS_ALL, "LAUNCH_EA_APP_IN_WINE_DESKTOP"),
            (PASS_ALL.replace("CANARY x64-process              PASS", "CANARY x64-process              FAIL").replace("failures=0", "failures=1"), "FIX_X64_FEX_RUNTIME"),
            (PASS_ALL.replace("CANARY child-process            PASS", "CANARY child-process            FAIL").replace("failures=0", "failures=1"), "FIX_PSEUDO_PROCESS_HANDOFF"),
            (PASS_ALL.replace("CANARY sensapi                  PASS", "CANARY sensapi                  FAIL").replace("failures=0", "failures=1"), "FIX_WINDOWS_NETWORK_STATE_APIS"),
            (PASS_ALL.replace("CANARY tcp-1.1.1.1-443          PASS", "CANARY tcp-1.1.1.1-443          FAIL").replace("failures=0", "failures=1"), "FIX_IPAD_GUEST_NETWORK_ROUTE"),
            (PASS_ALL.replace("CANARY winhttp-https            PASS", "CANARY winhttp-https            FAIL").replace("failures=0", "failures=1"), "FIX_WINHTTP_HTTPS_PATH"),
        )
        for iteration in range(678):
            text, expected = variants[iteration % len(variants)]
            report = PARSE.parse(f"run={iteration}\n{text}")
            self.assertEqual(report["next_gate"], expected, f"iteration {iteration}")
            self.assertEqual(report["physical_device_success"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
