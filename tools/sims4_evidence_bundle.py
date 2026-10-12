#!/usr/bin/env python3
"""Combine Sims 4 iPad preflight, runtime audit, and device-log triage into one evidence record."""

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
        "runtime": "SIMS4_MADEIRA_RUNTIME_AUDIT_V1",
        "triage": "SIMS4_MADEIRA_TRIAGE_V1",
    }
    schema_ok = schemas == expected

    next_gate = triage.get("next_gate") or runtime.get("next_gate") or preflight.get("next_gate")
    payload_ready = bool(preflight.get("payload_ready"))
    runtime_fp = runtime.get("runtime_fingerprint_sha256")

    blockers: list[str] = []
    if not schema_ok:
        blockers.append("INPUT_SCHEMA_MISMATCH")
    if not payload_ready:
        blockers.append("STATIC_PAYLOAD_NOT_READY")
    if not runtime_fp:
        blockers.append("RUNTIME_FINGERPRINT_MISSING")
    if triage.get("success_claim") not in (None, "UNPROVEN"):
        blockers.append("TRIAGE_MADE_UNSUPPORTED_SUCCESS_CLAIM")

    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "input_schemas": schemas,
        "input_schema_ok": schema_ok,
        "input_sha256": input_hashes or {},
        "game_executable_sha256": (preflight.get("game_executable") or {}).get("sha256"),
        "runtime_fingerprint_sha256": runtime_fp,
        "dlc_count": preflight.get("dlc_count"),
        "payload_ready": payload_ready,
        "triage_findings": triage.get("findings", []),
        "positive_signals": triage.get("positive_signals", []),
        "next_gate": next_gate,
        "bundle_blockers": blockers,
        "physical_device_success": "UNPROVEN",
        "rule": (
            "This bundle records evidence identity and the next diagnostic gate only. "
            "It never promotes a physical-device gate by itself."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a reproducible Sims 4 iPad evidence bundle")
    ap.add_argument("--preflight", required=True, type=pathlib.Path)
    ap.add_argument("--runtime-audit", required=True, type=pathlib.Path)
    ap.add_argument("--triage", required=True, type=pathlib.Path)
    ap.add_argument("--run-id", required=True, help="Human/device run identifier, e.g. ipad-2026-10-12-001")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    preflight, preflight_hash = load_json(args.preflight)
    runtime, runtime_hash = load_json(args.runtime_audit)
    triage, triage_hash = load_json(args.triage)
    bundle = make_bundle(
        preflight,
        runtime,
        triage,
        run_id=args.run_id,
        input_hashes={
            "preflight": preflight_hash,
            "runtime_audit": runtime_hash,
            "triage": triage_hash,
        },
    )
    args.out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0 if not bundle["bundle_blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
