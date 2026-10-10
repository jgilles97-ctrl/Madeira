#!/usr/bin/env python3
"""Static audit of Madeira's HunieCam-critical touch drag/release path.

HunieCam depends heavily on drag-and-drop. Public Windows touchscreen reports
say a touch/stylus drag can move but fail at release, so Cycle 7 verifies that
Madeira's own touch-as-mouse path explicitly synthesizes a Windows LEFTUP event
all the way into Wine's hardware-input path.

This tool reads source text only. It does not claim the physical device works;
it proves that the intended release transport is present in the source being
built, so a missing source-side release cannot be confused with a device/game
runtime failure.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_INPUT_PATH_AUDIT_V1"

FILES = {
    "swift": pathlib.Path("app/Madeira/ContentView.swift"),
    "bridge": pathlib.Path("app/Madeira/Winios/Winios.m"),
    "driver": pathlib.Path("build/win32u-unix/driver_ios.c"),
}

CHECKS = (
    ("swift_drag_commit_down", "swift", r"tmCommitDrag[\s\S]{0,800}?winios_post_touch_down"),
    ("swift_drag_move", "swift", r"touchModeMoved[\s\S]{0,3500}?winios_post_touch_move"),
    ("swift_normal_lift_posts_up", "swift", r"touchModeEnded[\s\S]{0,1400}?winios_post_touch_up"),
    ("swift_cancel_posts_up", "swift", r"touchModeCancelled[\s\S]{0,900}?winios_post_touch_up"),
    ("bridge_up_function_exists", "bridge", r"void\s+winios_post_touch_up\s*\("),
    ("bridge_up_is_leftup_absolute", "bridge", r"winios_post_touch_up[\s\S]{0,500}?MOUSEEVENTF_LEFTUP\s*\|\s*MOUSEEVENTF_ABSOLUTE"),
    ("bridge_queues_mouse_event", "bridge", r"winios_post_touch_up[\s\S]{0,500}?winios_q_push_ev\s*\(\s*WINIOS_EV_MOUSE"),
    ("bridge_drain_calls_driver", "bridge", r"winios_drv_post_mouse\s*\(\s*e\.x\s*,\s*e\.y\s*,\s*e\.flags"),
    ("driver_preserves_flags", "driver", r"input\.mi\.dwFlags\s*=\s*flags"),
    ("driver_sends_hardware_input", "driver", r"send_hardware_message\s*\(\s*NULL\s*,\s*0\s*,\s*&input\s*,\s*0\s*\)"),
)


def audit(root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve()
    texts: dict[str, str] = {}
    errors: list[str] = []
    file_state: dict[str, Any] = {}
    for key, rel in FILES.items():
        path = root / rel
        exists = path.is_file()
        file_state[key] = {"path": rel.as_posix(), "exists": exists}
        if not exists:
            errors.append(f"Required input-path source is missing: {rel.as_posix()}")
            texts[key] = ""
        else:
            texts[key] = path.read_text(encoding="utf-8", errors="replace")

    checks: list[dict[str, Any]] = []
    for name, file_key, pattern in CHECKS:
        passed = bool(re.search(pattern, texts.get(file_key, ""), re.MULTILINE))
        checks.append({"name": name, "file": FILES[file_key].as_posix(), "passed": passed})
        if not passed:
            errors.append(f"Input release invariant failed: {name}")

    all_pass = not errors
    return {
        "schema": SCHEMA,
        "passed": all_pass,
        "files": file_state,
        "checks": checks,
        "errors": errors,
        "proven_by_source": {
            "touch_drag_posts_button_down": next((c["passed"] for c in checks if c["name"] == "swift_drag_commit_down"), False),
            "touch_drag_posts_motion": next((c["passed"] for c in checks if c["name"] == "swift_drag_move"), False),
            "touch_lift_posts_left_button_up": all(next((c["passed"] for c in checks if c["name"] == n), False) for n in ("swift_normal_lift_posts_up", "bridge_up_is_leftup_absolute", "bridge_drain_calls_driver", "driver_sends_hardware_input")),
        },
        "not_proven": "Static source presence does not prove HunieCam reacts correctly on a physical iPad. Device Evidence V3 must still show three successful real gameplay drag/releases.",
        "rule": "Do not patch the input transport merely because HunieCam has a public Windows touchscreen release bug. Madeira already synthesizes mouse input; patch only if device/log evidence shows this chain failing in practice.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Audit Madeira's HunieCam-critical drag/release input chain")
    p.add_argument("root", nargs="?", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = audit(args.root)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
