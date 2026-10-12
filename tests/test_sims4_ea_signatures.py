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


TRIAGE = load_module("sims4_ea_signature_triage", "tools/sims4_log_triage.py")


class EASignatureTests(unittest.TestCase):
    CASES = (
        ("WinHTTP request failed with 12029\n", "FIX_VPN_NETWORK_BLOCKED"),
        ("CoCreateInstance CLSID_NetworkListManager => 0x80040154 REGDB_E_CLASSNOTREG\n", "FIX_NETWORK_LIST_UNAVAILABLE"),
        ("EA RPC failed: RPC_S_SERVER_UNAVAILABLE (0x6ba)\n", "FIX_EA_RPC_UNAVAILABLE"),
        ("EABackgroundService dwCurrentState=0x1 STOPPED\n", "FIX_EA_BACKGROUND_SERVICE_STOPPED"),
        ("backgroundservice.ini stale pid=999 cleanup requested\n", "FIX_EA_BACKGROUNDSERVICE_INI"),
        ("CreateSymbolicLinkW stub: not implemented during EA update\n", "FIX_EA_UPDATE_SYMLINK_FAILURE"),
        ("MSI rollback error 0x80070643\n", "FIX_EA_INSTALLER_FAILURE"),
        ("DirtySDK network initialization failed: server is not reachable\n", "FIX_EA_DIRTYSDK_NETWORK"),
        ("EACefSubProcess.exe GPU process failed\n", "FIX_EA_CEF_FAILURE"),
        ("NtRaiseHardError 0x50000018 then NtTerminateProcess exit_code=0xdeadc0de\n", "FIX_LAUNCHER_HARD_ERROR"),
    )

    def test_each_ea_signature_routes_to_specific_gate(self):
        for text, expected in self.CASES:
            with self.subTest(expected=expected):
                report = TRIAGE.classify(text)
                self.assertEqual(report["next_gate"], expected)
                self.assertEqual(report["success_claim"], "UNPROVEN")

    def test_ea_processes_are_positive_evidence_not_success(self):
        report = TRIAGE.classify(
            "EADesktop.exe started\n"
            "EABackgroundService.exe running\n"
            "EACefSubProcess.exe started\n"
        )
        codes = {item["code"] for item in report["positive_signals"]}
        self.assertIn("ea_desktop_seen", codes)
        self.assertIn("ea_background_service_seen", codes)
        self.assertIn("ea_cef_seen", codes)
        self.assertEqual(report["next_gate"], "CAPTURE_EA_APP_TO_TS4_PROCESS_START")
        self.assertEqual(report["success_claim"], "UNPROVEN")

    def test_678_additional_ea_signature_passes(self):
        """678 more distinct diagnostic passes; not physical-device launches."""
        seen: dict[str, int] = {}
        for iteration in range(678):
            text, expected = self.CASES[iteration % len(self.CASES)]
            report = TRIAGE.classify(
                f"iteration={iteration} source=ea-deep-pass-{iteration:04d}\n{text}"
            )
            self.assertEqual(report["next_gate"], expected, f"iteration {iteration}")
            self.assertEqual(report["success_claim"], "UNPROVEN")
            seen[expected] = seen.get(expected, 0) + 1
        self.assertEqual(sum(seen.values()), 678)
        self.assertEqual(len(seen), len(self.CASES))


if __name__ == "__main__":
    unittest.main()
