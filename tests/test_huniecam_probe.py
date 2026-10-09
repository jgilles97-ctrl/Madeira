import importlib.util
import pathlib
import struct
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_probe", ROOT / "tools" / "huniecam_probe.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_probe"] = mod
SPEC.loader.exec_module(mod)


def write_fake_pe(path: pathlib.Path, machine: int = 0x014C):
    data = bytearray(512)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    path.write_bytes(data)


def make_known_shape(root: pathlib.Path):
    exe = root / "HunieCamStudio.exe"
    write_fake_pe(exe)
    (root / "steam_api.dll").write_bytes(b"root steam")
    data = root / "HunieCamStudio_Data"
    (data / "Managed").mkdir(parents=True)
    (data / "Mono").mkdir()
    (data / "Plugins").mkdir()
    (data / "Managed" / "Assembly-CSharp.dll").write_bytes(b"managed")
    (data / "Managed" / "Assembly-CSharp-firstpass.dll").write_bytes(b"firstpass")
    (data / "Mono" / "mono.dll").write_bytes(b"mono")
    (data / "Plugins" / "steam_api.dll").write_bytes(b"plugin steam")
    (data / "Plugins" / "CSteamworks.dll").write_bytes(b"csteam")
    (data / "globalgamemanagers").write_bytes(b"Unity 5.3.4f1\x00")
    (data / "resources.assets.resS").write_bytes(b"assets")
    return data


class HunieCamProbeTests(unittest.TestCase):
    def test_known_i386_unity_mono_steam_shape_is_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_known_shape(root)
            report = mod.probe_install(root)
            self.assertTrue(report["exe_found"])
            self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_PROBE_V2")
            self.assertEqual(report["identity"]["pe"]["architecture"], "i386")
            self.assertTrue(report["runtime_signals"]["bundled_unity_mono_found"])
            self.assertFalse(report["runtime_signals"]["wine_mono_required_for_game_runtime"])
            self.assertTrue(report["runtime_signals"]["plugin_steam_api_found"])
            self.assertTrue(report["runtime_signals"]["root_steam_api_found"])
            self.assertIn("5.3.4f1", report["runtime_signals"]["unity_versions_seen"])
            self.assertTrue(report["depot_shape"]["looks_like_known_windows_depot"])
            self.assertEqual(report["depot_shape"]["matched"], report["depot_shape"]["total"])
            self.assertEqual(report["route"]["cpu"], "Madeira WoW64 + FEX x86")
            self.assertEqual(report["route"]["runtime"], "game-bundled Unity Mono")
            self.assertEqual(report["route"]["graphics_baseline"], "DXMT Direct3D 9 emulated frontend")
            self.assertIn("program folder", report["route"]["working_directory"])
            self.assertFalse(report["route"]["streaming"])
            changes = {x["change"] for x in report["conditional_experiments"]}
            self.assertIn("per-game config: env.MADEIRA_WOW_RWX_PLAIN = 1", changes)
            self.assertIn("launch argument: -force-d3d9", changes)

    def test_existing_unity_output_log_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            data = make_known_shape(root)
            log = data / "output_log.txt"
            log.write_text("Initialize engine version: 5.3.4f1\n")
            report = mod.probe_install(root)
            self.assertTrue(report["runtime_signals"]["unity_output_log_found"])
            self.assertEqual(pathlib.Path(report["runtime_signals"]["unity_output_log"]), log)

    def test_missing_executable_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = mod.probe_install(pathlib.Path(tmp))
            self.assertFalse(report["exe_found"])
            self.assertTrue(report["warnings"])
            self.assertTrue(report["next_actions"])

    def test_x64_is_reported_without_pretending_i386(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            write_fake_pe(root / "HunieCamStudio.exe", 0x8664)
            report = mod.probe_install(root)
            self.assertEqual(report["identity"]["pe"]["architecture"], "x86_64")
            self.assertFalse(report["identity"]["pe"]["is_32bit_x86"])
            self.assertEqual(report["route"]["cpu"], "verify from PE result")
            self.assertTrue(any("Unexpected" in w for w in report["warnings"]))

    def test_public_reference_never_overrides_actual_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_known_shape(root)
            (root / "HunieCamStudio_Data" / "globalgamemanagers").write_bytes(b"Unity 5.6.7f1\x00")
            report = mod.probe_install(root)
            self.assertIn("5.6.7f1", report["runtime_signals"]["unity_versions_seen"])
            self.assertTrue(any("public metadata" in w for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
