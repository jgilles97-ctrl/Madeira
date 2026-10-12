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


BUNDLE = load_module("sims4_evidence_bundle", "tools/sims4_evidence_bundle.py")


class EvidenceBundleTests(unittest.TestCase):
    def fixtures(self):
        return (
            {
                "schema": "SIMS4_IPAD_PREFLIGHT_V2",
                "payload_ready": True,
                "dlc_count": 3,
                "game_executable": {"sha256": "gamehash"},
                "next_gate": "EA_APP_DEVICE_QUALIFICATION",
            },
            {
                "schema": "SIMS4_MADEIRA_RUNTIME_AUDIT_V1",
                "runtime_fingerprint_sha256": "runtimehash",
                "next_gate": "CAPTURE_EXACT_RUNTIME_FINGERPRINT_WITH_FIRST_EA_APP_DEVICE_LOG",
            },
            {
                "schema": "SIMS4_MADEIRA_TRIAGE_V1",
                "findings": [],
                "positive_signals": [],
                "next_gate": "CAPTURE_EA_APP_TO_TS4_PROCESS_START",
                "success_claim": "UNPROVEN",
            },
        )

    def ea_fixture(self, *, ready=True):
        return {
            "schema": "SIMS4_EA_PREFIX_AUDIT_V1",
            "static_ready": ready,
            "next_gate": "RUN_SIM4_LAUNCHER_CANARY_ON_IPAD" if ready else "FIX_EA_PREFIX_STATIC_BLOCKERS",
            "components": {
                "EADesktop.exe": {"sha256": "ea-desktop-hash"},
                "EALauncher.exe": {"sha256": "ea-launcher-hash"},
                "EABackgroundService.exe": {"sha256": "ea-service-hash"},
                "EACefSubProcess.exe": {"sha256": "ea-cef-hash"},
            },
            "backgroundservice_ini": {"sha256": "ea-ini-hash"},
        }

    def test_bundle_preserves_identity_and_never_claims_device_success(self):
        preflight, runtime, triage = self.fixtures()
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-001")
        self.assertTrue(result["input_schema_ok"])
        self.assertEqual(result["game_executable_sha256"], "gamehash")
        self.assertEqual(result["runtime_fingerprint_sha256"], "runtimehash")
        self.assertFalse(result["ea_prefix_included"])
        self.assertEqual(result["next_gate"], "CAPTURE_EA_APP_TO_TS4_PROCESS_START")
        self.assertEqual(result["physical_device_success"], "UNPROVEN")
        self.assertEqual(result["bundle_blockers"], [])

    def test_optional_ea_prefix_identity_is_bound_into_bundle(self):
        preflight, runtime, triage = self.fixtures()
        ea = self.ea_fixture()
        result = BUNDLE.make_bundle(
            preflight, runtime, triage,
            run_id="ipad-ea-001", ea_prefix=ea,
            input_hashes={"ea_prefix_audit": "audit-file-hash"},
        )
        self.assertTrue(result["input_schema_ok"])
        self.assertTrue(result["ea_prefix_included"])
        self.assertTrue(result["ea_prefix_static_ready"])
        self.assertEqual(result["ea_component_sha256"]["EADesktop.exe"], "ea-desktop-hash")
        self.assertEqual(result["ea_backgroundservice_ini_sha256"], "ea-ini-hash")
        self.assertEqual(result["input_sha256"]["ea_prefix_audit"], "audit-file-hash")
        self.assertEqual(result["physical_device_success"], "UNPROVEN")

    def test_unready_ea_prefix_blocks_and_outranks_stale_device_log_gate(self):
        preflight, runtime, triage = self.fixtures()
        ea = self.ea_fixture(ready=False)
        triage["next_gate"] = "MEASURE_FIRST_FRAME_AND_MENU"
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-ea-002", ea_prefix=ea)
        self.assertIn("EA_PREFIX_STATIC_NOT_READY", result["bundle_blockers"])
        self.assertEqual(result["next_gate"], "FIX_EA_PREFIX_STATIC_BLOCKERS")
        self.assertEqual(result["physical_device_success"], "UNPROVEN")

    def test_schema_mismatch_is_blocking(self):
        preflight, runtime, triage = self.fixtures()
        triage["schema"] = "OLD_TRIAGE"
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-002")
        self.assertIn("INPUT_SCHEMA_MISMATCH", result["bundle_blockers"])

    def test_ea_schema_mismatch_is_blocking(self):
        preflight, runtime, triage = self.fixtures()
        ea = self.ea_fixture()
        ea["schema"] = "OLD_EA_AUDIT"
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-002b", ea_prefix=ea)
        self.assertIn("INPUT_SCHEMA_MISMATCH", result["bundle_blockers"])

    def test_missing_static_readiness_is_blocking(self):
        preflight, runtime, triage = self.fixtures()
        preflight["payload_ready"] = False
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-003")
        self.assertIn("STATIC_PAYLOAD_NOT_READY", result["bundle_blockers"])

    def test_unsupported_success_claim_is_blocking(self):
        preflight, runtime, triage = self.fixtures()
        triage["success_claim"] = "GAMEPLAY_CONFIRMED"
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-004")
        self.assertIn("TRIAGE_MADE_UNSUPPORTED_SUCCESS_CLAIM", result["bundle_blockers"])
        self.assertEqual(result["physical_device_success"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
