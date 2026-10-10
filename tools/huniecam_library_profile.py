#!/usr/bin/env python3
"""Generate the clean Madeira LibraryEntry fragment for HunieCam Studio.

The tool does not edit Madeira's library. It produces a deterministic fragment
that a local agent/user can compare with the entry on-device. The executable
path must be relative to the Wine prefix's drive_c, matching Madeira's library
contract.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from pathlib import PurePosixPath
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_LIBRARY_PROFILE_V1"


def validate_relative_exe(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    p = PurePosixPath(raw)
    if not raw or raw.startswith("/") or ":" in raw.split("/")[0]:
        raise ValueError("relative executable must be a path under Madeira drive_c, not an absolute host/Windows path")
    if any(part in {"..", ""} for part in p.parts):
        raise ValueError("relative executable may not escape drive_c")
    if p.name.casefold() != "huniecamstudio.exe":
        raise ValueError("relative executable must end in HunieCamStudio.exe")
    return p.as_posix()


def build(relative_exe: str, title: str = "HunieCam Studio") -> dict[str, Any]:
    rel = validate_relative_exe(relative_exe)
    entry = {
        "title": title,
        "relativePath": rel,
        "bits": 32,
        "arguments": "",
        "resolution": "1280x720",
        "display": "fit",
        "fpsMode": 1,
        "reducedX87": False,
        "liveLogs": False,
        "performance": False,
        "touchControls": False,
        "launchMode": "direct",
        "config": "",
    }
    return {
        "schema": SCHEMA,
        "entry_fragment": entry,
        "derived_working_folder": str(PurePosixPath(rel).parent),
        "official_steam_reference": {
            "app_id": 426000,
            "windows_executable": "HunieCamStudio.exe",
            "launch_arguments": "",
        },
        "why": {
            "bits": "The owned preflight should prove i386 before use.",
            "resolution": "1280x720 is a conservative 16:9 PC mode within HunieCam's known resolution range.",
            "fpsMode": "Madeira fpsMode=1 is 60 FPS; avoid uncapped timing as the baseline.",
            "display": "Fit preserves the game's aspect ratio for reliable pointer mapping.",
            "launchMode": "Direct isolates game/runtime compatibility from the Steam/Dock layer.",
            "config": "Empty by default; every non-default compatibility change must be a separately guarded A/B run.",
        },
        "rule": "Compare this fragment with the on-device entry; do not overwrite a working profile blindly. Preserve the previous entry before changes.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Generate the baseline HunieCam Madeira library profile")
    p.add_argument("relative_exe", help="Path under drive_c, e.g. Games/HunieCam Studio/HunieCamStudio.exe")
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    try:
        report = build(args.relative_exe)
    except ValueError as exc:
        p.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
