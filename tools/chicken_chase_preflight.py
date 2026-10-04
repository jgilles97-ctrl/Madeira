#!/usr/bin/env python3
"""Chicken Chase -> Madeira iPad preflight.

Dependency-free PE inspection for the 2007 Chicken Chase Windows executable.
It does not modify the game, patch registration, or bypass licensing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any

IMAGE_FILE_MACHINE_I386 = 0x014C
PE32_MAGIC = 0x10B
PE32_PLUS_MAGIC = 0x20B
DIR_IMPORT = 1
DIR_COM_DESCRIPTOR = 14
SECTION_EXECUTE = 0x20000000
SECTION_READ = 0x40000000
SECTION_WRITE = 0x80000000

GRAPHICS = {
    "gdi32.dll": "GDI",
    "ddraw.dll": "DirectDraw",
    "d3d8.dll": "Direct3D 8",
    "d3d9.dll": "Direct3D 9",
    "opengl32.dll": "OpenGL",
}
AUDIO = {
    "winmm.dll": "WinMM",
    "dsound.dll": "DirectSound",
    "openal32.dll": "OpenAL",
    "fmod.dll": "FMOD",
    "fmodex.dll": "FMOD Ex",
    "bass.dll": "BASS",
}
INPUT = {
    "user32.dll": "Win32 mouse/window input",
    "dinput.dll": "DirectInput",
    "dinput8.dll": "DirectInput 8",
}
STOREFRONT_TOKENS = ("reflexive", "bigfish", "bfg", "gamehouse", "oberon")

CORE_I386_MODULES = [
    "ntdll.dll",
    "kernel32.dll",
    "kernelbase.dll",
    "user32.dll",
    "gdi32.dll",
    "winmm.dll",
]
OPTIONAL_BY_API = {
    "DirectDraw": ["ddraw.dll"],
    "Direct3D 9": ["d3d9.dll"],
    "DirectInput": ["dinput.dll"],
    "DirectInput 8": ["dinput8.dll"],
    "DirectSound": ["dsound.dll"],
}


class PEError(ValueError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def entropy(blob: bytes) -> float:
    if not blob:
        return 0.0
    counts = Counter(blob)
    n = len(blob)
    return -sum((count / n) * math.log2(count / n) for count in counts.values())


def read_c_string(data: bytes, offset: int, limit: int = 512) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset, min(len(data), offset + limit))
    if end < 0:
        end = min(len(data), offset + limit)
    return data[offset:end].decode("latin1", errors="replace")


def parse_pe(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise PEError("not an MZ/PE executable")

    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off + 24 > len(data) or data[pe_off:pe_off + 4] != b"PE\0\0":
        raise PEError("PE signature not found")

    coff = pe_off + 4
    machine, section_count, timestamp, _, _, opt_size, characteristics = struct.unpack_from(
        "<HHIIIHH", data, coff
    )
    opt = coff + 20
    if opt + opt_size > len(data):
        raise PEError("truncated optional header")

    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == PE32_MAGIC:
        arch = "PE32 x86" if machine == IMAGE_FILE_MACHINE_I386 else "PE32"
        data_dir_base = opt + 96
        number_of_rva_and_sizes = struct.unpack_from("<I", data, opt + 92)[0]
    elif magic == PE32_PLUS_MAGIC:
        arch = "PE32+"
        data_dir_base = opt + 112
        number_of_rva_and_sizes = struct.unpack_from("<I", data, opt + 108)[0]
    else:
        raise PEError("unsupported optional-header magic 0x%04x" % magic)

    sections = []
    section_table = opt + opt_size
    for index in range(section_count):
        off = section_table + index * 40
        if off + 40 > len(data):
            raise PEError("truncated section table")
        raw_name = data[off:off + 8].split(b"\0", 1)[0]
        name = raw_name.decode("latin1", errors="replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, off + 8)
        sec_chars = struct.unpack_from("<I", data, off + 36)[0]
        blob = b""
        if raw_offset < len(data):
            blob = data[raw_offset:min(len(data), raw_offset + raw_size)]
        sections.append({
            "name": name,
            "virtual_size": virtual_size,
            "virtual_address": virtual_address,
            "raw_size": raw_size,
            "raw_offset": raw_offset,
            "characteristics": sec_chars,
            "readable": bool(sec_chars & SECTION_READ),
            "writable": bool(sec_chars & SECTION_WRITE),
            "executable": bool(sec_chars & SECTION_EXECUTE),
            "entropy": round(entropy(blob), 4),
        })

    def directory(index: int) -> tuple[int, int]:
        if index >= min(number_of_rva_and_sizes, 16):
            return 0, 0
        off = data_dir_base + index * 8
        if off + 8 > opt + opt_size:
            return 0, 0
        return struct.unpack_from("<II", data, off)

    def rva_to_offset(rva: int) -> int | None:
        for section in sections:
            start = section["virtual_address"]
            span = max(section["virtual_size"], section["raw_size"])
            if start <= rva < start + span:
                delta = rva - start
                out = section["raw_offset"] + delta
                if 0 <= out < len(data):
                    return out
        if 0 <= rva < section_table:
            return rva
        return None

    imports: list[str] = []
    import_rva, import_size = directory(DIR_IMPORT)
    import_off = rva_to_offset(import_rva) if import_rva else None
    if import_off is not None:
        cursor = import_off
        end = min(len(data), import_off + max(import_size, 20))
        descriptors_seen = 0
        while cursor + 20 <= len(data) and cursor < end + 4096 and descriptors_seen < 256:
            original_first_thunk, _, _, name_rva, first_thunk = struct.unpack_from("<IIIII", data, cursor)
            if not any((original_first_thunk, name_rva, first_thunk)):
                break
            name_off = rva_to_offset(name_rva)
            dll = read_c_string(data, name_off if name_off is not None else -1).strip().lower()
            if dll:
                imports.append(dll)
            cursor += 20
            descriptors_seen += 1

    com_rva, com_size = directory(DIR_COM_DESCRIPTOR)
    managed = bool(com_rva and com_size) or "mscoree.dll" in imports

    return {
        "machine": machine,
        "machine_hex": "0x%04x" % machine,
        "architecture": arch,
        "is_i386": machine == IMAGE_FILE_MACHINE_I386 and magic == PE32_MAGIC,
        "optional_magic": magic,
        "timestamp": timestamp,
        "characteristics": characteristics,
        "managed_dotnet": managed,
        "import_dlls": sorted(set(imports)),
        "sections": sections,
    }


def parse_cenluma_audit(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    pe = raw.get("pefile", {})
    imports = sorted((pe.get("imports") or {}).keys())
    machine = str(pe.get("machine") or "")
    managed = any("mscoree" in dll.lower() for dll in imports)
    return {
        "source_audit": str(path),
        "architecture": machine,
        "is_i386": machine.lower().startswith("x86") and "64" not in machine,
        "managed_dotnet": managed,
        "import_dlls": imports,
        "sections": pe.get("sections") or [],
        "sha256": raw.get("sha256"),
        "size": raw.get("size"),
        "path": raw.get("path"),
    }


def classify_api(imports: list[str]) -> dict[str, Any]:
    dlls = {dll.lower() for dll in imports}
    graphics = [label for dll, label in GRAPHICS.items() if dll in dlls]
    audio = [label for dll, label in AUDIO.items() if dll in dlls]
    input_apis = [label for dll, label in INPUT.items() if dll in dlls]
    storefront = sorted(
        dll for dll in dlls if any(token in dll for token in STOREFRONT_TOKENS)
    )

    renderer = "Unknown"
    renderer_risk = "yellow"
    reason = "No known renderer import detected; inspect dynamic-load strings/runtime logs."
    if "Direct3D 9" in graphics:
        renderer = "Direct3D 9"
        renderer_risk = "green-yellow"
        reason = "Madeira has an explicit i386 D3D9 to DXMT/Metal path."
    elif "DirectDraw" in graphics:
        renderer = "DirectDraw"
        renderer_risk = "yellow-red"
        reason = (
            "Madeira builds Wine's i386 ddraw module, but Chicken Chase DirectDraw "
            "presentation remains an on-device acceptance risk until proven."
        )
    elif "GDI" in graphics:
        renderer = "GDI"
        renderer_risk = "green"
        reason = (
            "Madeira's iOS win32u driver explicitly composites GDI window surfaces; "
            "this is the most favorable old-game path."
        )
    elif "Direct3D 8" in graphics:
        renderer = "Direct3D 8"
        renderer_risk = "yellow-red"
        reason = "No explicit Madeira D3D8 Metal fast path is documented; requires runtime proof."
    elif "OpenGL" in graphics:
        renderer = "OpenGL"
        renderer_risk = "red"
        reason = "OpenGL is not a primary documented Madeira graphics route."

    return {
        "graphics": graphics,
        "audio": audio,
        "input": input_apis,
        "renderer": renderer,
        "renderer_risk": renderer_risk,
        "renderer_reason": reason,
        "storefront_named_imports": storefront,
    }


def section_risks(sections: list[dict[str, Any]]) -> dict[str, Any]:
    wx = []
    high_entropy_exec = []
    for section in sections:
        name = str(section.get("name") or "")
        writable = bool(section.get("writable"))
        executable = bool(section.get("executable"))
        chars = section.get("characteristics")
        if isinstance(chars, str) and chars.startswith("0x"):
            try:
                value = int(chars, 16)
                writable = writable or bool(value & SECTION_WRITE)
                executable = executable or bool(value & SECTION_EXECUTE)
            except ValueError:
                pass
        elif isinstance(chars, int):
            writable = writable or bool(chars & SECTION_WRITE)
            executable = executable or bool(chars & SECTION_EXECUTE)
        ent = float(section.get("entropy") or 0)
        if writable and executable:
            wx.append(name)
        if executable and ent >= 7.2:
            high_entropy_exec.append({"name": name, "entropy": ent})
    return {
        "writable_executable_sections": wx,
        "high_entropy_executable_sections": high_entropy_exec,
        "packed_or_smc_risk": bool(wx or high_entropy_exec),
    }


def check_madeira_farm(repo: Path, api: dict[str, Any]) -> dict[str, Any]:
    farm = repo / "app/Madeira/i386-windows"
    required = list(CORE_I386_MODULES)
    for label in api["graphics"] + api["input"] + api["audio"]:
        required.extend(OPTIONAL_BY_API.get(label, []))
    required = sorted(set(required))

    missing = [name for name in required if not (farm / name).is_file()]
    built_files = []
    if farm.is_dir():
        built_files = sorted(p.name for p in farm.iterdir() if p.is_file())

    return {
        "repo": str(repo),
        "farm": str(farm),
        "farm_exists": farm.is_dir(),
        "farm_file_count": len(built_files),
        "required_modules": required,
        "missing_required_modules": missing,
        "ready_for_i386_launch": not missing,
        "build_command": "build/wine-i386/build.sh",
    }


def recommendation(pe: dict[str, Any], api: dict[str, Any], risks: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    warnings = []

    if not pe.get("is_i386"):
        blockers.append("Recovered Chicken Chase executable is not confirmed PE32 i386.")

    if pe.get("managed_dotnet"):
        warnings.append(
            "Managed/.NET image detected. Some Madeira M4 reports show managed runtimes "
            "requesting anonymous RWX memory; treat this as a device-test risk."
        )

    if risks["packed_or_smc_risk"]:
        warnings.append(
            "Writable+executable/high-entropy executable section detected; an old packer or "
            "self-modifying code can make the FEX/JIT path harder."
        )

    if api["renderer"] == "DirectDraw":
        warnings.append(
            "DirectDraw is the highest-value compatibility experiment: test Madeira's existing "
            "Wine i386 ddraw path before writing any renderer replacement."
        )

    profile: dict[str, Any] = {
        "resolution": "800x600",
        "aspect_scaling": "Fit",
        "touch_mode": "Touch / direct pointer",
        "relative_pointer": False,
        "touch_mapping": "finger position -> guest coordinate -> left click",
        "fps_limit": 60,
        "desktop_mode": False,
        "pointer_autolock": False,
        "initial_engine_overrides": "none",
    }

    if api["renderer"] == "Direct3D 9":
        profile["d3d9"] = "default emulated frontend first; compare native only after baseline evidence"

    return {
        "blockers": blockers,
        "warnings": warnings,
        "profile": profile,
        "first_run_order": [
            "Copy the whole recovered Chicken Chase folder into Madeira/wine/drive_c.",
            "Add chicken_chase.exe to Madeira's Other games library.",
            "Set resolution to 800x600 and Aspect & scaling to Fit.",
            "Set pointer mode to Touch; keep Relative off.",
            "Start with Madeira's default WoW64/runtime settings and no speculative overrides.",
            "Enable JIT before Play and confirm Madeira reports JIT + Memory+ ready.",
            "Reach a real level; verify graphics, audio, tap-to-click, drag, level completion, quit/relaunch save persistence.",
            "Export madeira-log.txt and run tools/madeira_log_triage.py on any failure.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    pe = report["pe"]
    api = report["api"]
    risks = report["risks"]
    farm = report["madeira"]
    rec = report["recommendation"]

    lines = [
        "# Chicken Chase -> Madeira iPad preflight",
        "",
        "## Verdict",
        "",
        "- Architecture: **%s**" % pe.get("architecture", "unknown"),
        "- PE32 i386: **%s**" % ("yes" if pe.get("is_i386") else "no/unconfirmed"),
        "- Managed/.NET: **%s**" % ("yes" if pe.get("managed_dotnet") else "no"),
        "- Renderer: **%s**" % api["renderer"],
        "- Renderer risk: **%s**" % api["renderer_risk"],
        "- Renderer note: %s" % api["renderer_reason"],
        "- Madeira i386 farm ready: **%s**" % ("yes" if farm["ready_for_i386_launch"] else "no"),
        "",
        "## Imports",
        "",
        "- Graphics: %s" % (", ".join(api["graphics"]) or "none detected"),
        "- Audio: %s" % (", ".join(api["audio"]) or "none detected"),
        "- Input: %s" % (", ".join(api["input"]) or "none detected"),
        "- Storefront-named DLL imports: %s" % (", ".join(api["storefront_named_imports"]) or "none"),
        "",
        "## iPad/JIT risk",
        "",
        "- Writable+executable sections: %s" % (", ".join(risks["writable_executable_sections"]) or "none"),
        "- High-entropy executable sections: %s"
        % (
            ", ".join(
                "%s (%.2f)" % (row["name"], row["entropy"])
                for row in risks["high_entropy_executable_sections"]
            )
            or "none"
        ),
        "",
        "## Madeira i386 farm",
        "",
        "- Farm: %s" % farm["farm"],
        "- Files present: %s" % farm["farm_file_count"],
        "- Missing required modules: %s" % (", ".join(farm["missing_required_modules"]) or "none"),
    ]
    if farm["missing_required_modules"]:
        lines += ["", "Build/rebuild command:", "", "    " + farm["build_command"]]

    lines += [
        "",
        "## First iPad profile",
        "",
        "- Resolution: **800x600**",
        "- Aspect & scaling: **Fit**",
        "- Pointer mode: **Touch**",
        "- Relative pointer: **off**",
        "- Desktop mode: **off**",
        "- Pointer auto-lock: **off**",
        "- Engine overrides: **none initially**",
    ]

    if rec["blockers"]:
        lines += ["", "## Blockers", ""]
        lines += ["- " + item for item in rec["blockers"]]
    if rec["warnings"]:
        lines += ["", "## Warnings", ""]
        lines += ["- " + item for item in rec["warnings"]]

    lines += ["", "## Acceptance sequence", ""]
    lines += ["%d. %s" % (i + 1, item) for i, item in enumerate(rec["first_run_order"])]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Chicken Chase EXE or Cenluma audit.json")
    parser.add_argument(
        "--madeira-repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Madeira checkout root",
    )
    parser.add_argument("--json", type=Path, help="Write machine-readable report here")
    parser.add_argument("--markdown", type=Path, help="Write Markdown report here")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    if not source.is_file():
        print("ERROR: input not found:", source)
        return 2

    try:
        if source.suffix.lower() == ".json":
            pe = parse_cenluma_audit(source)
        else:
            pe = parse_pe(source)
            pe["path"] = str(source)
            pe["size"] = source.stat().st_size
            pe["sha256"] = sha256(source)
    except (PEError, json.JSONDecodeError, OSError, KeyError, struct.error) as exc:
        print("ERROR:", exc)
        return 3

    api = classify_api(pe.get("import_dlls") or [])
    risks = section_risks(pe.get("sections") or [])
    madeira = check_madeira_farm(args.madeira_repo.expanduser().resolve(), api)
    rec = recommendation(pe, api, risks)

    report = {
        "source": str(source),
        "pe": pe,
        "api": api,
        "risks": risks,
        "madeira": madeira,
        "recommendation": rec,
    }

    rendered = render_markdown(report)
    print(rendered, end="")

    if args.json:
        target = args.json.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        target = args.markdown.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered)

    if rec["blockers"]:
        return 10
    if not madeira["ready_for_i386_launch"]:
        return 11
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
