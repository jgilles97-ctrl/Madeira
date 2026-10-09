#!/usr/bin/env python3
"""Evidence-based acceptance gate evaluator for the HunieCam iPad/Madeira port.

The evaluator never invents a pass. Automated evidence can prove some gates;
manual device observations are supplied explicitly as booleans in a small JSON
file. Missing evidence remains UNKNOWN rather than being silently treated as a
failure or success.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ACCEPTANCE_V1"


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def manual_value(manual: dict[str, Any] | None, key: str) -> bool | None:
    if not manual or key not in manual:
        return None
    value = manual[key]
    return value if isinstance(value, bool) else None


def gate(name: str, value: bool | None, evidence: str, required: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if value is True else "FAIL" if value is False else "UNKNOWN",
        "required": required,
        "evidence": evidence,
    }


def evaluate(
    preflight: dict[str, Any] | None,
    session: dict[str, Any] | None,
    save_after: dict[str, Any] | None,
    save_relaunch: dict[str, Any] | None,
    manual: dict[str, Any] | None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    owned_identity = None
    if preflight:
        pe = preflight.get("identity", {}).get("pe", {})
        owned_identity = bool(preflight.get("exe_found")) and bool(pe.get("valid_pe")) and bool(preflight.get("identity", {}).get("exe_sha256"))
    gates.append(gate("owned_game_identity", owned_identity,
                      "Preflight must identify a real PE executable and record its SHA-256."))

    runtime_ready = manual_value(manual, "jit_memory_ready")
    gates.append(gate("jit_and_memory_ready", runtime_ready,
                      "Manual device observation: Madeira showed JIT and Memory+ ready before launch."))

    stage = int(session.get("deepest_stage", 0)) if session else 0
    launch_ok = stage >= 20 if session else None
    gates.append(gate("windows_launch", launch_ok,
                      "Session triage reached the Windows executable stage (>=20)."))

    managed_ok = stage >= 65 if session else None
    gates.append(gate("game_managed_code", managed_ok,
                      "Session triage saw Assembly-CSharp.dll / equivalent game managed-code stage (>=65)."))

    gameplay = manual_value(manual, "real_gameplay")
    gates.append(gate("real_gameplay", gameplay,
                      "Manual observation: a real management/gameplay session was interactive, not only a splash/menu."))

    rendering = manual_value(manual, "rendering_correct")
    gates.append(gate("rendering_correct", rendering,
                      "Manual observation: text, sprites, panels and effects rendered without blocking corruption."))

    pointer = manual_value(manual, "pointer_aligned")
    gates.append(gate("pointer_aligned", pointer,
                      "Manual observation: taps/clicks landed correctly across corners, menus and small targets."))

    audio = manual_value(manual, "audio_correct")
    gates.append(gate("audio_correct", audio,
                      "Manual observation: music/effects were present and stable without persistent crackle/latency."))

    save_written = None
    if save_after:
        save_written = bool(save_after.get("progress_write_detected")) if "progress_write_detected" in save_after else None
    gates.append(gate("save_write_detected", save_written,
                      "Save compare detected at least one legitimate tree change after visible progress."))

    persistence = None
    if save_after and save_relaunch:
        # The post-progress snapshot must match the post-relaunch snapshot.
        after_tree = save_after.get("tree_sha256")
        relaunch_tree = save_relaunch.get("tree_sha256")
        if after_tree is not None and relaunch_tree is not None:
            persistence = after_tree == relaunch_tree
    gates.append(gate("save_survives_relaunch", persistence,
                      "Post-progress and post-relaunch save snapshots must have the same aggregate tree hash."))

    save_visible = manual_value(manual, "save_progress_visible_after_relaunch")
    gates.append(gate("save_progress_visible_after_relaunch", save_visible,
                      "Manual observation: the relaunched game visibly restored the same progress."))

    performance = manual_value(manual, "performance_acceptable")
    gates.append(gate("performance_acceptable", performance,
                      "Manual observation/measurement: representative busy play had acceptable frame pacing and no runaway game speed."))

    stability = manual_value(manual, "stable_30_minutes")
    gates.append(gate("stable_30_minutes", stability,
                      "Manual observation: representative play lasted at least 30 minutes without crash/freeze."))

    cold = manual_value(manual, "three_cold_launches")
    gates.append(gate("three_cold_launches", cold,
                      "Manual observation: three full cold launches reached the usable game state."))

    suspend = manual_value(manual, "two_suspend_resume_cycles")
    gates.append(gate("two_suspend_resume_cycles", suspend,
                      "Manual observation: two background/foreground cycles returned with image/audio/input/save state intact."))

    repeatable = manual_value(manual, "repeatable_profile")
    gates.append(gate("repeatable_profile", repeatable,
                      "Manual observation: the documented final launch profile reproduces the same result from a clean Madeira start."))

    required = [g for g in gates if g["required"]]
    counts = {s: sum(1 for g in required if g["status"] == s) for s in ("PASS", "FAIL", "UNKNOWN")}
    complete = counts["FAIL"] == 0 and counts["UNKNOWN"] == 0
    if counts["FAIL"]:
        overall = "NOT_READY_FAILED_GATE"
    elif counts["UNKNOWN"]:
        overall = "NOT_READY_MISSING_EVIDENCE"
    else:
        overall = "ACCEPTED"

    next_gate = next((g for g in required if g["status"] != "PASS"), None)
    return {
        "schema": SCHEMA,
        "overall": overall,
        "accepted": complete,
        "counts": counts,
        "next_unproven_gate": next_gate,
        "gates": gates,
        "rule": "Unknown is never treated as pass. The port is accepted only when every required gate is PASS.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate HunieCam iPad/Madeira acceptance gates")
    parser.add_argument("--preflight", type=pathlib.Path)
    parser.add_argument("--session", type=pathlib.Path)
    parser.add_argument("--save-after", type=pathlib.Path)
    parser.add_argument("--save-relaunch", type=pathlib.Path)
    parser.add_argument("--manual", type=pathlib.Path, help="JSON booleans for device-observation gates")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()

    report = evaluate(load(args.preflight), load(args.session), load(args.save_after), load(args.save_relaunch), load(args.manual))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
