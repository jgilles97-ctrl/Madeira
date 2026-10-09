#!/usr/bin/env python3
"""Create a privacy-minimal manifest for one HunieCam/Madeira evidence set.

Cycle 6 records sealed per-launch identity, owned-EXE dependency evidence,
run-linked device-observation setup, and cold-launch repeatability. Raw logs,
saves, binaries and credentials remain out of the manifest body.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "MADEIRA_HUNIECAM_EVIDENCE_MANIFEST_V4"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def descriptor(path: pathlib.Path | None, kind: str) -> dict[str, Any] | None:
    if path is None:
        return None
    st = path.stat()
    return {"kind": kind, "name": path.name, "bytes": st.st_size, "sha256": sha256(path)}


def load_json(path: pathlib.Path | None) -> dict[str, Any] | None:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def summary(kind: str, data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    if kind == "preflight":
        ident = data.get("identity", {})
        runtime = data.get("runtime_signals", {})
        return {"schema": data.get("schema"), "exe_found": data.get("exe_found"), "exe_sha256": ident.get("exe_sha256"), "architecture": ident.get("pe", {}).get("architecture") if isinstance(ident.get("pe"), dict) else None, "runtime_family": runtime.get("runtime_family"), "unity_versions_seen": runtime.get("unity_versions_seen"), "depot_shape": data.get("depot_shape")}
    if kind == "session":
        return {"schema": data.get("schema"), "deepest_stage": data.get("deepest_stage"), "deepest_stage_name": data.get("deepest_stage_name"), "marker_codes": [m.get("code") for m in data.get("markers", [])], "failure_codes": [f.get("code") for f in data.get("failures", [])], "next_priority": data.get("next", {}).get("priority") if isinstance(data.get("next"), dict) else None}
    if kind == "guard":
        return {"schema": data.get("schema"), "status": data.get("status"), "experiment": data.get("experiment"), "changes": data.get("changes")}
    if kind == "issues":
        return {"schema": data.get("schema"), "best_match": data.get("best_match"), "explicit_nonmatches": data.get("explicit_nonmatches")}
    if kind == "ledger":
        attempts = data.get("attempts", [])
        return {"schema": data.get("schema"), "attempt_count": len(attempts), "best_stage": data.get("best_stage"), "best_attempt": data.get("best_attempt")}
    if kind == "run_record":
        build = data.get("build") if isinstance(data.get("build"), dict) else {}
        return {"schema": data.get("schema"), "ready_for_comparison": data.get("ready_for_comparison"), "build_fingerprint_sha256": build.get("fingerprint_sha256"), "profile_sha256": data.get("profile_sha256")}
    if kind == "run_context":
        return {"schema": data.get("schema"), "ready": data.get("ready"), "run_id_sha256": data.get("run_id_sha256"), "build_fingerprint_sha256": data.get("build_fingerprint_sha256"), "profile_sha256": data.get("profile_sha256"), "session_summary": data.get("session_summary")}
    if kind == "pe_imports":
        return {"schema": data.get("schema"), "valid": data.get("valid"), "file_sha256": data.get("file_sha256"), "import_count": data.get("import_count"), "categories": sorted((data.get("categories") or {}).keys()) if isinstance(data.get("categories"), dict) else []}
    if kind == "contract":
        return {"schema": data.get("schema"), "valid": data.get("valid"), "run_id_sha256": data.get("run_id_sha256"), "errors": data.get("errors"), "warnings": data.get("warnings")}
    if kind == "device_template":
        return {"schema": data.get("schema"), "run_id_sha256": data.get("run_id_sha256"), "build_fingerprint_sha256": data.get("build_fingerprint_sha256"), "profile_sha256": data.get("profile_sha256")}
    if kind == "repeatability":
        return {"schema": data.get("schema"), "passed": data.get("passed"), "run_count": data.get("run_count"), "unique_run_count": data.get("unique_run_count"), "build_fingerprint_sha256": data.get("build_fingerprint_sha256"), "profile_sha256": data.get("profile_sha256")}
    if kind == "save_verification":
        return {"schema": data.get("schema"), "progress_write_detected": data.get("progress_write_detected"), "save_tree_survived_relaunch": data.get("save_tree_survived_relaunch"), "machine_gate_pass": data.get("machine_gate_pass"), "after_tree_sha256": data.get("after_tree_sha256"), "relaunch_tree_sha256": data.get("relaunch_tree_sha256")}
    if kind.startswith("save"):
        return {"schema": data.get("schema"), "tree_sha256": data.get("tree_sha256"), "file_count": data.get("file_count"), "progress_write_detected": data.get("progress_write_detected")}
    if kind == "acceptance":
        return {"schema": data.get("schema"), "overall": data.get("overall"), "accepted": data.get("accepted"), "counts": data.get("counts"), "next_unproven_gate": data.get("next_unproven_gate"), "run_id_sha256": data.get("run_id_sha256")}
    return {"schema": data.get("schema")}


def build(inputs: dict[str, pathlib.Path | None]) -> dict[str, Any]:
    structured_kinds = {"preflight", "session", "guard", "issues", "ledger", "run_record", "run_context", "pe_imports", "contract", "device_template", "repeatability", "save_before", "save_after", "save_relaunch", "save_verification", "acceptance"}
    files: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for kind, path in inputs.items():
        if path is None:
            continue
        files.append(descriptor(path, kind))  # type: ignore[arg-type]
        if kind in structured_kinds:
            summaries[kind] = summary(kind, load_json(path))

    present = {f["kind"] for f in files}
    pre = summaries.get("preflight") or {}
    context = summaries.get("run_context") or {}
    contract = summaries.get("contract") or {}
    imports = summaries.get("pe_imports") or {}
    device = summaries.get("device_template") or {}
    repeat = summaries.get("repeatability") or {}
    minimum_review = {"preflight", "session", "madeira_log"}.issubset(present)
    sealed_launch = bool(context.get("ready") and context.get("run_id_sha256") and contract.get("valid") and contract.get("run_id_sha256") == context.get("run_id_sha256"))
    dependency_audit = bool(imports.get("valid") and imports.get("file_sha256") and imports.get("file_sha256") == pre.get("exe_sha256"))
    device_template_linked = bool(device.get("run_id_sha256") and device.get("run_id_sha256") == context.get("run_id_sha256") and device.get("build_fingerprint_sha256") == context.get("build_fingerprint_sha256") and device.get("profile_sha256") == context.get("profile_sha256"))
    repeatability_complete = bool(repeat.get("passed") and int(repeat.get("unique_run_count") or 0) >= 3 and repeat.get("build_fingerprint_sha256") == context.get("build_fingerprint_sha256") and repeat.get("profile_sha256") == context.get("profile_sha256"))
    acceptance_complete = bool((summaries.get("acceptance") or {}).get("accepted"))
    save_machine_complete = bool((summaries.get("save_verification") or {}).get("machine_gate_pass"))
    integrity_warnings: list[str] = []

    guard = summaries.get("guard") or {}
    if guard.get("status") == "FAIL": integrity_warnings.append("The config guard rejected this run profile; do not promote it as valid evidence.")
    if pre and not pre.get("exe_sha256"): integrity_warnings.append("Preflight is present but lacks an executable SHA-256 identity.")
    session = summaries.get("session") or {}
    if session and not session.get("deepest_stage") and "madeira_log" in present: integrity_warnings.append("A Madeira log is present but the structured session report proves no game stage; inspect whether the correct log was analyzed.")
    if "run_context" in present and not sealed_launch: integrity_warnings.append("Run context is present but the launch is not sealed to a matching valid evidence contract.")
    if "pe_imports" in present and not dependency_audit: integrity_warnings.append("PE dependency audit is present but does not validate against the owned executable identity.")
    if "device_template" in present and not device_template_linked: integrity_warnings.append("Device test template is not linked to the sealed primary launch identity.")
    if "repeatability" in present and not repeatability_complete: integrity_warnings.append("Cold-launch repeatability report is present but does not prove three unique matching-build/profile launches.")
    save_verify = summaries.get("save_verification") or {}
    if save_verify and save_verify.get("progress_write_detected") and not save_verify.get("save_tree_survived_relaunch"): integrity_warnings.append("The game wrote save progress, but the exact post-progress save tree did not survive relaunch.")

    return {
        "schema": SCHEMA,
        "title": "HunieCam Studio",
        "steam_app_id": 426000,
        "files": sorted(files, key=lambda x: x["kind"]),
        "summaries": summaries,
        "minimum_review_bundle_complete": minimum_review,
        "sealed_launch_identity_complete": sealed_launch,
        "pe_dependency_audit_complete": dependency_audit,
        "device_template_linked_to_primary_run": device_template_linked,
        "cold_launch_repeatability_complete": repeatability_complete,
        "save_machine_verification_complete": save_machine_complete,
        "device_acceptance_complete": acceptance_complete,
        "integrity_warnings": integrity_warnings,
        "privacy": {"raw_logs_embedded": False, "save_contents_embedded": False, "absolute_paths_embedded": False, "credentials_embedded": False, "proprietary_binaries_embedded": False},
        "rule": "Share the manifest plus only raw evidence specifically needed for the current blocker. Never add Steam credentials, JIT pairing secrets, saves, or proprietary game binaries.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Build a HunieCam/Madeira evidence manifest")
    for name in ("preflight", "session", "guard", "issues", "ledger", "run-record", "run-context", "pe-imports", "contract", "device-template", "repeatability", "save-before", "save-after", "save-relaunch", "save-verification", "acceptance", "madeira-log", "unity-log"):
        p.add_argument(f"--{name}", dest=name.replace("-", "_"), type=pathlib.Path)
    p.add_argument("--json", dest="json_path", type=pathlib.Path, required=True)
    args = p.parse_args()
    inputs = {"preflight": args.preflight, "session": args.session, "guard": args.guard, "issues": args.issues, "ledger": args.ledger, "run_record": args.run_record, "run_context": args.run_context, "pe_imports": args.pe_imports, "contract": args.contract, "device_template": args.device_template, "repeatability": args.repeatability, "save_before": args.save_before, "save_after": args.save_after, "save_relaunch": args.save_relaunch, "save_verification": args.save_verification, "acceptance": args.acceptance, "madeira_log": args.madeira_log, "unity_log": args.unity_log}
    report = build(inputs)
    args.json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
