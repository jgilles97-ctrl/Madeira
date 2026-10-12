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
                "schema": "SIMS4_MADEIRA_RUNTIME_AUDIT_V2",
                "runtime_fingerprint_sha256": "runtimehash",
                "validated_launcher_coverage_present": 4,
                "validated_launcher_coverage_total": 4,
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

    def canary_fixture(self, *, failed=None, missing=None, next_gate="LAUNCH_EA_APP_IN_WINE_DESKTOP"):
        return {
            "schema": "SIMS4_LAUNCHER_CANARY_RESULT_V1",
            "failed_checks": failed or [],
            "missing_checks": missing or [],
            "summary_consistent": True,
            "ea_service_stopped_observed": False,
            "dwrite_arial_resolution": {
                "passed": True,
                "arial_found": True,
                "liberation_sans_found": True,
                "tahoma_found": True,
            },
            "next_gate": next_gate,
            "physical_device_success": "UNPROVEN",
        }

    def cef_fixture(self, *, next_gate="CORRELATE_EA_CEF_ROLES_WITH_WINDOW_AND_TS4_START"):
        return {
            "schema": "SIMS4_EA_CEF_ROLES_V1",
            "role_counts": {"gpu-process": 1, "renderer": 1, "utility": 1},
            "utility_sub_type_counts": {"network.mojom.networkservice": 1},
            "fatal_by_role": {},
            "role_coverage": {
                "gpu_process_seen": True,
                "renderer_seen": True,
                "network_service_seen": True,
            },
            "next_gate": next_gate,
            "physical_device_success": "UNPROVEN",
        }

    def test_bundle_preserves_identity_and_never_claims_device_success(self):
        preflight, runtime, triage = self.fixtures()
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-001")
        self.assertEqual(result["schema"], "SIMS4_IPAD_EVIDENCE_V2")
        self.assertTrue(result["input_schema_ok"])
        self.assertEqual(result["game_executable_sha256"], "gamehash")
        self.assertEqual(result["runtime_fingerprint_sha256"], "runtimehash")
        self.assertEqual(result["runtime_validated_launcher_coverage_present"], 4)
        self.assertEqual(result["runtime_validated_launcher_coverage_total"], 4)
        self.assertFalse(result["ea_prefix_included"])
        self.assertFalse(result["launcher_canary_included"])
        self.assertFalse(result["cef_roles_included"])
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

    def test_launcher_canary_and_cef_evidence_are_bound(self):
        preflight, runtime, triage = self.fixtures()
        canary = self.canary_fixture()
        cef = self.cef_fixture()
        result = BUNDLE.make_bundle(
            preflight, runtime, triage,
            run_id="ipad-ea-003",
            launcher_canary=canary,
            cef_roles=cef,
            input_hashes={"launcher_canary": "canary-file-hash", "cef_roles": "cef-file-hash"},
        )
        self.assertTrue(result["input_schema_ok"])
        self.assertTrue(result["launcher_canary_included"])
        self.assertTrue(result["cef_roles_included"])
        self.assertTrue(result["launcher_canary"]["dwrite_arial_resolution"]["arial_found"])
        self.assertEqual(result["cef_roles"]["role_counts"]["renderer"], 1)
        self.assertEqual(result["input_sha256"]["launcher_canary"], "canary-file-hash")
        self.assertEqual(result["input_sha256"]["cef_roles"], "cef-file-hash")
        self.assertEqual(result["bundle_blockers"], [])

    def test_failed_canary_blocks_and_outranks_later_ea_log(self):
        preflight, runtime, triage = self.fixtures()
        canary = self.canary_fixture(
            failed=["dwrite-arial"],
            next_gate="FIX_EA_CEF_ARIAL_FONT_RESOLUTION",
        )
        triage["next_gate"] = "CAPTURE_GRAPHICS_INITIALIZATION"
        result = BUNDLE.make_bundle(
            preflight, runtime, triage,
            run_id="ipad-ea-004",
            launcher_canary=canary,
        )
        self.assertIn("LAUNCHER_CANARY_HAS_FAILURES", result["bundle_blockers"])
        self.assertEqual(result["next_gate"], "FIX_EA_CEF_ARIAL_FONT_RESOLUTION")

    def test_incomplete_canary_blocks(self):
        preflight, runtime, triage = self.fixtures()
        canary = self.canary_fixture(
            missing=["winhttp-https"],
            next_gate="REPEAT_LAUNCHER_CANARY_WITH_COMPLETE_OUTPUT",
        )
        result = BUNDLE.make_bundle(
            preflight, runtime, triage,
            run_id="ipad-ea-005",
            launcher_canary=canary,
        )
        self.assertIn("LAUNCHER_CANARY_INCOMPLETE", result["bundle_blockers"])
        self.assertEqual(result["next_gate"], "REPEAT_LAUNCHER_CANARY_WITH_COMPLETE_OUTPUT")

    def test_cef_specific_gate_can_drive_next_step_when_no_triage_failure(self):
        preflight, runtime, triage = self.fixtures()
        canary = self.canary_fixture()
        cef = self.cef_fixture(next_gate="ISOLATE_EA_CEF_GPU_PROCESS_FAILURE")
        result = BUNDLE.make_bundle(
            preflight, runtime, triage,
            run_id="ipad-ea-006",
            launcher_canary=canary,
            cef_roles=cef,
        )
        self.assertEqual(result["next_gate"], "ISOLATE_EA_CEF_GPU_PROCESS_FAILURE")

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

    def test_runtime_v1_is_rejected_so_old_audits_cannot_mix_with_v2(self):
        preflight, runtime, triage = self.fixtures()
        runtime["schema"] = "SIMS4_MADEIRA_RUNTIME_AUDIT_V1"
        result = BUNDLE.make_bundle(preflight, runtime, triage, run_id="ipad-old-runtime")
        self.assertIn("INPUT_SCHEMA_MISMATCH", result["bundle_blockers"])

    def test_old_canary_schema_is_rejected(self):
        preflight, runtime, triage = self.fixtures()
        canary = self.canary_fixture()
        canary["schema"] = "OLD_CANARY"
        result = BUNDLE.make_bundle(
            preflight, runtime, triage,
            run_id="ipad-old-canary",
            launcher_canary=canary,
        )
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
