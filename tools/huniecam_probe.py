#!/usr/bin/env python3
"""Read-only preflight for a legitimately owned HunieCam Studio Windows install.

The probe never modifies game files. It identifies the actual Windows build,
checks the classic Unity/Mono/Steamworks layout, records hashes, and emits the
smallest sensible Madeira route. Public depot metadata is used only as a shape
check; the owned files remain the authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import struct
from typing import Iterable

SCHEMA = "MADEIRA_HUNIECAM_PROBE_V2"
TITLE = "HunieCam Studio"
EXPECTED_EXE = "HunieCamStudio.exe"
KNOWN_STEAM_APP_ID = 426000
KNOWN_PUBLIC_BUILD_ID = 8271768
KNOWN_WINDOWS_DEPOT_ID = 426001
KNOWN_WINDOWS_DEPOT_MIB = 686.61
KNOWN_UNITY_VERSION = "5.3.4f1"
UNITY_VERSION_RE = re.compile(rb"(?<![0-9A-Za-z])([0-9]{1,4}\.[0-9]+\.[0-9]+[a-z][0-9]+)(?![0-9A-Za-z])")

EXPECTED_LAYOUT = (
    "Managed/Assembly-CSharp.dll",
    "Managed/Assembly-CSharp-firstpass.dll",
    "Mono/mono.dll",
    "Plugins/CSteamworks.dll",
    "Plugins/steam_api.dll",
    "globalgamemanagers",
    "resources.assets.resS",
)


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

    names = {0x014C: "i386", 0x8664: "x86_64", 0xAA64: "arm64", 0xA641: "arm64ec"}
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


def tree_size(root: pathlib.Path) -> tuple[int, int]:
    files = 0
    total = 0
    try:
        iterator = root.rglob("*")
        for p in iterator:
            try:
                if p.is_file():
                    files += 1
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return files, total


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
        "public_reference": {
            "steam_build_id": KNOWN_PUBLIC_BUILD_ID,
            "windows_depot_id": KNOWN_WINDOWS_DEPOT_ID,
            "windows_depot_size_mib": KNOWN_WINDOWS_DEPOT_MIB,
            "unity_version": KNOWN_UNITY_VERSION,
            "note": "Reference only; the owned files are authoritative.",
        },
        "source": str(root),
        "read_only": True,
        "exe_found": exe is not None,
        "expected_exe": EXPECTED_EXE,
        "findings": [],
        "warnings": [],
        "identity": {},
        "runtime_signals": {},
        "depot_shape": {},
        "route": {},
        "conditional_experiments": [],
        "next_actions": [],
    }

    findings: list[str] = report["findings"]  # type: ignore[assignment]
    warnings: list[str] = report["warnings"]  # type: ignore[assignment]
    next_actions: list[str] = report["next_actions"]  # type: ignore[assignment]
    experiments: list[dict[str, str]] = report["conditional_experiments"]  # type: ignore[assignment]

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

    root_index = _casefold_index(root)
    data_index = _casefold_index(data_dir) if data_dir.is_dir() else {}
    managed = _first_existing(data_index, ["Managed/Assembly-CSharp.dll"])
    firstpass = _first_existing(data_index, ["Managed/Assembly-CSharp-firstpass.dll"])
    mono = _first_existing(data_index, ["Mono/mono.dll"])
    plugin_steam_api = _first_existing(data_index, ["Plugins/steam_api.dll"])
    csteamworks = _first_existing(data_index, ["Plugins/CSteamworks.dll"])
    global_manager = _first_existing(data_index, ["globalgamemanagers"])
    top_steam_api = _first_existing(root_index, ["steam_api.dll"])
    output_log = _first_existing(data_index, ["output_log.txt"])
    unity_scan_paths = [p for p in (global_manager, exe) if p is not None]
    unity_versions = scan_unity_versions(unity_scan_paths)

    files, bytes_total = tree_size(root)
    identity["install_files_seen"] = files
    identity["install_bytes_seen"] = bytes_total
    identity["install_mib_seen"] = round(bytes_total / (1024 * 1024), 2)
    if managed: identity["assembly_csharp_sha256"] = sha256_file(managed)
    if mono: identity["unity_mono_sha256"] = sha256_file(mono)
    if top_steam_api: identity["root_steam_api_sha256"] = sha256_file(top_steam_api)

    layout_hits: dict[str, bool] = {}
    for rel in EXPECTED_LAYOUT:
        layout_hits[rel] = rel.casefold() in data_index
    layout_score = sum(layout_hits.values())
    depot_shape: dict[str, object] = report["depot_shape"]  # type: ignore[assignment]
    depot_shape.update({
        "expected_data_files": layout_hits,
        "matched": layout_score,
        "total": len(EXPECTED_LAYOUT),
        "root_steam_api_found": top_steam_api is not None,
        "looks_like_known_windows_depot": layout_score >= 6 and top_steam_api is not None,
    })

    signals: dict[str, object] = report["runtime_signals"]  # type: ignore[assignment]
    signals.update({
        "data_dir_found": data_dir.is_dir(),
        "managed_assembly_found": managed is not None,
        "firstpass_assembly_found": firstpass is not None,
        "bundled_unity_mono_found": mono is not None,
        "wine_mono_required_for_game_runtime": False if mono else None,
        "plugin_steam_api_found": plugin_steam_api is not None,
        "root_steam_api_found": top_steam_api is not None,
        "csteamworks_found": csteamworks is not None,
        "unity_versions_seen": unity_versions,
        "unity_output_log_found": output_log is not None,
        "unity_output_log": str(output_log) if output_log else None,
        "known_title_renderer": "Direct3D 9",
        "steam_cloud_known": False,
    })

    arch = pe.get("architecture") if isinstance(pe, dict) else None
    is_i386 = bool(isinstance(pe, dict) and pe.get("is_32bit_x86"))
    if is_i386:
        findings.append("The Windows executable is 32-bit x86, so Madeira's WoW64/i386 route is the correct CPU path.")
    elif arch:
        warnings.append(f"Unexpected Windows executable architecture: {arch}; re-check the owned build before tuning Madeira.")

    if mono and managed:
        findings.append("HunieCam ships its own Unity Mono runtime and managed assemblies. Madeira's downloadable Wine Mono is not a prerequisite for this game.")
    else:
        warnings.append("Expected bundled Unity Mono/managed files were not both found; the install may be incomplete or a different store/build layout.")

    if layout_score >= 6 and top_steam_api:
        findings.append("The install layout strongly matches the known Windows Steam depot shape.")
    else:
        warnings.append(f"Only {layout_score}/{len(EXPECTED_LAYOUT)} known Unity/depot layout signals matched; treat public metadata as guidance only.")

    if top_steam_api and plugin_steam_api:
        findings.append("Steam API DLLs exist both beside the EXE and inside Unity Plugins. Keep the launch working directory at the game install folder/program folder; Madeira already defaults direct launches this way.")

    if unity_versions:
        findings.append("Unity version string(s) found in the owned files: " + ", ".join(unity_versions))
        if KNOWN_UNITY_VERSION not in unity_versions:
            warnings.append(f"Known public metadata points to Unity {KNOWN_UNITY_VERSION}, but the scanned file strings differ. Test the actual build you own.")

    if output_log:
        findings.append("A Unity output_log.txt already exists; feed it to tools/huniecam_session_triage.py with the Madeira log.")

    route: dict[str, object] = report["route"]  # type: ignore[assignment]
    route.update({
        "cpu": "Madeira WoW64 + FEX x86" if is_i386 else "verify from PE result",
        "runtime": "game-bundled Unity Mono" if mono else "verify from install",
        "wine_mono_download": "not needed for HunieCam's own Unity runtime" if mono else "not determined",
        "graphics_baseline": "DXMT Direct3D 9 emulated frontend",
        "unity_arguments_baseline": "",
        "working_directory": "game/program folder (Madeira direct-launch default)",
        "input_baseline": "direct pointer/tap + keyboard/mouse; do not require XInput",
        "steam_baseline": "separate direct-game compatibility from Madeira Dock/Steam integration",
        "save_path": r"%USERPROFILE%\AppData\LocalLow\HuniePot\HunieCam Studio\",
        "streaming": False,
        "native_recompile": False,
    })

    experiments.extend([
        {
            "when": "Unity output log unexpectedly selects Direct3D 11",
            "change": "launch argument: -force-d3d9",
            "reason": "Old Unity Windows players support -force-d3d9; do not add it when D3D9 is already selected.",
        },
        {
            "when": "Unity/Mono reaches managed startup but the Madeira log shows repeated protected-memory store faults or [store-undecoded]",
            "change": "per-game config: env.MADEIRA_WOW_RWX_PLAIN = 1",
            "reason": "Current Madeira auto-matches Wine Mono, not Unity's bundled Mono. Use only as a one-variable WoW64 A/B experiment.",
        },
        {
            "when": "Unity selects D3D9 and CPU/Mono startup succeeds, but rendering still crashes/corrupts",
            "change": "per-game config: d3d9 = native",
            "reason": "Compare Madeira's native and translated D3D9 frontends only after the failure is graphics-specific.",
        },
    ])

    next_actions.extend([
        "Use this current-upstream compatibility branch and confirm JIT + Memory+ are ready before launch.",
        "Create an isolated HunieCam library entry pointing at HunieCamStudio.exe; leave the original game copy untouched.",
        "Use direct launch first with the program folder as the working folder, default D3D9 routing, 60 FPS, and no speculative config switches.",
        "After the first run export madeira-log.txt and copy HunieCamStudio_Data/output_log.txt if Unity created it.",
        "Run tools/huniecam_session_triage.py so the next experiment is chosen from evidence, one variable at a time.",
        "Once startup works, verify pointer alignment, audio, disposable save/relaunch, 30-minute stability, three cold launches, and suspend/resume.",
    ])
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
    pe = report.get("identity", {}).get("pe", {}) if isinstance(report.get("identity"), dict) else {}
    return 0 if report.get("exe_found") and isinstance(pe, dict) and pe.get("valid_pe") else 2


if __name__ == "__main__":
    raise SystemExit(main())
