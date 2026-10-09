#!/usr/bin/env python3
"""Read-only preflight for a legitimately owned HunieCam Studio Windows install.

The probe never modifies game files. It inventories the minimum signals needed
to choose a Madeira launch route, hashes a few identity files, and emits JSON
that can be attached to a reproducible compatibility report without bundling
proprietary game content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import struct
from typing import Iterable

SCHEMA = "MADEIRA_HUNIECAM_PROBE_V1"
TITLE = "HunieCam Studio"
EXPECTED_EXE = "HunieCamStudio.exe"
KNOWN_STEAM_APP_ID = 426000
UNITY_VERSION_RE = re.compile(rb"(?<![0-9A-Za-z])([0-9]{1,4}\.[0-9]+\.[0-9]+[a-z][0-9]+)(?![0-9A-Za-z])")


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pe_machine(path: pathlib.Path) -> dict[str, object]:
    try:
        with path.open("rb") as f:
            dos = f.read(64)
            if len(dos) < 64 or dos[:2] != b"MZ":
                return {"valid_pe": False, "error": "missing MZ header"}
            e_lfanew = struct.unpack_from("<I", dos, 0x3C)[0]
            if e_lfanew > 64 * 1024 * 1024:
                return {"valid_pe": False, "error": "unreasonable PE header offset"}
            f.seek(e_lfanew)
            header = f.read(6)
            if len(header) < 6 or header[:4] != b"PE\0\0":
                return {"valid_pe": False, "error": "missing PE signature"}
            machine = struct.unpack_from("<H", header, 4)[0]
    except OSError as exc:
        return {"valid_pe": False, "error": str(exc)}

    names = {
        0x014C: "i386",
        0x8664: "x86_64",
        0xAA64: "arm64",
        0xA641: "arm64ec",
    }
    return {
        "valid_pe": True,
        "machine": f"0x{machine:04x}",
        "architecture": names.get(machine, "unknown"),
        "is_32bit_x86": machine == 0x014C,
    }


def _casefold_index(root: pathlib.Path) -> dict[str, pathlib.Path]:
    out: dict[str, pathlib.Path] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            try:
                key = p.relative_to(root).as_posix().casefold()
            except ValueError:
                continue
            out.setdefault(key, p)
    return out


def _first_existing(index: dict[str, pathlib.Path], candidates: Iterable[str]) -> pathlib.Path | None:
    for candidate in candidates:
        p = index.get(candidate.casefold())
        if p is not None:
            return p
    return None


def scan_unity_versions(paths: Iterable[pathlib.Path], max_bytes_each: int = 8 * 1024 * 1024) -> list[str]:
    found: set[str] = set()
    for path in paths:
        try:
            with path.open("rb") as f:
                data = f.read(max_bytes_each)
        except OSError:
            continue
        for match in UNITY_VERSION_RE.finditer(data):
            try:
                found.add(match.group(1).decode("ascii"))
            except UnicodeDecodeError:
                pass
    return sorted(found)


def find_install_root(source: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path | None]:
    source = source.expanduser().resolve()
    if source.is_file():
        return source.parent, source
    if source.is_dir():
        exact = source / EXPECTED_EXE
        if exact.is_file():
            return source, exact
        for child in source.iterdir():
            if child.is_file() and child.name.casefold() == EXPECTED_EXE.casefold():
                return source, child
    return source, None


def probe_install(source: pathlib.Path) -> dict[str, object]:
    root, exe = find_install_root(source)
    report: dict[str, object] = {
        "schema": SCHEMA,
        "title": TITLE,
        "steam_app_id": KNOWN_STEAM_APP_ID,
        "source": str(root),
        "read_only": True,
        "exe_found": exe is not None,
        "expected_exe": EXPECTED_EXE,
        "findings": [],
        "warnings": [],
        "identity": {},
        "runtime_signals": {},
        "route": {},
        "next_actions": [],
    }

    findings: list[str] = report["findings"]  # type: ignore[assignment]
    warnings: list[str] = report["warnings"]  # type: ignore[assignment]
    next_actions: list[str] = report["next_actions"]  # type: ignore[assignment]

    if exe is None:
        warnings.append(f"{EXPECTED_EXE} was not found at the supplied path.")
        next_actions.append("Point this probe at the Windows install folder containing HunieCamStudio.exe.")
        return report

    pe = parse_pe_machine(exe)
    identity: dict[str, object] = report["identity"]  # type: ignore[assignment]
    identity["exe"] = exe.name
    identity["exe_bytes"] = exe.stat().st_size
    identity["exe_sha256"] = sha256_file(exe)
    identity["pe"] = pe

    data_dir = root / "HunieCamStudio_Data"
    if not data_dir.is_dir():
        for child in root.iterdir():
            if child.is_dir() and child.name.casefold() == "huniecamstudio_data":
                data_dir = child
                break

    scan_root = data_dir if data_dir.is_dir() else root
    index = _casefold_index(scan_root)

    managed = _first_existing(index, ["Managed/Assembly-CSharp.dll", "managed/assembly-csharp.dll"])
    mono = _first_existing(index, ["Mono/mono.dll", "mono/mono.dll"])
    steam_api = _first_existing(index, ["Plugins/steam_api.dll", "plugins/steam_api.dll"])
    csteamworks = _first_existing(index, ["Plugins/CSteamworks.dll", "plugins/csteamworks.dll"])
    global_manager = _first_existing(index, ["globalgamemanagers"])
    unity_scan_paths = [p for p in (global_manager, exe) if p is not None]
    unity_versions = scan_unity_versions(unity_scan_paths)

    signals: dict[str, object] = report["runtime_signals"]  # type: ignore[assignment]
    signals.update(
        {
            "data_dir_found": data_dir.is_dir(),
            "managed_assembly_found": managed is not None,
            "mono_runtime_found": mono is not None,
            "steam_api_found": steam_api is not None,
            "csteamworks_found": csteamworks is not None,
            "unity_versions_seen": unity_versions,
            "known_title_renderer": "Direct3D 9",
        }
    )

    if managed:
        identity["assembly_csharp_sha256"] = sha256_file(managed)
    if mono:
        identity["mono_sha256"] = sha256_file(mono)

    arch = pe.get("architecture") if isinstance(pe, dict) else None
    is_i386 = bool(isinstance(pe, dict) and pe.get("is_32bit_x86"))
    if is_i386:
        findings.append("The Windows executable is 32-bit x86, so Madeira's WoW64/i386 route is the correct CPU path.")
    elif arch:
        warnings.append(f"Unexpected Windows executable architecture: {arch}; re-check the owned build before tuning Madeira.")

    if mono and managed:
        findings.append("Unity/Mono runtime signals are present; Mono/JIT compatibility must be validated from the current Madeira log.")
    else:
        warnings.append("Expected Unity/Mono files were not both found; the install may be incomplete or laid out differently.")

    if steam_api or csteamworks:
        findings.append("Steamworks files are present. Test direct game launch first, then Steam/Dock only if licensing or API behavior requires it.")

    if unity_versions:
        findings.append("Unity version string(s) were found in the owned files: " + ", ".join(unity_versions))

    route: dict[str, object] = report["route"]  # type: ignore[assignment]
    route.update(
        {
            "cpu": "Madeira WoW64 + FEX x86" if is_i386 else "verify from PE result",
            "graphics_baseline": "DXMT Direct3D 9 emulated frontend",
            "graphics_ab_test": "d3d9 = native only after a clean baseline",
            "input_baseline": "direct pointer/tap + keyboard/mouse; do not require XInput",
            "streaming": False,
            "native_recompile": False,
        }
    )

    next_actions.extend(
        [
            "Use a current-upstream Madeira build and confirm JIT + Memory+ are ready before launch.",
            "Create an isolated HunieCam library entry that points at HunieCamStudio.exe; leave the original game copy untouched.",
            "First launch with default D3D9 routing and no speculative compatibility switches.",
            "Export madeira-log.txt immediately after the first launch and run tools/madeira_log_triage.py on it.",
            "If graphics fail but CPU/Mono startup succeeds, A/B only the per-game `d3d9 = native` setting.",
            "Verify pointer/tap accuracy, sound, pause/menu behavior, save creation, save persistence after relaunch, and a sustained play session.",
        ]
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only HunieCam Studio preflight for Madeira")
    parser.add_argument("source", type=pathlib.Path, help="Windows install folder or HunieCamStudio.exe")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path, help="Write the report to a JSON file")
    args = parser.parse_args()

    report = probe_install(args.source)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("exe_found") and report.get("identity", {}).get("pe", {}).get("valid_pe") else 2


if __name__ == "__main__":
    raise SystemExit(main())
