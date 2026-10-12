#!/usr/bin/env python3
"""Combine Sims 4 iPad payload, runtime, optional EA-prefix, and device-log evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "SIMS4_IPAD_EVIDENCE_V1"


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
        expected["ea_prefix"] = "SIMS4_EA_PREFIX_AUDIT_V1"
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

    if not payload_ready:
        next_gate = preflight.get("next_gate") or "FIX_STATIC_PAYLOAD"
    elif ea_prefix is not None and not ea_static_ready:
        next_gate = ea_prefix.get("next_gate") or "FIX_EA_PREFIX_STATIC_BLOCKERS"
    else:
        next_gate = triage.get("next_gate") or (
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
        "dlc_count": preflight.get("dlc_count"),
        "payload_ready": payload_ready,
        "triage_findings": triage.get("findings", []),
        "positive_signals": triage.get("positive_signals", []),
        "next_gate": next_gate,
        "bundle_blockers": blockers,
        "physical_device_success": "UNPROVEN",
        "rule": (
            "This bundle records exact payload/runtime/EA-prefix evidence and the next diagnostic gate only. "
            "It never promotes a physical-device gate by itself."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a reproducible Sims 4 iPad evidence bundle")
    ap.add_argument("--preflight", required=True, type=pathlib.Path)
    ap.add_argument("--runtime-audit", required=True, type=pathlib.Path)
    ap.add_argument("--ea-prefix-audit", type=pathlib.Path, help="Optional output from sims4_ea_prefix_audit.py")
    ap.add_argument("--triage", required=True, type=pathlib.Path)
    ap.add_argument("--run-id", required=True, help="Human/device run identifier, e.g. ipad-2026-10-12-001")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    preflight, preflight_hash = load_json(args.preflight)
    runtime, runtime_hash = load_json(args.runtime_audit)
    triage, triage_hash = load_json(args.triage)
    ea_prefix = None
    hashes = {
        "preflight": preflight_hash,
        "runtime_audit": runtime_hash,
        "triage": triage_hash,
    }
    if args.ea_prefix_audit:
        ea_prefix, ea_hash = load_json(args.ea_prefix_audit)
        hashes["ea_prefix_audit"] = ea_hash

    bundle = make_bundle(
        preflight,
        runtime,
        triage,
        run_id=args.run_id,
        ea_prefix=ea_prefix,
        input_hashes=hashes,
    )
    args.out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0 if not bundle["bundle_blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
