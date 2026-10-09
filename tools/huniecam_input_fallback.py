#!/usr/bin/env python3
"""Choose the next HunieCam input experiment from physical-device evidence.

HunieCam is drag-heavy and has a reported Windows touchscreen release problem.
Madeira, however, has its own touch-as-mouse pipeline. This planner separates:
- screen-coordinate/pointer mapping failures;
- finger-only drag/release translation failures;
- direct-finger vs Madeira touch-pointer differences;
- failures that also reproduce with a real hardware mouse/trackpad.

It never edits Madeira and never recommends multiple changes at once.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_INPUT_FALLBACK_V1"
TOUCH_MODES = ("direct_finger", "touch_pointer")
HARDWARE_MODES = ("hardware_mouse", "hardware_trackpad")


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    normalized = data.get("normalized")
    return normalized if isinstance(normalized, dict) else data


def _bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def _trial(item: dict[str, Any]) -> dict[str, Any]:
    mode = item.get("input_mode") if isinstance(item.get("input_mode"), str) else None
    steps = {k: _bool(item.get(k)) for k in ("press_registered", "movement_registered", "release_registered", "game_response_registered")}
    if any(v is False for v in steps.values()):
        result = False
    elif any(v is None for v in steps.values()):
        result = None
    else:
        result = True
    return {"mode": mode, "steps": steps, "result": result}


def _pointer_state(payload: dict[str, Any]) -> bool | None:
    rows = payload.get("pointer_grid") if isinstance(payload.get("pointer_grid"), list) else []
    if rows:
        values = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            values.append(_bool(item.get("passed")))
        if len(values) < 9 or any(v is None for v in values[:9]):
            return None
        return all(v is True for v in values[:9])
    tested, passed = payload.get("pointer_points_tested"), payload.get("pointer_points_passed")
    if isinstance(tested, (int, float)) and not isinstance(tested, bool) and isinstance(passed, (int, float)) and not isinstance(passed, bool):
        return tested >= 9 and passed == tested
    return None


def analyze(device: dict[str, Any], source_audit: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _payload(device)
    warnings: list[str] = []
    if payload.get("schema") != "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3":
        warnings.append("Device evidence is not current V3; input diagnosis may be incomplete.")

    pointer = _pointer_state(payload)
    rows = [_trial(x) for x in payload.get("drag_release_trials", []) if isinstance(x, dict)]
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["mode"]:
            by_mode[str(row["mode"])].append(row)

    def mode_pass(mode: str) -> bool | None:
        vals = [x["result"] for x in by_mode.get(mode, [])]
        if len(vals) < 3:
            return None
        vals = vals[:3]
        if any(v is False for v in vals):
            return False
        if any(v is None for v in vals):
            return None
        return True

    direct = mode_pass("direct_finger")
    touch_pointer = mode_pass("touch_pointer")
    hardware_values = [mode_pass(m) for m in HARDWARE_MODES]
    hardware = True if any(v is True for v in hardware_values) else False if any(v is False for v in hardware_values) and all(v is not None for v in hardware_values) else None

    release_specific = any(
        row["steps"]["press_registered"] is True
        and row["steps"]["movement_registered"] is True
        and row["steps"]["release_registered"] is False
        for row in rows
    )
    source_ok = None if source_audit is None else bool(source_audit.get("passed") and (source_audit.get("proven_by_source") or {}).get("touch_lift_posts_left_button_up"))

    if pointer is False:
        status = "POINTER_MAPPING_BLOCKER"
        action = "Fix pointer/display mapping before changing drag mechanics. Keep renderer/runtime/dependency settings unchanged."
        experiment = None
    elif pointer is None:
        status = "NEED_POINTER_EVIDENCE"
        action = "Complete the nine-point pointer sweep before diagnosing drag/release. A release test is ambiguous if coordinates are not already proven."
        experiment = None
    elif direct is True:
        status = "DIRECT_FINGER_DRAG_PROVEN"
        action = "Keep direct finger input. Do not enable touch-pointer mode or patch the transport; continue the remaining acceptance gates."
        experiment = None
    elif touch_pointer is True:
        status = "TOUCH_POINTER_DRAG_PROVEN"
        action = "Use Madeira touch-pointer mode as the final touch interaction mode, then collect a clean three-trial primary acceptance set in that one mode."
        experiment = {"one_variable": "input mode", "from": "direct_finger", "to": "touch_pointer"}
    elif direct is False and touch_pointer is None:
        status = "TRY_TOUCH_POINTER_ONE_VARIABLE"
        action = "Keep the same build, resolution, renderer and compatibility config. Change only Madeira input mode from direct finger to touch-pointer and run three drag/release trials."
        experiment = {"one_variable": "input mode", "from": "direct_finger", "to": "touch_pointer"}
    elif direct is False and touch_pointer is False and hardware is True:
        status = "TOUCH_TRANSLATION_BLOCKER"
        action = "Both finger paths fail while hardware mouse/trackpad works. Inspect Madeira [winios] post_touch_up and drv_post_mouse status lines for the failed finger run before changing runtime/graphics settings."
        experiment = None
    elif direct is False and touch_pointer is False and hardware is None:
        status = "COMPARE_HARDWARE_POINTER"
        action = "Both finger modes fail. Without changing the game profile, run three equivalent drags with a hardware mouse/trackpad. This isolates touch translation from game/window input handling."
        experiment = {"one_variable": "physical input source", "to": "hardware_mouse_or_trackpad", "diagnostic_only": True}
    elif hardware is False:
        status = "NOT_TOUCH_SPECIFIC"
        action = "The failure also reproduces with hardware pointer input. Stop touch-specific patching; inspect game/window hit-testing, focus, Steam/game state and the first relevant runtime input error."
        experiment = None
    else:
        status = "NEED_DRAG_EVIDENCE"
        action = "Record at least three complete press→move→release→game-response trials for one finger mode before changing anything."
        experiment = None

    if release_specific and source_ok is True:
        warnings.append("The observed failure is release-specific even though the built source contains an explicit LEFTUP→Wine hardware-input path. Capture [winios] post_touch_up and drv_post_mouse status from the failing run before patching source.")
    elif release_specific and source_ok is None:
        warnings.append("The observed failure is release-specific. Run huniecam_input_path_audit.py before assuming Madeira lacks a release event.")

    return {
        "schema": SCHEMA,
        "status": status,
        "pointer_grid": pointer,
        "mode_results": {"direct_finger": direct, "touch_pointer": touch_pointer, "hardware_pointer": hardware},
        "release_specific_failure_seen": release_specific,
        "source_release_path_proven": source_ok,
        "action": action,
        "experiment": experiment,
        "warnings": warnings,
        "rule": "Change one input variable at a time. Hardware mouse/trackpad is a diagnostic comparator only and never satisfies the touch-first acceptance gate.",
    }


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Choose the next HunieCam input experiment from device evidence")
    p.add_argument("--device-evidence", type=pathlib.Path, required=True)
    p.add_argument("--source-audit", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = analyze(load(args.device_evidence) or {}, load(args.source_audit))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
