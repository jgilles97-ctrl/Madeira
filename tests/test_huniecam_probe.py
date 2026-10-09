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
    steam = b"same steam api bytes"
    (root / "steam_api.dll").write_bytes(steam)
    data = root / "HunieCamStudio_Data"
    (data / "Managed").mkdir(parents=True)
    (data / "Mono").mkdir()
    (data / "Plugins").mkdir()
    for name, payload in {
        "Assembly-CSharp.dll": b"managed",
        "Assembly-CSharp-firstpass.dll": b"firstpass",
        "mscorlib.dll": b"mscorlib",
        "System.dll": b"system",
        "UnityEngine.dll": b"unityengine",
        "UnityEngine.UI.dll": b"unityui",
    }.items():
        (data / "Managed" / name).write_bytes(payload)
    (data / "Mono" / "mono.dll").write_bytes(b"mono")
    (data / "Plugins" / "steam_api.dll").write_bytes(steam)
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
            self.assertEqual(report["schema"], "MADEIRA_HUNIECAM_PROBE_V4")
            self.assertEqual(report["identity"]["pe"]["architecture"], "i386")
            self.assertTrue(report["runtime_signals"]["bundled_unity_mono_found"])
            self.assertTrue(report["runtime_signals"]["mono_runtime_found"])
            self.assertFalse(report["runtime_signals"]["gameassembly_found"])
            self.assertEqual(report["runtime_signals"]["runtime_family"], "Unity Mono")
            self.assertFalse(report["runtime_signals"]["wine_mono_required_for_game_runtime"])
            self.assertTrue(report["runtime_signals"]["renderer_must_be_observed_from_log"])
            self.assertFalse(report["runtime_signals"]["title_native_fps_cap"])
            self.assertTrue(report["runtime_signals"]["plugin_steam_api_found"])
            self.assertTrue(report["runtime_signals"]["root_steam_api_found"])
            self.assertTrue(report["runtime_signals"]["steam_api_copies_identical"])
            self.assertIn("5.3.4f1", report["runtime_signals"]["unity_versions_seen"])
            self.assertTrue(report["depot_shape"]["looks_like_known_windows_depot"])
            self.assertEqual(report["depot_shape"]["matched"], report["depot_shape"]["total"])
            self.assertEqual(report["route"]["cpu"], "Madeira WoW64 + FEX x86")
            self.assertEqual(report["route"]["runtime"], "game-bundled Unity Mono")
            self.assertIn("no renderer override", report["route"]["graphics_baseline"])
            self.assertEqual(report["route"]["minimum_graphics_reference"], "DirectX 9.0a compatible")
            self.assertEqual(report["route"]["max_builtin_widescreen_resolution_reference"], "1600x900")
            self.assertEqual(report["route"]["fps_baseline"], 60)
            self.assertIn("Software\\HuniePot\\HunieCam Studio", report["route"]["config_registry_path"])
            self.assertEqual(report["route"]["official_steam_windows_launch"]["executable"], "HunieCamStudio.exe")
            self.assertEqual(report["route"]["official_steam_windows_launch"]["arguments"], "")
            self.assertIn("program folder", report["route"]["working_directory"])
            self.assertFalse(report["route"]["streaming"])
            changes = {x["change"] for x in report["conditional_experiments"]}
            self.assertIn("per-game config: env.MADEIRA_WOW_RWX_PLAIN = 1", changes)
            self.assertIn("launch argument: -force-d3d9", changes)
            d3d = next(x for x in report["conditional_experiments"] if x["change"] == "launch argument: -force-d3d9")
            self.assertIn("AND", d3d["when"])

    def test_existing_unity_output_log_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            data = make_known_shape(root)
            log = data / "output_log.txt"
            log.write_text("Initialize engine version: 5.3.4f1\n")
            report = mod.probe_install(root)
            self.assertTrue(report["runtime_signals"]["unity_output_log_found"])
            self.assertEqual(pathlib.Path(report["runtime_signals"]["unity_output_log"]), log)

    def test_different_steam_api_copies_are_reported_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            data = make_known_shape(root)
            (data / "Plugins" / "steam_api.dll").write_bytes(b"different")
            report = mod.probe_install(root)
            self.assertFalse(report["runtime_signals"]["steam_api_copies_identical"])
            self.assertTrue(any("steam_api.dll copies differ" in w for w in report["warnings"]))

    def test_gameassembly_changes_runtime_family_and_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_known_shape(root)
            (root / "GameAssembly.dll").write_bytes(b"unexpected il2cpp")
            report = mod.probe_install(root)
            self.assertTrue(report["runtime_signals"]["gameassembly_found"])
            self.assertEqual(report["runtime_signals"]["runtime_family"], "IL2CPP/unexpected")
            self.assertEqual(report["route"]["runtime"], "verify from install")

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
            self.assertTrue(any("public metadata" in w.lower() for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
