#!/usr/bin/env python3
"""Evidence-based acceptance gates for the HunieCam iPad/Madeira port.

Automated evidence proves machine-observable gates. Device observations are
provided in JSON. Missing evidence remains UNKNOWN. Counted requirements
(30-minute run, three cold launches, two suspend/resume cycles and pointer-grid
coverage) are checked numerically so a vague checkbox cannot accidentally pass
them. Legacy booleans remain accepted for older evidence files.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ACCEPTANCE_V3"


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def manual_bool(manual: dict[str, Any] | None, key: str) -> bool | None:
    if not manual or key not in manual:
        return None
    value = manual[key]
    return value if isinstance(value, bool) else None


def number(manual: dict[str, Any] | None, key: str) -> float | None:
    if not manual or key not in manual:
        return None
    value = manual[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def threshold_or_legacy(manual: dict[str, Any] | None, numeric_key: str, minimum: float, legacy_key: str) -> bool | None:
    value = number(manual, numeric_key)
    if value is not None:
        return value >= minimum
    return manual_bool(manual, legacy_key)


def pointer_gate(manual: dict[str, Any] | None) -> bool | None:
    tested = number(manual, "pointer_points_tested")
    passed = number(manual, "pointer_points_passed")
    if tested is not None or passed is not None:
        if tested is None or passed is None:
            return None
        # Nine points = four corners, four edge-midpoints and centre. Requiring
        # every tested point to pass prevents one easy centre click from passing.
        return tested >= 9 and passed == tested
    return manual_bool(manual, "pointer_aligned")


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
    save_verification: dict[str, Any] | None,
    manual: dict[str, Any] | None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    owned_identity = None
    if preflight:
        pe = preflight.get("identity", {}).get("pe", {})
        owned_identity = bool(preflight.get("exe_found")) and bool(pe.get("valid_pe")) and bool(preflight.get("identity", {}).get("exe_sha256"))
    gates.append(gate("owned_game_identity", owned_identity,
                      "Preflight identified a real PE executable and recorded its SHA-256."))

    gates.append(gate("jit_and_memory_ready", manual_bool(manual, "jit_memory_ready"),
                      "Device observation: Madeira showed JIT and Memory+ ready before launch."))

    stage = int(session.get("deepest_stage", 0)) if session else 0
    gates.append(gate("windows_launch", stage >= 20 if session else None,
                      "Session triage reached Windows executable stage >=20."))
    gates.append(gate("game_managed_code", stage >= 65 if session else None,
                      "Session triage reached game managed-code stage >=65."))

    gates.append(gate("real_gameplay", manual_bool(manual, "real_gameplay"),
                      "Device observation: a real management/gameplay session was interactive, not only splash/menu."))
    gates.append(gate("rendering_correct", manual_bool(manual, "rendering_correct"),
                      "Device observation: text, sprites, panels and effects rendered without blocking corruption."))
    gates.append(gate("pointer_grid", pointer_gate(manual),
                      "Counted device sweep: >=9 screen points tested and every tested point passed; legacy pointer_aligned boolean remains supported."))
    gates.append(gate("audio_correct", manual_bool(manual, "audio_correct"),
                      "Device observation: music/effects were present and stable without persistent crackle/latency."))

    write_detected = persistence = save_machine_gate = None
    if save_verification:
        if "progress_write_detected" in save_verification:
            write_detected = bool(save_verification.get("progress_write_detected"))
        if "save_tree_survived_relaunch" in save_verification:
            persistence = bool(save_verification.get("save_tree_survived_relaunch"))
        if "machine_gate_pass" in save_verification:
            save_machine_gate = bool(save_verification.get("machine_gate_pass"))
    gates.append(gate("save_write_detected", write_detected,
                      "Three-stage save verification detected a real before→after tree change."))
    gates.append(gate("save_survives_relaunch", persistence,
                      "Exact post-progress save tree still existed after full Madeira/game relaunch."))
    gates.append(gate("save_machine_verification", save_machine_gate,
                      "Machine save gate requires both a progress write and relaunch persistence."))
    gates.append(gate("save_progress_visible_after_relaunch", manual_bool(manual, "save_progress_visible_after_relaunch"),
                      "Device observation: relaunched game visibly restored the same progress."))

    gates.append(gate("performance_acceptable", manual_bool(manual, "performance_acceptable"),
                      "Measured/observed busy play had acceptable frame pacing and no runaway game speed."))
    gates.append(gate("stable_30_minutes", threshold_or_legacy(manual, "stable_minutes", 30, "stable_30_minutes"),
                      "Counted representative stable play must be >=30 minutes; legacy boolean remains supported."))
    gates.append(gate("three_cold_launches", threshold_or_legacy(manual, "cold_launches", 3, "three_cold_launches"),
                      "Counted successful cold launches must be >=3; legacy boolean remains supported."))
    gates.append(gate("two_suspend_resume_cycles", threshold_or_legacy(manual, "suspend_resume_cycles", 2, "two_suspend_resume_cycles"),
                      "Counted successful background/foreground cycles must be >=2; legacy boolean remains supported."))
    gates.append(gate("repeatable_profile", manual_bool(manual, "repeatable_profile"),
                      "Device observation: documented final profile reproduced the same result from a clean Madeira start."))

    required = [g for g in gates if g["required"]]
    counts = {s: sum(1 for g in required if g["status"] == s) for s in ("PASS", "FAIL", "UNKNOWN")}
    complete = counts["FAIL"] == 0 and counts["UNKNOWN"] == 0
    overall = "NOT_READY_FAILED_GATE" if counts["FAIL"] else "NOT_READY_MISSING_EVIDENCE" if counts["UNKNOWN"] else "ACCEPTED"
    next_gate = next((g for g in required if g["status"] != "PASS"), None)
    return {
        "schema": SCHEMA,
        "overall": overall,
        "accepted": complete,
        "counts": counts,
        "next_unproven_gate": next_gate,
        "gates": gates,
        "thresholds": {"pointer_points": 9, "stable_minutes": 30, "cold_launches": 3, "suspend_resume_cycles": 2},
        "rule": "Unknown is never pass. Counted gates must meet their threshold. The port is accepted only when every required gate is PASS.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate HunieCam iPad/Madeira acceptance gates")
    parser.add_argument("--preflight", type=pathlib.Path)
    parser.add_argument("--session", type=pathlib.Path)
    parser.add_argument("--save-verification", type=pathlib.Path,
                        help="JSON from huniecam_save_probe.py verify BEFORE AFTER RELAUNCH")
    parser.add_argument("--manual", type=pathlib.Path, help="JSON with explicit device observations/counts")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = evaluate(load(args.preflight), load(args.session), load(args.save_verification), load(args.manual))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
