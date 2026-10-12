from __future__ import annotations

import importlib.util
import pathlib
import struct
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PREFLIGHT = load_module("sims4_preflight", "tools/sims4_ipad_preflight.py")
TRIAGE = load_module("sims4_triage", "tools/sims4_log_triage.py")


def write_fake_pe(path: pathlib.Path, machine: int) -> None:
    data = bytearray(512)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class PreflightTests(unittest.TestCase):
    def test_good_payload_is_ready_and_counts_dlc(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            write_fake_pe(root / "Game/Bin/TS4_x64.exe", 0x8664)
            (root / "Data").mkdir()
            (root / "EP01").mkdir()
            (root / "GP11").mkdir()
            (root / "SP84").mkdir()
            report = PREFLIGHT.preflight(root)
            self.assertTrue(report["payload_ready"])
            self.assertEqual(report["dlc_count"], 3)
            self.assertEqual(report["game_executable"]["machine_name"], "x86-64")
            self.assertEqual(report["device_claim"], "UNPROVEN")

    def test_x86_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            write_fake_pe(root / "Game/Bin/TS4_x64.exe", 0x014C)
            (root / "Data").mkdir()
            report = PREFLIGHT.preflight(root)
            self.assertFalse(report["payload_ready"])
            self.assertFalse(report["checks"]["ts4_x64_is_x86_64_pe"])

    def test_ea_prefix_components_are_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "game"
            root.mkdir()
            write_fake_pe(root / "Game/Bin/TS4_x64.exe", 0x8664)
            (root / "Data").mkdir()
            prefix = pathlib.Path(td) / "prefix"
            base = prefix / "drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop"
            for name in ("EADesktop.exe", "EALauncher.exe", "EABackgroundService.exe", "EACefSubProcess.exe"):
                write_fake_pe(base / name, 0x8664)
            report = PREFLIGHT.preflight(root, prefix)
            self.assertTrue(report["ea_prefix"]["launcher_static_ready"])
            self.assertEqual(report["ea_prefix"]["component_count"], 4)


class TriageTests(unittest.TestCase):
    def test_missing_dll_wins_first_failure(self):
        report = TRIAGE.classify(
            "err:module:import_dll Library NETPROFM.dll not found\n"
            "TS4_x64.exe\n"
            "0xc0000005 later\n"
        )
        self.assertEqual(report["findings"][0]["code"], "missing_dll")
        self.assertEqual(report["next_gate"], "FIX_MISSING_DLL")

    def test_ea_cef_is_separate_from_ts4(self):
        report = TRIAGE.classify("EACefSubProcess.exe GPU process failed\n")
        codes = {x["code"] for x in report["findings"]}
        self.assertIn("ea_cef_failure", codes)

    def test_window_signal_advances_gate_without_claiming_success(self):
        report = TRIAGE.classify('[win-name] #4 text="The Sims 4"\n')
        self.assertEqual(report["next_gate"], "MEASURE_FIRST_FRAME_AND_MENU")
        self.assertEqual(report["success_claim"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
