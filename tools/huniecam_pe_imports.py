#!/usr/bin/env python3
"""Read the Windows PE import table for HunieCamStudio.exe without modification.

This avoids guessing which Windows APIs/runtimes the owned executable actually
requests. The parser reports imported DLL names only; it does not load DLLs,
download redistributables, inspect function bodies, or alter the game/prefix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_PE_IMPORTS_V1"


def _u16(data: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(data):
        raise ValueError("PE field is outside file bounds")
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        raise ValueError("PE field is outside file bounds")
    return struct.unpack_from("<I", data, off)[0]


def _c_string(data: bytes, off: int, limit: int = 512) -> str:
    if off < 0 or off >= len(data):
        raise ValueError("PE string is outside file bounds")
    end = data.find(b"\x00", off, min(len(data), off + limit))
    if end < 0:
        raise ValueError("PE import name is not NUL-terminated within limit")
    return data[off:end].decode("ascii", errors="replace")


def _rva_to_offset(rva: int, sections: list[dict[str, int]]) -> int:
    for sec in sections:
        va = sec["virtual_address"]
        span = max(sec["virtual_size"], sec["raw_size"])
        if va <= rva < va + span:
            delta = rva - va
            if delta >= sec["raw_size"]:
                raise ValueError("RVA points into zero-fill portion of section")
            return sec["raw_pointer"] + delta
    raise ValueError(f"RVA 0x{rva:x} is not mapped by any PE section")


def classify(dlls: list[str]) -> dict[str, list[str]]:
    out = {
        "steam": [],
        "graphics": [],
        "input": [],
        "audio": [],
        "visual_c_runtime": [],
        "dotnet_or_mono_host": [],
        "network": [],
        "system": [],
        "other": [],
    }
    for original in dlls:
        name = original.lower()
        if name in {"steam_api.dll", "steam_api64.dll"} or "steam" in name:
            bucket = "steam"
        elif name.startswith(("d3d", "dxgi", "ddraw", "opengl", "vulkan")):
            bucket = "graphics"
        elif name.startswith(("xinput", "dinput", "hid", "winmm")):
            bucket = "input"
        elif name.startswith(("dsound", "xaudio", "x3daudio", "openal", "fmod")):
            bucket = "audio"
        elif name.startswith(("msvcr", "msvcp", "vcruntime", "ucrtbase")):
            bucket = "visual_c_runtime"
        elif name.startswith(("mscoree", "mono")):
            bucket = "dotnet_or_mono_host"
        elif name.startswith(("winhttp", "wininet", "ws2_32", "iphlpapi", "dnsapi")):
            bucket = "network"
        elif name.startswith(("kernel32", "user32", "gdi32", "advapi32", "shell32", "ole32", "oleaut32", "comdlg32", "shlwapi", "ntdll")):
            bucket = "system"
        else:
            bucket = "other"
        out[bucket].append(original)
    return {k: sorted(v, key=str.casefold) for k, v in out.items() if v}


def parse(path: pathlib.Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    dlls: list[str] = []
    machine = optional_magic = None
    data = b""
    try:
        data = path.read_bytes()
        if len(data) < 0x40 or data[:2] != b"MZ":
            raise ValueError("Not an MZ/PE executable")
        pe = _u32(data, 0x3C)
        if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\x00\x00":
            raise ValueError("PE signature not found")
        machine = _u16(data, pe + 4)
        section_count = _u16(data, pe + 6)
        optional_size = _u16(data, pe + 20)
        optional = pe + 24
        if optional + optional_size > len(data):
            raise ValueError("Optional header extends past file")
        optional_magic = _u16(data, optional)
        if optional_magic == 0x10B:
            data_dir_base = optional + 96
        elif optional_magic == 0x20B:
            data_dir_base = optional + 112
        else:
            raise ValueError(f"Unsupported PE optional-header magic 0x{optional_magic:x}")
        if data_dir_base + 16 > optional + optional_size:
            raise ValueError("PE optional header has no complete import data directory")
        import_rva = _u32(data, data_dir_base + 8)
        import_size = _u32(data, data_dir_base + 12)

        section_table = optional + optional_size
        sections: list[dict[str, int]] = []
        for index in range(section_count):
            off = section_table + index * 40
            if off + 40 > len(data):
                raise ValueError("Section table extends past file")
            sections.append({
                "virtual_size": _u32(data, off + 8),
                "virtual_address": _u32(data, off + 12),
                "raw_size": _u32(data, off + 16),
                "raw_pointer": _u32(data, off + 20),
            })

        if import_rva:
            desc = _rva_to_offset(import_rva, sections)
            max_descriptors = max(1, min(4096, import_size // 20 + 1 if import_size else 4096))
            for _ in range(max_descriptors):
                if desc + 20 > len(data):
                    raise ValueError("Import descriptor extends past file")
                fields = struct.unpack_from("<IIIII", data, desc)
                if fields == (0, 0, 0, 0, 0):
                    break
                name_rva = fields[3]
                name_off = _rva_to_offset(name_rva, sections)
                name = _c_string(data, name_off).strip()
                if name:
                    dlls.append(name)
                desc += 20
            else:
                warnings.append("Import descriptor scan hit its safety limit before a zero terminator.")
    except (OSError, ValueError, struct.error) as exc:
        errors.append(str(exc))

    dedup: dict[str, str] = {}
    for name in dlls:
        dedup.setdefault(name.casefold(), name)
    normalized = sorted(dedup.values(), key=str.casefold)
    sha = hashlib.sha256(data).hexdigest() if data else None
    arch = {0x14C: "i386", 0x8664: "x86_64", 0xAA64: "arm64"}.get(machine, f"machine_0x{machine:x}" if machine is not None else None)
    return {
        "schema": SCHEMA,
        "source_label": path.name,
        "exists": path.is_file(),
        "file_sha256": sha,
        "machine": machine,
        "architecture": arch,
        "optional_header_magic": optional_magic,
        "import_count": len(normalized),
        "imports": normalized,
        "categories": classify(normalized),
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
        "rule": "Use the owned EXE's import list to identify exact prerequisites. Do not install random redistributables or native DLL overrides merely because a different Unity/Wine game needed them.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Audit HunieCamStudio.exe imported DLL dependencies")
    p.add_argument("exe", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = parse(args.exe)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
