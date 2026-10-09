#!/usr/bin/env python3
"""Generate and normalize structured on-device evidence for HunieCam acceptance.

Cycle 7 Device Evidence V3 adds a title-specific drag/release test. HunieCam is
reported to accept touch dragging on Windows but fail to register the release,
which can make its portrait-heavy gameplay unusable. A pointer grid therefore
is not enough: real gameplay drags must prove press, movement, release and the
resulting game response. Unknown observations remain null.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3"
POINTER_POINTS = (
    "top_left", "top_center", "top_right",
    "middle_left", "center", "middle_right",
    "bottom_left", "bottom_center", "bottom_right",
)
DRAG_RELEASE_TRIALS = 3


def _link(run_context: dict[str, Any] | None) -> dict[str, Any]:
    context = run_context or {}
    ready = bool(context.get("ready") and context.get("run_id_sha256"))
    return {
        "run_id_sha256": context.get("run_id_sha256") if ready else None,
        "build_fingerprint_sha256": context.get("build_fingerprint_sha256") if ready else None,
        "profile_sha256": context.get("profile_sha256") if ready else None,
    }


def template(run_context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        **_link(run_context),
        "jit_memory_ready": None,
        "real_gameplay": None,
        "rendering_correct": None,
        "audio_correct": None,
        "save_progress_visible_after_relaunch": None,
        "performance_acceptable": None,
        "repeatable_profile": None,
        "stable_minutes": 0,
        "pointer_grid": [{"point": point, "passed": None, "note": ""} for point in POINTER_POINTS],
        "drag_release_trials": [
            {
                "trial": i,
                "input_mode": None,
                "press_registered": None,
                "movement_registered": None,
                "release_registered": None,
                "game_response_registered": None,
                "note": "",
            }
            for i in range(1, DRAG_RELEASE_TRIALS + 1)
        ],
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
        "drag_release_notes": "",
        "rendering_notes": "",
        "audio_notes": "",
        "performance_notes": "",
        "rule": "Use true/false only after observing the result on the iPad. For each drag trial, prove press, movement, release and the resulting in-game response separately. Leave unknown items null and never reuse this run-linked form for another launch.",
    }


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _drag_trial_state(item: dict[str, Any]) -> bool | None:
    values = [
        _bool(item.get("press_registered")),
        _bool(item.get("movement_registered")),
        _bool(item.get("release_registered")),
        _bool(item.get("game_response_registered")),
    ]
    if any(v is False for v in values):
        return False
    if any(v is None for v in values):
        return None
    return True


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    if data.get("schema") not in {"MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V1", "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V2", SCHEMA}:
        warnings.append(f"Unexpected device-evidence schema: {data.get('schema')!r}")

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

    drag_rows = data.get("drag_release_trials") if isinstance(data.get("drag_release_trials"), list) else []
    drag_states = [_drag_trial_state(x) for x in drag_rows if isinstance(x, dict)]
    drag_tested = sum(1 for x in drag_states if x is not None)
    drag_passed = sum(1 for x in drag_states if x is True)
    drag_complete = len(drag_states) >= DRAG_RELEASE_TRIALS and all(x is True for x in drag_states[:DRAG_RELEASE_TRIALS])
    if data.get("schema") != SCHEMA:
        warnings.append("Legacy device evidence does not prove the Cycle 7 HunieCam drag-release gate.")

    cold = data.get("cold_launch_trials") if isinstance(data.get("cold_launch_trials"), list) else []
    cold_values = [_bool(x.get("success")) for x in cold if isinstance(x, dict)]
    suspend = data.get("suspend_resume_trials") if isinstance(data.get("suspend_resume_trials"), list) else []
    suspend_values = [_bool(x.get("success")) for x in suspend if isinstance(x, dict)]

    normalized = dict(data)
    normalized["schema"] = SCHEMA
    normalized["pointer_points_tested"] = len(passed) + len(failed)
    normalized["pointer_points_passed"] = len(passed)
    normalized["drag_release_trials_tested"] = drag_tested
    normalized["drag_release_trials_passed"] = drag_passed
    normalized["cold_launches"] = sum(1 for x in cold_values if x is True)
    normalized["suspend_resume_cycles"] = sum(1 for x in suspend_values if x is True)

    complete_pointer = not missing and not unknown and not failed and len(passed) == len(POINTER_POINTS)
    cold_complete = len(cold_values) >= 3 and all(x is True for x in cold_values[:3])
    suspend_complete = len(suspend_values) >= 2 and all(x is True for x in suspend_values[:2])
    run_link_ready = all(bool(normalized.get(k)) for k in ("run_id_sha256", "build_fingerprint_sha256", "profile_sha256"))
    if not run_link_ready:
        warnings.append("Device observations are not linked to a sealed run ID/build/profile; final acceptance must remain unproven.")

    return {
        "schema": SCHEMA,
        "normalized": normalized,
        "derived": {
            "pointer_grid_complete": complete_pointer,
            "pointer_missing": missing,
            "pointer_unknown": unknown,
            "pointer_failed": failed,
            "drag_release_trials_complete": drag_complete,
            "drag_release_trials_tested": drag_tested,
            "drag_release_trials_passed": drag_passed,
            "cold_launch_trials_complete": cold_complete,
            "suspend_resume_trials_complete": suspend_complete,
            "run_link_ready": run_link_ready,
        },
        "warnings": warnings,
        "rule": "Structured trial details are authoritative. Final acceptance requires three real HunieCam gameplay drag/release trials in which press, movement, release and the resulting game response all succeed.",
    }


def _load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def main() -> int:
    p = argparse.ArgumentParser(description="Generate/normalize HunieCam iPad device evidence")
    sub = p.add_subparsers(dest="command", required=True)
    make = sub.add_parser("template")
    make.add_argument("--run-context", type=pathlib.Path, help="Optional sealed huniecam-run-context.json to bind this observation form")
    make.add_argument("--json", dest="json_path", type=pathlib.Path)
    norm = sub.add_parser("normalize")
    norm.add_argument("input", type=pathlib.Path)
    norm.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = template(_load(args.run_context)) if args.command == "template" else summarize(json.loads(args.input.read_text(encoding="utf-8")))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
