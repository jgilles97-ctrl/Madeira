#!/usr/bin/env python3
"""Combine Sims 4 iPad payload, runtime, launcher, optional EA-prefix, and device-log evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "SIMS4_IPAD_EVIDENCE_V2"


def load_json(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def make_bundle(
    preflight: dict[str, Any],
    runtime: dict[str, Any],
    triage: dict[str, Any],
    *,
    run_id: str,
    ea_prefix: dict[str, Any] | None = None,
    launcher_canary: dict[str, Any] | None = None,
    cef_roles: dict[str, Any] | None = None,
    input_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not run_id.strip():
        raise ValueError("run_id must not be empty")

    schemas = {
        "preflight": preflight.get("schema"),
        "runtime": runtime.get("schema"),
        "triage": triage.get("schema"),
    }
    expected = {
        "preflight": "SIMS4_IPAD_PREFLIGHT_V2",
        "runtime": "SIMS4_MADEIRA_RUNTIME_AUDIT_V2",
        "triage": "SIMS4_MADEIRA_TRIAGE_V1",
    }
    if ea_prefix is not None:
        schemas["ea_prefix"] = ea_prefix.get("schema")
        expected["ea_prefix"] = "SIMS4_EA_PREFIX_AUDIT_V2"
    if launcher_canary is not None:
        schemas["launcher_canary"] = launcher_canary.get("schema")
        expected["launcher_canary"] = "SIMS4_LAUNCHER_CANARY_RESULT_V1"
    if cef_roles is not None:
        schemas["cef_roles"] = cef_roles.get("schema")
        expected["cef_roles"] = "SIMS4_EA_CEF_ROLES_V1"
    schema_ok = schemas == expected

    payload_ready = bool(preflight.get("payload_ready"))
    runtime_fp = runtime.get("runtime_fingerprint_sha256")
    ea_static_ready = None if ea_prefix is None else bool(ea_prefix.get("static_ready"))

    blockers: list[str] = []
    if not schema_ok:
        blockers.append("INPUT_SCHEMA_MISMATCH")
    if not payload_ready:
        blockers.append("STATIC_PAYLOAD_NOT_READY")
    if not runtime_fp:
        blockers.append("RUNTIME_FINGERPRINT_MISSING")
    if ea_prefix is not None and not ea_static_ready:
        blockers.append("EA_PREFIX_STATIC_NOT_READY")
    if triage.get("success_claim") not in (None, "UNPROVEN"):
        blockers.append("TRIAGE_MADE_UNSUPPORTED_SUCCESS_CLAIM")
    if launcher_canary is not None:
        if launcher_canary.get("physical_device_success") not in (None, "UNPROVEN"):
            blockers.append("CANARY_MADE_UNSUPPORTED_SUCCESS_CLAIM")
        if launcher_canary.get("failed_checks"):
            blockers.append("LAUNCHER_CANARY_HAS_FAILURES")
        if launcher_canary.get("missing_checks"):
            blockers.append("LAUNCHER_CANARY_INCOMPLETE")
        if launcher_canary.get("summary_consistent") is False:
            blockers.append("LAUNCHER_CANARY_SUMMARY_MISMATCH")

    # Gate precedence is strict: static prerequisites > launcher prerequisites >
    # log/CEF interpretation. This prevents a newer-looking EA log from
    # outranking a broken payload or failed small canary.
    if not payload_ready:
        next_gate = preflight.get("next_gate") or "FIX_STATIC_PAYLOAD"
    elif ea_prefix is not None and not ea_static_ready:
        next_gate = ea_prefix.get("next_gate") or "FIX_EA_PREFIX_STATIC_BLOCKERS"
    elif launcher_canary is not None and (
        launcher_canary.get("failed_checks")
        or launcher_canary.get("missing_checks")
        or launcher_canary.get("summary_consistent") is False
    ):
        next_gate = launcher_canary.get("next_gate") or "FIX_LAUNCHER_CANARY"
    elif triage.get("findings"):
        next_gate = triage.get("next_gate")
    elif cef_roles is not None and cef_roles.get("next_gate") not in (
        None,
        "CORRELATE_EA_CEF_ROLES_WITH_WINDOW_AND_TS4_START",
    ):
        next_gate = cef_roles.get("next_gate")
    else:
        next_gate = triage.get("next_gate") or (
            cef_roles.get("next_gate") if cef_roles else None
        ) or (
            launcher_canary.get("next_gate") if launcher_canary else None
        ) or (
            ea_prefix.get("next_gate") if ea_prefix else None
        ) or runtime.get("next_gate") or preflight.get("next_gate")

    ea_component_hashes: dict[str, str] = {}
    ea_background_ini_hash = None
    if ea_prefix is not None:
        for name, record in (ea_prefix.get("components") or {}).items():
            if isinstance(record, dict) and record.get("sha256"):
                ea_component_hashes[name] = str(record["sha256"])
        ini = ea_prefix.get("backgroundservice_ini") or {}
        if isinstance(ini, dict):
            ea_background_ini_hash = ini.get("sha256")

    canary_summary = None
    if launcher_canary is not None:
        canary_summary = {
            "failed_checks": launcher_canary.get("failed_checks", []),
            "missing_checks": launcher_canary.get("missing_checks", []),
            "summary_consistent": launcher_canary.get("summary_consistent"),
            "ea_service_stopped_observed": launcher_canary.get("ea_service_stopped_observed"),
            "dwrite_arial_resolution": launcher_canary.get("dwrite_arial_resolution"),
            "next_gate": launcher_canary.get("next_gate"),
        }

    cef_summary = None
    if cef_roles is not None:
        cef_summary = {
            "role_counts": cef_roles.get("role_counts", {}),
            "utility_sub_type_counts": cef_roles.get("utility_sub_type_counts", {}),
            "fatal_by_role": cef_roles.get("fatal_by_role", {}),
            "role_coverage": cef_roles.get("role_coverage", {}),
            "next_gate": cef_roles.get("next_gate"),
        }

    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "input_schemas": schemas,
        "input_schema_ok": schema_ok,
        "input_sha256": input_hashes or {},
        "game_executable_sha256": (preflight.get("game_executable") or {}).get("sha256"),
        "runtime_fingerprint_sha256": runtime_fp,
        "runtime_validated_launcher_coverage_present": runtime.get("validated_launcher_coverage_present"),
        "runtime_validated_launcher_coverage_total": runtime.get("validated_launcher_coverage_total"),
        "ea_prefix_included": ea_prefix is not None,
        "ea_prefix_static_ready": ea_static_ready,
        "ea_component_sha256": ea_component_hashes,
        "ea_backgroundservice_ini_sha256": ea_background_ini_hash,
        "launcher_canary_included": launcher_canary is not None,
        "launcher_canary": canary_summary,
        "cef_roles_included": cef_roles is not None,
        "cef_roles": cef_summary,
        "dlc_count": preflight.get("dlc_count"),
        "payload_ready": payload_ready,
        "triage_findings": triage.get("findings", []),
        "positive_signals": triage.get("positive_signals", []),
        "next_gate": next_gate,
        "bundle_blockers": blockers,
        "physical_device_success": "UNPROVEN",
        "rule": (
            "This bundle binds exact payload/runtime/EA-prefix/launcher/CEF evidence and the next diagnostic gate only. "
            "It never promotes a physical-device success by itself."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a reproducible Sims 4 iPad evidence bundle")
    ap.add_argument("--preflight", required=True, type=pathlib.Path)
    ap.add_argument("--runtime-audit", required=True, type=pathlib.Path)
    ap.add_argument("--ea-prefix-audit", type=pathlib.Path, help="Optional output from sims4_ea_prefix_audit.py")
    ap.add_argument("--launcher-canary", type=pathlib.Path, help="Optional output from sims4_launcher_canary_parse.py")
    ap.add_argument("--cef-roles", type=pathlib.Path, help="Optional output from sims4_ea_cef_roles.py")
    ap.add_argument("--triage", required=True, type=pathlib.Path)
    ap.add_argument("--run-id", required=True, help="Human/device run identifier, e.g. ipad-2026-10-12-001")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    preflight, preflight_hash = load_json(args.preflight)
    runtime, runtime_hash = load_json(args.runtime_audit)
    triage, triage_hash = load_json(args.triage)
    ea_prefix = None
    launcher_canary = None
    cef_roles = None
    hashes = {
        "preflight": preflight_hash,
        "runtime_audit": runtime_hash,
        "triage": triage_hash,
    }
    if args.ea_prefix_audit:
        ea_prefix, ea_hash = load_json(args.ea_prefix_audit)
        hashes["ea_prefix_audit"] = ea_hash
    if args.launcher_canary:
        launcher_canary, canary_hash = load_json(args.launcher_canary)
        hashes["launcher_canary"] = canary_hash
    if args.cef_roles:
        cef_roles, cef_hash = load_json(args.cef_roles)
        hashes["cef_roles"] = cef_hash

    bundle = make_bundle(
        preflight,
        runtime,
        triage,
        run_id=args.run_id,
        ea_prefix=ea_prefix,
        launcher_canary=launcher_canary,
        cef_roles=cef_roles,
        input_hashes=hashes,
    )
    args.out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0 if not bundle["bundle_blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
