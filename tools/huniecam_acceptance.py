#!/usr/bin/env python3
"""Evidence-based acceptance gates for the HunieCam iPad/Madeira port.

Cycle 6 adds a same-launch requirement: device observations must be linked to the
sealed run context they describe. It also understands the normalized wrapper
emitted by huniecam_device_evidence.py. Missing evidence remains UNKNOWN and can
never pass; machine provenance/performance gates cannot be manually overridden.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ACCEPTANCE_V5"
POINTER_POINTS = {
    "top_left", "top_center", "top_right",
    "middle_left", "center", "middle_right",
    "bottom_left", "bottom_center", "bottom_right",
}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _manual_payload(manual: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manual:
        return None
    normalized = manual.get("normalized")
    if isinstance(normalized, dict):
        return normalized
    return manual


def manual_bool(manual: dict[str, Any] | None, key: str) -> bool | None:
    payload = _manual_payload(manual)
    if not payload or key not in payload:
        return None
    value = payload[key]
    return value if isinstance(value, bool) else None


def number(manual: dict[str, Any] | None, key: str) -> float | None:
    payload = _manual_payload(manual)
    if not payload or key not in payload:
        return None
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def threshold_or_legacy(manual: dict[str, Any] | None, numeric_key: str, minimum: float, legacy_key: str) -> bool | None:
    value = number(manual, numeric_key)
    if value is not None:
        return value >= minimum
    return manual_bool(manual, legacy_key)


def pointer_gate(manual: dict[str, Any] | None) -> bool | None:
    payload = _manual_payload(manual)
    if payload and isinstance(payload.get("pointer_grid"), list):
        seen: dict[str, bool | None] = {}
        for item in payload["pointer_grid"]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("point", ""))
            value = item.get("passed")
            seen[name] = value if isinstance(value, bool) else None
        if not POINTER_POINTS.issubset(seen):
            return None
        required = [seen[name] for name in POINTER_POINTS]
        if any(v is False for v in required):
            return False
        if any(v is None for v in required):
            return None
        return True

    tested = number(payload, "pointer_points_tested")
    passed = number(payload, "pointer_points_passed")
    if tested is not None or passed is not None:
        if tested is None or passed is None:
            return None
        return tested >= 9 and passed == tested
    return manual_bool(payload, "pointer_aligned")


def trial_gate(manual: dict[str, Any] | None, list_key: str, minimum: int, numeric_key: str, legacy_key: str) -> bool | None:
    payload = _manual_payload(manual)
    if payload and isinstance(payload.get(list_key), list):
        values: list[bool | None] = []
        for item in payload[list_key]:
            if not isinstance(item, dict):
                continue
            value = item.get("success")
            values.append(value if isinstance(value, bool) else None)
        if len(values) < minimum:
            return None
        required = values[:minimum]
        if any(v is False for v in required):
            return False
        if any(v is None for v in required):
            return None
        return True
    return threshold_or_legacy(payload, numeric_key, minimum, legacy_key)


def device_run_link(manual: dict[str, Any] | None, run_context: dict[str, Any] | None) -> bool | None:
    payload = _manual_payload(manual)
    if not payload or not run_context:
        return None
    expected = (
        run_context.get("run_id_sha256"),
        run_context.get("build_fingerprint_sha256"),
        run_context.get("profile_sha256"),
    )
    observed = (
        payload.get("run_id_sha256"),
        payload.get("build_fingerprint_sha256"),
        payload.get("profile_sha256"),
    )
    if any(not x for x in expected) or any(not x for x in observed):
        return None
    return observed == expected


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
    performance: dict[str, Any] | None = None,
    evidence_contract: dict[str, Any] | None = None,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    owned_identity = None
    if preflight:
        pe = preflight.get("identity", {}).get("pe", {})
        owned_identity = bool(preflight.get("exe_found")) and bool(pe.get("valid_pe")) and bool(preflight.get("identity", {}).get("exe_sha256"))
    gates.append(gate("owned_game_identity", owned_identity,
                      "Preflight identified a real PE executable and recorded its SHA-256."))

    contract_ok = None if evidence_contract is None else bool(evidence_contract.get("valid"))
    gates.append(gate("evidence_contract_valid", contract_ok,
                      "Evidence contract proves supported schemas and consistent owned-build/profile/run provenance."))

    context_ok = None if run_context is None else bool(run_context.get("ready") and run_context.get("run_id_sha256"))
    gates.append(gate("run_context_ready", context_ok,
                      "Cycle 6 run context seals this exact structured session/run record and Madeira/Unity log pair to one launch ID."))
    gates.append(gate("device_evidence_same_run", device_run_link(manual, run_context),
                      "Device observation form must carry the same run ID, owned-build fingerprint and launch-profile fingerprint as the sealed run context."))

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
                      "Structured nine-point sweep preferred; all four corners, four edge-midpoints and centre must pass."))
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

    perf_clean = None if performance is None else bool(performance.get("comparison_clean"))
    gates.append(gate("performance_measurement_clean", perf_clean,
                      "Automated performance evidence must contain measurements, prove the intended FPS cap, and avoid serious thermal pressure / Low Power Mode."))
    gates.append(gate("performance_acceptable", manual_bool(manual, "performance_acceptable"),
                      "Observed busy play had acceptable responsiveness/frame pacing and no runaway game speed."))

    gates.append(gate("stable_30_minutes", threshold_or_legacy(manual, "stable_minutes", 30, "stable_30_minutes"),
                      "Representative stable play must be >=30 minutes."))
    gates.append(gate("three_cold_launches", trial_gate(manual, "cold_launch_trials", 3, "cold_launches", "three_cold_launches"),
                      "Three explicit successful cold-launch trials are preferred; aggregate count/legacy boolean remain supported."))
    gates.append(gate("two_suspend_resume_cycles", trial_gate(manual, "suspend_resume_trials", 2, "suspend_resume_cycles", "two_suspend_resume_cycles"),
                      "Two explicit successful background/foreground trials are preferred; aggregate count/legacy boolean remain supported."))
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
        "run_id_sha256": run_context.get("run_id_sha256") if run_context else None,
        "counts": counts,
        "next_unproven_gate": next_gate,
        "gates": gates,
        "thresholds": {"pointer_points": 9, "stable_minutes": 30, "cold_launches": 3, "suspend_resume_cycles": 2},
        "rule": "Unknown is never pass. Final acceptance requires same-launch device observations, valid cross-file provenance and clean automated performance; manual observations cannot override machine gates.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate HunieCam iPad/Madeira acceptance gates")
    parser.add_argument("--preflight", type=pathlib.Path)
    parser.add_argument("--session", type=pathlib.Path)
    parser.add_argument("--save-verification", type=pathlib.Path,
                        help="JSON from huniecam_save_probe.py verify BEFORE AFTER RELAUNCH")
    parser.add_argument("--manual", type=pathlib.Path, help="Structured/normalized JSON from huniecam_device_evidence.py")
    parser.add_argument("--performance", type=pathlib.Path, help="JSON from huniecam_performance.py")
    parser.add_argument("--evidence-contract", type=pathlib.Path, help="JSON from huniecam_evidence_contract.py")
    parser.add_argument("--run-context", type=pathlib.Path, help="Sealed JSON from huniecam_run_context.py")
    parser.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = parser.parse_args()
    report = evaluate(
        load(args.preflight), load(args.session), load(args.save_verification), load(args.manual),
        load(args.performance), load(args.evidence_contract), load(args.run_context),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
