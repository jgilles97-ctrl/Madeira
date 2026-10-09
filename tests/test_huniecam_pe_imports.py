import importlib.util
import pathlib
import struct
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huniecam_pe_imports", ROOT / "tools" / "huniecam_pe_imports.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["huniecam_pe_imports"] = mod
SPEC.loader.exec_module(mod)


def write_pe(path: pathlib.Path, dlls=("KERNEL32.dll", "d3d9.dll", "steam_api.dll", "msvcr100.dll")):
    data = bytearray(0x800)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    pe = 0x80
    data[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<H", data, pe + 4, 0x14C)
    struct.pack_into("<H", data, pe + 6, 1)
    struct.pack_into("<H", data, pe + 20, 0xE0)
    opt = pe + 24
    struct.pack_into("<H", data, opt, 0x10B)
    # Import directory = data directory index 1.
    struct.pack_into("<II", data, opt + 96 + 8, 0x1000, (len(dlls) + 1) * 20)
    sec = opt + 0xE0
    data[sec:sec + 8] = b".rdata\0\0"
    struct.pack_into("<I", data, sec + 8, 0x500)
    struct.pack_into("<I", data, sec + 12, 0x1000)
    struct.pack_into("<I", data, sec + 16, 0x500)
    struct.pack_into("<I", data, sec + 20, 0x200)
    name_rva = 0x1100
    for i, name in enumerate(dlls):
        desc = 0x200 + i * 20
        struct.pack_into("<IIIII", data, desc, 0, 0, 0, name_rva, 0)
        name_off = 0x200 + (name_rva - 0x1000)
        encoded = name.encode("ascii") + b"\0"
        data[name_off:name_off + len(encoded)] = encoded
        name_rva += 0x30
    path.write_bytes(data)


class HunieCamPEImportsTests(unittest.TestCase):
    def test_parses_and_classifies_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "HunieCamStudio.exe"
            write_pe(exe)
            report = mod.parse(exe)
            self.assertTrue(report["valid"])
            self.assertEqual(report["architecture"], "i386")
            self.assertIn("d3d9.dll", report["imports"])
            self.assertIn("d3d9.dll", report["categories"]["graphics"])
            self.assertIn("steam_api.dll", report["categories"]["steam"])
            self.assertIn("msvcr100.dll", report["categories"]["visual_c_runtime"])
            self.assertIn("KERNEL32.dll", report["categories"]["system"])

    def test_deduplicates_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "x.exe"
            write_pe(exe, ("USER32.dll", "user32.DLL"))
            report = mod.parse(exe)
            self.assertEqual(report["import_count"], 1)

    def test_invalid_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "x.exe"
            exe.write_bytes(b"not a pe")
            report = mod.parse(exe)
            self.assertFalse(report["valid"])
            self.assertTrue(report["errors"])

    def test_missing_import_directory_is_valid_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "x.exe"
            write_pe(exe, ())
            report = mod.parse(exe)
            self.assertTrue(report["valid"])
            self.assertEqual(report["imports"], [])

    def test_network_and_audio_categories_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "x.exe"
            write_pe(exe, ("WINHTTP.dll", "dsound.dll", "XINPUT1_3.dll"))
            report = mod.parse(exe)
            self.assertIn("WINHTTP.dll", report["categories"]["network"])
            self.assertIn("dsound.dll", report["categories"]["audio"])
            self.assertIn("XINPUT1_3.dll", report["categories"]["input"])


if __name__ == "__main__":
    unittest.main()
