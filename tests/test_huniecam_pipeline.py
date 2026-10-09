import importlib.util
import json
import pathlib
import struct
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("huniecam_pipeline", TOOLS / "huniecam_pipeline.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_pipeline"] = mod
SPEC.loader.exec_module(mod)


def fake_pe(path):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x014C)
    path.write_bytes(data)


def make_install(root):
    fake_pe(root / "HunieCamStudio.exe")
    steam = b"steam"
    (root / "steam_api.dll").write_bytes(steam)
    data = root / "HunieCamStudio_Data"
    (data / "Managed").mkdir(parents=True)
    (data / "Mono").mkdir()
    (data / "Plugins").mkdir()
    for name in ("Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll", "mscorlib.dll", "System.dll", "UnityEngine.dll", "UnityEngine.UI.dll"):
        (data / "Managed" / name).write_bytes(name.encode())
    (data / "Mono" / "mono.dll").write_bytes(b"mono")
    (data / "Plugins" / "steam_api.dll").write_bytes(steam)
    (data / "Plugins" / "CSteamworks.dll").write_bytes(b"c")
    (data / "globalgamemanagers").write_bytes(b"Unity 5.3.4f1")
    (data / "resources.assets.resS").write_bytes(b"assets")
    return data


class HunieCamPipelineTests(unittest.TestCase):
    def test_pipeline_writes_structured_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            install = base / "game"
            install.mkdir()
            data = make_install(install)
            madeira = base / "madeira-log.txt"
            madeira.write_text("\n".join([
                "[WineProc] Target exe: HunieCamStudio.exe",
                "fps=60", "fps=59", "fps=61",
                "[device-load] thermal=nominal low-power=0 capture=0",
            ]))
            unity = data / "output_log.txt"
            unity.write_text("\n".join([
                "Initialize engine version: 5.3.4f1",
                "GfxDevice: creating device client; threaded=1",
                "Version: Direct3D 9.0c",
                "Begin MonoManager ReloadAssembly",
                "Loading HunieCamStudio_Data/Managed/Assembly-CSharp.dll into Unity Child Domain",
                "UnloadTime: 1 ms",
            ]))
            out = base / "evidence"
            summary = mod.run(install, madeira, unity, out)
            self.assertEqual(summary["schema"], "MADEIRA_HUNIECAM_PIPELINE_V2")
            self.assertEqual(summary["guard_status"], "PASS")
            self.assertTrue(summary["evidence_contract_valid"])
            self.assertTrue(summary["run_record_ready"])
            self.assertTrue(summary["fps_cap_effective"])
            self.assertTrue(summary["performance_comparison_clean"])
            self.assertTrue(summary["owned_build_fingerprint"])
            self.assertGreaterEqual(summary["deepest_stage"], 75)
            self.assertEqual(summary["next_run_status"], "RUN_ACCEPTANCE_BASELINE")
            for name in (
                "huniecam-preflight.json", "huniecam-session.json", "huniecam-issues.json",
                "huniecam-performance.json", "huniecam-run-record.json",
                "huniecam-evidence-contract.json", "huniecam-next-run.json",
                "huniecam-evidence-manifest.json", "huniecam-pipeline-summary.json",
            ):
                self.assertTrue((out / name).is_file(), name)
            manifest = json.loads((out / "huniecam-evidence-manifest.json").read_text())
            self.assertTrue(manifest["minimum_review_bundle_complete"])

    def test_pipeline_surfaces_guard_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            install = base / "game"
            install.mkdir()
            make_install(install)
            madeira = base / "madeira-log.txt"
            madeira.write_text("[WineProc] Target exe: HunieCamStudio.exe\n")
            out = base / "evidence"
            summary = mod.run(install, madeira, None, out, config_text="d3d9 = native", arguments="-force-d3d9")
            self.assertEqual(summary["guard_status"], "FAIL")
            self.assertFalse(summary["evidence_contract_valid"])

    def test_pipeline_flags_ineffective_60fps_cap_without_faking_failure_of_core_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            install = base / "game"
            install.mkdir()
            make_install(install)
            madeira = base / "madeira-log.txt"
            madeira.write_text("fps=90\nfps=92\nfps=91\n[device-load] thermal=nominal low-power=0 capture=0\n")
            out = base / "evidence"
            summary = mod.run(install, madeira, None, out)
            self.assertFalse(summary["fps_cap_effective"])
            self.assertFalse(summary["performance_comparison_clean"])
            self.assertTrue(summary["evidence_contract_valid"])


if __name__ == "__main__":
    unittest.main()
