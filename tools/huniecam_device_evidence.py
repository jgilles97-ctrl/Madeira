#!/usr/bin/env python3
"""Generate and normalize structured on-device evidence for HunieCam acceptance.

The template replaces vague checkboxes with named pointer positions and counted
cold-launch / suspend-resume trials. Unknown observations stay null.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V1"
POINTER_POINTS = (
    "top_left", "top_center", "top_right",
    "middle_left", "center", "middle_right",
    "bottom_left", "bottom_center", "bottom_right",
)


def template() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "jit_memory_ready": None,
        "real_gameplay": None,
        "rendering_correct": None,
        "audio_correct": None,
        "save_progress_visible_after_relaunch": None,
        "performance_acceptable": None,
        "repeatable_profile": None,
        "stable_minutes": 0,
        "pointer_grid": [{"point": point, "passed": None, "note": ""} for point in POINTER_POINTS],
        "cold_launch_trials": [
            {"trial": 1, "success": None, "note": ""},
            {"trial": 2, "success": None, "note": ""},
            {"trial": 3, "success": None, "note": ""},
        ],
        "suspend_resume_trials": [
            {"trial": 1, "success": None, "note": ""},
            {"trial": 2, "success": None, "note": ""},
        ],
        "gameplay_notes": "",
        "rendering_notes": "",
        "audio_notes": "",
        "performance_notes": "",
        "rule": "Use true/false only after observing the result on the iPad. Leave unknown items null. Do not convert missing evidence into success.",
    }


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    points = data.get("pointer_grid") if isinstance(data.get("pointer_grid"), list) else []
    point_map: dict[str, bool | None] = {}
    duplicates: set[str] = set()
    for item in points:
        if not isinstance(item, dict):
            continue
        name = str(item.get("point", ""))
        if name in point_map:
            duplicates.add(name)
        point_map[name] = _bool(item.get("passed"))
    missing = [p for p in POINTER_POINTS if p not in point_map]
    unknown = [p for p in POINTER_POINTS if point_map.get(p) is None]
    failed = [p for p in POINTER_POINTS if point_map.get(p) is False]
    passed = [p for p in POINTER_POINTS if point_map.get(p) is True]
    if duplicates:
        warnings.append("Duplicate pointer-grid point(s): " + ", ".join(sorted(duplicates)))
    if missing:
        warnings.append("Missing pointer-grid point(s): " + ", ".join(missing))

    cold = data.get("cold_launch_trials") if isinstance(data.get("cold_launch_trials"), list) else []
    cold_values = [_bool(x.get("success")) for x in cold if isinstance(x, dict)]
    suspend = data.get("suspend_resume_trials") if isinstance(data.get("suspend_resume_trials"), list) else []
    suspend_values = [_bool(x.get("success")) for x in suspend if isinstance(x, dict)]

    normalized = dict(data)
    normalized["pointer_points_tested"] = len(passed) + len(failed)
    normalized["pointer_points_passed"] = len(passed)
    normalized["cold_launches"] = sum(1 for x in cold_values if x is True)
    normalized["suspend_resume_cycles"] = sum(1 for x in suspend_values if x is True)

    complete_pointer = not missing and not unknown and not failed and len(passed) == len(POINTER_POINTS)
    cold_complete = len(cold_values) >= 3 and all(x is True for x in cold_values[:3])
    suspend_complete = len(suspend_values) >= 2 and all(x is True for x in suspend_values[:2])

    return {
        "schema": SCHEMA,
        "normalized": normalized,
        "derived": {
            "pointer_grid_complete": complete_pointer,
            "pointer_missing": missing,
            "pointer_unknown": unknown,
            "pointer_failed": failed,
            "cold_launch_trials_complete": cold_complete,
            "suspend_resume_trials_complete": suspend_complete,
        },
        "warnings": warnings,
        "rule": "Structured trial details are authoritative when present; derived counts are convenience fields for the acceptance evaluator.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Generate/normalize HunieCam iPad device evidence")
    sub = p.add_subparsers(dest="command", required=True)
    make = sub.add_parser("template")
    make.add_argument("--json", dest="json_path", type=pathlib.Path)
    norm = sub.add_parser("normalize")
    norm.add_argument("input", type=pathlib.Path)
    norm.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    if args.command == "template":
        report = template()
    else:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        report = summarize(raw)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
