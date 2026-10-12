#!/usr/bin/env python3
"""Static EA App Wine-prefix audit for the Sims 4 local iPad lane.

This intentionally does not mutate the prefix. It records launcher/service/CEF
shape and EA registry state before a physical-device test is spent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any

SCHEMA = "SIMS4_EA_PREFIX_AUDIT_V2"

EA_RELATIVE = {
    "EADesktop.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EADesktop.exe",
    "EALauncher.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe",
    "EABackgroundService.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EABackgroundService.exe",
    "EACefSubProcess.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EACefSubProcess.exe",
}

BACKGROUND_INI = "ProgramData/EA Desktop/backgroundservice.ini"
SERVICE_NAME = "EABackgroundService"
NETWORK_LIST_CLSID = "DCB00C01-570F-4A9B-8D69-199FDBA5723B"
EA_DESKTOP_KEY = r"software\electronic arts\ea desktop"
LINK2EA_KEY = r"software\classes\link2ea"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_drive_c(prefix: pathlib.Path) -> pathlib.Path:
    prefix = prefix.resolve()
    if prefix.name.lower() == "drive_c":
        return prefix
    if (prefix / "drive_c").is_dir():
        return prefix / "drive_c"
    return prefix


def file_record(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    st = path.stat()
    return {
        "path": str(path),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": sha256(path),
    }


def read_text(path: pathlib.Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def normalized_reg_path(value: str) -> str:
    """Collapse Wine .reg escaped backslashes for tolerant key matching."""
    return re.sub(r"\\+", r"\\", value.strip().lower())


def parse_wine_dword(text: str, key_fragment: str, value_name: str) -> int | None:
    active = False
    wanted_key = normalized_reg_path(key_fragment)
    value_re = re.compile(rf'^"{re.escape(value_name)}"=dword:([0-9a-fA-F]+)\s*$')
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = normalized_reg_path(line[1:-1])
            active = wanted_key in section
            continue
        if active:
            match = value_re.match(line)
            if match:
                return int(match.group(1), 16)
    return None


def registry_key_present(text: str, key_fragment: str) -> bool:
    wanted = normalized_reg_path(key_fragment)
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            if wanted in normalized_reg_path(line[1:-1]):
                return True
    return False


def parse_background_ini(path: pathlib.Path) -> dict[str, Any]:
    rec = file_record(path)
    if rec is None:
        return {
            "present": False,
            "path": str(path),
            "pid_candidates": [],
            "stale_state": "NOT_PRESENT",
        }
    text = read_text(path)
    pids = sorted({int(x) for x in re.findall(r"(?im)\b(?:pid|processid)\s*[=:]\s*(\d+)\b", text)})
    return {
        "present": True,
        **rec,
        "pid_candidates": pids,
        "stale_state": "UNKNOWN_UNTIL_SERVICE_STATUS_IS_QUERIED_ON_DEVICE",
        "cleanup_rule": (
            "Do not delete this file just because it exists. Proton deletes it when "
            "EABackgroundService is STOP_PENDING or STOPPED; prove that state first."
        ),
    }


def audit(prefix: pathlib.Path) -> dict[str, Any]:
    prefix = prefix.resolve()
    drive_c = resolve_drive_c(prefix)
    prefix_root = drive_c.parent if drive_c.name.lower() == "drive_c" else prefix

    components: dict[str, Any] = {}
    missing: list[str] = []
    for name, rel in EA_RELATIVE.items():
        path = drive_c.joinpath(*rel.split("/"))
        rec = file_record(path)
        components[name] = rec
        if rec is None:
            missing.append(name)

    system_reg_path = prefix_root / "system.reg"
    user_reg_path = prefix_root / "user.reg"
    system_reg = read_text(system_reg_path)
    user_reg = read_text(user_reg_path)
    combined = system_reg + "\n" + user_reg

    service_registered = SERVICE_NAME.lower() in system_reg.lower()
    nlm_registered = (
        NETWORK_LIST_CLSID.lower() in combined.lower()
        and "netprofm.dll" in combined.lower()
    )
    link2ea_registered = registry_key_present(combined, LINK2EA_KEY)
    ea_desktop_key_present = registry_key_present(system_reg, EA_DESKTOP_KEY)
    is_unavailable = parse_wine_dword(system_reg, EA_DESKTOP_KEY, "IsUnavailable")

    background_ini = parse_background_ini(drive_c.joinpath(*BACKGROUND_INI.split("/")))

    blockers: list[str] = []
    if not drive_c.is_dir():
        blockers.append("DRIVE_C_NOT_FOUND")
    if missing:
        blockers.append("EA_COMPONENTS_MISSING")
    if system_reg and not service_registered:
        blockers.append("EA_BACKGROUND_SERVICE_NOT_REGISTERED")
    if system_reg and not link2ea_registered:
        blockers.append("LINK2EA_ASSOCIATION_MISSING")
    if is_unavailable not in (None, 0):
        blockers.append("EA_DESKTOP_ISUNAVAILABLE_SET")

    static_ready = not blockers
    return {
        "schema": SCHEMA,
        "prefix": str(prefix),
        "drive_c": str(drive_c),
        "components": components,
        "missing_components": missing,
        "registry": {
            "system_reg_present": system_reg_path.is_file(),
            "user_reg_present": user_reg_path.is_file(),
            "ea_background_service_registered": service_registered,
            "network_list_manager_registered": nlm_registered,
            "ea_desktop_key_present": ea_desktop_key_present,
            "ea_desktop_is_unavailable": is_unavailable,
            "link2ea_registered": link2ea_registered,
        },
        "backgroundservice_ini": background_ini,
        "static_ready": static_ready,
        "blockers": blockers,
        "proton_evidence_rules": {
            "is_unavailable": (
                "Proton clears HKLM\\Software\\Electronic Arts\\EA Desktop\\IsUnavailable when nonzero before link2ea launch. "
                "This audit reports and blocks on the state but does not mutate it."
            ),
            "link2ea": (
                "Proton treats a missing Software\\Classes\\link2ea association as a broken EA Desktop installation. "
                "This audit detects the missing association but does not reinstall or delete registry trees."
            ),
            "desktop_close_timeout_ms": 3000,
        },
        "device_probe_required": [
            "SCM opens",
            "EABackgroundService query succeeds and current state is captured",
            "DirectWrite resolves Arial before EA CEF is launched",
            "sensapi!IsNetworkAlive succeeds",
            "INetworkListManager CoCreateInstance succeeds",
            "TCP route works after JIT VPN handoff",
            "WinHTTP HTTPS works",
            "x64 child process survives parent/child handoff",
        ],
        "known_ea_state_rule": (
            "If EABackgroundService is STOP_PENDING or STOPPED and backgroundservice.ini exists, "
            "capture it first, then test the Proton-style cleanup as one isolated variable."
        ),
        "next_gate": "RUN_SIM4_LAUNCHER_CANARY_ON_IPAD" if static_ready else "FIX_EA_PREFIX_STATIC_BLOCKERS",
        "physical_device_success": "UNPROVEN",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit an EA App Wine prefix before Sims 4 iPad device testing")
    ap.add_argument("prefix", type=pathlib.Path)
    ap.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = ap.parse_args()
    report = audit(args.prefix)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["static_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
