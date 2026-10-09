#!/usr/bin/env python3
"""Validate that HunieCam evidence files belong to one coherent device run.

The contract catches stale/mixed JSON before downstream tools use it. It does
not require every optional artifact, but any artifact supplied must have a
supported schema and agree on the owned executable/build provenance.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V1"
SUPPORTED = {
    "preflight": {"MADEIRA_HUNIECAM_PROBE_V3", "MADEIRA_HUNIECAM_PROBE_V4"},
    "session": {"MADEIRA_HUNIECAM_SESSION_V2"},
    "guard": {"MADEIRA_HUNIECAM_CONFIG_GUARD_V1", "MADEIRA_HUNIECAM_CONFIG_GUARD_V2"},
    "performance": {"MADEIRA_HUNIECAM_PERFORMANCE_V1", "MADEIRA_HUNIECAM_PERFORMANCE_V2"},
    "run_record": {"MADEIRA_HUNIECAM_RUN_RECORD_V1"},
    "acceptance": {"MADEIRA_HUNIECAM_ACCEPTANCE_V2", "MADEIRA_HUNIECAM_ACCEPTANCE_V3", "MADEIRA_HUNIECAM_ACCEPTANCE_V4"},
}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _exe_hash(preflight: dict[str, Any] | None) -> str | None:
    if not preflight:
        return None
    identity = preflight.get("identity") if isinstance(preflight.get("identity"), dict) else {}
    return identity.get("exe_sha256")


def validate(
    preflight: dict[str, Any] | None,
    session: dict[str, Any] | None = None,
    guard: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    run_record: dict[str, Any] | None = None,
    acceptance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts = {
        "preflight": preflight,
        "session": session,
        "guard": guard,
        "performance": performance,
        "run_record": run_record,
        "acceptance": acceptance,
    }
    errors: list[str] = []
    warnings: list[str] = []
    schemas: dict[str, str | None] = {}

    if not preflight:
        errors.append("Preflight is required to anchor evidence to the owned game binary.")

    for name, value in artifacts.items():
        if value is None:
            continue
        schema = value.get("schema")
        schemas[name] = schema
        allowed = SUPPORTED.get(name, set())
        if allowed and schema not in allowed:
            errors.append(f"Unsupported {name} schema: {schema!r}; supported: {sorted(allowed)}")

    owned_hash = _exe_hash(preflight)
    if preflight and not owned_hash:
        errors.append("Preflight is missing identity.exe_sha256.")

    if session:
        embedded = session.get("preflight") if isinstance(session.get("preflight"), dict) else {}
        embedded_identity = embedded.get("identity") if isinstance(embedded.get("identity"), dict) else {}
        session_hash = embedded_identity.get("exe_sha256")
        if session_hash and owned_hash and session_hash != owned_hash:
            errors.append("Session embedded executable hash does not match the supplied preflight.")
        evidence = session.get("evidence") if isinstance(session.get("evidence"), dict) else {}
        if not evidence.get("madeira_log_present", False):
            warnings.append("Session report does not prove a Madeira log was present.")

    if guard:
        if guard.get("status") == "FAIL":
            errors.append("Config guard rejected the recorded launch profile; do not promote this run as valid evidence.")
        elif guard.get("status") == "WARN":
            warnings.append("Config guard contains warnings/unreviewed variables; keep them visible in any comparison.")

    if run_record:
        build = run_record.get("build") if isinstance(run_record.get("build"), dict) else {}
        material = build.get("material") if isinstance(build.get("material"), dict) else {}
        record_hash = material.get("exe_sha256")
        if record_hash and owned_hash and record_hash != owned_hash:
            errors.append("Run record executable hash does not match the supplied preflight.")
        if not run_record.get("ready_for_comparison"):
            errors.append("Run record is not ready_for_comparison.")
        if session:
            rec_session = run_record.get("session") if isinstance(run_record.get("session"), dict) else {}
            if int(rec_session.get("deepest_stage", -1)) != int(session.get("deepest_stage", 0)):
                errors.append("Run record deepest stage does not match the session report.")

    if performance:
        cap = performance.get("fps_cap") if isinstance(performance.get("fps_cap"), dict) else {}
        if cap and cap.get("expected") is not None and cap.get("effective") is False:
            warnings.append("The intended FPS cap was not proven effective; timing/performance acceptance must remain unproven.")

    if acceptance and acceptance.get("accepted") is True:
        if errors:
            errors.append("Acceptance says ACCEPTED while the evidence contract has provenance/schema errors.")
        if performance and not performance.get("comparison_clean", False):
            errors.append("Acceptance says ACCEPTED but supplied performance evidence is not clean/comparable.")

    return {
        "schema": SCHEMA,
        "valid": not errors,
        "owned_executable_sha256": owned_hash,
        "artifact_schemas": schemas,
        "present_artifacts": [name for name, value in artifacts.items() if value is not None],
        "errors": errors,
        "warnings": warnings,
        "rule": "Never combine evidence across different owned executable hashes. Unsupported/stale schemas and guard-rejected profiles must be repaired before a run can be promoted.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Validate one HunieCam evidence set")
    p.add_argument("--preflight", type=pathlib.Path, required=True)
    p.add_argument("--session", type=pathlib.Path)
    p.add_argument("--guard", type=pathlib.Path)
    p.add_argument("--performance", type=pathlib.Path)
    p.add_argument("--run-record", type=pathlib.Path)
    p.add_argument("--acceptance", type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args()
    report = validate(
        load(args.preflight), load(args.session), load(args.guard),
        load(args.performance), load(args.run_record), load(args.acceptance),
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
