from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


AUDIT = load_module("sims4_runtime_audit", "tools/sims4_runtime_audit.py")
TRIAGE = load_module("sims4_log_triage_stress", "tools/sims4_log_triage.py")


class RuntimeAuditTests(unittest.TestCase):
    def test_fingerprint_is_order_independent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "B.DLL").write_bytes(b"beta")
            (root / "a.dll").write_bytes(b"alpha")
            first = AUDIT.audit(root)["runtime_fingerprint_sha256"]
            for child in root.iterdir():
                child.unlink()
            (root / "a.dll").write_bytes(b"alpha")
            (root / "B.DLL").write_bytes(b"beta")
            second = AUDIT.audit(root)["runtime_fingerprint_sha256"]
            self.assertEqual(first, second)

    def test_fingerprint_changes_when_runtime_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            dll = root / "d3d11.dll"
            dll.write_bytes(b"v1")
            first = AUDIT.audit(root)["runtime_fingerprint_sha256"]
            dll.write_bytes(b"v2")
            second = AUDIT.audit(root)["runtime_fingerprint_sha256"]
            self.assertNotEqual(first, second)

    def test_validated_launcher_coverage_is_inventory_not_ea_requirement(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            report = AUDIT.audit(root)
            self.assertEqual(report["schema"], "SIMS4_MADEIRA_RUNTIME_AUDIT_V2")
            self.assertTrue(report["runtime_exists"])
            self.assertEqual(report["validated_launcher_coverage_present"], 0)
            self.assertEqual(report["validated_launcher_coverage_total"], 4)
            for item in report["validated_launcher_coverage_modules"].values():
                self.assertEqual(item["status"], "not_bundled")
                self.assertEqual(item["evidence_class"], "physically_validated_madeira_launcher_coverage")
                self.assertEqual(item["ea_requirement"], "UNPROVEN")
            self.assertEqual(report["device_claim"], "UNPROVEN")

    def test_validated_coverage_counter_tracks_bundled_modules(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "netprofm.dll").write_bytes(b"netprofm")
            (root / "sensapi.dll").write_bytes(b"sensapi")
            report = AUDIT.audit(root)
            self.assertEqual(report["validated_launcher_coverage_present"], 2)
            self.assertEqual(report["validated_launcher_coverage_modules"]["netprofm.dll"]["status"], "bundled")
            self.assertEqual(report["validated_launcher_coverage_modules"]["sensapi.dll"]["status"], "bundled")


class ConvergenceStressTests(unittest.TestCase):
    """678 deterministic diagnostic passes; these are NOT 678 physical iPad runs."""

    CASES = (
        ("err:module:import_dll Library NETPROFM.dll not found\n", "FIX_MISSING_DLL"),
        ("EACefSubProcess.exe GPU process failed\n", "FIX_EA_CEF_FAILURE"),
        ("out of memory while allocating guest arena\n", "FIX_MEMORY_FAILURE"),
        ("dxmt d3d11 initialization failed\n", "FIX_DXMT_FAILURE"),
        ('[win-name] #4 text="The Sims 4"\n', "MEASURE_FIRST_FRAME_AND_MENU"),
        ("TS4_x64.exe launched\n", "CAPTURE_GRAPHICS_INITIALIZATION"),
        ("EA App started with no decisive signal\n", "CAPTURE_EA_APP_TO_TS4_PROCESS_START"),
    )

    def test_678_convergence_passes(self):
        counts: dict[str, int] = {}
        for iteration in range(678):
            text, expected_gate = self.CASES[iteration % len(self.CASES)]
            report = TRIAGE.classify(f"iteration={iteration}\n{text}")
            self.assertEqual(report["schema"], "SIMS4_MADEIRA_TRIAGE_V1")
            self.assertEqual(report["next_gate"], expected_gate, f"iteration {iteration}")
            self.assertEqual(report["success_claim"], "UNPROVEN")
            counts[expected_gate] = counts.get(expected_gate, 0) + 1
        self.assertEqual(sum(counts.values()), 678)
        self.assertEqual(len(counts), len(self.CASES))


if __name__ == "__main__":
    unittest.main()
