#!/usr/bin/env python3
"""Validate that HunieCam evidence files belong to one coherent device run.

Cycle 6 evidence-contract V3 validates build/profile/session provenance, the
owned EXE import audit, and Run Context V2 hashes for the exact guard and
performance reports. Legacy Run Context V1 remains readable for analysis but
cannot satisfy final Cycle 6 acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_EVIDENCE_CONTRACT_V3"
SUPPORTED = {
    "preflight": {"MADEIRA_HUNIECAM_PROBE_V3", "MADEIRA_HUNIECAM_PROBE_V4"},
    "session": {"MADEIRA_HUNIECAM_SESSION_V2", "MADEIRA_HUNIECAM_SESSION_V3"},
    "guard": {"MADEIRA_HUNIECAM_CONFIG_GUARD_V1", "MADEIRA_HUNIECAM_CONFIG_GUARD_V2"},
    "performance": {"MADEIRA_HUNIECAM_PERFORMANCE_V1", "MADEIRA_HUNIECAM_PERFORMANCE_V2"},
    "run_record": {"MADEIRA_HUNIECAM_RUN_RECORD_V1"},
    "run_context": {"MADEIRA_HUNIECAM_RUN_CONTEXT_V1", "MADEIRA_HUNIECAM_RUN_CONTEXT_V2"},
    "pe_imports": {"MADEIRA_HUNIECAM_PE_IMPORTS_V1"},
    "acceptance": {"MADEIRA_HUNIECAM_ACCEPTANCE_V2", "MADEIRA_HUNIECAM_ACCEPTANCE_V3", "MADEIRA_HUNIECAM_ACCEPTANCE_V4", "MADEIRA_HUNIECAM_ACCEPTANCE_V5", "MADEIRA_HUNIECAM_ACCEPTANCE_V6"},
}


def load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def _sha_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _exe_hash(preflight: dict[str, Any] | None) -> str | None:
    if not preflight: return None
    identity = preflight.get("identity") if isinstance(preflight.get("identity"), dict) else {}
    return identity.get("exe_sha256")


def validate(preflight: dict[str, Any] | None, session: dict[str, Any] | None = None, guard: dict[str, Any] | None = None, performance: dict[str, Any] | None = None, run_record: dict[str, Any] | None = None, acceptance: dict[str, Any] | None = None, run_context: dict[str, Any] | None = None, pe_imports: dict[str, Any] | None = None) -> dict[str, Any]:
    artifacts = {"preflight": preflight, "session": session, "guard": guard, "performance": performance, "run_record": run_record, "run_context": run_context, "pe_imports": pe_imports, "acceptance": acceptance}
    errors: list[str] = []; warnings: list[str] = []; schemas: dict[str, str | None] = {}
    if not preflight: errors.append("Preflight is required to anchor evidence to the owned game binary.")
    for name, value in artifacts.items():
        if value is None: continue
        schema = value.get("schema"); schemas[name] = schema; allowed = SUPPORTED.get(name, set())
        if allowed and schema not in allowed: errors.append(f"Unsupported {name} schema: {schema!r}; supported: {sorted(allowed)}")

    owned_hash = _exe_hash(preflight)
    if preflight and not owned_hash: errors.append("Preflight is missing identity.exe_sha256.")
    if session:
        embedded = session.get("preflight") if isinstance(session.get("preflight"), dict) else {}; embedded_identity = embedded.get("identity") if isinstance(embedded.get("identity"), dict) else {}; session_hash = embedded_identity.get("exe_sha256")
        if session_hash and owned_hash and session_hash != owned_hash: errors.append("Session embedded executable hash does not match the supplied preflight.")
        evidence = session.get("evidence") if isinstance(session.get("evidence"), dict) else {}
        if not evidence.get("madeira_log_present", False): warnings.append("Session report does not prove a Madeira log was present.")

    if guard:
        if guard.get("status") == "FAIL": errors.append("Config guard rejected the recorded launch profile; do not promote this run as valid evidence.")
        elif guard.get("status") == "WARN": warnings.append("Config guard contains warnings/unreviewed variables; keep them visible in any comparison.")

    record_build_fp = record_profile_fp = None
    if run_record:
        build = run_record.get("build") if isinstance(run_record.get("build"), dict) else {}; material = build.get("material") if isinstance(build.get("material"), dict) else {}; record_hash = material.get("exe_sha256"); record_build_fp = build.get("fingerprint_sha256"); record_profile_fp = run_record.get("profile_sha256")
        if record_hash and owned_hash and record_hash != owned_hash: errors.append("Run record executable hash does not match the supplied preflight.")
        if not run_record.get("ready_for_comparison"): errors.append("Run record is not ready_for_comparison.")
        if session:
            rec_session = run_record.get("session") if isinstance(run_record.get("session"), dict) else {}
            if int(rec_session.get("deepest_stage", -1)) != int(session.get("deepest_stage", 0)): errors.append("Run record deepest stage does not match the session report.")

    context_v2 = bool(run_context and run_context.get("schema") == "MADEIRA_HUNIECAM_RUN_CONTEXT_V2")
    if run_context:
        if not run_context.get("ready"): errors.append("Run context is not ready; this launch cannot be treated as a sealed evidence set.")
        if run_record:
            if run_context.get("build_fingerprint_sha256") != record_build_fp: errors.append("Run context owned-build fingerprint does not match the run record.")
            if run_context.get("profile_sha256") != record_profile_fp: errors.append("Run context launch-profile fingerprint does not match the run record.")
            if run_context.get("run_record_sha256") != _sha_json(run_record): errors.append("Run context does not hash the supplied run record; evidence may come from different launches.")
        if session and run_context.get("session_sha256") != _sha_json(session): errors.append("Run context does not hash the supplied session report; evidence may come from different launches.")
        if context_v2:
            if guard is not None and run_context.get("guard_sha256") != _sha_json(guard): errors.append("Run context does not hash the supplied config-guard report; evidence may come from different launches.")
            if performance is not None and run_context.get("performance_sha256") != _sha_json(performance): errors.append("Run context does not hash the supplied performance report; evidence may come from different launches.")
            if guard is None and run_context.get("guard_sha256"): errors.append("Run context seals a guard report but none was supplied to the contract.")
            if performance is None and run_context.get("performance_sha256"): errors.append("Run context seals a performance report but none was supplied to the contract.")
        else:
            warnings.append("Legacy Run Context V1 does not seal guard/performance JSON; it is inspectable but insufficient for final Cycle 6 acceptance.")
        logs = run_context.get("logs") if isinstance(run_context.get("logs"), dict) else {}; madeira = logs.get("madeira") if isinstance(logs.get("madeira"), dict) else {}
        if not madeira.get("present"): errors.append("Run context does not prove a Madeira log was present.")
    else:
        warnings.append("No per-launch run context supplied. Legacy analysis is allowed, but final Cycle 6 acceptance must include Run Context V2.")

    if pe_imports:
        if not pe_imports.get("valid"): errors.append("PE import audit is invalid; dependency conclusions must remain unproven.")
        import_hash = pe_imports.get("file_sha256")
        if import_hash and owned_hash and import_hash != owned_hash: errors.append("PE import audit came from a different executable than the preflight identity.")

    if performance:
        cap = performance.get("fps_cap") if isinstance(performance.get("fps_cap"), dict) else {}
        if cap and cap.get("expected") is not None and cap.get("effective") is False: warnings.append("The intended FPS cap was not proven effective; timing/performance acceptance must remain unproven.")

    if acceptance and acceptance.get("accepted") is True:
        if errors: errors.append("Acceptance says ACCEPTED while the evidence contract has provenance/schema errors.")
        if performance and not performance.get("comparison_clean", False): errors.append("Acceptance says ACCEPTED but supplied performance evidence is not clean/comparable.")
        if run_context is None: errors.append("Cycle 6 acceptance says ACCEPTED without a per-launch run context.")
        elif not context_v2: errors.append("Cycle 6 acceptance requires Run Context V2 so guard and performance evidence are sealed.")
        elif acceptance.get("run_id_sha256") and acceptance.get("run_id_sha256") != run_context.get("run_id_sha256"): errors.append("Acceptance report run ID does not match the supplied sealed run context.")

    return {"schema": SCHEMA, "valid": not errors, "owned_executable_sha256": owned_hash, "run_id_sha256": run_context.get("run_id_sha256") if run_context else None, "run_context_v2_complete": context_v2 and bool(run_context and run_context.get("guard_sha256") and run_context.get("performance_sha256")), "artifact_schemas": schemas, "present_artifacts": [name for name, value in artifacts.items() if value is not None], "errors": errors, "warnings": warnings, "rule": "Never combine evidence across owned executables or launch run IDs. Final Cycle 6 acceptance requires Run Context V2, sealing the exact guard and performance reports too."}


def main() -> int:
    p = argparse.ArgumentParser(description="Validate one HunieCam evidence set")
    p.add_argument("--preflight", type=pathlib.Path, required=True); p.add_argument("--session", type=pathlib.Path); p.add_argument("--guard", type=pathlib.Path); p.add_argument("--performance", type=pathlib.Path); p.add_argument("--run-record", type=pathlib.Path); p.add_argument("--run-context", type=pathlib.Path); p.add_argument("--pe-imports", type=pathlib.Path); p.add_argument("--acceptance", type=pathlib.Path); p.add_argument("--json", dest="json_path", type=pathlib.Path)
    args = p.parse_args(); report = validate(load(args.preflight), load(args.session), load(args.guard), load(args.performance), load(args.run_record), load(args.acceptance), load(args.run_context), load(args.pe_imports)); text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path: args.json_path.write_text(text + "\n", encoding="utf-8")
    print(text); return 0 if report["valid"] else 2


if __name__ == "__main__": raise SystemExit(main())
