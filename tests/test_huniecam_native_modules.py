import importlib.util
import pathlib
import struct
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"; sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("huniecam_native_modules", TOOLS / "huniecam_native_modules.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC); sys.modules["huniecam_native_modules"] = mod; SPEC.loader.exec_module(mod)


def write_pe(path: pathlib.Path, dlls=()):
    data = bytearray(0x800); data[:2] = b"MZ"; struct.pack_into("<I", data, 0x3C, 0x80); pe = 0x80; data[pe:pe+4] = b"PE\0\0"; struct.pack_into("<H", data, pe+4, 0x14C); struct.pack_into("<H", data, pe+6, 1); struct.pack_into("<H", data, pe+20, 0xE0); opt = pe+24; struct.pack_into("<H", data, opt, 0x10B); struct.pack_into("<II", data, opt+104, 0x1000 if dlls else 0, (len(dlls)+1)*20 if dlls else 0); sec = opt+0xE0; data[sec:sec+8] = b".rdata\0\0"; struct.pack_into("<I", data, sec+8, 0x500); struct.pack_into("<I", data, sec+12, 0x1000); struct.pack_into("<I", data, sec+16, 0x500); struct.pack_into("<I", data, sec+20, 0x200); rva=0x1100
    for i,name in enumerate(dlls):
        struct.pack_into("<IIIII", data, 0x200+i*20,0,0,0,rva,0); off=0x200+(rva-0x1000); enc=name.encode()+b"\0"; data[off:off+len(enc)]=enc; rva+=0x30
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)


class HunieCamNativeModulesTests(unittest.TestCase):
    def test_scans_exe_root_dll_and_plugins_but_not_managed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/"game"; root.mkdir(); write_pe(root/"HunieCamStudio.exe", ("KERNEL32.dll",)); write_pe(root/"steam_api.dll", ("WS2_32.dll",)); write_pe(root/"HunieCamStudio_Data"/"Plugins"/"CSteamworks.dll", ("steam_api.dll",)); managed=root/"HunieCamStudio_Data"/"Managed"/"Assembly-CSharp.dll"; managed.parent.mkdir(parents=True); managed.write_bytes(b"managed-not-pe")
            report=mod.scan(root); self.assertTrue(report["valid"]); self.assertEqual(report["module_count"],3); paths={x["relative_path"] for x in report["modules"]}; self.assertNotIn("HunieCamStudio_Data/Managed/Assembly-CSharp.dll",paths); self.assertIn("HunieCamStudio_Data/Plugins/CSteamworks.dll",paths)
    def test_requester_map_identifies_indirect_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); write_pe(root/"HunieCamStudio.exe",()); write_pe(root/"plugin.dll",("XINPUT1_3.dll",)); report=mod.scan(root); self.assertIn("xinput1_3.dll",report["dependency_requesters"]); self.assertEqual(report["dependency_requesters"]["xinput1_3.dll"],["plugin.dll"])
    def test_missing_exe_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=mod.scan(pathlib.Path(tmp)); self.assertFalse(report["valid"]); self.assertTrue(report["errors"])
    def test_absolute_paths_not_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/"game"; root.mkdir(); write_pe(root/"HunieCamStudio.exe"); report=mod.scan(root); self.assertNotIn(str(root.parent),str(report)); self.assertFalse(report["privacy"]["absolute_paths_embedded"])


if __name__ == "__main__": unittest.main()
