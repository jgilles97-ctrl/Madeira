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

    def test_bundle_preserves_identity_and_never_claims_device_success(self):
        preflight, runtime, triage = self.fixtures()
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-001")
        self.assertTrue(result["input_schema_ok"])
        self.assertEqual(result["game_executable_sha256"], "gamehash")
        self.assertEqual(result["runtime_fingerprint_sha256"], "runtimehash")
        self.assertEqual(result["next_gate"], "CAPTURE_EA_APP_TO_TS4_PROCESS_START")
        self.assertEqual(result["physical_device_success"], "UNPROVEN")
        self.assertEqual(result["bundle_blockers"], [])

    def test_schema_mismatch_is_blocking(self):
        preflight, runtime, triage = self.fixtures()
        triage["schema"] = "OLD_TRIAGE"
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-002")
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
