#!/usr/bin/env python3
"""Static preflight for The Sims 4 on Madeira/iPad.

This tool does not launch Wine or the game. It inspects the staged Windows game
folder and, optionally, an EA App Wine prefix so device tests start from a known
payload instead of guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
from dataclasses import dataclass, asdict
from typing import Iterable

SCHEMA = "SIMS4_IPAD_PREFLIGHT_V2"
PE_X64 = 0x8664
PE_X86 = 0x014C

DLC_PREFIXES = ("EP", "GP", "SP", "FP")
EA_COMPONENTS = (
    ("EADesktop.exe", ("Program Files/Electronic Arts/EA Desktop/EA Desktop/EADesktop.exe",)),
    ("EALauncher.exe", ("Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe",)),
    ("EABackgroundService.exe", (
        "Program Files/Electronic Arts/EA Desktop/EA Desktop/EABackgroundService.exe",
        "Program Files/Electronic Arts/EA Desktop/EABackgroundService.exe",
    )),
    ("EACefSubProcess.exe", (
        "Program Files/Electronic Arts/EA Desktop/EA Desktop/EACefSubProcess.exe",
        "Program Files/Electronic Arts/EA Desktop/EACefSubProcess.exe",
    )),
)


@dataclass(frozen=True)
class PEInfo:
    path: str
    machine: int | None
    machine_name: str
    is_pe: bool
    size: int
    sha256: str


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_pe(path: pathlib.Path) -> PEInfo:
    size = path.stat().st_size
    machine: int | None = None
    is_pe = False
    try:
        with path.open("rb") as fh:
            if fh.read(2) != b"MZ":
                raise ValueError("missing MZ")
            fh.seek(0x3C)
            raw = fh.read(4)
            if len(raw) != 4:
                raise ValueError("short DOS header")
            pe_off = struct.unpack("<I", raw)[0]
            fh.seek(pe_off)
            if fh.read(4) != b"PE\0\0":
                raise ValueError("missing PE signature")
            raw = fh.read(2)
            if len(raw) != 2:
                raise ValueError("short COFF header")
            machine = struct.unpack("<H", raw)[0]
            is_pe = True
    except (OSError, ValueError, struct.error):
        pass
    names = {PE_X64: "x86-64", PE_X86: "x86"}
    return PEInfo(
        path=str(path),
        machine=machine,
        machine_name=names.get(machine, f"0x{machine:04x}" if machine is not None else "unknown"),
        is_pe=is_pe,
        size=size,
        sha256=sha256_file(path),
    )


def find_ts4_exe(root: pathlib.Path) -> pathlib.Path | None:
    candidates = (
        root / "Game" / "Bin" / "TS4_x64.exe",
        root / "The Sims 4" / "Game" / "Bin" / "TS4_x64.exe",
        root / "TS4_x64.exe",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def inventory_dlc(root: pathlib.Path) -> list[str]:
    out: list[str] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return out
    for child in children:
        name = child.name.upper()
        if not child.is_dir():
            continue
        if len(name) >= 4 and name[:2] in DLC_PREFIXES and name[2:].isdigit():
            out.append(name)
    return sorted(out)


def folder_size(root: pathlib.Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            try:
                total += (pathlib.Path(dirpath) / name).stat().st_size
            except OSError:
                pass
    return total


def locate_ea_component(drive_c: pathlib.Path, rels: Iterable[str]) -> pathlib.Path | None:
    for rel in rels:
        path = drive_c.joinpath(*rel.split("/"))
        if path.is_file():
            return path
    return None


def inspect_ea_prefix(prefix: pathlib.Path | None) -> dict[str, object]:
    if prefix is None:
        return {
            "provided": False,
            "drive_c": None,
            "components": {},
            "component_count": 0,
            "launcher_static_ready": False,
        }
    drive_c = prefix / "drive_c" if (prefix / "drive_c").is_dir() else prefix
    components: dict[str, object] = {}
    count = 0
    for label, rels in EA_COMPONENTS:
        found = locate_ea_component(drive_c, rels)
        if found:
            info = read_pe(found)
            components[label] = asdict(info)
            count += 1
        else:
            components[label] = None
    return {
        "provided": True,
        "drive_c": str(drive_c),
        "components": components,
        "component_count": count,
        "launcher_static_ready": count == len(EA_COMPONENTS),
    }


def preflight(root: pathlib.Path, ea_prefix: pathlib.Path | None = None, size_scan: bool = False) -> dict[str, object]:
    root = root.resolve()
    exe = find_ts4_exe(root)
    dlc = inventory_dlc(root)
    game_info = asdict(read_pe(exe)) if exe else None

    payload_ready = bool(
        exe
        and game_info
        and game_info["is_pe"]
        and game_info["machine"] == PE_X64
        and (root / "Data").is_dir()
    )

    checks = {
        "root_exists": root.is_dir(),
        "ts4_x64_found": exe is not None,
        "ts4_x64_is_x86_64_pe": bool(game_info and game_info["is_pe"] and game_info["machine"] == PE_X64),
        "data_folder_present": (root / "Data").is_dir(),
        "game_bin_present": (root / "Game" / "Bin").is_dir(),
    }

    result: dict[str, object] = {
        "schema": SCHEMA,
        "game_root": str(root),
        "checks": checks,
        "payload_ready": payload_ready,
        "game_executable": game_info,
        "dlc_count": len(dlc),
        "dlc": dlc,
        "ea_prefix": inspect_ea_prefix(ea_prefix.resolve() if ea_prefix else None),
        "device_claim": "UNPROVEN",
        "next_gate": (
            "EA_APP_DEVICE_QUALIFICATION"
            if payload_ready and ea_prefix
            else "STAGE_GAME_AND_OPTIONAL_EA_PREFIX"
        ),
        "notes": [
            "Static readiness only; this does not prove Madeira, EA App, or The Sims 4 runs on iPad.",
            "Keep the first device experiment single-variable: qualify the EA launcher path separately from TS4 rendering.",
        ],
    }
    if size_scan:
        result["install_size_bytes"] = folder_size(root)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Static Sims 4/Madeira iPad preflight")
    ap.add_argument("game_root", type=pathlib.Path, help="The Sims 4 install root")
    ap.add_argument("--ea-prefix", type=pathlib.Path, help="Wine prefix or drive_c containing EA App")
    ap.add_argument("--size", action="store_true", help="Measure the entire game folder (slower)")
    ap.add_argument("--json", dest="json_path", type=pathlib.Path, help="Write JSON report")
    args = ap.parse_args()

    report = preflight(args.game_root, args.ea_prefix, args.size)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["payload_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
