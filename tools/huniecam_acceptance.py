#!/usr/bin/env python3
"""Hard acceptance gates for the HunieCam iPad/Madeira port.

Cycle 6 Acceptance V7 requires Run Context V2 (guard/performance sealed), exact
same-run primary device observations, Save Verify V2 from one hashed expected
HunieCam save folder, and Repeatability V2 proving three distinct sealed cold
launches on one owned build/profile. Unknown evidence never passes.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_ACCEPTANCE_V7"
POINTER_POINTS = {"top_left", "top_center", "top_right", "middle_left", "center", "middle_right", "bottom_left", "bottom_center", "bottom_right"}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def _manual_payload(manual: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manual: return None
    normalized = manual.get("normalized")
    return normalized if isinstance(normalized, dict) else manual


def manual_bool(manual: dict[str, Any] | None, key: str) -> bool | None:
    payload = _manual_payload(manual)
    if not payload or key not in payload: return None
    value = payload[key]; return value if isinstance(value, bool) else None


def number(manual: dict[str, Any] | None, key: str) -> float | None:
    payload = _manual_payload(manual)
    if not payload or key not in payload: return None
    value = payload[key]
    return None if isinstance(value, bool) or not isinstance(value, (int, float)) else float(value)


def threshold_or_legacy(manual: dict[str, Any] | None, numeric_key: str, minimum: float, legacy_key: str) -> bool | None:
    value = number(manual, numeric_key)
    return value >= minimum if value is not None else manual_bool(manual, legacy_key)


def pointer_gate(manual: dict[str, Any] | None) -> bool | None:
    payload = _manual_payload(manual)
    if payload and isinstance(payload.get("pointer_grid"), list):
        seen: dict[str, bool | None] = {}
        for item in payload["pointer_grid"]:
            if not isinstance(item, dict): continue
            value = item.get("passed"); seen[str(item.get("point", ""))] = value if isinstance(value, bool) else None
        if not POINTER_POINTS.issubset(seen): return None
        required = [seen[name] for name in POINTER_POINTS]
        if any(v is False for v in required): return False
        if any(v is None for v in required): return None
        return True
    tested = number(payload, "pointer_points_tested"); passed = number(payload, "pointer_points_passed")
    if tested is not None or passed is not None: return None if tested is None or passed is None else tested >= 9 and passed == tested
    return manual_bool(payload, "pointer_aligned")


def trial_gate(manual: dict[str, Any] | None, list_key: str, minimum: int, numeric_key: str, legacy_key: str) -> bool | None:
    payload = _manual_payload(manual)
    if payload and isinstance(payload.get(list_key), list):
        values = []
        for item in payload[list_key]:
            if not isinstance(item, dict): continue
            value = item.get("success"); values.append(value if isinstance(value, bool) else None)
        if len(values) < minimum: return None
        required = values[:minimum]
        if any(v is False for v in required): return False
        if any(v is None for v in required): return None
        return True
    return threshold_or_legacy(payload, numeric_key, minimum, legacy_key)


def context_gate(run_context: dict[str, Any] | None) -> bool | None:
    if run_context is None: return None
    return bool(run_context.get("schema") == "MADEIRA_HUNIECAM_RUN_CONTEXT_V2" and run_context.get("ready") and run_context.get("run_id_sha256") and run_context.get("guard_sha256") and run_context.get("performance_sha256"))


def device_run_link(manual: dict[str, Any] | None, run_context: dict[str, Any] | None) -> bool | None:
    payload = _manual_payload(manual)
    if not payload or not run_context: return None
    expected = (run_context.get("run_id_sha256"), run_context.get("build_fingerprint_sha256"), run_context.get("profile_sha256")); observed = (payload.get("run_id_sha256"), payload.get("build_fingerprint_sha256"), payload.get("profile_sha256"))
    if any(not x for x in expected) or any(not x for x in observed): return None
    return observed == expected


def save_v2_gate(save_verification: dict[str, Any] | None) -> bool | None:
    if save_verification is None: return None
    return bool(save_verification.get("schema") == "MADEIRA_HUNIECAM_SAVE_VERIFY_V2" and save_verification.get("same_source_directory_proven") and save_verification.get("expected_save_folder_proven") and save_verification.get("machine_gate_pass") and not save_verification.get("errors"))


def repeatability_gate(repeatability: dict[str, Any] | None, run_context: dict[str, Any] | None) -> bool | None:
    if not repeatability or not run_context: return None
    if repeatability.get("schema") != "MADEIRA_HUNIECAM_REPEATABILITY_V2" or not repeatability.get("passed"): return False
    if repeatability.get("build_fingerprint_sha256") != run_context.get("build_fingerprint_sha256") or repeatability.get("profile_sha256") != run_context.get("profile_sha256"): return False
    runs = repeatability.get("runs") if isinstance(repeatability.get("runs"), list) else []; run_ids = {r.get("run_id_sha256") for r in runs if isinstance(r, dict) and r.get("run_id_sha256")}; primary = run_context.get("run_id_sha256")
    if not primary: return None
    return primary in run_ids and len(run_ids) >= 3


def gate(name: str, value: bool | None, evidence: str) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if value is True else "FAIL" if value is False else "UNKNOWN", "required": True, "evidence": evidence}


def evaluate(preflight: dict[str, Any] | None, session: dict[str, Any] | None, save_verification: dict[str, Any] | None, manual: dict[str, Any] | None, performance: dict[str, Any] | None = None, evidence_contract: dict[str, Any] | None = None, run_context: dict[str, Any] | None = None, repeatability: dict[str, Any] | None = None) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    owned_identity = None
    if preflight:
        pe = preflight.get("identity", {}).get("pe", {}); owned_identity = bool(preflight.get("exe_found")) and bool(pe.get("valid_pe")) and bool(preflight.get("identity", {}).get("exe_sha256"))
    gates.append(gate("owned_game_identity", owned_identity, "Preflight proved a real owned Windows PE executable and SHA-256."))
    gates.append(gate("evidence_contract_valid", None if evidence_contract is None else bool(evidence_contract.get("valid") and evidence_contract.get("schema") == "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V3"), "Current evidence contract must validate the sealed launch."))
    gates.append(gate("run_context_v2_ready", context_gate(run_context), "Run Context V2 must seal session, profile, guard, performance and logs to one launch ID."))
    gates.append(gate("device_evidence_same_run", device_run_link(manual, run_context), "Primary device observations must carry the same run ID/build/profile."))
    gates.append(gate("jit_and_memory_ready", manual_bool(manual, "jit_memory_ready"), "Madeira showed JIT and Memory+ ready before launch."))
    stage = int(session.get("deepest_stage", 0)) if session else 0
    gates.append(gate("windows_launch", stage >= 20 if session else None, "Session triage reached Windows executable stage >=20.")); gates.append(gate("game_managed_code", stage >= 65 if session else None, "Session triage reached game managed code stage >=65."))
    gates.append(gate("real_gameplay", manual_bool(manual, "real_gameplay"), "Real management gameplay was interactive, not just splash/menu.")); gates.append(gate("rendering_correct", manual_bool(manual, "rendering_correct"), "Text, sprites, panels and effects rendered correctly.")); gates.append(gate("pointer_grid", pointer_gate(manual), "All nine pointer targets must pass.")); gates.append(gate("audio_correct", manual_bool(manual, "audio_correct"), "Music/effects were present and stable."))

    write_detected = persistence = machine = None
    if save_verification:
        if "progress_write_detected" in save_verification: write_detected = bool(save_verification.get("progress_write_detected"))
        if "save_tree_survived_relaunch" in save_verification: persistence = bool(save_verification.get("save_tree_survived_relaunch"))
        if "machine_gate_pass" in save_verification: machine = bool(save_verification.get("machine_gate_pass"))
    gates.append(gate("save_write_detected", write_detected, "BEFORE→AFTER save tree changed.")); gates.append(gate("save_survives_relaunch", persistence, "Post-progress save tree survived full relaunch.")); gates.append(gate("save_verify_v2_exact_folder", save_v2_gate(save_verification), "Save Verify V2 must prove one exact hashed directory and expected HunieCam Studio folder.")); gates.append(gate("save_machine_verification", machine, "Machine save gate requires write + persistence.")); gates.append(gate("save_progress_visible_after_relaunch", manual_bool(manual, "save_progress_visible_after_relaunch"), "The relaunched game visibly restored the same progress."))

    perf_clean = None if performance is None else bool(performance.get("comparison_clean")); gates.append(gate("performance_measurement_clean", perf_clean, "Measured performance must prove the intended cap and clean device state.")); gates.append(gate("performance_acceptable", manual_bool(manual, "performance_acceptable"), "Busy play remained acceptably responsive with no runaway timing.")); gates.append(gate("stable_30_minutes", threshold_or_legacy(manual, "stable_minutes", 30, "stable_30_minutes"), "Representative play stayed stable for >=30 minutes.")); gates.append(gate("three_cold_launches_observed", trial_gate(manual, "cold_launch_trials", 3, "cold_launches", "three_cold_launches"), "Three cold launches were visibly successful.")); gates.append(gate("three_sealed_cold_launches", repeatability_gate(repeatability, run_context), "Repeatability V2 proves >=3 distinct Context V2 run IDs on one build/profile, including the primary run.")); gates.append(gate("two_suspend_resume_cycles", trial_gate(manual, "suspend_resume_trials", 2, "suspend_resume_cycles", "two_suspend_resume_cycles"), "Two background/foreground cycles succeeded.")); gates.append(gate("repeatable_profile", manual_bool(manual, "repeatable_profile"), "The documented final profile reproduced the result from a clean Madeira start."))

    counts = {s: sum(1 for g in gates if g["status"] == s) for s in ("PASS", "FAIL", "UNKNOWN")}; complete = counts["FAIL"] == 0 and counts["UNKNOWN"] == 0; overall = "NOT_READY_FAILED_GATE" if counts["FAIL"] else "NOT_READY_MISSING_EVIDENCE" if counts["UNKNOWN"] else "ACCEPTED"; next_gate = next((g for g in gates if g["status"] != "PASS"), None)
    return {"schema": SCHEMA, "overall": overall, "accepted": complete, "run_id_sha256": run_context.get("run_id_sha256") if run_context else None, "counts": counts, "next_unproven_gate": next_gate, "gates": gates, "thresholds": {"pointer_points": 9, "stable_minutes": 30, "cold_launches": 3, "sealed_cold_launches": 3, "suspend_resume_cycles": 2}, "rule": "Unknown is never pass. Final acceptance requires current Context V2 + Contract V3 + Save Verify V2 + Repeatability V2, same-run device evidence and clean measured performance."}


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate HunieCam iPad/Madeira final acceptance")
    p.add_argument("--preflight", type=pathlib.Path); p.add_argument("--session", type=pathlib.Path); p.add_argument("--save-verification", type=pathlib.Path); p.add_argument("--manual", type=pathlib.Path); p.add_argument("--performance", type=pathlib.Path); p.add_argument("--evidence-contract", type=pathlib.Path); p.add_argument("--run-context", type=pathlib.Path); p.add_argument("--repeatability", type=pathlib.Path); p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args(); report = evaluate(load(args.preflight), load(args.session), load(args.save_verification), load(args.manual), load(args.performance), load(args.evidence_contract), load(args.run_context), load(args.repeatability)); text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text); return 0 if report["accepted"] else 2


if __name__ == "__main__": raise SystemExit(main())
