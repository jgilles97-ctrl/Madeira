#!/usr/bin/env python3
"""Compare two sealed HunieCam input-mode experiments using real gameplay evidence.

Changing Madeira input mode is now a profile change, so direct-finger vs
touch-pointer tests must be separate sealed runs. This helper proves the same
owned build/native modules were used, input_mode was the only profile variable,
each Device Evidence V3 file belongs to its exact run, and the nine-point pointer
baseline remained valid before judging HunieCam's real drag/release outcome.

Hardware mouse/trackpad may be used as a diagnostic comparator, but never becomes
a recommended final touch mode.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import huniecam_run_compare as run_compare

SCHEMA = "MADEIRA_HUNIECAM_INPUT_AB_V1"
DEVICE_SCHEMA = "MADEIRA_HUNIECAM_DEVICE_EVIDENCE_V3"
TOUCH_MODES = {"direct_finger", "touch_pointer"}
HARDWARE_MODES = {"hardware_mouse", "hardware_trackpad"}
POINTER_POINTS = {"top_left","top_center","top_right","middle_left","center","middle_right","bottom_left","bottom_center","bottom_right"}


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    normalized = data.get("normalized")
    return normalized if isinstance(normalized, dict) else data


def _pointer(payload: dict[str, Any]) -> bool | None:
    rows = payload.get("pointer_grid") if isinstance(payload.get("pointer_grid"), list) else []
    if rows:
        seen: dict[str, bool | None] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            value = item.get("passed")
            seen[str(item.get("point", ""))] = value if isinstance(value, bool) else None
        if not POINTER_POINTS.issubset(seen):
            return None
        vals = [seen[name] for name in POINTER_POINTS]
        if any(v is False for v in vals):
            return False
        if any(v is None for v in vals):
            return None
        return True
    tested, passed = payload.get("pointer_points_tested"), payload.get("pointer_points_passed")
    if isinstance(tested, (int, float)) and not isinstance(tested, bool) and isinstance(passed, (int, float)) and not isinstance(passed, bool):
        return tested >= 9 and passed == tested
    return None


def _drag(payload: dict[str, Any]) -> tuple[bool | None, str | None]:
    rows = [x for x in (payload.get("drag_release_trials") if isinstance(payload.get("drag_release_trials"), list) else []) if isinstance(x, dict)]
    if len(rows) < 3:
        return None, None
    rows = rows[:3]
    modes = [x.get("input_mode") if isinstance(x.get("input_mode"), str) else None for x in rows]
    if any(m is None for m in modes) or len(set(modes)) != 1:
        return False, None
    vals: list[bool | None] = []
    for row in rows:
        steps=[]
        for key in ("press_registered", "movement_registered", "release_registered", "game_response_registered"):
            value=row.get(key);steps.append(value if isinstance(value, bool) else None)
        if any(v is False for v in steps):
            vals.append(False)
        elif any(v is None for v in steps):
            vals.append(None)
        else:
            vals.append(True)
    if any(v is False for v in vals):
        return False, modes[0]
    if any(v is None for v in vals):
        return None, modes[0]
    return True, modes[0]


def _context_record_link(context: dict[str, Any], record: dict[str, Any]) -> list[str]:
    errors=[]
    build=record.get("build") if isinstance(record.get("build"), dict) else {}
    profile=record.get("profile") if isinstance(record.get("profile"), dict) else {}
    if context.get("schema") != "MADEIRA_HUNIECAM_RUN_CONTEXT_V2" or not context.get("ready"):
        errors.append("Run context is not current ready Context V2.")
    if not record.get("ready_for_comparison"):
        errors.append("Run record is not ready_for_comparison.")
    if context.get("build_fingerprint_sha256") != build.get("fingerprint_sha256"):
        errors.append("Run context build fingerprint does not match run record.")
    if context.get("profile_sha256") != record.get("profile_sha256"):
        errors.append("Run context profile fingerprint does not match run record.")
    if context.get("input_mode") != profile.get("input_mode"):
        errors.append("Run context input mode does not match hashed run profile.")
    if not context.get("run_id_sha256"):
        errors.append("Run context has no sealed run ID.")
    return errors


def _device_link(device: dict[str, Any], context: dict[str, Any]) -> list[str]:
    payload=_payload(device);errors=[]
    if payload.get("schema") != DEVICE_SCHEMA:
        errors.append(f"Device evidence is not current {DEVICE_SCHEMA}.")
    for key in ("run_id_sha256", "build_fingerprint_sha256", "profile_sha256"):
        if not payload.get(key) or payload.get(key) != context.get(key):
            errors.append(f"Device evidence {key} does not match its sealed run context.")
    return errors


def compare(before_record: dict[str, Any], before_context: dict[str, Any], before_device: dict[str, Any], after_record: dict[str, Any], after_context: dict[str, Any], after_device: dict[str, Any]) -> dict[str, Any]:
    errors=[]
    errors.extend(f"before: {x}" for x in _context_record_link(before_context, before_record))
    errors.extend(f"after: {x}" for x in _context_record_link(after_context, after_record))
    errors.extend(f"before: {x}" for x in _device_link(before_device, before_context))
    errors.extend(f"after: {x}" for x in _device_link(after_device, after_context))

    before_build=(before_record.get("build") or {}).get("fingerprint_sha256") if isinstance(before_record.get("build"),dict) else None
    after_build=(after_record.get("build") or {}).get("fingerprint_sha256") if isinstance(after_record.get("build"),dict) else None
    if not before_build or before_build != after_build:
        errors.append("The runs do not use the same owned-build fingerprint.")
    if before_context.get("native_module_set_sha256") != after_context.get("native_module_set_sha256"):
        errors.append("The runs do not use the same bundled native-module set.")
    if before_context.get("run_id_sha256") == after_context.get("run_id_sha256"):
        errors.append("A/B comparison requires two distinct sealed run IDs.")

    before_profile=before_record.get("profile") if isinstance(before_record.get("profile"),dict) else {}
    after_profile=after_record.get("profile") if isinstance(after_record.get("profile"),dict) else {}
    changes=run_compare.profile_changes(before_profile, after_profile)
    changed_keys=[x.get("key") for x in changes]
    if changed_keys != ["input_mode"]:
        errors.append(f"Input A/B must change only input_mode; observed profile changes: {changed_keys}.")

    before_payload=_payload(before_device);after_payload=_payload(after_device)
    before_pointer=_pointer(before_payload);after_pointer=_pointer(after_payload)
    before_drag,before_mode=_drag(before_payload);after_drag,after_mode=_drag(after_payload)
    if before_mode != before_profile.get("input_mode"):
        errors.append("Before device drag mode does not match before sealed run profile.")
    if after_mode != after_profile.get("input_mode"):
        errors.append("After device drag mode does not match after sealed run profile.")

    if errors:
        status="INVALID_EXPERIMENT";keep=False;recommended=None;reason=errors[0]
    elif before_pointer is not True or after_pointer is not True:
        status="POINTER_BASELINE_NOT_PROVEN";keep=False;recommended=None;reason="Both runs must pass the same nine-point pointer baseline before drag/release differences can be attributed to input mode."
    elif before_drag is True and after_drag is True:
        status="BOTH_MODES_WORK";keep=False;recommended=before_mode if before_mode in TOUCH_MODES else after_mode if after_mode in TOUCH_MODES else None;reason="Both tested modes complete real HunieCam drag/release; keep the already-working touch mode unless another measured usability reason justifies switching."
    elif before_drag is not True and after_drag is True:
        if after_mode in TOUCH_MODES:
            status="TOUCH_MODE_IMPROVED";keep=True;recommended=after_mode;reason="The single input-mode change converted incomplete/failed real gameplay drag evidence into three complete touch drag/releases."
        else:
            status="HARDWARE_DIAGNOSTIC_IMPROVED";keep=False;recommended=None;reason="Hardware pointer succeeds where the prior mode did not. This diagnoses the input path but cannot become the touch-first final mode."
    elif before_drag is True and after_drag is not True:
        status="REGRESSION";keep=False;recommended=before_mode if before_mode in TOUCH_MODES else None;reason="The input-mode change regressed real drag/release behavior. Roll it back."
    elif before_drag is False and after_drag is False:
        status="NO_TOUCH_IMPROVEMENT";keep=False;recommended=None;reason="Both modes fail real drag/release. Do not retain the change; use the source/runtime input evidence to isolate the common failure."
    else:
        status="INCONCLUSIVE";keep=False;recommended=None;reason="At least one run has incomplete/unknown drag evidence. Complete three trials in each sealed run before promoting a mode."

    return {
        "schema":SCHEMA,
        "valid_experiment":not errors,
        "status":status,
        "profile_changes":changes,
        "before":{"run_id_sha256":before_context.get("run_id_sha256"),"input_mode":before_mode,"pointer_grid":before_pointer,"drag_release":before_drag},
        "after":{"run_id_sha256":after_context.get("run_id_sha256"),"input_mode":after_mode,"pointer_grid":after_pointer,"drag_release":after_drag},
        "keep_after_mode":keep,
        "recommended_final_touch_mode":recommended,
        "errors":errors,
        "reason":reason,
        "rule":"Input A/B evidence is promotable only when two distinct sealed runs use the same owned build/native modules, input_mode is the only profile change, each Device V3 report belongs to its run, and both pointer baselines pass. Hardware pointer success is diagnostic only.",
    }


def load(path:pathlib.Path)->dict[str,Any]:return json.loads(path.read_text(encoding="utf-8"))
def main()->int:
    p=argparse.ArgumentParser(description="Compare two sealed HunieCam input-mode runs")
    for side in ("before","after"):
        p.add_argument(f"--{side}-record",type=pathlib.Path,required=True);p.add_argument(f"--{side}-context",type=pathlib.Path,required=True);p.add_argument(f"--{side}-device",type=pathlib.Path,required=True)
    p.add_argument("--json",dest="json_path",type=pathlib.Path);args=p.parse_args();report=compare(load(args.before_record),load(args.before_context),load(args.before_device),load(args.after_record),load(args.after_context),load(args.after_device));text=json.dumps(report,indent=2,sort_keys=True)
    if args.json_path:args.json_path.write_text(text+"\n",encoding="utf-8")
    print(text);return 0 if report["valid_experiment"] else 2
if __name__=="__main__":raise SystemExit(main())
