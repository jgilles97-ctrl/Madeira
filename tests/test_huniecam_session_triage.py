import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_session_triage", ROOT / "tools" / "huniecam_session_triage.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_session_triage"] = mod
SPEC.loader.exec_module(mod)


class HunieCamSessionTriageTests(unittest.TestCase):
    def test_clean_unity53_d3d9_start_reaches_acceptance(self):
        madeira = "[WineProc] Target exe: C:\\Games\\HunieCam Studio\\HunieCamStudio.exe\n"
        unity = "\n".join([
            "Initialize engine version: 5.3.4f1 (fdbb5133b820)",
            "GfxDevice: creating device client; threaded=1",
            "Version: Direct3D 9.0c [driver]",
            "Begin MonoManager ReloadAssembly",
            "Loading C:\\Game\\HunieCamStudio_Data\\Managed\\Assembly-CSharp.dll into Unity Child Domain",
            "FMOD initialized on device",
            "UnloadTime: 0.234 ms",
        ])
        report = mod.analyze(madeira, unity)
        self.assertGreaterEqual(report["deepest_stage"], 75)
        self.assertEqual(report["next"]["priority"], "device acceptance")

    def test_clean_d3d11_selection_does_not_force_d3d9(self):
        unity = "\n".join([
            "Initialize engine version: 5.3.4f1",
            "GfxDevice: creating device client; threaded=1",
            "Version: Direct3D 11.0 [level 11.0]",
        ])
        report = mod.analyze("", unity)
        self.assertEqual(report["next"]["priority"], "continue clean D3D11 baseline")
        self.assertEqual(report["next"]["experiment"]["arguments"], "")

    def test_d3d11_plus_graphics_crash_recommends_force_d3d9(self):
        unity = "Initialize engine version: 5.3.4f1\nGfxDevice: creating device client; threaded=1\nVersion: Direct3D 11.0\nCrash!!!\n"
        report = mod.analyze("", unity)
        self.assertEqual(report["next"]["priority"], "renderer A/B after D3D11 failure")
        self.assertEqual(report["next"]["experiment"]["arguments"], "-force-d3d9")

    def test_store_undecoded_with_unity_mono_recommends_rwx_ab(self):
        madeira = "[WineProc] Target exe: HunieCamStudio.exe\nHunieCamStudio_Data\\Mono\\mono.dll loaded\n[store-undecoded] #1 insn=0xa9882149\n"
        report = mod.analyze(madeira, "Begin MonoManager ReloadAssembly")
        self.assertEqual(report["next"]["priority"], "Unity Mono protected-memory writes")
        self.assertIn("MADEIRA_WOW_RWX_PLAIN = 1", report["next"]["experiment"]["config"])

    def test_store_undecoded_without_mono_does_not_recommend_rwx(self):
        report = mod.analyze("[store-undecoded] #1 insn=0xa9882149\n", "")
        self.assertEqual(report["next"]["priority"], "unclassified Madeira store/runtime blocker")
        self.assertEqual(report["next"]["experiment"]["config"], "")

    def test_guest_breakpoint_label_does_not_recommend_rwx(self):
        madeira = "[wr-strip-declined] view protect=0x180002d { SEC_IMAGE WRITECOPY }\n[store-undecoded] #1 insn=0xd4200000\n"
        report = mod.analyze(madeira, "Begin MonoManager ReloadAssembly")
        self.assertEqual(report["next"]["priority"], "WoW64 breakpoint / self-modifying image runtime bug")
        self.assertEqual(report["next"]["upstream_reference"], "willfaust/Madeira#173")

    def test_mono_suspend_hybrid_abort_recommends_removing_override(self):
        report = mod.analyze("Cannot transition thread 0x123 from STATE_BLOCKING with DO_BLOCKING\n", "Begin MonoManager ReloadAssembly")
        self.assertEqual(report["next"]["priority"], "remove incompatible Mono suspend override")
        self.assertEqual(report["next"]["upstream_reference"], "willfaust/Madeira#123")

    def test_jit_failure_wins_over_later_crash(self):
        madeira = "[jit-debugger] attached=0 at the pool request\nc0000005\n[store-undecoded] #1\n"
        self.assertEqual(mod.analyze(madeira, "")["next"]["priority"], "runtime prerequisite")

    def test_missing_dll_wins_before_graphics(self):
        madeira = '0024:err:module:import_dll Library foo.dll (needed by L"HunieCamStudio.exe") not found\nc0000005\n'
        self.assertEqual(mod.analyze(madeira, "")["next"]["priority"], "Windows dependency")

    def test_graphics_init_failure_without_selected_api_recommends_force(self):
        unity = "Initialize engine version: 5.3.4f1\nGfxDevice: creating device client; threaded=1\nFailed to initialize graphics\n"
        report = mod.analyze("", unity)
        self.assertEqual(report["next"]["priority"], "graphics API selection")
        self.assertEqual(report["next"]["experiment"]["arguments"], "-force-d3d9")

    def test_crash_after_proven_d3d9_recommends_native_frontend_ab(self):
        madeira = "d3d9-emulated.dll load\nc0000005\n"
        unity = "Initialize engine version: 5.3.4f1\nGfxDevice: creating device client; threaded=1\nVersion: Direct3D 9.0c\nCrash!!!\n"
        report = mod.analyze(madeira, unity)
        self.assertEqual(report["next"]["priority"], "D3D9 implementation A/B")
        self.assertEqual(report["next"]["experiment"]["config"], "d3d9 = native")

    def test_steam_failure_is_separate_lane(self):
        report = mod.analyze("", "Initialize engine version: 5.3.4f1\nSteamAPI_Init failed\n")
        self.assertEqual(report["next"]["priority"], "Steam integration")

    def test_pointer_markers_are_evidence_not_acceptance(self):
        report = mod.analyze("[hwinput] mouse path=GCMouse absolute=1\n[winios] cursor set hotspot=1,2\n", "")
        codes = {m["code"] for m in report["markers"]}
        self.assertIn("hardware_pointer", codes)
        self.assertIn("windows_cursor", codes)
        self.assertNotEqual(report["next"]["priority"], "device acceptance")


if __name__ == "__main__":
    unittest.main()
