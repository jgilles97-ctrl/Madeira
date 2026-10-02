#!/usr/bin/env python3
"""Host checks for tools/house-party/fingerprint.py."""
import importlib.util
import json
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("hp_fingerprint", ROOT / "tools/house-party/fingerprint.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def make_pe(path: Path, machine=0x8664, imports=("d3d11.dll", "steam_api64.dll", "xinput1_4.dll")):
    peoff = 0x80
    data = bytearray(0x1000)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, peoff)
    data[peoff:peoff + 4] = b"PE\0\0"
    fh = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, 0xF0, 0x22)
    data[peoff + 4:peoff + 24] = fh
    opt = bytearray(0xF0)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<II", opt, 112 + 8, 0x1000, 20 * (len(imports) + 1))
    data[peoff + 24:peoff + 24 + len(opt)] = opt
    sh = bytearray(40)
    sh[:6] = b".idata"
    struct.pack_into("<IIII", sh, 8, 0x1000, 0x1000, 0x800, 0x200)
    data[peoff + 24 + 0xF0:peoff + 24 + 0xF0 + 40] = sh
    names = 0x200 + 20 * (len(imports) + 1)
    for i, name in enumerate(imports):
        rva = 0x1000 + (names - 0x200)
        struct.pack_into("<IIIII", data, 0x200 + i * 20, 0, 0, 0, rva, 0)
        raw = name.encode() + b"\0"
        data[names:names + len(raw)] = raw
        names += len(raw)
    path.write_bytes(data)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "House Party"
    root.mkdir()
    make_pe(root / "HouseParty.exe")
    (root / "UnityPlayer.dll").write_bytes(b"x 2021.3.33f1 x")
    (root / "GameAssembly.dll").write_bytes(b"il2cpp")
    metadata = root / "HouseParty_Data/il2cpp_data/Metadata"
    metadata.mkdir(parents=True)
    (metadata / "global-metadata.dat").write_bytes(struct.pack("<II", 0xFAB11BAF, 29) + b"metadata")
    (root / "HouseParty_Data/boot.config").write_text("gfx-enable-gfx-jobs=1\nwait-for-native-debugger=0\n")
    (root / "HouseParty_Data/ScriptingAssemblies.json").write_text(json.dumps({
        "names": ["Assembly-CSharp.dll", "UnityEngine.CoreModule.dll", "UnityEngine.VideoModule.dll"]
    }))
    plugins = root / "HouseParty_Data/Plugins/x86_64"
    plugins.mkdir(parents=True)
    make_pe(plugins / "sample.dll", imports=("user32.dll",))
    (root / "steam_api64.dll").write_bytes(b"steam")

    before = {p.relative_to(root): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    out = root.parent / "manifest.json"
    assert MOD.main([str(root), "-o", str(out)]) == 0
    report = json.loads(out.read_text())
    after = {p.relative_to(root): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}

    assert before == after, "fingerprint modified source files"
    assert report["source_policy"] == "read-only"
    assert report["game"]["architecture"]["value"] == "x86_64"
    assert report["engine"]["family"]["value"] == "Unity"
    assert report["engine"]["unity_version"]["value"] == "2021.3.33f1"
    assert report["engine"]["scripting_backend"]["value"] == "IL2CPP"
    assert report["engine"]["il2cpp_metadata_version"]["value"] == 29
    assert "Assembly-CSharp.dll" in report["engine"]["scripting_assemblies"]
    assert report["engine"]["boot_config"]["values"]["gfx-enable-gfx-jobs"] == "1"
    assert {"api": "Direct3D 11", "evidence": "PE import d3d11.dll"} in report["compatibility"]["graphics_apis"]
    assert "xinput1_4.dll" in report["compatibility"]["input_api_imports"]
    assert report["compatibility"]["unity_video_module"]["value"] is True
    assert report["compatibility"]["launcher_executables"][0]["machine"] == "x86_64"
    plugin = next(x for x in report["compatibility"]["native_plugins"] if x["path"].endswith("sample.dll"))
    assert plugin["machine"] == "x86_64"
    assert "HouseParty.exe" in report["hashes"]["sha256"]
    assert "GameAssembly.dll" in report["hashes"]["sha256"]
    assert "HouseParty_Data/Plugins/x86_64/sample.dll" in report["hashes"]["sha256"]

print("PASS: House Party fingerprint detects x64 Unity IL2CPP/D3D11 evidence and leaves sources untouched")
