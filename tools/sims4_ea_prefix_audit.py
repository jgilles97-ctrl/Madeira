#!/usr/bin/env python3
"""Static EA App Wine-prefix audit for the Sims 4 local iPad lane.

This intentionally does not mutate the prefix. It records the launcher/service/CEF
shape and flags things that must be proven on the physical device before cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any

SCHEMA = "SIMS4_EA_PREFIX_AUDIT_V1"

EA_RELATIVE = {
    "EADesktop.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EADesktop.exe",
    "EALauncher.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe",
    "EABackgroundService.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EABackgroundService.exe",
    "EACefSubProcess.exe": "Program Files/Electronic Arts/EA Desktop/EA Desktop/EACefSubProcess.exe",
}

BACKGROUND_INI = "ProgramData/EA Desktop/backgroundservice.ini"
SERVICE_NAME = "EABackgroundService"
NETWORK_LIST_CLSID = "DCB00C01-570F-4A9B-8D69-199FDBA5723B"


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

    background_ini = parse_background_ini(drive_c.joinpath(*BACKGROUND_INI.split("/")))

    blockers: list[str] = []
    if not drive_c.is_dir():
        blockers.append("DRIVE_C_NOT_FOUND")
    if missing:
        blockers.append("EA_COMPONENTS_MISSING")
    if system_reg and not service_registered:
        blockers.append("EA_BACKGROUND_SERVICE_NOT_REGISTERED")

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
        },
        "backgroundservice_ini": background_ini,
        "static_ready": static_ready,
        "blockers": blockers,
        "device_probe_required": [
            "SCM opens",
            "EABackgroundService query succeeds and current state is captured",
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
